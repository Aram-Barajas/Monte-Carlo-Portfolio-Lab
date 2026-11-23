import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from fastapi.testclient import TestClient

from backend.api import app
from backend.backtest import backtest_portfolio


class BacktestTests(unittest.TestCase):

    def setUp(self):
        self.prices = pd.DataFrame(
            {
                "NVDA": [100, 120, 96],
                "VTI": [100, 100, 100]
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

    def test_known_portfolio_trajectory(self):
        result = backtest_portfolio(
            self.prices,
            self.weights
        )

        np.testing.assert_allclose(
            result["trajectory"]["value"],
            [1000, 1100, 990]
        )

        np.testing.assert_allclose(
            result["trajectory"]["drawdown"],
            [0, 0, 0.1]
        )

        self.assertAlmostEqual(
            result["ending_value"], 990
        )

        self.assertAlmostEqual(
            result["total_return"], -0.01
        )

        self.assertAlmostEqual(
            result["max_drawdown"], 0.1
        )

        self.assertAlmostEqual(
            result["cagr"],
            0.99 ** 126 - 1
        )

        self.assertAlmostEqual(
            result["annualized_volatility"],
            np.std([0.1, -0.1], ddof=1) *
            np.sqrt(252)
        )

        self.assertEqual(
            result["observations"], 2
        )

    def test_initial_value_and_column_order(self):
        result = backtest_portfolio(
            self.prices[["VTI", "NVDA"]],
            self.weights,
            initial_value=2000
        )

        self.assertAlmostEqual(
            result["ending_value"], 1980
        )

        self.assertAlmostEqual(
            result["total_return"], -0.01
        )

    def test_flat_portfolio_has_undefined_sharpe(self):
        result = backtest_portfolio(
            self.prices,
            {
                "NVDA": 0.0,
                "VTI": 1.0
            }
        )

        self.assertEqual(
            result["ending_value"], 1000
        )

        self.assertEqual(result["cagr"], 0)

        self.assertEqual(
            result["annualized_volatility"], 0
        )

        self.assertIsNone(
            result["sharpe_ratio"]
        )

    def test_trims_nonoverlapping_history(self):
        prices = pd.DataFrame(
            {
                "NVDA": [
                    100, 100, 120, 96, np.nan
                ],
                "VTI": [
                    np.nan, 100, 100, 100, 100
                ]
            },
            index=pd.date_range(
                "2025-01-01",
                periods=5
            )
        )

        result = backtest_portfolio(
            prices,
            self.weights
        )

        self.assertEqual(
            len(result["trajectory"]), 3
        )

        self.assertEqual(
            result["trajectory"].index[0],
            prices.index[1]
        )

        self.assertEqual(
            result["trajectory"].index[-1],
            prices.index[3]
        )

        self.assertAlmostEqual(
            result["ending_value"], 990
        )

    def test_internal_missing_prices_rejected(self):
        prices = self.prices.copy()

        prices.iloc[1, 0] = np.nan

        with self.assertRaisesRegex(
            ValueError,
            "missing prices"
        ):
            backtest_portfolio(
                prices,
                self.weights
            )

    def test_invalid_initial_values(self):
        for value in (
            0, -1, np.inf, np.nan, True
        ):
            with self.subTest(value=value):

                with self.assertRaises(ValueError):
                    backtest_portfolio(
                        self.prices,
                        self.weights,
                        value
                    )

    def test_invalid_weights_and_short_history(self):

        with self.assertRaises(ValueError):
            backtest_portfolio(
                self.prices,
                {
                    "NVDA": 0.5,
                    "VTI": 0.4
                }
            )

        with self.assertRaisesRegex(
            ValueError,
            "3 overlapping"
        ):
            backtest_portfolio(
                self.prices.iloc[:2],
                self.weights
            )

    def test_numerical_overflow(self):
        prices = self.prices.copy().astype(float)

        prices.iloc[-1, 0] = 1e300

        with self.assertRaisesRegex(
            ValueError,
            "numerical limits"
        ):
            backtest_portfolio(
                prices,
                self.weights
            )

    def test_endpoint(self):
        request = {
            "tickers": ["NVDA", "VTI"],

            "weights": self.weights,

            "start": "2025-01-01",

            "end": "2025-02-01",

            "initial_value": 1000
        }

        client = TestClient(app)

        with patch(
            "backend.api.fetch_historical_prices",
            return_value=self.prices
        ) as fetch:

            response = client.post(
                "/api/backtest",
                json=request
            )

            self.assertEqual(
                response.status_code, 200
            )

            body = response.json()

            self.assertAlmostEqual(
                body["ending_value"], 990
            )

            self.assertEqual(
                body["trajectory"][0]["date"],
                "2025-01-02"
            )

            self.assertEqual(
                body["trajectory"][0]["value"],
                1000
            )

            self.assertEqual(
                len(body["trajectory"]), 3
            )

            fetch.assert_called_once()

        invalid = client.post(
            "/api/backtest",
            json={
                **request,
                "initial_value": 0
            }
        )

        self.assertEqual(
            invalid.status_code, 422
        )

        with patch(
            "backend.api.fetch_historical_prices",
            return_value=self.prices.iloc[:2]
        ):
            self.assertEqual(
                client.post(
                    "/api/backtest",
                    json=request
                ).status_code,
                422
            )


if __name__ == "__main__":
    unittest.main()
