import unittest

import numpy as np
import pandas as pd

from backend.covariance import (
    calculate_correlation_matrix,
    calculate_covariance_matrix,
    calculate_portfolio_variance,
    calculate_portfolio_volatility,
)

from backend.portfolio_metrics import (
    calculate_portfolio_metrics
)


class CovarianceTests(unittest.TestCase):

    def setUp(self):
        self.returns = pd.DataFrame({
            "A": [0.01, 0.02, 0.03],
            "B": [0.03, 0.02, 0.01],
            "C": [0.01, 0.04, 0.01]
        })

        self.weights = {
            "A": 0.5,
            "B": 0.3,
            "C": 0.2
        }

    def test_daily_sample_covariance(self):
        matrix = calculate_covariance_matrix(
            self.returns, 1
        )

        expected = [
            [0.0001, -0.0001, 0],
            [-0.0001, 0.0001, 0],
            [0, 0, 0.0003]
        ]

        np.testing.assert_allclose(
            matrix, expected, atol=1e-12
        )

        self.assertEqual(
            matrix.index.tolist(),
            ["A", "B", "C"]
        )

        self.assertEqual(
            matrix.columns.tolist(),
            ["A", "B", "C"]
        )

    def test_annualized_covariance(self):
        daily = calculate_covariance_matrix(
            self.returns, 1
        )

        annual = calculate_covariance_matrix(
            self.returns
        )

        pd.testing.assert_frame_equal(
            annual, daily * 252
        )

    def test_correlation_matrix(self):
        matrix = calculate_correlation_matrix(
            self.returns
        )

        np.testing.assert_allclose(
            matrix,
            [
                [1, -1, 0],
                [-1, 1, 0],
                [0, 0, 1]
            ],
            atol=1e-12
        )

    def test_positive_correlation(self):
        data = self.returns.assign(
            D=self.returns["A"] * 2
        )

        matrix = calculate_correlation_matrix(data)

        self.assertAlmostEqual(
            matrix.loc["A", "D"], 1
        )

    def test_constant_asset_correlation_is_undefined(self):
        data = self.returns.assign(CONSTANT=0.0)

        correlation = calculate_correlation_matrix(data)

        self.assertTrue(
            correlation["CONSTANT"].isna().all()
        )

        covariance = calculate_covariance_matrix(data, 1)

        np.testing.assert_allclose(
            covariance["CONSTANT"], 0
        )

    def test_covariance_is_positive_semidefinite(self):
        covariance = calculate_covariance_matrix(
            self.returns
        )

        eigenvalues = np.linalg.eigvalsh(covariance)

        self.assertTrue(
            (eigenvalues >= -1e-12).all()
        )

    def test_weighted_portfolio_variance(self):
        variance = calculate_portfolio_variance(
            self.returns,
            self.weights,
            1
        )

        self.assertAlmostEqual(
            variance, 0.000016
        )

    def test_volatility_matches_existing_metrics(self):
        expected = calculate_portfolio_metrics(
            self.returns,
            self.weights
        )

        actual = calculate_portfolio_volatility(
            self.returns,
            self.weights
        )

        self.assertAlmostEqual(
            actual,
            expected["annualized_volatility"]
        )

    def test_perfectly_offsetting_assets(self):
        weights = {
            "A": 0.5,
            "B": 0.5,
            "C": 0.0
        }

        self.assertAlmostEqual(
            calculate_portfolio_volatility(
                self.returns, weights
            ),
            0
        )

    def test_weight_order_does_not_matter(self):
        reversed_weights = {
            "C": 0.2,
            "B": 0.3,
            "A": 0.5
        }

        expected = calculate_portfolio_variance(
            self.returns,
            self.weights
        )

        self.assertAlmostEqual(
            calculate_portfolio_variance(
                self.returns,
                reversed_weights
            ),
            expected
        )

    def test_single_asset(self):
        volatility = calculate_portfolio_volatility(
            self.returns[["A"]],
            {"A": 1}
        )

        self.assertAlmostEqual(
            volatility,
            0.01 * np.sqrt(252)
        )

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            calculate_covariance_matrix(
                self.returns, 0
            )

        with self.assertRaises(ValueError):
            calculate_correlation_matrix(
                self.returns.iloc[:1]
            )

        with self.assertRaises(ValueError):
            calculate_portfolio_variance(
                self.returns, {"A": 1}
            )


if __name__ == "__main__":
    unittest.main()