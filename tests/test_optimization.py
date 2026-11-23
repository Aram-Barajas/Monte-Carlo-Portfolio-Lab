import unittest

from unittest.mock import patch

import numpy as np
import pandas as pd

from fastapi.testclient import TestClient

from backend.api import app
from backend.optimization import optimize_portfolio


class OptimizationTests(unittest.TestCase):

    def setUp(self):

        # Asset B has twice the volatility of asset A.
        # Their deviations are uncorrelated.

        self.returns = pd.DataFrame({
            "A": [.011, -.009, .011, -.009],
            "B": [.022, .022, -.018, -.018]
        })

        self.weights = {
            "A": .5,
            "B": .5
        }

        self.request = {
            "tickers": ["A", "B"],

            "weights": self.weights,

            "start": "2025-01-01",

            "end": "2026-01-01"
        }

    def test_known_minimum_variance(self):

        result = optimize_portfolio(
            self.returns,
            self.weights
        )

        self.assertAlmostEqual(
            result["minimum_volatility"]["weights"]["A"],
            .8,
            places=6
        )

        self.assertLess(
            result["minimum_volatility"]["annualized_volatility"],
            result["current"]["annualized_volatility"]
        )

    def test_known_maximum_sharpe(self):

        result = optimize_portfolio(
            self.returns,
            self.weights
        )

        self.assertAlmostEqual(
            result["maximum_sharpe"]["weights"]["A"],
            2 / 3,
            places=6
        )

        self.assertGreaterEqual(
            result["maximum_sharpe"]["sharpe_ratio"],
            result["current"]["sharpe_ratio"]
        )

    def test_limits_and_current_allocation(self):

        result = optimize_portfolio(
            self.returns,

            {"A": 1, "B": 0},

            max_weight=.6
        )

        self.assertFalse(
            result["current_respects_max_weight"]
        )

        self.assertEqual(
            result["current"]["weights"],
            {"A": 1, "B": 0}
        )

        for name in (
            "minimum_volatility",
            "maximum_sharpe"
        ):

            weights = result[name]["weights"]

            self.assertAlmostEqual(
                sum(weights.values()),
                1
            )

            self.assertAlmostEqual(
                weights["A"],
                .6,
                places=6
            )

            self.assertGreaterEqual(
                min(weights.values()),
                0
            )

    def test_equal_weight_constraint_and_single_asset(self):

        result = optimize_portfolio(
            self.returns,
            self.weights,

            max_weight=.5
        )

        self.assertEqual(
            result["maximum_sharpe"]["weights"],
            self.weights
        )

        self.assertEqual(
            result["minimum_volatility"]["weights"],
            self.weights
        )

        single = optimize_portfolio(
            self.returns[["A"]],
            {"A": 1}
        )

        self.assertEqual(
            single["maximum_sharpe"]["weights"],
            {"A": 1}
        )

    def test_no_positive_excess(self):

        result = optimize_portfolio(
            self.returns,
            self.weights,

            annual_risk_free_rate=1
        )

        self.assertIsNone(
            result["maximum_sharpe"]
        )

        self.assertIn(
            "positive",
            result["maximum_sharpe_unavailable_reason"]
        )

    def test_zero_volatility(self):

        constant = pd.DataFrame({
            "A": [.01] * 4,
            "B": [.02] * 4
        })

        result = optimize_portfolio(
            constant,
            self.weights
        )

        self.assertIsNone(
            result["maximum_sharpe"]
        )

        self.assertIsNone(
            result["minimum_volatility"]["sharpe_ratio"]
        )

        self.assertIn(
            "volatility",
            result["maximum_sharpe_unavailable_reason"]
        )

    def test_cap_prevents_positive_excess(self):

        returns = self.returns.copy()

        returns["B"] -= .01

        result = optimize_portfolio(
            returns,
            self.weights,

            max_weight=.6
        )

        self.assertIsNone(
            result["maximum_sharpe"]
        )

        self.assertIn(
            "positive",
            result["maximum_sharpe_unavailable_reason"]
        )

    def test_risk_free_rate_changes_sharpe_allocation(self):

        result = optimize_portfolio(
            self.returns,
            self.weights,

            annual_risk_free_rate=.252
        )

        self.assertAlmostEqual(
            result["maximum_sharpe"]["weights"]["B"],
            1,
            places=6
        )

    def test_perfect_negative_correlation(self):

        returns = pd.DataFrame({
            "A": [.02, -.01, .02, -.01],
            "B": [-.01, .02, -.01, .02]
        })

        result = optimize_portfolio(
            returns,
            self.weights
        )

        self.assertAlmostEqual(
            result["minimum_volatility"]["annualized_volatility"],
            0
        )

        self.assertIsNone(
            result["maximum_sharpe"]
        )

    def test_invalid_inputs(self):

        for cap in (
            .4, 1.1, True, np.nan
        ):

            with self.subTest(cap=cap):

                with self.assertRaises(ValueError):

                    optimize_portfolio(
                        self.returns,
                        self.weights,

                        max_weight=cap
                    )

        with self.assertRaises(ValueError):

            optimize_portfolio(
                self.returns,
                self.weights,

                annual_risk_free_rate=np.inf
            )

        with self.assertRaises(ValueError):

            optimize_portfolio(
                self.returns,
                {"A": .5, "B": .4}
            )

    def test_api(self):

        client = TestClient(app)

        with patch(
            "backend.api.fetch_daily_returns",

            return_value=self.returns
        ) as fetch:

            response = client.post(
                "/api/optimize",

                json={
                    **self.request,
                    "max_weight": .6
                }
            )

            self.assertEqual(
                response.status_code,
                200
            )

            self.assertAlmostEqual(
                response.json()["minimum_volatility"]["weights"]["A"],
                .6
            )

            fetch.assert_called_once_with(
                ["A", "B"],
                "2025-01-01",
                "2026-01-01"
            )

    def test_api_invalid_cap_and_source_error(self):

        client = TestClient(app)

        with patch(
            "backend.api.fetch_daily_returns"
        ) as fetch:

            response = client.post(
                "/api/optimize",

                json={
                    **self.request,
                    "max_weight": .4
                }
            )

            self.assertEqual(
                response.status_code,
                422
            )

            fetch.assert_not_called()

        with patch(
            "backend.api.fetch_daily_returns",

            side_effect=RuntimeError
        ):

            response = client.post(
                "/api/optimize",

                json=self.request
            )

            self.assertEqual(
                response.status_code,
                502
            )


if __name__ == "__main__":
    unittest.main()