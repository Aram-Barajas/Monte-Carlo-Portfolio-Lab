"""Historical return and volatility calculations for long-only portfolios."""

from collections.abc import Mapping
from numbers import Integral, Real

import numpy as np
import pandas as pd


TRADING_DAYS = 252


def validate_returns(returns):
    """Validate historical fractional returns."""

    if not isinstance(returns, pd.DataFrame) or returns.empty:
        raise ValueError(
            "Expected a non-empty DataFrame of asset returns."
        )

    if len(returns) < 2:
        raise ValueError(
            "At least two return observations are required."
        )

    if returns.columns.has_duplicates or returns.index.has_duplicates:
        raise ValueError(
            "Return data contains duplicate columns or dates."
        )

    values = returns.apply(
        pd.to_numeric,
        errors="raise"
    ).astype(float)

    if not np.isfinite(values.to_numpy()).all():
        raise ValueError(
            "Returns must be finite and contain no missing values."
        )

    if (values < -1).any().any():
        raise ValueError(
            "Simple returns cannot be less than -100%."
        )

    return values


def validate_weights(weights, tickers):
    """Validate portfolio allocation weights."""

    if not isinstance(weights, Mapping) or set(weights) != set(tickers):
        raise ValueError(
            "Weights must match the return data's ticker symbols."
        )

    if any(
        isinstance(weight, bool) or not isinstance(weight, Real)
        for weight in weights.values()
    ):
        raise ValueError("Weights must be numeric.")

    ordered = pd.Series(
        weights,
        dtype=float
    ).reindex(tickers)

    if not np.isfinite(ordered.to_numpy()).all() or (ordered < 0).any():
        raise ValueError(
            "Weights must be finite and nonnegative."
        )

    if not np.isclose(
        ordered.sum(),
        1.0,
        rtol=0,
        atol=1e-8
    ):
        raise ValueError(
            "Portfolio weights must sum to 1.0 (100%)."
        )

    return ordered


def validate_periods_per_year(periods_per_year):

    if (
        isinstance(periods_per_year, bool)
        or not isinstance(periods_per_year, Integral)
        or periods_per_year <= 0
    ):
        raise ValueError(
            "Periods per year must be a positive integer."
        )


def calculate_asset_metrics(
    returns,
    periods_per_year=TRADING_DAYS
):
    """Calculate annualized return and volatility for each asset."""

    validate_periods_per_year(periods_per_year)
    returns = validate_returns(returns)

    return pd.DataFrame({
        "annualized_return":
            returns.mean() * periods_per_year,

        "annualized_volatility":
            returns.std(ddof=1) * np.sqrt(periods_per_year)
    })


def calculate_portfolio_returns(returns, weights):
    """Calculate daily returns assuming daily rebalancing."""

    returns = validate_returns(returns)
    weights = validate_weights(weights, returns.columns)

    return returns.dot(weights).rename("portfolio")


def calculate_portfolio_metrics(
    returns,
    weights,
    periods_per_year=TRADING_DAYS
):
    """Calculate annualized portfolio return and volatility."""

    validate_periods_per_year(periods_per_year)

    portfolio = calculate_portfolio_returns(
        returns,
        weights
    )

    return {
        "annualized_return":
            float(portfolio.mean() * periods_per_year),

        "annualized_volatility":
            float(portfolio.std(ddof=1) * np.sqrt(periods_per_year))
    }