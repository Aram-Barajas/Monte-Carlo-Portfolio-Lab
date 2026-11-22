"""Simulate daily rebalanced portfolios using correlated log returns."""

from numbers import Integral, Real

import numpy as np
import pandas as pd

from .portfolio_metrics import (
    TRADING_DAYS,
    validate_returns,
    validate_weights
)


DAYS_PER_MONTH = 21
MAX_PATH_VALUES = 30_000_000
MAX_RANDOM_DRAWS = 200_000_000


def estimate_log_return_parameters(returns):
    """Estimate daily log-return means and covariance."""

    returns = validate_returns(returns)

    if (returns <= -1).any().any():
        raise ValueError(
            "Log-return modeling requires returns greater than -100%."
        )

    log_returns = np.log1p(returns)

    return (
        log_returns.mean(),
        log_returns.cov(ddof=1)
    )


def simulate_portfolio(
    returns,
    weights,
    initial_value=1000,
    trading_days=TRADING_DAYS,
    num_simulations=1000,
    monthly_contribution=0,
    seed=None
):
    """Generate simulated portfolio value trajectories."""

    # Validate monetary inputs.
    for name, value in (
        ("initial_value", initial_value),
        ("monthly_contribution", monthly_contribution)
    ):
        if (
            isinstance(value, bool)
            or not isinstance(value, Real)
            or not np.isfinite(value)
            or value < 0
        ):
            raise ValueError(
                f"{name} must be finite and nonnegative."
            )

    # Validate simulation parameters.
    for name, value in (
        ("trading_days", trading_days),
        ("num_simulations", num_simulations)
    ):
        if (
            isinstance(value, bool)
            or not isinstance(value, Integral)
            or value <= 0
        ):
            raise ValueError(
                f"{name} must be a positive integer."
            )

    if seed is not None and (
        isinstance(seed, bool)
        or not isinstance(seed, Integral)
        or seed < 0
    ):
        raise ValueError(
            "seed must be a nonnegative integer or None."
        )

    # Estimate historical return parameters.
    means, covariance = estimate_log_return_parameters(
        returns
    )

    weights = validate_weights(
        weights,
        means.index
    ).to_numpy()

    trading_days = int(trading_days)
    num_simulations = int(num_simulations)

    # Prevent excessively large simulations.
    if (
        num_simulations * (trading_days + 1)
        > MAX_PATH_VALUES

        or num_simulations * trading_days * len(weights)
        > MAX_RANDOM_DRAWS
    ):
        raise ValueError(
            "Simulation is too large. Reduce paths, days, or assets."
        )

    # Decompose the covariance matrix.
    eigenvalues, eigenvectors = np.linalg.eigh(
        covariance.to_numpy()
    )

    factor = eigenvectors * np.sqrt(
        np.maximum(eigenvalues, 0.0)
    )

    # Initialize the random number generator.
    rng = np.random.default_rng(seed)

    # Store portfolio values for every simulation.
    paths = np.empty(
        (num_simulations, trading_days + 1)
    )

    paths[:, 0] = initial_value
    means = means.to_numpy()

    try:
        with np.errstate(over="raise", invalid="raise"):

            for day in range(1, trading_days + 1):

                random_shocks = rng.standard_normal(
                    (num_simulations, len(weights))
                )

                log_returns = (
                    means + random_shocks @ factor.T
                )

                gross_returns = (
                    np.exp(log_returns) @ weights
                )

                paths[:, day] = (
                    paths[:, day - 1] * gross_returns
                )

                # Add contributions approximately monthly.
                if day % DAYS_PER_MONTH == 0:
                    paths[:, day] += monthly_contribution

    except FloatingPointError as error:
        raise ValueError(
            "Simulation values exceeded numerical limits."
        ) from error

    if not np.isfinite(paths).all():
        raise ValueError(
            "Simulation produced non-finite values."
        )

    return paths


def summarize_simulations(paths):
    """Calculate percentile bands for every trading day."""

    paths = np.asarray(paths, dtype=float)

    if (
        paths.ndim != 2
        or paths.shape[0] == 0
        or paths.shape[1] == 0
    ):
        raise ValueError(
            "Expected a non-empty two-dimensional array of paths."
        )

    if not np.isfinite(paths).all() or (paths < 0).any():
        raise ValueError(
            "Paths must contain finite, nonnegative values."
        )

    bands = np.percentile(
        paths,
        [5, 25, 50, 75, 95],
        axis=0
    ).T

    return pd.DataFrame(
        bands,
        index=pd.Index(
            range(paths.shape[1]),
            name="trading_day"
        ),
        columns=[
            "p05",
            "p25",
            "median",
            "p75",
            "p95"
        ]
    )