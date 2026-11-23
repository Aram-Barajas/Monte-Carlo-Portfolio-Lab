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

    def test_bootstrap_matches_circular_joint_blocks(self):
        returns = pd.DataFrame({"A": [.10, -.05, .03], "B": [-.02, .07, -.01]})
        weights = {"A": .4, "B": .6}
        rng = np.random.default_rng(42)
        expected = np.full((8, 6), 100.0)
        gross = 1 + returns.to_numpy() @ np.array([.4, .6])
        for day in range(5):
            if day % 3 == 0:
                starts = rng.integers(3, size=8)
            expected[:, day + 1] = expected[:, day] * gross[(starts + day % 3) % 3]
        paths = simulate_portfolio(returns, weights, 100, 5, 8, seed=42,
                                   model="block_bootstrap", block_length=3)
        np.testing.assert_allclose(paths, expected, rtol=1e-12)

    def test_bootstrap_preserves_cross_asset_pairing(self):
        returns = pd.DataFrame({"A": [.1, -.1, .2, -.2], "B": [-.1, .1, -.2, .2]})
        paths = simulate_portfolio(returns, {"A": .5, "B": .5}, 100, 25, 50,
                                   seed=42, model="block_bootstrap", block_length=2)
        np.testing.assert_allclose(paths, 100, rtol=1e-12)

    def test_alternative_models_reproduce_seed_and_contributions(self):
        for model in ("block_bootstrap", "gaussian_uncertain"):
            with self.subTest(model=model):
                kwargs = dict(model=model, block_length=2, seed=42,
                              trading_days=42, num_simulations=25, monthly_contribution=100)
                first = simulate_portfolio(self.returns, self.weights, **kwargs)
                second = simulate_portfolio(self.returns, self.weights, **kwargs)
                np.testing.assert_array_equal(first, second)
                different = simulate_portfolio(self.returns, self.weights, **{**kwargs, "seed": 43})
                self.assertFalse(np.array_equal(first, different))
                without = simulate_portfolio(self.returns, self.weights,
                                             **{**kwargs, "monthly_contribution": 0})
                np.testing.assert_allclose(first[:, 20], without[:, 20])
                np.testing.assert_allclose(first[:, 21] - without[:, 21], 100)
                np.testing.assert_allclose(first[:, 42] - without[:, 42],
                                           100 * without[:, 42] / without[:, 21] + 100)

    def test_drift_shrinkage_zero_mean_is_not_zero_return_assumption(self):
        returns = pd.DataFrame({"A": [.01] * 4})
        for model in ("gaussian", "gaussian_uncertain", "block_bootstrap"):
            with self.subTest(model=model):
                paths = simulate_portfolio(returns, {"A": 1}, 100, 10, 5,
                                           seed=12, model=model, block_length=2, drift_weight=.5)
                np.testing.assert_allclose(paths[:, -1], 100 * 1.01**5, rtol=1e-12)

    def test_uncertain_mean_has_expected_terminal_log_variance(self):
        returns = pd.DataFrame({"A": np.expm1([-.03, .01, .04, -.02, .01])})
        horizon = 30
        daily_variance = np.log1p(returns["A"]).var(ddof=1)
        for model, expected in (
            ("gaussian", horizon * daily_variance),
            ("gaussian_uncertain", (horizon + horizon**2 / len(returns)) * daily_variance),
        ):
            with self.subTest(model=model):
                paths = simulate_portfolio(returns, {"A": 1}, 100, horizon, 10000,
                                           seed=42, model=model)
                measured = np.log(paths[:, -1] / 100).var(ddof=1)
                self.assertTrue(np.isclose(measured, expected, rtol=.05), (measured, expected))

    def test_invalid_model_parameters(self):
        for kwargs in (
            {"model": "other"}, {"drift_weight": -1}, {"drift_weight": 1.1},
            {"drift_weight": np.nan}, {"drift_weight": True},
            {"block_length": 0}, {"block_length": 1.5}, {"block_length": True},
            {"model": "block_bootstrap", "block_length": 5},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                simulate_portfolio(self.returns, self.weights, **kwargs)
        with self.assertRaisesRegex(ValueError, "chronological"):
            simulate_portfolio(self.returns.iloc[::-1], self.weights,
                               model="block_bootstrap", block_length=2)

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
