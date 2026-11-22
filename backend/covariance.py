"""Measure how historical asset returns move together."""

import numpy as np

from .portfolio_metrics import (
    TRADING_DAYS,
    validate_periods_per_year,
    validate_returns,
    validate_weights,
)


def calculate_covariance_matrix(
    returns,
    periods_per_year=TRADING_DAYS
):
    """Calculate the annualized sample covariance matrix."""

    validate_periods_per_year(periods_per_year)
    returns = validate_returns(returns)

    covariance = returns.cov(ddof=1) * periods_per_year

    if not np.isfinite(covariance.to_numpy()).all():
        raise ValueError(
            "Covariance matrix contains non-finite values."
        )

    return covariance


def calculate_correlation_matrix(returns):
    """Calculate Pearson correlations between assets."""

    returns = validate_returns(returns)

    return returns.corr(method="pearson")


def calculate_portfolio_variance(
    returns,
    weights,
    periods_per_year=TRADING_DAYS
):
    """Calculate annualized portfolio variance."""

    covariance = calculate_covariance_matrix(
        returns,
        periods_per_year
    )

    weights = validate_weights(
        weights,
        covariance.columns
    ).to_numpy()

    variance = float(
        weights @ covariance.to_numpy() @ weights
    )

    if not np.isfinite(variance):
        raise ValueError("Portfolio variance is not finite.")

    # Prevent tiny negative values caused by rounding.
    return max(0.0, variance)


def calculate_portfolio_volatility(
    returns,
    weights,
    periods_per_year=TRADING_DAYS
):
    """Calculate portfolio volatility from covariance."""

    variance = calculate_portfolio_variance(
        returns,
        weights,
        periods_per_year
    )

    return float(np.sqrt(variance))