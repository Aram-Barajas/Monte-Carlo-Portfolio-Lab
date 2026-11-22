"""Replay historical returns for a fixed-weight portfolio."""

from numbers import Real

import numpy as np
import pandas as pd

from .market_data import (
    _validate_prices,
    calculate_daily_returns
)

from .portfolio_metrics import (
    TRADING_DAYS,
    calculate_portfolio_returns
)

from .risk_metrics import calculate_historical_risk


def backtest_portfolio(
    prices,
    weights,
    initial_value=1000,
    confidence=0.95,
    annual_risk_free_rate=0.0
):
    """Backtest a daily rebalanced portfolio without cash flows."""

    if (
        isinstance(initial_value, bool)
        or not isinstance(initial_value, Real)
        or not np.isfinite(initial_value)
        or initial_value <= 0
    ):
        raise ValueError(
            "Initial value must be positive and finite."
        )

    prices = _validate_prices(prices)

    # Find the overlapping historical period.
    start = max(
        prices[column].first_valid_index()
        for column in prices
    )

    end = min(
        prices[column].last_valid_index()
        for column in prices
    )

    prices = prices.loc[start:end]

    if len(prices) < 3:
        raise ValueError(
            "At least three overlapping price dates are required."
        )

    if prices.isna().any().any():
        raise ValueError(
            "Backtest price history contains missing prices."
        )

    returns = calculate_daily_returns(prices)

    portfolio = calculate_portfolio_returns(
        returns,
        weights
    )

    try:
        with np.errstate(
            over="raise",
            invalid="raise",
            divide="raise"
        ):
            # Calculate cumulative portfolio growth.
            growth = np.concatenate((
                [1.0],
                np.cumprod(
                    1 + portfolio.to_numpy()
                )
            ))

            values = initial_value * growth

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
        returns,
        weights,
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

        "trajectory": trajectory
    }