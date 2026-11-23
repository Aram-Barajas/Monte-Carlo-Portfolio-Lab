"""Shared self-financing portfolio evolution and trading assumptions."""

from numbers import Real

import numpy as np

from .portfolio_metrics import TRADING_DAYS


REBALANCE_INTERVALS = {"daily": 1, "monthly": 21, "quarterly": 63, "annual": 252}
REBALANCE_POLICIES = (*REBALANCE_INTERVALS, "buy_hold", "threshold")


def validate_policy(rebalancing, trading_cost_bps, rebalance_threshold):
    if rebalancing not in REBALANCE_POLICIES:
        raise ValueError("Unknown rebalancing policy.")
    for name, value, low, high in (
        ("Trading cost (basis points)", trading_cost_bps, 0, 500),
        ("Rebalance threshold", rebalance_threshold, 0.001, 1),
    ):
        if isinstance(value, bool) or not isinstance(value, Real) or not np.isfinite(value) or not low <= value <= high:
            raise ValueError(f"{name} must be between {low} and {high}.")


class PortfolioTracker:
    """Track dollar holdings across paths; contributions are invested at target weights."""

    def __init__(self, weights, initial_value, count, *, rebalancing="daily",
                 trading_cost_bps=0, rebalance_threshold=.05):
        validate_policy(rebalancing, trading_cost_bps, rebalance_threshold)
        self.weights = np.asarray(weights, dtype=float)
        self.rebalancing = rebalancing
        self.cost_rate = trading_cost_bps / 10000
        self.threshold = rebalance_threshold
        self.values = np.full(count, initial_value, dtype=float)
        self.costs = np.zeros(count, dtype=float)
        self.holdings = np.tile(initial_value * self.weights, (count, 1))

    def advance(self, gross_returns, day, contribution=0):
        """Apply market returns, purchase contributions, then rebalance if due."""
        if self.rebalancing == "daily" and self.cost_rate == 0:
            # Preserve the original fast fixed-weight behavior with zero costs.
            self.values = self.values * (gross_returns @ self.weights) + contribution
            # Maintain the same self-financing holdings invariant as the general path.
            self.holdings = self.values[:, None] * self.weights
            return self.values

        self.holdings *= gross_returns
        if contribution:
            invested = contribution / (1 + self.cost_rate)
            self.costs += contribution - invested
            self.holdings += invested * self.weights

        values = self.holdings.sum(axis=1)
        if self.rebalancing == "threshold":
            current = np.divide(self.holdings, values[:, None],
                                out=np.zeros_like(self.holdings), where=values[:, None] > 0)
            due = (values > 0) & (np.abs(current - self.weights).max(axis=1) >= self.threshold)
        else:
            interval = REBALANCE_INTERVALS.get(self.rebalancing)
            due = np.full(len(values), interval is not None and day % interval == 0)

        if due.any():
            before = values[due]
            holdings = self.holdings[due]
            # Pay a per-side cost on actual traded notional. Solve
            # fee = rate * sum(abs(target * (before - fee) - holdings)).
            # The map is a contraction (rate <= .05); 12 updates give
            # relative error below floating-point precision.
            fee = np.zeros_like(before)
            if self.cost_rate:
                for _ in range(12):
                    fee = self.cost_rate * np.abs((before - fee)[:, None] * self.weights - holdings).sum(axis=1)
            after = before - fee
            self.holdings[due] = after[:, None] * self.weights
            self.costs[due] += fee
            values[due] = after

        self.values = values
        return values


def inflation_factors(annual_inflation, trading_days):
    """Return constant-inflation deflators, relative to day zero."""
    if (isinstance(annual_inflation, bool) or not isinstance(annual_inflation, Real)
            or not np.isfinite(annual_inflation) or not -.05 <= annual_inflation <= .25):
        raise ValueError("Annual inflation must be between -5% and 25%.")
    return (1 + annual_inflation) ** (np.arange(trading_days + 1) / TRADING_DAYS)
