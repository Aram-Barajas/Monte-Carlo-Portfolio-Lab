import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from backend.api import app
from backend.robust_optimization import optimize_robust_portfolio


class RobustOptimizationTests(unittest.TestCase):
    def setUp(self):
        self.returns = pd.DataFrame({
            "A": np.tile([.01, -.01, .01, -.01], 28),
            "B": np.tile([.02, .02, -.02, -.02], 28),
        }, index=pd.bdate_range("2024-01-01", periods=112))
        self.weights = {"A": .5, "B": .5}

    def optimize(self, **kwargs):
        return optimize_robust_portfolio(self.returns, self.weights, **kwargs)

    def test_known_minimum_variance_weights(self):
        result = self.optimize(mean_shrinkage=0, covariance_shrinkage=0)
        for key in ("traditional", "robust"):
            allocation = result[key]["weights"]
            self.assertAlmostEqual(allocation["A"], .8, places=6)
            self.assertAlmostEqual(allocation["B"], .2, places=6)
            self.assertAlmostEqual(result[key]["turnover"], .3, places=6)

    def test_caps_and_turnover(self):
        for options, expected in [
            ({"max_weight": .65}, .65),
            ({"max_turnover": .1}, .6),
            ({"max_turnover": 0}, .5),
            ({"max_weight": .5}, .5),
        ]:
            with self.subTest(options=options):
                data = self.optimize(**options)
                for key in ("traditional", "robust"):
                    self.assertAlmostEqual(data[key]["weights"]["A"], expected, places=6)
                    self.assertAlmostEqual(sum(data[key]["weights"].values()), 1)

    def test_infeasible_turnover_and_valid_boundary(self):
        current = {"A": .9, "B": .1}
        with self.assertRaisesRegex(ValueError, "Turnover limit"):
            optimize_robust_portfolio(self.returns, current, max_weight=.6, max_turnover=.2)
        result = optimize_robust_portfolio(self.returns, current, max_weight=.6, max_turnover=.3)
        self.assertFalse(result["current_respects_max_weight"])
        self.assertEqual(result["current"]["weights"], current)
        self.assertAlmostEqual(result["robust"]["weights"]["A"], .6)
        self.assertAlmostEqual(result["robust"]["turnover"], .3)

    def test_mean_shrinkage_reduces_dependence_on_sample_mean(self):
        returns = self.returns.copy()
        returns["B"] += .002
        result = optimize_robust_portfolio(returns, self.weights, mean_shrinkage=1, covariance_shrinkage=1)
        self.assertGreater(result["traditional"]["weights"]["B"], result["robust"]["weights"]["B"])
        self.assertAlmostEqual(result["robust"]["weights"]["A"], .8, places=5)

    def test_covariance_shrinkage(self):
        returns = self.returns.assign(B=self.returns.A * 2)
        result = optimize_robust_portfolio(returns, self.weights, mean_shrinkage=0, covariance_shrinkage=1)
        self.assertAlmostEqual(result["traditional"]["weights"]["A"], 1)
        self.assertAlmostEqual(result["robust"]["weights"]["A"], .8, places=5)

    def test_holdout_has_no_effect_on_fitted_weights(self):
        original = self.optimize()
        changed = self.returns.copy()
        changed.iloc[84:, 0] = .03
        changed.iloc[84:, 1] = -.02
        result = optimize_robust_portfolio(changed.iloc[::-1], self.weights)
        self.assertEqual(result["training_period"]["observations"], 84)
        self.assertEqual(result["holdout_period"]["observations"], 28)
        for key in ("traditional", "robust"):
            self.assertEqual(original[key]["weights"], result[key]["weights"])
            self.assertEqual(original[key]["training"], result[key]["training"])
            self.assertNotEqual(original[key]["holdout"], result[key]["holdout"])
            w = result[key]["weights"]
            expected = (1 + .03 * w["A"] - .02 * w["B"]) ** 28 - 1
            self.assertAlmostEqual(result[key]["holdout"]["total_return"], expected)

    def test_constant_and_single_asset(self):
        result = optimize_robust_portfolio(self.returns[["A"]].assign(A=0), {"A": 1})
        self.assertEqual(result["robust"]["weights"], {"A": 1})
        self.assertIsNone(result["robust"]["holdout"]["sharpe_ratio"])

    def test_multi_asset_regularized_objective_and_constraints(self):
        rng = np.random.default_rng(28)
        returns = pd.DataFrame(rng.normal([.001, -.001, .0005, .0001, .002], .02, (160, 5)),
                               index=pd.bdate_range("2024-01-01", periods=160), columns=list("ABCDE"))
        current = dict.fromkeys(returns.columns, .2)
        result = optimize_robust_portfolio(returns, current, max_weight=.4, max_turnover=.15)
        train = returns.iloc[:120]
        mean = train.mean().to_numpy() * 252
        mean = .5 * mean + .5 * mean.mean()
        covariance = train.cov().to_numpy() * 252
        covariance = .75 * covariance + .25 * np.diag(np.diag(covariance))
        initial = np.full(5, .2)
        weights = np.array(list(result["robust"]["weights"].values()))
        utility = lambda w: mean @ w - 2.5 * (w @ covariance @ w)
        self.assertGreaterEqual(utility(weights) + 1e-9, utility(initial))
        self.assertAlmostEqual(weights.sum(), 1)
        self.assertLessEqual(weights.max(), .4 + 1e-8)
        self.assertLessEqual(result["robust"]["turnover"], .15 + 1e-8)

    def test_invalid_inputs_and_insufficient_history(self):
        for options in ({"mean_shrinkage": 1.1}, {"covariance_shrinkage": -1},
                        {"risk_aversion": 0}, {"holdout_fraction": .6}, {"max_turnover": True},
                        {"max_weight": .49}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.optimize(**options)
        with self.assertRaisesRegex(ValueError, "at least 63 training"):
            optimize_robust_portfolio(self.returns.iloc[:80], self.weights)

    def test_endpoint_and_validation(self):
        request = {"tickers": ["A", "B"], "weights": self.weights, "start": "2024-01-01",
                   "end": "2025-01-01", "max_turnover": .1}
        with patch("backend.api.fetch_daily_returns", return_value=self.returns) as fetch:
            client = TestClient(app)
            response = client.post("/api/robust-optimize", json=request)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertAlmostEqual(response.json()["robust"]["turnover"], .1)
            fetch.assert_called_once_with(["A", "B"], "2024-01-01", "2025-01-01")
            request["max_turnover"] = 1.1
            self.assertEqual(client.post("/api/robust-optimize", json=request).status_code, 422)
            request.update(weights={"A": .9, "B": .1}, max_weight=.6, max_turnover=.1)
            self.assertEqual(client.post("/api/robust-optimize", json=request).status_code, 422)
            fetch.assert_called_once()
