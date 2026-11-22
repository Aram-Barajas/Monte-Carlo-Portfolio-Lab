import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from fastapi.testclient import TestClient

from backend.api import app
from backend.benchmark import compare_benchmark


class BenchmarkTests(unittest.TestCase):

    def setUp(self):

        self.prices = pd.DataFrame(
            {
                "NVDA": [100, 120, 96],
                "VTI": [100, 100, 100],
                "SPY": [100, 105, 110]
            },
            index=pd.date_range(
                "2025-01-02",
                periods=3,
                freq="B"
            )
        )

        self.weights = {
            "NVDA": 0.5,
            "VTI": 0.5
        }

        self.request = {
            "tickers": ["NVDA", "VTI"],
            "weights": self.weights,
            "benchmark": "SPY",
            "start": "2025-01-01",
            "end": "2025-02-01",
            "initial_value": 1000
        }

        self.client = TestClient(app)

    def test_known_comparison(self):

        result = compare_benchmark(
            self.prices,
            self.weights,
            "SPY"
        )

        self.assertAlmostEqual(
            result["portfolio"]["ending_value"],
            990
        )

        self.assertAlmostEqual(
            result["benchmark"]["ending_value"],
            1100
        )

        self.assertAlmostEqual(
            result["excess_total_return"],
            -0.11
        )

        self.assertAlmostEqual(
            result["excess_cagr"],
            0.99 ** 126 - 1.1 ** 126
        )

    def test_shared_history(self):

        prices = pd.DataFrame(
            {
                "NVDA": [80, 100, 120, 96, 110],
                "VTI": [100, 100, 100, 100, 100],
                "SPY": [np.nan, 100, 105, 110, np.nan]
            },
            index=pd.date_range(
                "2025-01-01",
                periods=5
            )
        )

        result = compare_benchmark(
            prices,
            self.weights,
            "SPY"
        )

        for name in ("portfolio", "benchmark"):

            self.assertTrue(
                result[name]["trajectory"].index.equals(
                    prices.index[1:4]
                )
            )

            self.assertEqual(
                result[name]["observations"],
                2
            )

            self.assertEqual(
                result[name]["trajectory"]["value"].iloc[0],
                1000
            )

    def test_benchmark_already_owned(self):

        prices = self.prices[["VTI"]]

        result = compare_benchmark(
            prices,
            {"VTI": 1.0},
            "VTI",
            2000
        )

        self.assertEqual(
            result["excess_total_return"],
            0
        )

        self.assertEqual(
            result["excess_cagr"],
            0
        )

        self.assertEqual(
            result["benchmark"]["ending_value"],
            2000
        )

        self.assertIsNone(
            result["benchmark"]["sharpe_ratio"]
        )

    def test_reject_missing_prices(self):

        prices = self.prices.copy().astype(float)

        prices.loc[prices.index[1], "SPY"] = np.nan

        with self.assertRaisesRegex(
            ValueError,
            "missing prices"
        ):
            compare_benchmark(
                prices,
                self.weights,
                "SPY"
            )

    def test_reject_missing_benchmark(self):

        with self.assertRaises(ValueError):

            compare_benchmark(
                self.prices[["NVDA", "VTI"]],
                self.weights,
                "SPY"
            )

    def test_endpoint(self):

        with patch(
            "backend.api.fetch_historical_prices",
            return_value=self.prices
        ) as fetch:

            response = self.client.post(
                "/api/benchmark",
                json=self.request
            )

            self.assertEqual(
                response.status_code,
                200
            )

            body = response.json()

            self.assertEqual(
                body["benchmark_ticker"],
                "SPY"
            )

            self.assertAlmostEqual(
                body["excess_total_return"],
                -0.11
            )

            self.assertEqual(
                body["portfolio"]["trajectory"][0]["date"],
                "2025-01-02"
            )

            self.assertEqual(
                body["benchmark"]["trajectory"][0]["value"],
                1000
            )

            fetch.assert_called_once_with(
                ["NVDA", "VTI", "SPY"],
                "2025-01-01",
                "2025-02-01"
            )

    def test_endpoint_alias_and_deduplication(self):

        prices = self.prices.rename(
            columns={"VTI": "BRK-B"}
        )[["NVDA", "BRK-B"]]

        request = {
            **self.request,
            "tickers": ["NVDA", "BRK-B"],
            "weights": {
                "NVDA": 0.5,
                "BRK-B": 0.5
            },
            "benchmark": " brk.b "
        }

        with patch(
            "backend.api.fetch_historical_prices",
            return_value=prices
        ) as fetch:

            response = self.client.post(
                "/api/benchmark",
                json=request
            )

            self.assertEqual(
                response.status_code,
                200
            )

            self.assertEqual(
                response.json()["benchmark_ticker"],
                "BRK-B"
            )

            fetch.assert_called_once_with(
                ["NVDA", "BRK-B"],
                "2025-01-01",
                "2025-02-01"
            )

    def test_invalid_requests(self):

        tickers = [
            f"T{i}" for i in range(20)
        ]

        invalid = [
            {"benchmark": ""},
            {"benchmark": "BAD SYMBOL"},
            {"benchmark": "A" * 21},
            {"initial_value": 0},
            {
                "tickers": tickers,
                "weights": dict.fromkeys(
                    tickers,
                    0.05
                )
            }
        ]

        with patch(
            "backend.api.fetch_historical_prices"
        ) as fetch:

            for changes in invalid:

                with self.subTest(changes=changes):

                    response = self.client.post(
                        "/api/benchmark",
                        json={
                            **self.request,
                            **changes
                        }
                    )

                    self.assertEqual(
                        response.status_code,
                        422
                    )

            fetch.assert_not_called()

    def test_data_source_error(self):

        with patch(
            "backend.api.fetch_historical_prices",
            side_effect=RuntimeError
        ):

            response = self.client.post(
                "/api/benchmark",
                json=self.request
            )

            self.assertEqual(
                response.status_code,
                502
            )


if __name__ == "__main__":
    unittest.main()