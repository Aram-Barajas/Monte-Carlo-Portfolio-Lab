"""Historical portfolio risk and downside risk of simulated outcomes."""

from numbers import Real

import numpy as np

from .monte_carlo import DAYS_PER_MONTH

from .portfolio_metrics import (
    TRADING_DAYS,
    calculate_portfolio_returns,
    validate_periods_per_year
)


def calculate_loss_metrics(losses, confidence=0.95):
    """Calculate empirical VaR and expected shortfall."""

    if (
        isinstance(confidence, bool)
        or not isinstance(confidence, Real)
        or not 0 < confidence < 1
    ):
        raise ValueError(
            "Confidence must be between 0 and 1 (exclusive)."
        )

    losses = np.asarray(losses, dtype=float)

    if (
        losses.ndim != 1
        or losses.size == 0
        or not np.isfinite(losses).all()
    ):
        raise ValueError(
            "Expected a non-empty array of finite losses."
        )

    var = np.quantile(
        losses,
        confidence,
        method="inverted_cdf"
    )

    # Sort losses from largest to smallest.
    worst = np.sort(losses)[::-1]

    tail_size = (1 - confidence) * len(worst)

    whole = int(tail_size)
    fraction = tail_size - whole

    total = worst[:whole].sum()

    if fraction > 0:
        total += fraction * worst[whole]

    return {
        "value_at_risk": float(var),

        "expected_shortfall":
            float(total / tail_size)
    }


def calculate_historical_risk(
    returns,
    weights,
    confidence=0.95,
    annual_risk_free_rate=0.0,
    periods_per_year=TRADING_DAYS
):
    """Calculate risk metrics using historical portfolio returns."""

    validate_periods_per_year(periods_per_year)

    if (
        isinstance(annual_risk_free_rate, bool)
        or not isinstance(annual_risk_free_rate, Real)
        or not np.isfinite(annual_risk_free_rate)
    ):
        raise ValueError(
            "Annual risk-free rate must be a finite number."
        )

    portfolio = calculate_portfolio_returns(
        returns,
        weights
    ).sort_index()

    risk = calculate_loss_metrics(
        -portfolio.to_numpy(),
        confidence
    )

    # Annualized return and volatility.
    annual_return = (
        portfolio.mean() * periods_per_year
    )

    annual_volatility = (
        portfolio.std(ddof=1)
        * np.sqrt(periods_per_year)
    )

    # Calculate Sharpe ratio.
    sharpe = None

    if annual_volatility > 1e-12:
        sharpe = float(
            (annual_return - annual_risk_free_rate)
            / annual_volatility
        )

    # Calculate historical cumulative wealth.
    wealth = np.concatenate((
        [1.0],
        np.cumprod(1 + portfolio.to_numpy())
    ))

    if not np.isfinite(wealth).all():
        raise ValueError(
            "Historical wealth exceeded numerical limits."
        )

    # Calculate maximum drawdown.
    peaks = np.maximum.accumulate(wealth)

    drawdowns = 1 - wealth / peaks

    return {
        "confidence": float(confidence),

        "daily_var":
            risk["value_at_risk"],

        "daily_expected_shortfall":
            risk["expected_shortfall"],

        "max_drawdown":
            float(drawdowns.max()),

        "sharpe_ratio": sharpe
    }


def calculate_simulation_risk(
    paths,
    monthly_contribution=0,
    confidence=0.95
):
    """Calculate downside risk from simulated portfolio outcomes."""

    if (
        isinstance(monthly_contribution, bool)
        or not isinstance(monthly_contribution, Real)
        or not np.isfinite(monthly_contribution)
        or monthly_contribution < 0
    ):
        raise ValueError(
            "Monthly contribution must be finite and nonnegative."
        )

    paths = np.asarray(paths, dtype=float)

    if (
        paths.ndim != 2
        or paths.shape[0] == 0
        or paths.shape[1] < 2
    ):
        raise ValueError(
            "Expected simulation paths with an initial and final value."
        )

    if (
        not np.isfinite(paths).all()
        or (paths < 0).any()
    ):
        raise ValueError(
            "Paths must contain finite, nonnegative values."
        )

    if not (paths[:, 0] == paths[0, 0]).all():
        raise ValueError(
            "All paths must have the same initial value."
        )

    trading_days = paths.shape[1] - 1

    total_invested = (
        paths[0, 0]
        + (trading_days // DAYS_PER_MONTH)
        * monthly_contribution
    )

    if not np.isfinite(total_invested):
        raise ValueError(
            "Total invested capital exceeded numerical limits."
        )

    ending_values = paths[:, -1]

    # Compare outcomes against total contributed capital.
    losses = total_invested - ending_values

    losses[
        np.isclose(losses, 0, atol=1e-8, rtol=0)
    ] = 0

    risk = calculate_loss_metrics(
        losses,
        confidence
    )

    return {
        "confidence": float(confidence),

        "total_invested":
            float(total_invested),

        "mean_ending_value":
            float(ending_values.mean()),

        "median_ending_value":
            float(np.median(ending_values)),

        "probability_of_loss":
            float((losses > 0).mean()),

        "terminal_var":
            risk["value_at_risk"],

        "terminal_expected_shortfall":
            risk["expected_shortfall"]
    }