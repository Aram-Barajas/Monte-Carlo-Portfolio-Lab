import unittest

import numpy as np
import pandas as pd

from backend.monte_carlo import (
    estimate_log_return_parameters,
    simulate_portfolio,
    summarize_simulations
)


class MonteCarloTests(unittest.TestCase):

    def setUp(self):
        self.returns = pd.DataFrame({
            "NVDA": [0.02, -0.01, 0.03, -0.02],
            "VTI": [0.01, -0.005, 0.015, -0.01]
        })

        self.weights = {
            "NVDA": 0.4,
            "VTI": 0.6
        }

    def test_log_return_parameters(self):
        means, covariance = estimate_log_return_parameters(
            self.returns
        )

        expected = np.log1p(
            self.returns.to_numpy()
        )

        np.testing.assert_allclose(
            means,
            expected.mean(axis=0)
        )

        np.testing.assert_allclose(
            covariance,
            np.cov(expected, rowvar=False)
        )

    def test_shape_and_starting_value(self):
        paths = simulate_portfolio(
            self.returns, self.weights,
            500, 10, 25, seed=42
        )

        self.assertEqual(paths.shape, (25, 11))
        np.testing.assert_allclose(paths[:, 0], 500)
        self.assertTrue((paths >= 0).all())

    def test_reproducible_seed(self):
        first = simulate_portfolio(
            self.returns, self.weights, seed=42
        )

        second = simulate_portfolio(
            self.returns, self.weights, seed=42
        )

        np.testing.assert_array_equal(first, second)

    def test_different_seeds(self):
        first = simulate_portfolio(
            self.returns, self.weights,
            100, 5, 10, seed=1
        )

        second = simulate_portfolio(
            self.returns, self.weights,
            100, 5, 10, seed=2
        )

        self.assertFalse(
            np.array_equal(first, second)
        )

    def test_zero_return(self):
        returns = pd.DataFrame({
            "A": [0.0, 0.0, 0.0]
        })

        paths = simulate_portfolio(
            returns, {"A": 1},
            100, 10, 5, seed=1
        )

        np.testing.assert_allclose(paths, 100)

    def test_constant_return_compounds(self):
        returns = pd.DataFrame({
            "A": [0.01, 0.01, 0.01]
        })

        paths = simulate_portfolio(
            returns, {"A": 1},
            100, 10, 5, seed=1
        )

        expected = 100 * 1.01 ** np.arange(11)

        np.testing.assert_allclose(
            paths,
            np.tile(expected, (5, 1))
        )

    def test_weighted_asset_growth(self):
        returns = pd.DataFrame({
            "A": [0.02, 0.02],
            "B": [0.0, 0.0]
        })

        paths = simulate_portfolio(
            returns,
            {"A": 0.5, "B": 0.5},
            100, 2, 5, seed=1
        )

        np.testing.assert_allclose(
            paths[:, -1],
            100 * 1.01 ** 2
        )

    def test_monthly_contributions(self):
        returns = pd.DataFrame({
            "A": [0.0, 0.0]
        })

        paths = simulate_portfolio(
            returns, {"A": 1},
            100, 42, 5, 50, seed=1
        )

        np.testing.assert_allclose(paths[:, 20], 100)
        np.testing.assert_allclose(paths[:, 21], 150)
        np.testing.assert_allclose(paths[:, 42], 200)

    def test_contributions_added_after_daily_growth(self):
        returns = pd.DataFrame({
            "A": [0.01, 0.01]
        })

        paths = simulate_portfolio(
            returns, {"A": 1},
            100, 21, 5, 50, seed=1
        )

        np.testing.assert_allclose(
            paths[:, 21],
            100 * 1.01 ** 21 + 50
        )

    def test_singular_covariance_preserves_negative_correlation(self):
        logs = np.array([-0.1, 0.0, 0.1])

        returns = pd.DataFrame({
            "A": np.expm1(logs),
            "B": np.expm1(-logs)
        })

        paths = simulate_portfolio(
            returns,
            {"A": 0.5, "B": 0.5},
            100, 1, 500, seed=42
        )

        self.assertTrue(
            (paths[:, 1] >= 100 - 1e-8).all()
        )

    def test_summary_percentiles(self):
        paths = np.array([
            [100, 90],
            [100, 110],
            [100, 130]
        ])

        summary = summarize_simulations(paths)

        self.assertEqual(summary.shape, (2, 5))
        self.assertEqual(summary.index.name, "trading_day")
        self.assertEqual(summary.loc[1, "median"], 110)
        self.assertAlmostEqual(summary.loc[1, "p05"], 92)

        self.assertTrue(
            (summary.loc[0] == 100).all()
        )

    def test_invalid_parameters(self):
        for kwargs in (
            {"initial_value": -1},
            {"initial_value": np.inf},
            {"trading_days": 0},
            {"trading_days": 1.5},
            {"num_simulations": 0},
            {"monthly_contribution": -1},
            {"seed": -1},
            {"num_simulations": 10_000_000}
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    simulate_portfolio(
                        self.returns,
                        self.weights,
                        **kwargs
                    )

    def test_invalid_returns_or_weights(self):
        with self.assertRaises(ValueError):
            simulate_portfolio(
                self.returns,
                {"NVDA": 1}
            )

        with self.assertRaises(ValueError):
            estimate_log_return_parameters(
                pd.DataFrame({"A": [-1.0, 0.1]})
            )

    def test_invalid_summary_paths(self):
        for paths in (
            [],
            [[100, np.nan]],
            [[100, -1]]
        ):
            with self.subTest(paths=paths):
                with self.assertRaises(ValueError):
                    summarize_simulations(paths)


if __name__ == "__main__":
    unittest.main()