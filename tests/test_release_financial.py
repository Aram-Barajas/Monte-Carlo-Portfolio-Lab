"""Regression checks for the audit's highest-risk financial assumptions."""

import unittest

import numpy as np
import pandas as pd

from backend.api import SimulationRequest
from backend.monte_carlo import simulate_portfolio
from backend.portfolio_policy import PortfolioTracker


class ReleaseFinancialTests(unittest.TestCase):
    def setUp(self):
        log_history = [-.025, .007, .015, -.009, .021, -.014, .004, .012]
        self.returns = pd.DataFrame({"TEST": np.expm1(log_history)})
        self.weights = {"TEST": 1.}

    def test_api_defaults_to_uncertain_mean(self):
        request = SimulationRequest(tickers=["TEST"], start="2023-01-01",
                                    end="2026-01-01", weights=self.weights)
        self.assertEqual(request.model, "gaussian_uncertain")
        self.assertEqual(request.annual_risk_free_rate, 0.)
        with self.assertRaises(ValueError):
            SimulationRequest(tickers=["TEST"], start="2023-01-01",
                              end="2026-01-01", weights=self.weights,
                              annual_risk_free_rate=float("nan"))

    def test_shrinking_drift_does_not_shrink_sampling_uncertainty(self):
        """Same random shocks mean only deterministic drift should change."""
        seed = 441
        horizon = 24
        zero = simulate_portfolio(self.returns, self.weights, initial_value=100,
                                  trading_days=horizon, num_simulations=350,
                                  seed=seed, model="gaussian_uncertain", drift_weight=0)
        full = simulate_portfolio(self.returns, self.weights, initial_value=100,
                                  trading_days=horizon, num_simulations=350,
                                  seed=seed, model="gaussian_uncertain", drift_weight=1)
        expected = horizon * np.log1p(self.returns["TEST"]).mean()
        np.testing.assert_allclose(
            np.log(full[:, -1] / zero[:, -1]), expected, atol=1e-12, rtol=0,
        )
        self.assertGreater(np.std(np.log(zero[:, -1])), .01)

    def test_uncertain_mean_variance_matches_iid_theory_under_shrinkage(self):
        """Model variance: horizon*sigma^2 + horizon^2*sigma^2/n."""
        horizon, paths = 21, 7000
        values = simulate_portfolio(self.returns, self.weights,
                                    initial_value=100, trading_days=horizon,
                                    num_simulations=paths, seed=1234,
                                    model="gaussian_uncertain", drift_weight=.3)
        measured = float(np.log(values[:, -1] / 100).var(ddof=1))
        daily_var = float(np.log1p(self.returns["TEST"]).var(ddof=1))
        expected = daily_var * (horizon + horizon * horizon / len(self.returns))
        self.assertAlmostEqual(measured / expected, 1, delta=.08)

    def test_daily_zero_cost_tracker_keeps_holdings_and_values_in_sync(self):
        rng = np.random.default_rng(53)
        tracker = PortfolioTracker(np.array([.25, .75]), 500, 4,
                                   rebalancing="daily", trading_cost_bps=0)
        for day in range(1, 28):
            gross = np.exp(rng.normal(0, .015, (4, 2)))
            contribution = 100 if day % 21 == 0 else 0
            previous = tracker.values.copy()
            current = tracker.advance(gross, day, contribution)
            expected = previous * (gross @ np.array([.25, .75])) + contribution
            np.testing.assert_allclose(current, expected)
            np.testing.assert_allclose(tracker.holdings.sum(axis=1), current)
            np.testing.assert_allclose(tracker.holdings,
                                       current[:, None] * np.array([.25, .75]))
        np.testing.assert_array_equal(tracker.costs, np.zeros(4))


if __name__ == "__main__":
    unittest.main()
