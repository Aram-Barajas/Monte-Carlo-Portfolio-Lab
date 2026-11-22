import unittest
from unittest.mock import patch

import pandas as pd

from fastapi.testclient import TestClient

from backend.api import app, PortfolioRequest
from backend.market_data import normalize_tickers

from backend.portfolio_metrics import (
    normalize_rounded_weights,
    validate_weights
)


class AllocationNormalizationTests(unittest.TestCase):

    def test_aliases_and_exchange_suffixes(self):

        self.assertEqual(
            normalize_tickers([
                " brk.b ",
                "BRK.A",
                "bf.b",
                "SHOP.TO",
                "VOD.L"
            ]),
            [
                "BRK-B",
                "BRK-A",
                "BF-B",
                "SHOP.TO",
                "VOD.L"
            ]
        )

    def test_duplicate_aliases_rejected(self):

        with self.assertRaises(ValueError):
            normalize_tickers(["BRK.B", "BRK-B"])

    def test_rounded_totals_normalized(self):

        for total in (0.9995, 0.9999, 1.0, 1.0001, 1.0005):

            with self.subTest(total=total):

                weights = {
                    "A": total * .6,
                    "B": total * .4
                }

                result = normalize_rounded_weights(
                    weights,
                    ["A", "B"]
                )

                self.assertAlmostEqual(result.sum(), 1.0)
                self.assertAlmostEqual(result["A"], .6)
                self.assertAlmostEqual(result["B"], .4)

    def test_invalid_totals_rejected(self):

        for total in (0, .95, .9994, 1.0006, 1.05):

            with self.subTest(total=total):

                with self.assertRaises(ValueError):

                    normalize_rounded_weights(
                        {"A": total},
                        ["A"]
                    )

    def test_negative_and_nonfinite_rejected(self):

        invalid_weights = [
            {"A": -0.1, "B": 1.1},
            {"A": float("nan"), "B": 1},
            {"A": True, "B": 0}
        ]

        for weights in invalid_weights:

            with self.subTest(weights=weights):

                with self.assertRaises(ValueError):

                    normalize_rounded_weights(
                        weights,
                        ["A", "B"]
                    )

    def test_engine_remains_strict(self):

        with self.assertRaises(ValueError):

            validate_weights(
                {"A": .9999},
                ["A"]
            )

    def test_brokerage_example(self):

        allocation = {
            "VTI": 25.68,
            "JPM": 4.54,
            "AAPL": 15.97,
            "VXUS": 2.63,
            "BRK.B": .72,
            "WMT": 34.73,
            "GOOGL": 10.54,
            "AMZN": 5.18
        }

        request = PortfolioRequest(
            tickers=list(allocation),

            weights={
                ticker: value / 100
                for ticker, value in allocation.items()
            },

            start="2023-01-01",
            end="2026-01-01"
        )

        self.assertAlmostEqual(
            sum(request.weights.values()),
            1.0
        )

        self.assertIn("BRK-B", request.weights)

        self.assertNotIn("BRK.B", request.weights)

    @patch("backend.api.fetch_daily_returns")
    def test_portfolio_endpoint(self, fetch):

        fetch.return_value = pd.DataFrame({
            "VTI": [.01, -.01, .02],
            "BRK-B": [.02, -.01, .01]
        })

        response = TestClient(app).post(
            "/api/portfolio",
            json={
                "tickers": ["VTI", "BRK.B"],

                "weights": {
                    "VTI": .6,
                    "BRK.B": .3999
                },

                "start": "2023-01-01",
                "end": "2026-01-01"
            }
        )

        self.assertEqual(response.status_code, 200)

        fetch.assert_called_once_with(
            ["VTI", "BRK-B"],
            "2023-01-01",
            "2026-01-01"
        )

        self.assertAlmostEqual(
            sum(response.json()["weights"].values()),
            1.0
        )

    @patch("backend.api.fetch_daily_returns")
    def test_comparison_endpoint(self, fetch):

        fetch.return_value = pd.DataFrame({
            "VTI": [.01, -.01, .02],
            "BRK-B": [.02, -.01, .01]
        })

        response = TestClient(app).post(
            "/api/compare",
            json={
                "tickers": ["VTI"],

                "weights": {
                    "VTI": .9999
                },

                "comparison_weights": {
                    "BRK.B": 1.0001
                },

                "start": "2023-01-01",
                "end": "2026-01-01",
                "trading_days": 5,
                "num_simulations": 10,
                "seed": 42
            }
        )

        self.assertEqual(response.status_code, 200)

        body = response.json()

        self.assertEqual(
            body["portfolio_a"]["analysis"]["weights"],
            {"VTI": 1.0}
        )

        self.assertEqual(
            body["portfolio_b"]["analysis"]["weights"],
            {"BRK-B": 1.0}
        )

    @patch("backend.api.fetch_daily_returns")
    def test_alias_collision_before_download(self, fetch):

        response = TestClient(app).post(
            "/api/portfolio",
            json={
                "tickers": ["BRK-B"],

                "weights": {
                    "BRK.B": .5,
                    "BRK-B": .5
                },

                "start": "2023-01-01",
                "end": "2026-01-01"
            }
        )

        self.assertEqual(response.status_code, 422)

        fetch.assert_not_called()