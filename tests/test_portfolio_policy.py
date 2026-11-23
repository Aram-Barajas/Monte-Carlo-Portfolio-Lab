"""Reference-value tests for portfolio trading and real-dollar accounting."""

import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from backend.api import app
from backend.backtest import backtest_portfolio
from backend.benchmark import compare_benchmark
from backend.monte_carlo import simulate_portfolio
from backend.portfolio_policy import PortfolioTracker, inflation_factors


class TradingPolicyTests(unittest.TestCase):
    def setUp(self):
        self.weights = {"A": .5, "B": .5}
        self.prices = pd.DataFrame({"A": [100., 200., 100.], "B": [100., 100., 100.]},
                                   index=pd.date_range("2025-01-02", periods=3, freq="B"))

    def test_buy_hold_and_daily_rebalance_differ(self):
        hold = backtest_portfolio(self.prices, self.weights, rebalancing="buy_hold")
        daily = backtest_portfolio(self.prices, self.weights)
        self.assertAlmostEqual(hold["ending_value"], 1000)
        self.assertAlmostEqual(daily["ending_value"], 1125)

    def test_periodic_rebalancing_tracks_drift_until_due(self):
        for policy, interval in (("monthly", 21), ("quarterly", 63), ("annual", 252)):
            with self.subTest(policy=policy):
                tracker = PortfolioTracker([.5, .5], 1000, 1, rebalancing=policy)
                tracker.advance(np.array([2., 1.]), 1)
                for day in range(2, interval):
                    tracker.advance(np.ones(2), day)
                np.testing.assert_allclose(tracker.holdings, [[1000, 500]])
                tracker.advance(np.ones(2), interval)
                np.testing.assert_allclose(tracker.holdings, [[750, 750]])

    def test_threshold_is_absolute_weight_drift_and_checked_per_path(self):
        tracker = PortfolioTracker([.5, .5], 1000, 2, rebalancing="threshold", rebalance_threshold=.1)
        tracker.advance(np.array([[2., 1.], [1.1, 1.]]), 1)
        np.testing.assert_allclose(tracker.holdings, [[750, 750], [550, 500]])

    def test_rebalance_fee_is_self_financing(self):
        tracker = PortfolioTracker([.5, .5], 1000, 1, trading_cost_bps=100)
        value = tracker.advance(np.array([2., 1.]), 1)[0]
        self.assertAlmostEqual(value, 1495)
        self.assertAlmostEqual(tracker.costs[0], 5)
        np.testing.assert_allclose(tracker.holdings, [[747.5, 747.5]])
        # Actual purchases plus sales, times the per-side fee, reconcile exactly.
        gross_notional = np.abs(tracker.holdings[0] - [1000, 500]).sum()
        self.assertAlmostEqual(1500 - value, .01 * gross_notional)

    def test_costs_and_realized_net_backtest_risk(self):
        result = backtest_portfolio(self.prices, self.weights, trading_cost_bps=100)
        values = result["trajectory"]["value"].to_numpy()
        np.testing.assert_allclose(values, [1000, 1495, 1117.5125])
        self.assertAlmostEqual(result["trading_costs"], 8.7375)
        net_returns = values[1:] / values[:-1] - 1
        self.assertAlmostEqual(result["annualized_volatility"], net_returns.std(ddof=1) * np.sqrt(252))
        self.assertAlmostEqual(result["sharpe_ratio"], net_returns.mean() / net_returns.std(ddof=1) * np.sqrt(252))

    def test_simulation_buy_hold_matches_closed_form(self):
        returns = pd.DataFrame({"A": [.01] * 4, "B": [0.] * 4})
        for model in ("gaussian", "gaussian_uncertain", "block_bootstrap"):
            with self.subTest(model=model):
                paths = simulate_portfolio(returns, self.weights, trading_days=30, num_simulations=5,
                                           model=model, block_length=2, seed=42, rebalancing="buy_hold")
                np.testing.assert_allclose(paths[:, -1], 500 * 1.01**30 + 500)

    def test_contribution_purchases_are_net_of_costs_even_when_buy_and_hold(self):
        paths, costs = simulate_portfolio(pd.DataFrame({"A": [0., 0.]}), {"A": 1},
                                         trading_days=42, num_simulations=4, monthly_contribution=100,
                                         rebalancing="buy_hold", trading_cost_bps=100, return_costs=True)
        np.testing.assert_allclose(paths[:, -1], 1000 + 200 / 1.01)
        np.testing.assert_allclose(costs, 200 - 200 / 1.01)

    def test_zero_initial_capital_with_threshold_is_finite(self):
        paths, costs = simulate_portfolio(pd.DataFrame({"A": [0., 0.], "B": [0., 0.]}), self.weights,
                                         initial_value=0, trading_days=21, num_simulations=3,
                                         monthly_contribution=100, rebalancing="threshold", return_costs=True)
        np.testing.assert_allclose(paths[:, :21], 0)
        np.testing.assert_allclose(paths[:, -1], 100)
        np.testing.assert_allclose(costs, 0)

    def test_benchmark_is_untraded_and_shared_dates_preserved(self):
        prices = self.prices.assign(VTI=[100., 110., 120.])
        result = compare_benchmark(prices, self.weights, "VTI", trading_cost_bps=100)
        self.assertAlmostEqual(result["portfolio"]["trading_costs"], 8.7375)
        self.assertEqual(result["benchmark"]["trading_costs"], 0)
        self.assertAlmostEqual(result["benchmark"]["ending_value"], 1200)
        self.assertEqual(result["benchmark"]["rebalancing"], "buy_hold")

    def test_constant_inflation_deflator(self):
        factors = inflation_factors(.03, 504)
        self.assertAlmostEqual(factors[0], 1)
        self.assertAlmostEqual(factors[252], 1.03)
        self.assertAlmostEqual(factors[504], 1.03**2)

    @patch("backend.api.fetch_daily_returns")
    def test_api_real_bands_and_nominal_risk(self, fetch):
        fetch.return_value = pd.DataFrame({"A": [0., 0.], "B": [0., 0.]})
        payload = {"tickers": ["A", "B"], "weights": self.weights, "start": "2025-01-01",
                   "end": "2026-01-01", "trading_days": 252, "num_simulations": 4,
                   "annual_inflation": .04, "trading_cost_bps": 100,
                   "rebalancing": "buy_hold", "monthly_contribution": 100, "seed": 42}
        response = TestClient(app).post("/api/simulate", json=payload)
        self.assertEqual(response.status_code, 200)
        result = response.json()
        nominal = 1000 + 1200 / 1.01
        self.assertAlmostEqual(result["percentiles"][-1]["median"], nominal)
        self.assertAlmostEqual(result["real_percentiles"][-1]["median"], nominal / 1.04)
        self.assertAlmostEqual(result["median_trading_costs"], 1200 - 1200 / 1.01)
        self.assertEqual(result["simulation_risk"]["total_invested"], 2200)
        self.assertEqual(result["simulation_risk"]["probability_of_loss"], 1)

    @patch("backend.api.fetch_daily_returns")
    def test_comparison_same_policy_and_shocks(self, fetch):
        fetch.return_value = pd.DataFrame({"A": [.02, -.01, .03], "B": [.01, .02, -.01]})
        payload = {"tickers": ["A", "B"], "weights": self.weights, "comparison_weights": self.weights,
                   "start": "2025-01-01", "end": "2026-01-01", "trading_days": 42,
                   "num_simulations": 10, "rebalancing": "threshold", "rebalance_threshold": .01,
                   "trading_cost_bps": 20, "annual_inflation": .03, "seed": 42}
        response = TestClient(app).post("/api/compare", json=payload)
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result["portfolio_a"]["ending_values"], result["portfolio_b"]["ending_values"])
        self.assertEqual(result["portfolio_a"]["real_percentiles"], result["portfolio_b"]["real_percentiles"])

    @patch("backend.api.fetch_historical_prices")
    def test_historical_endpoints_apply_policy(self, fetch):
        client = TestClient(app)
        payload = {"tickers": ["A", "B"], "weights": self.weights,
                   "start": "2025-01-01", "end": "2026-01-01",
                   "trading_cost_bps": 100, "rebalancing": "daily"}
        fetch.return_value = self.prices
        backtest = client.post("/api/backtest", json=payload)
        self.assertEqual(backtest.status_code, 200)
        self.assertAlmostEqual(backtest.json()["ending_value"], 1117.5125)
        fetch.return_value = self.prices.assign(VTI=[100., 110., 120.])
        benchmark = client.post("/api/benchmark", json={**payload, "benchmark": "VTI"})
        self.assertEqual(benchmark.status_code, 200)
        self.assertAlmostEqual(benchmark.json()["portfolio"]["trading_costs"], 8.7375)
        self.assertEqual(benchmark.json()["benchmark"]["trading_costs"], 0)

    @patch("backend.api.fetch_daily_returns")
    def test_api_validation_rejects_invalid_trading_assumptions_before_fetch(self, fetch):
        payload = {"tickers": ["A", "B"], "weights": self.weights,
                   "start": "2025-01-01", "end": "2026-01-01"}
        for settings in ({"rebalancing": "invalid"}, {"trading_cost_bps": -1},
                         {"rebalance_threshold": 0}, {"annual_inflation": .3}):
            with self.subTest(settings=settings):
                result = TestClient(app).post("/api/simulate", json={**payload, **settings})
                self.assertEqual(result.status_code, 422)
        fetch.assert_not_called()

    def test_invalid_policy_rejected(self):
        for settings in ({"rebalancing": "never"}, {"trading_cost_bps": -1},
                         {"trading_cost_bps": 501}, {"rebalance_threshold": 0},
                         {"rebalance_threshold": float("nan")}):
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                backtest_portfolio(self.prices, self.weights, **settings)
        with self.assertRaises(ValueError):
            inflation_factors(-1, 252)
