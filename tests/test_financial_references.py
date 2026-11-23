"""Compare financial analytics against independently known solutions."""

import unittest

import numpy as np
import pandas as pd

from backend.backtest import backtest_portfolio
from backend.frontier import calculate_efficient_frontier
from backend.monte_carlo import simulate_portfolio
from backend.optimization import optimize_portfolio
from backend.risk_metrics import calculate_simulation_risk


class FinancialReferenceTests(unittest.TestCase):

    def setUp(self):
        # Orthogonal deviations with shared components produce a non-diagonal,
        # positive-definite sample covariance matrix with known entries.
        a = np.array([1, -1, 1, -1])
        b = np.array([1, 1, -1, -1])
        c = np.array([1, -1, -1, 1])
        self.returns = pd.DataFrame({
            "A": .001 + .01 * a,
            "B": .002 + .005 * a + .02 * b,
            "C": .0015 + .003 * a + .004 * b + .015 * c,
        })
        self.weights = {"A": .4, "B": .3, "C": .3}
        self.covariance = (4 / 3) * np.array([
            [.0001, .00005, .00003],
            [.00005, .000425, .000095],
            [.00003, .000095, .00025],
        ])
        self.mean = np.array([.001, .002, .0015])

    def test_correlated_optimizer_against_closed_form(self):
        result = optimize_portfolio(self.returns, self.weights)
        # For these inputs, the unconstrained analytical optima satisfy
        # all long-only constraints, so they are also the constrained optima.
        for key, rhs in (("minimum_volatility", np.ones(3)),
                         ("maximum_sharpe", self.mean)):
            with self.subTest(objective=key):
                expected = np.linalg.solve(self.covariance, rhs)
                expected /= expected.sum()
                self.assertTrue((expected > 0).all())
                actual = [result[key]["weights"][symbol] for symbol in self.weights]
                np.testing.assert_allclose(actual, expected, atol=1e-6, rtol=0)

    def test_efficient_frontier_matches_analytical_interior_points(self):
        result = calculate_efficient_frontier(self.returns, self.weights, points=11)
        constraints = np.vstack([np.ones(3), self.mean])
        inverse = np.linalg.solve(self.covariance, constraints.T)
        checked = 0
        for point in result["frontier"][1:-1]:
            target = point["annualized_return"] / 252
            expected = inverse @ np.linalg.solve(
                constraints @ inverse, [1, target]
            )
            if np.min(expected) > 1e-6:  # only interior, feasible solutions
                checked += 1
                actual = [point["weights"][symbol] for symbol in self.weights]
                np.testing.assert_allclose(actual, expected, atol=1e-6, rtol=0)
        self.assertGreater(checked, 0)

    def test_single_asset_backtest_matches_adjusted_price_ratio(self):
        prices = pd.DataFrame({"A": [100., 120., 90., 135.]},
                              index=pd.date_range("2025-01-02", periods=4, freq="B"))
        result = backtest_portfolio(prices, {"A": 1.0}, initial_value=1000)
        np.testing.assert_allclose(result["trajectory"]["value"], [1000, 1200, 900, 1350])
        self.assertAlmostEqual(result["total_return"], .35)
        self.assertAlmostEqual(result["max_drawdown"], .25)

    def test_constant_returns_with_contributions_match_geometric_growth(self):
        returns = pd.DataFrame({"A": [.01] * 4})
        paths = simulate_portfolio(returns, {"A": 1.0}, initial_value=1000,
                                   trading_days=42, num_simulations=10,
                                   monthly_contribution=100, seed=42)
        # Contributions arrive at the end of day 21 and day 42.
        expected = 1000 * 1.01**42 + 100 * 1.01**21 + 100
        np.testing.assert_allclose(paths[:, -1], expected, rtol=1e-12)
        risk = calculate_simulation_risk(paths, 100)
        self.assertEqual(risk["total_invested"], 1200)
        self.assertEqual(risk["probability_of_loss"], 0)
