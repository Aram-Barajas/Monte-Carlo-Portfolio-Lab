import unittest

import numpy as np
import pandas as pd

from backend.portfolio_metrics import (
    calculate_asset_metrics,
    calculate_portfolio_metrics,
    calculate_portfolio_returns,
)


class PortfolioMetricsTests(unittest.TestCase):

    def setUp(self):
        self.returns = pd.DataFrame({
            "NVDA": [0.10, -0.10],
            "VTI": [0.00, 0.20]
        })

        self.weights = {
            "NVDA": 0.25,
            "VTI": 0.75
        }

    def test_annualized_asset_return(self):
        metrics = calculate_asset_metrics(
            self.returns,
            periods_per_year=4
        )

        self.assertAlmostEqual(
            metrics.loc["NVDA", "annualized_return"],
            0
        )

        self.assertAlmostEqual(
            metrics.loc["VTI", "annualized_return"],
            0.4
        )

    def test_annualized_asset_volatility(self):
        metrics = calculate_asset_metrics(
            self.returns,
            periods_per_year=4
        )

        expected = np.sqrt(0.02) * np.sqrt(4)

        self.assertAlmostEqual(
            metrics.loc["NVDA", "annualized_volatility"],
            expected
        )

        self.assertAlmostEqual(
            metrics.loc["VTI", "annualized_volatility"],
            expected
        )

    def test_weighted_returns(self):
        result = calculate_portfolio_returns(
            self.returns,
            self.weights
        )

        np.testing.assert_allclose(
            result,
            [0.025, 0.125]
        )

    def test_portfolio_metrics(self):
        metrics = calculate_portfolio_metrics(
            self.returns,
            self.weights,
            4
        )

        self.assertAlmostEqual(
            metrics["annualized_return"],
            0.3
        )

        self.assertAlmostEqual(
            metrics["annualized_volatility"],
            np.sqrt(0.005) * 2
        )

    def test_default_252_trading_days(self):
        metrics = calculate_asset_metrics(self.returns)

        self.assertAlmostEqual(
            metrics.loc["VTI", "annualized_return"],
            0.1 * 252
        )

    def test_weight_order_does_not_change_results(self):
        result = calculate_portfolio_returns(
            self.returns,
            {
                "VTI": 0.75,
                "NVDA": 0.25
            }
        )

        np.testing.assert_allclose(
            result,
            [0.025, 0.125]
        )

    def test_single_asset_portfolio(self):
        data = self.returns[["NVDA"]]

        result = calculate_portfolio_returns(
            data,
            {"NVDA": 1}
        )

        np.testing.assert_allclose(
            result,
            data["NVDA"]
        )

    def test_diversification_reduces_volatility(self):
        result = calculate_portfolio_metrics(
            self.returns,
            {
                "NVDA": 0.5,
                "VTI": 0.5
            }
        )

        self.assertAlmostEqual(
            result["annualized_volatility"],
            0
        )

    def test_invalid_weights(self):
        for weights in (
            {"NVDA": 1},
            {"NVDA": 0.5, "VTI": 0.5, "AMZN": 0},
            {"NVDA": 0.3, "VTI": 0.3},
            {"NVDA": -0.2, "VTI": 1.2},
            {"NVDA": np.nan, "VTI": 1},
            {"NVDA": "0.5", "VTI": 0.5}
        ):
            with self.subTest(weights=weights):
                with self.assertRaises(ValueError):
                    calculate_portfolio_returns(
                        self.returns,
                        weights
                    )

    def test_invalid_returns(self):
        for value in (np.nan, np.inf, -1.01):

            with self.subTest(value=value):
                data = self.returns.copy()
                data.iloc[0, 0] = value

                with self.assertRaises(ValueError):
                    calculate_asset_metrics(data)

    def test_insufficient_returns(self):
        with self.assertRaises(ValueError):
            calculate_asset_metrics(
                self.returns.iloc[:1]
            )

    def test_invalid_periods_per_year(self):
        for periods in (0, -1, 2.5, True):

            with self.subTest(periods=periods):
                with self.assertRaises(ValueError):
                    calculate_asset_metrics(
                        self.returns,
                        periods
                    )


if __name__ == "__main__":
    unittest.main()