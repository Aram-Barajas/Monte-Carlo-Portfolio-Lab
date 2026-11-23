import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from backend.api import app
from backend.model_validation import score_forecast, validate_models
from backend.monte_carlo import SIMULATION_MODELS


class ModelValidationTests(unittest.TestCase):
    def setUp(self):
        self.returns = pd.DataFrame({
            "A": np.tile([.01, -.006, .007, -.004], 40),
            "B": np.tile([-.004, .005, .009, -.002], 40),
        }, index=pd.bdate_range("2024-01-01", periods=160))
        self.weights = {"A": .6, "B": .4}
        self.settings = dict(training_days=63, forecast_days=10, max_folds=4,
                             num_simulations=100, block_length=5, seed=42)

    def run_validation(self, **changes):
        return validate_models(self.returns, self.weights, **{**self.settings, **changes})

    def test_score_against_pairwise_reference(self):
        samples = np.array([-.2, -.1, .1, .3])
        actual = -.05
        score = score_forecast(samples, actual)
        reference = np.abs(samples - actual).mean() - .5 * np.abs(samples[:, None] - samples[None, :]).mean()
        self.assertAlmostEqual(score["crps"], reference)
        self.assertEqual(score["pit"], .5)
        self.assertEqual(score["probability_loss"], .5)
        self.assertEqual(score["brier_loss"], .25)
        self.assertTrue(score["inside_50"])
        self.assertTrue(score["inside_90"])

    def test_degenerate_ties_and_tails(self):
        zero = score_forecast(np.zeros(100), 0)
        self.assertEqual(zero["pit"], .5)
        self.assertEqual(zero["crps"], 0)
        self.assertEqual(zero["brier_loss"], 0)
        self.assertTrue(zero["inside_90"])
        below = score_forecast(np.zeros(100), -.1)
        self.assertTrue(below["below_05"])
        self.assertEqual(below["pit"], 0)
        self.assertAlmostEqual(below["crps"], .1)
        self.assertEqual(below["brier_loss"], 1)
        above = score_forecast(np.zeros(100), .1)
        self.assertTrue(above["above_95"])
        self.assertEqual(above["pit"], 1)
        with self.assertRaises(ValueError):
            score_forecast([np.nan], 0)

    def test_fold_dates_and_realized_compounding(self):
        result = self.run_validation()
        self.assertEqual(result["fold_count"], 4)
        self.assertEqual(result["seed"], 42)
        for i, fold in enumerate(result["folds"]):
            start = 120 + i * 10
            self.assertEqual(fold["training_start"], self.returns.index[start - 63].strftime("%Y-%m-%d"))
            self.assertEqual(fold["training_end"], self.returns.index[start - 1].strftime("%Y-%m-%d"))
            self.assertEqual(fold["forecast_start"], self.returns.index[start].strftime("%Y-%m-%d"))
            self.assertEqual(fold["forecast_end"], self.returns.index[start + 9].strftime("%Y-%m-%d"))
            actual = (1 + self.returns.iloc[start:start + 10] @ pd.Series(self.weights)).prod() - 1
            self.assertAlmostEqual(fold["actual_return"], actual)
        for model in SIMULATION_MODELS:
            summary = result["models"][model]
            scores = [row["models"][model] for row in result["folds"]]
            self.assertEqual(sum(summary["pit_histogram"]), 4)
            self.assertEqual(summary["coverage_90"], np.mean([score["inside_90"] for score in scores]))
            self.assertAlmostEqual(summary["mean_crps"], np.mean([score["crps"] for score in scores]))

    def test_no_future_leakage_and_seed_reproducibility(self):
        original = self.run_validation()
        changed = self.returns.copy()
        changed.iloc[150:] = -.1
        result = validate_models(changed.iloc[::-1], self.weights, **self.settings)
        self.assertEqual(result["folds"][:-1], original["folds"][:-1])
        self.assertNotEqual(result["folds"][-1]["actual_return"], original["folds"][-1]["actual_return"])
        for model in SIMULATION_MODELS:
            for quantile in ("p05", "p25", "median", "p75", "p95", "probability_loss"):
                self.assertEqual(result["folds"][-1]["models"][model][quantile],
                                 original["folds"][-1]["models"][model][quantile])
        self.assertEqual(original, self.run_validation())

    def test_constant_returns_and_coverage(self):
        flat = self.returns.assign(A=0., B=0.)
        result = validate_models(flat, self.weights, **self.settings)
        for summary in result["models"].values():
            self.assertEqual(summary["coverage_50"], 1)
            self.assertEqual(summary["coverage_90"], 1)
            self.assertEqual(summary["mean_crps"], 0)
            self.assertEqual(summary["pit_histogram"][5], 4)

    def test_insufficient_history_and_limits(self):
        with self.assertRaisesRegex(ValueError, "three complete"):
            validate_models(self.returns.iloc[:90], self.weights, **self.settings)
        shortened = validate_models(self.returns.iloc[:100], self.weights, **self.settings)
        self.assertEqual(shortened["fold_count"], 3)
        for changes in ({"num_simulations": 99}, {"seed": -1}, {"block_length": 64},
                        {"drift_weight": 1.1}, {"forecast_days": 4},
                        {"max_folds": 24, "forecast_days": 252, "num_simulations": 1000}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.run_validation(**changes)

    def test_api_and_early_validation(self):
        request = {"tickers": ["A", "B"], "weights": self.weights, "start": "2024-01-01",
                   "end": "2025-01-01", **self.settings}
        with patch("backend.api.fetch_daily_returns", return_value=self.returns) as fetch:
            client = TestClient(app)
            response = client.post("/api/validate-models", json=request)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["fold_count"], 4)
            self.assertEqual(response.json()["start"], "2024-01-01")
            request["block_length"] = 64
            self.assertEqual(client.post("/api/validate-models", json=request).status_code, 422)
            fetch.assert_called_once()
