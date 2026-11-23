import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from backend.api import app
from backend.monte_carlo import simulate_portfolio
from backend.planning import evaluate_goal_paths, plan_portfolio


class PlanningTests(unittest.TestCase):
    def setUp(self):
        self.returns = pd.DataFrame({"A": np.tile([.005, -.004, .007, -.003], 30)},
                                    index=pd.bdate_range("2024-01-01", periods=120))
        self.weights = {"A": 1.}
        self.settings = dict(initial_value=1000, monthly_contribution=100, contribution_growth=0,
                             annual_inflation=0, goal=2200, target_probability=.8)

    def test_flat_market_and_goal_threshold(self):
        result = evaluate_goal_paths(np.ones((4, 12)), **self.settings)
        self.assertEqual(result["goal_probability"], 1)
        self.assertEqual(result["annual"][-1]["median"], 2200)
        self.assertEqual(result["required_monthly_contribution"], 100)
        self.assertEqual(result["required_contribution_probability"], 1)
        self.assertIsNone(result["median_shortfall_when_missed"])

    def test_inflation_and_escalation(self):
        result = evaluate_goal_paths(np.ones((4, 24)), **{
            **self.settings, "contribution_growth": .1, "annual_inflation": .05, "goal": 3000})
        contributed = 1000 + 1200 + 1320
        last = result["annual"][-1]
        self.assertAlmostEqual(last["nominal_contributed"], contributed)
        self.assertAlmostEqual(last["median"], contributed / 1.05 ** 2)
        self.assertAlmostEqual(result["nominal_goal"], 3000 * 1.05 ** 2)
        self.assertAlmostEqual(result["required_monthly_contribution"], 91.57)

    def test_growth_before_contribution(self):
        paths = np.full((3, 12), 1.01)
        result = evaluate_goal_paths(paths, **self.settings)
        expected = 1000 * 1.01 ** 12 + 100 * sum(1.01 ** n for n in range(12))
        self.assertAlmostEqual(result["annual"][-1]["median"], expected)

    def test_empirical_order_statistic_and_monotonic_sensitivity(self):
        growth = np.ones((5, 12))
        growth[:, 0] = [.5, .75, 1., 1.25, 1.5]
        result = evaluate_goal_paths(growth, **{**self.settings, "goal": 2000, "monthly_contribution": 80})
        # Contributions arrive after first-month returns: thresholds 125, 104.166..., 83.333..., 62.5, 41.666...
        self.assertEqual(result["required_monthly_contribution"], 104.17)
        self.assertEqual(result["required_contribution_probability"], .8)
        self.assertEqual(result["goal_probability"], .4)
        self.assertAlmostEqual(result["median_shortfall_when_missed"], 290)
        probabilities = [row["goal_probability"] for row in result["sensitivity"]]
        self.assertEqual(probabilities, sorted(probabilities))

    def test_zero_contribution_and_already_funded(self):
        result = evaluate_goal_paths(np.ones((5, 12)), **{**self.settings, "goal": 1000, "monthly_contribution": 0})
        self.assertEqual(result["required_monthly_contribution"], 0)
        self.assertEqual(result["goal_probability"], 1)
        result = evaluate_goal_paths(np.ones((5, 12)), **{**self.settings, "initial_value": 0, "monthly_contribution": 0})
        self.assertEqual(result["goal_probability"], 0)
        self.assertEqual(result["required_monthly_contribution"], 183.34)

    def test_invalid_growth_and_parameters(self):
        for bad in (np.ones((3, 11)), np.zeros((3, 12)), np.full((3, 12), np.nan)):
            with self.subTest(bad=bad.shape), self.assertRaises(ValueError):
                evaluate_goal_paths(bad, **self.settings)
        for changes in ({"goal": 0}, {"annual_inflation": -.2}, {"target_probability": 1}, {"contribution_growth": .3}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                evaluate_goal_paths(np.ones((3, 12)), **{**self.settings, **changes})

    def test_monthly_recording_matches_daily_paths(self):
        for model in ("gaussian", "gaussian_uncertain", "block_bootstrap"):
            with self.subTest(model=model):
                kwargs = dict(trading_days=49, num_simulations=6, initial_value=100,
                              monthly_contribution=5, seed=42, model=model, block_length=5)
                daily = simulate_portfolio(self.returns, self.weights, **kwargs)
                sparse = simulate_portfolio(self.returns, self.weights, **kwargs, record_every=21)
                np.testing.assert_array_equal(sparse, daily[:, [0, 21, 42, 49]])

    def test_plan_matches_daily_engine_and_seed(self):
        expected = simulate_portfolio(self.returns, self.weights, initial_value=1000,
                                      monthly_contribution=100, trading_days=252, num_simulations=20,
                                      seed=42, model="gaussian", drift_weight=.5)
        kwargs = dict(years=1, num_simulations=20, model="gaussian", drift_weight=.5, seed=42, **self.settings)
        result = plan_portfolio(self.returns, self.weights, **kwargs)
        self.assertAlmostEqual(result["annual"][-1]["median"], np.median(expected[:, -1]))
        self.assertEqual(result["goal_probability"], np.mean(expected[:, -1] >= 2200))
        self.assertEqual(result, plan_portfolio(self.returns, self.weights, **kwargs))

    def test_long_horizon_and_request_limit(self):
        flat = self.returns.assign(A=0.)
        result = plan_portfolio(flat, self.weights, years=40, num_simulations=2, seed=42,
                                **self.settings)
        self.assertEqual(len(result["annual"]), 41)
        self.assertEqual(result["annual"][-1]["median"], 49000)
        with self.assertRaisesRegex(ValueError, "too large"):
            plan_portfolio(flat, self.weights, years=40, num_simulations=2000)

    def test_api_seed_and_validation(self):
        request = {"tickers": ["A"], "weights": self.weights, "years": 1,
                   "num_simulations": 5, "start": "2024-01-01", "end": "2025-01-01", "seed": 0}
        with patch("backend.api.fetch_daily_returns", return_value=self.returns) as fetch:
            client = TestClient(app)
            response = client.post("/api/plan", json=request)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["seed"], 0)
            self.assertEqual(len(response.json()["annual"]), 2)
            request.update(years=40, num_simulations=2000)
            self.assertEqual(client.post("/api/plan", json=request).status_code, 422)
            fetch.assert_called_once()
            request.update(years=1, num_simulations=5, seed=None)
            generated = client.post("/api/plan", json=request).json()
            self.assertIsInstance(generated["seed"], int)
