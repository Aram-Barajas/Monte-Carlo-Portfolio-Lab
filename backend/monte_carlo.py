"""Simulate portfolios using correlated log returns and trading policies."""

from numbers import Integral, Real

import numpy as np
import pandas as pd

from .portfolio_metrics import (
    TRADING_DAYS,
    validate_returns,
    validate_weights
)
from .portfolio_policy import PortfolioTracker, validate_policy


DAYS_PER_MONTH = 21
MAX_PATH_VALUES = 30_000_000
MAX_RANDOM_DRAWS = 200_000_000
SIMULATION_MODELS = ("gaussian", "gaussian_uncertain", "block_bootstrap")


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
    seed=None,
    *,
    model="gaussian",
    block_length=5,
    drift_weight=1.0,
    rebalancing="daily",
    trading_cost_bps=0,
    rebalance_threshold=.05,
    return_costs=False,
    record_every=1
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

    if model not in SIMULATION_MODELS:
        raise ValueError("Unknown simulation model.")
    if (isinstance(block_length, bool) or not isinstance(block_length, Integral)
            or not 1 <= block_length <= 252):
        raise ValueError("Block length must be an integer from 1 to 252.")
    if (isinstance(drift_weight, bool) or not isinstance(drift_weight, Real)
            or not np.isfinite(drift_weight) or not 0 <= drift_weight <= 1):
        raise ValueError("Drift weight must be between 0 and 1.")

    validate_policy(rebalancing, trading_cost_bps, rebalance_threshold)
    if (isinstance(record_every, bool) or not isinstance(record_every, Integral)
            or not 1 <= record_every <= trading_days):
        raise ValueError("Recording interval must be an integer within the simulation horizon.")

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
    record_count = 1 + (trading_days + record_every - 1) // record_every
    if (
        num_simulations * record_count
        > MAX_PATH_VALUES

        or num_simulations * trading_days * len(weights)
        > MAX_RANDOM_DRAWS
    ):
        raise ValueError(
            "Simulation is too large. Reduce paths, days, or assets."
        )

    # Initialize the random number generator.
    rng = np.random.default_rng(seed)

    historical_mean = means.to_numpy()
    drift = drift_weight * historical_mean
    if model == "block_bootstrap":
        if not returns.index.is_monotonic_increasing:
            raise ValueError("Bootstrap returns must be in chronological order.")
        if block_length > len(returns):
            raise ValueError("Block length exceeds available historical returns. Choose a shorter block or longer history.")
        log_history = np.log1p(returns.to_numpy(dtype=float))
        # Shrink mean log return toward zero without changing joint deviations.
        log_history = log_history + (drift - historical_mean)
    else:
        eigenvalues, eigenvectors = np.linalg.eigh(covariance.to_numpy())
        factor = eigenvectors * np.sqrt(np.maximum(eigenvalues, 0.0))
        if model == "gaussian_uncertain":
            # Draw one uncertain mean per path, held fixed for the entire horizon.
            # Under the IID Gaussian assumption, Cov(sample mean) = Sigma/n.
            # Shrinking the point estimate toward zero does NOT reduce the
            # amount of estimation noise in that historical sample.
            drift = drift + (1.0 / np.sqrt(len(returns))) * (
                rng.standard_normal((num_simulations, len(weights))) @ factor.T
            )

    # Store portfolio values for every simulation.
    paths = np.empty(
        (num_simulations, record_count)
    )

    paths[:, 0] = initial_value
    tracker = PortfolioTracker(weights, initial_value, num_simulations,
                               rebalancing=rebalancing, trading_cost_bps=trading_cost_bps,
                               rebalance_threshold=rebalance_threshold)
    recorded = 1
    try:
        with np.errstate(over="raise", invalid="raise"):

            for day in range(1, trading_days + 1):

                if model == "block_bootstrap":
                    offset = (day - 1) % block_length
                    if offset == 0:
                        starts = rng.integers(len(log_history), size=num_simulations)
                    # Sample whole rows together; circular blocks wrap at the end.
                    log_returns = log_history[(starts + offset) % len(log_history)]
                else:
                    random_shocks = rng.standard_normal((num_simulations, len(weights)))
                    log_returns = drift + random_shocks @ factor.T

                values = tracker.advance(
                    np.exp(log_returns), day,
                    monthly_contribution if day % DAYS_PER_MONTH == 0 else 0
                )
                if day % record_every == 0 or day == trading_days:
                    paths[:, recorded] = values
                    recorded += 1

    except FloatingPointError as error:
        raise ValueError(
            "Simulation values exceeded numerical limits."
        ) from error

    if not np.isfinite(paths).all() or not np.isfinite(tracker.costs).all():
        raise ValueError(
            "Simulation produced non-finite values."
        )

    return (paths, tracker.costs.copy()) if return_costs else paths


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
