"""Replay historical returns with configurable portfolio trading policies."""

from numbers import Real

import numpy as np
import pandas as pd

from .market_data import (
    align_price_history,
    calculate_daily_returns
)

from .portfolio_metrics import (
    TRADING_DAYS,
    validate_weights
)
from .portfolio_policy import PortfolioTracker

from .risk_metrics import calculate_historical_risk


def align_backtest_prices(prices):
    """Trim to common price dates and reject gaps within them."""
    return align_price_history(prices, minimum_dates=3)


def backtest_portfolio(
    prices,
    weights,
    initial_value=1000,
    confidence=0.95,
    annual_risk_free_rate=0.0,
    *,
    rebalancing="daily",
    trading_cost_bps=0,
    rebalance_threshold=.05
):
    """Backtest a portfolio without cash flows."""

    if (
        isinstance(initial_value, bool)
        or not isinstance(initial_value, Real)
        or not np.isfinite(initial_value)
        or initial_value <= 0
    ):
        raise ValueError(
            "Initial value must be positive and finite."
        )

    prices = align_backtest_prices(prices)

    returns = calculate_daily_returns(prices)

    ordered = validate_weights(weights, returns.columns).to_numpy()
    tracker = PortfolioTracker(ordered, initial_value, 1, rebalancing=rebalancing,
                               trading_cost_bps=trading_cost_bps,
                               rebalance_threshold=rebalance_threshold)

    try:
        with np.errstate(
            over="raise",
            invalid="raise",
            divide="raise"
        ):
            values = np.empty(len(returns) + 1)
            values[0] = initial_value
            for day, row in enumerate(returns.to_numpy(), start=1):
                values[day] = tracker.advance(1 + row, day)[0]
            growth = values / initial_value
            # All metrics use the realized path, net of charged trading costs.
            portfolio = pd.Series(values[1:] / values[:-1] - 1, index=returns.index)

            # Calculate historical drawdowns.
            peaks = np.maximum.accumulate(growth)

            drawdowns = 1 - growth / peaks

            # Calculate historical performance.
            total_return = growth[-1] - 1

            cagr = (
                growth[-1] **
                (TRADING_DAYS / len(portfolio))
                - 1
            )

            volatility = (
                portfolio.std(ddof=1) *
                np.sqrt(TRADING_DAYS)
            )

    except FloatingPointError as error:
        raise ValueError(
            "Backtest exceeded numerical limits."
        ) from error

    if (
        not np.isfinite(values).all()
        or not np.isfinite(
            [total_return, cagr, volatility]
        ).all()
    ):
        raise ValueError(
            "Backtest exceeded numerical limits."
        )

    risk = calculate_historical_risk(
        portfolio.to_frame("portfolio"),
        {"portfolio": 1.0},
        confidence,
        annual_risk_free_rate
    )

    if (
        risk["sharpe_ratio"] is not None
        and not np.isfinite(risk["sharpe_ratio"])
    ):
        raise ValueError(
            "Backtest exceeded numerical limits."
        )

    trajectory = pd.DataFrame(
        {
            "value": values,
            "drawdown": drawdowns
        },
        index=prices.index
    )

    return {
        "initial_value": float(initial_value),

        "ending_value": float(values[-1]),

        "total_return": float(total_return),

        "cagr": float(cagr),

        "annualized_volatility": float(volatility),

        "sharpe_ratio": risk["sharpe_ratio"],

        "max_drawdown": float(drawdowns.max()),

        "observations": len(portfolio),

        "rebalancing": rebalancing,
        "trading_cost_bps": trading_cost_bps,
        "rebalance_threshold": rebalance_threshold if rebalancing == "threshold" else None,
        "trading_costs": float(tracker.costs[0]),

        "trajectory": trajectory
    }
