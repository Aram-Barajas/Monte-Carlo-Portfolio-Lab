import unittest

import numpy as np
import pandas as pd

from backend.monte_carlo import simulate_portfolio

from backend.risk_metrics import (
    calculate_historical_risk,
    calculate_loss_metrics,
    calculate_simulation_risk
)


class RiskMetricsTests(unittest.TestCase):

    def test_empirical_value_at_risk(self):
        risk = calculate_loss_metrics(
            [10, 20, 30, 40], 0.5
        )

        self.assertEqual(risk["value_at_risk"], 20)
        self.assertAlmostEqual(risk["expected_shortfall"], 35)

    def test_fractional_tail(self):
        risk = calculate_loss_metrics(
            [10, 20, 30, 40], 0.625
        )

        self.assertEqual(risk["value_at_risk"], 30)

        self.assertAlmostEqual(
            risk["expected_shortfall"],
            (40 + 0.5 * 30) / 1.5
        )

    def test_boundary_ties(self):
        risk = calculate_loss_metrics(
            [0, 10, 10, 20], 0.625
        )

        self.assertEqual(risk["value_at_risk"], 10)

        self.assertAlmostEqual(
            risk["expected_shortfall"],
            (20 + 0.5 * 10) / 1.5
        )

    def test_all_gains_produce_negative_losses(self):
        risk = calculate_loss_metrics(
            [-30, -20, -10], 0.95
        )

        self.assertEqual(risk["value_at_risk"], -10)
        self.assertAlmostEqual(risk["expected_shortfall"], -10)

    def test_historical_daily_risk(self):
        returns = pd.DataFrame({
            "A": [-0.2, 0.25, -0.1, 0.1]
        })

        risk = calculate_historical_risk(
            returns,
            {"A": 1},
            confidence=0.75
        )

        self.assertAlmostEqual(risk["daily_var"], 0.1)

        self.assertAlmostEqual(
            risk["daily_expected_shortfall"], 0.2
        )

        self.assertAlmostEqual(risk["max_drawdown"], 0.2)

    def test_drawdown_from_previous_peak(self):
        returns = pd.DataFrame({
            "A": [0.2, -0.25, 0.1]
        })

        risk = calculate_historical_risk(
            returns, {"A": 1}
        )

        self.assertAlmostEqual(risk["max_drawdown"], 0.25)

    def test_total_loss_drawdown(self):
        returns = pd.DataFrame({
            "A": [-1, 0.2]
        })

        risk = calculate_historical_risk(
            returns, {"A": 1}
        )

        self.assertEqual(risk["max_drawdown"], 1)

    def test_sharpe_ratio(self):
        returns = pd.DataFrame({
            "A": [-0.1, 0.2]
        })

        risk = calculate_historical_risk(
            returns,
            {"A": 1},
            annual_risk_free_rate=0.04,
            periods_per_year=4
        )

        self.assertAlmostEqual(
            risk["sharpe_ratio"],
            0.16 / (np.sqrt(0.045) * 2)
        )

    def test_zero_volatility_sharpe_undefined(self):
        returns = pd.DataFrame({
            "A": [0.01, 0.01, 0.01]
        })

        risk = calculate_historical_risk(
            returns, {"A": 1}
        )

        self.assertIsNone(risk["sharpe_ratio"])
        self.assertAlmostEqual(risk["max_drawdown"], 0)

    def test_unsorted_dates(self):
        returns = pd.DataFrame({
            "A": [0.2, -0.25, 0.1]
        })

        expected = calculate_historical_risk(
            returns, {"A": 1}
        )

        actual = calculate_historical_risk(
            returns.iloc[::-1], {"A": 1}
        )

        self.assertEqual(actual, expected)

    def test_simulation_terminal_loss(self):
        paths = np.array([
            [100, 80],
            [100, 100],
            [100, 130],
            [100, 140]
        ])

        risk = calculate_simulation_risk(
            paths,
            confidence=0.75
        )

        self.assertEqual(risk["total_invested"], 100)
        self.assertEqual(risk["probability_of_loss"], 0.25)
        self.assertEqual(risk["median_ending_value"], 115)
        self.assertEqual(risk["mean_ending_value"], 112.5)
        self.assertEqual(risk["terminal_var"], 0)

        self.assertAlmostEqual(
            risk["terminal_expected_shortfall"], 20
        )

    def test_contributions_count_toward_invested_capital(self):
        paths = np.full((3, 43), 100.0)

        paths[:, -1] = [180, 200, 220]

        risk = calculate_simulation_risk(
            paths,
            monthly_contribution=50
        )

        self.assertEqual(risk["total_invested"], 200)

        self.assertAlmostEqual(
            risk["probability_of_loss"], 1 / 3
        )

    def test_zero_return_simulation_with_contributions(self):
        returns = pd.DataFrame({
            "A": [0.0, 0.0]
        })

        paths = simulate_portfolio(
            returns,
            {"A": 1},
            100, 42, 10, 50,
            seed=42
        )

        risk = calculate_simulation_risk(
            paths,
            monthly_contribution=50
        )

        self.assertEqual(risk["total_invested"], 200)
        self.assertEqual(risk["probability_of_loss"], 0)
        self.assertEqual(risk["terminal_var"], 0)

    def test_invalid_confidence_or_losses(self):
        for confidence in (0, 1, -0.1, np.nan, True):

            with self.subTest(confidence=confidence):
                with self.assertRaises(ValueError):
                    calculate_loss_metrics(
                        [1, 2], confidence
                    )

        for losses in ([], [[1, 2]], [1, np.inf]):

            with self.subTest(losses=losses):
                with self.assertRaises(ValueError):
                    calculate_loss_metrics(losses)

    def test_invalid_historical_inputs(self):
        returns = pd.DataFrame({
            "A": [0.01, 0.02]
        })

        with self.assertRaises(ValueError):
            calculate_historical_risk(
                returns,
                {"A": 1},
                annual_risk_free_rate=np.nan
            )

        with self.assertRaises(ValueError):
            calculate_historical_risk(
                returns, {"A": 0.5}
            )

    def test_invalid_simulation_inputs(self):
        for paths in (
            [],
            [[100]],
            [[100, -1]],
            [[100, np.inf]],
            [[100, 110], [200, 210]]
        ):
            with self.subTest(paths=paths):
                with self.assertRaises(ValueError):
                    calculate_simulation_risk(paths)

        with self.assertRaises(ValueError):
            calculate_simulation_risk(
                [[100, 110]],
                monthly_contribution=-1
            )


if __name__ == "__main__":
    unittest.main()