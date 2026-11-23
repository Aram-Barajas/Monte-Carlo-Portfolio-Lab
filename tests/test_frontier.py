import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from fastapi.testclient import TestClient

from backend.api import app
from backend.frontier import calculate_efficient_frontier


class FrontierTests(unittest.TestCase):

    def setUp(self):

        self.returns = pd.DataFrame({
            "A": [.011, -.009, .011, -.009],
            "B": [.022, .022, -.018, -.018]
        })

        self.weights = {
            "A": .5,
            "B": .5
        }

    def test_known_frontier(self):

        result = calculate_efficient_frontier(
            self.returns,
            self.weights,
            points=5
        )

        frontier = result["frontier"]

        self.assertEqual(len(frontier), 5)

        np.testing.assert_allclose(
            [p["weights"]["B"] for p in frontier],

            [.2, .4, .6, .8, 1],

            atol=1e-6
        )

        for point in frontier:

            daily = self.returns @ pd.Series(
                point["weights"]
            )

            self.assertAlmostEqual(
                point["annualized_return"],
                daily.mean() * 252
            )

            self.assertAlmostEqual(
                point["annualized_volatility"],
                daily.std() * np.sqrt(252)
            )

        self.assertTrue(
            all(
                a["annualized_volatility"]
                < b["annualized_volatility"]

                for a, b in zip(
                    frontier,
                    frontier[1:]
                )
            )
        )

    def test_concentration_limit(self):

        frontier = calculate_efficient_frontier(
            self.returns,
            self.weights,
            max_weight=.6
        )["frontier"]

        for point in frontier:

            self.assertAlmostEqual(
                sum(point["weights"].values()),
                1
            )

            self.assertLessEqual(
                max(point["weights"].values()),
                .60000001
            )

        self.assertAlmostEqual(
            frontier[-1]["weights"]["B"],
            .6
        )

    def test_fixed_or_single_asset(self):

        fixed = calculate_efficient_frontier(
            self.returns,
            self.weights,
            max_weight=.5
        )

        single = calculate_efficient_frontier(
            self.returns[["A"]],
            {"A": 1}
        )

        self.assertEqual(
            len(fixed["frontier"]),
            1
        )

        self.assertEqual(
            len(single["frontier"]),
            1
        )

    def test_constant_returns_remove_dominated_allocations(self):

        returns = pd.DataFrame({
            "A": [.01] * 4,
            "B": [.02] * 4
        })

        result = calculate_efficient_frontier(
            returns,
            self.weights
        )

        self.assertEqual(
            len(result["frontier"]),
            1
        )

        self.assertAlmostEqual(
            result["frontier"][0]["weights"]["B"],
            1
        )

        self.assertIsNone(
            result["maximum_sharpe"]
        )

    def test_negative_returns(self):

        result = calculate_efficient_frontier(
            self.returns - .01,
            self.weights
        )

        self.assertTrue(
            all(
                p["annualized_return"] < 0
                for p in result["frontier"]
            )
        )

        self.assertIsNone(
            result["maximum_sharpe"]
        )

    def test_invalid_point_count(self):

        for count in (1, 51, True, 2.5):

            with self.subTest(count=count):

                with self.assertRaises(ValueError):

                    calculate_efficient_frontier(
                        self.returns,
                        self.weights,
                        points=count
                    )

    def test_api(self):

        client = TestClient(app)

        request = {
            "tickers": ["A", "B"],

            "weights": self.weights,

            "start": "2025-01-01",

            "end": "2026-01-01",

            "points": 5
        }

        with patch(
            "backend.api.fetch_daily_returns",
            return_value=self.returns
        ) as fetch:

            response = client.post(
                "/api/frontier",
                json=request
            )

            self.assertEqual(
                response.status_code,
                200
            )

            self.assertEqual(
                len(response.json()["frontier"]),
                5
            )

            fetch.assert_called_once()

        with patch(
            "backend.api.fetch_daily_returns"
        ) as fetch:

            response = client.post(
                "/api/frontier",

                json={
                    **request,
                    "points": 100
                }
            )

            self.assertEqual(
                response.status_code,
                422
            )

            fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()