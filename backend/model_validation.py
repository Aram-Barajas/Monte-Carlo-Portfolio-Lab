"""Chronological, out-of-sample evaluation of simulated terminal distributions."""

from numbers import Integral, Real
from secrets import randbits

import numpy as np
import pandas as pd

from .monte_carlo import SIMULATION_MODELS, simulate_portfolio
from .portfolio_metrics import calculate_portfolio_returns, validate_returns, validate_weights


MAX_VALIDATION_DRAWS = 20_000_000


def score_forecast(samples, actual):
    """Score an empirical terminal-return distribution against one realization."""
    samples = np.asarray(samples, dtype=float)
    if (samples.ndim != 1 or not samples.size or not np.isfinite(samples).all()
            or not np.isfinite(actual)):
        raise ValueError("Forecast and actual returns must be finite.")
    p05, p25, median, p75, p95 = np.percentile(samples, [5, 25, 50, 75, 95])
    ordered = np.sort(samples)
    count = len(ordered)
    # E|X-y| - 1/2 E|X-X'|, with the pairwise term evaluated by sorting.
    with np.errstate(over="ignore", invalid="ignore"):
        pair_term = np.dot((2 * np.arange(count) + 1 - count) / count, ordered) / count
        crps = np.mean(np.abs(samples - actual)) - pair_term
        probability_loss = float(np.mean(samples < 0))
        pit = (np.sum(samples < actual) + .5 * np.sum(samples == actual)) / count
        result = {
            "p05": float(p05), "p25": float(p25), "median": float(median),
            "p75": float(p75), "p95": float(p95),
            "inside_50": bool(p25 <= actual <= p75),
            "inside_90": bool(p05 <= actual <= p95),
            "below_05": bool(actual < p05), "above_95": bool(actual > p95),
            "absolute_error": float(abs(median - actual)),
            "median_error": float(median - actual),
            "width_90": float(p95 - p05),
            "crps": float(max(0., crps)),
            "probability_loss": probability_loss,
            "brier_loss": float((probability_loss - (actual < 0)) ** 2),
            "pit": float(pit),
        }
    if not np.isfinite(crps) or not all(np.isfinite(value) for value in result.values()):
        raise ValueError("Forecast scores exceeded numerical limits.")
    return result


def _summarize(scores):
    # Wilson reference interval assumes independent Bernoulli folds. This is
    # descriptive only: market regimes and adjacent folds may be dependent.
    n = len(scores)
    successes = sum(row["inside_90"] for row in scores)
    p = successes / n
    z = 1.96
    denominator = 1 + z*z/n
    center = (p + z*z/(2*n)) / denominator
    spread = z * np.sqrt(p*(1-p)/n + z*z/(4*n*n)) / denominator
    def average(key):
        return float(np.mean([row[key] for row in scores]))
    histogram, _ = np.histogram([row["pit"] for row in scores], bins=np.linspace(0, 1, 11))
    summary = {
        "coverage_50": average("inside_50"), "coverage_90": average("inside_90"),
        "coverage_90_wilson_reference": [float(max(0., center-spread)), float(min(1., center+spread))],
        "below_05": sum(row["below_05"] for row in scores),
        "above_95": sum(row["above_95"] for row in scores),
        "mean_absolute_error": average("absolute_error"),
        "median_bias": average("median_error"),
        "mean_width_90": average("width_90"),
        "mean_crps": average("crps"), "mean_brier_loss": average("brier_loss"),
        "pit_histogram": histogram.tolist(),
    }
    if not all(np.isfinite(v) for k, v in summary.items()
               if k not in ("pit_histogram", "coverage_90_wilson_reference")):
        raise ValueError("Aggregate forecast scores exceeded numerical limits.")
    return summary


def validate_models(returns, weights, *, training_days=252, forecast_days=21,
                    max_folds=12, num_simulations=500, drift_weight=1.,
                    block_length=21, seed=None):
    """Run fixed-length training windows and disjoint subsequent test windows."""
    for name, value, low, high in (
        ("Training days", training_days, 63, 1260),
        ("Forecast days", forecast_days, 5, 252),
        ("Maximum folds", max_folds, 3, 24),
        ("Paths per forecast", num_simulations, 100, 1000),
        ("Block length", block_length, 1, 252),
    ):
        if isinstance(value, bool) or not isinstance(value, Integral) or not low <= value <= high:
            raise ValueError(f"{name} must be an integer from {low} to {high}.")
    if block_length > training_days:
        raise ValueError("Block length cannot exceed the training window.")
    if (isinstance(drift_weight, bool) or not isinstance(drift_weight, Real)
            or not np.isfinite(drift_weight) or not 0 <= drift_weight <= 1):
        raise ValueError("Drift weight must be between 0 and 1.")
    if seed is not None and (isinstance(seed, bool) or not isinstance(seed, Integral) or not 0 <= seed <= 2**32 - 1):
        raise ValueError("Seed must be a nonnegative 32-bit integer.")
    returns = validate_returns(returns)
    if not isinstance(returns.index, pd.DatetimeIndex) or returns.index.hasnans:
        raise ValueError("Model validation requires dated historical returns.")
    returns = returns.sort_index()
    weights = validate_weights(weights, returns.columns).to_dict()
    if max_folds * num_simulations * forecast_days * len(weights) * len(SIMULATION_MODELS) > MAX_VALIDATION_DRAWS:
        raise ValueError("Validation is too large. Reduce folds, forecast days, paths, or assets.")
    folds = min(max_folds, (len(returns) - training_days) // forecast_days)
    if folds < 3:
        raise ValueError("Choose more historical data or shorter windows: at least three complete forecast folds are required.")
    seed = randbits(32) if seed is None else int(seed)
    # Use reproducible, independent seeds for successive forecasts.
    seeds = np.random.SeedSequence(seed).generate_state(folds)
    results = []
    first_test = len(returns) - folds * forecast_days
    for fold in range(folds):
        start = first_test + fold * forecast_days
        training = returns.iloc[start - training_days:start]
        testing = returns.iloc[start:start + forecast_days]
        daily = calculate_portfolio_returns(testing, weights)
        with np.errstate(over="ignore", invalid="ignore"):
            actual = float(np.prod(1 + daily.to_numpy()) - 1)
        if not np.isfinite(actual):
            raise ValueError("Actual return exceeded numerical limits.")
        forecasts = {}
        for model in SIMULATION_MODELS:
            paths = simulate_portfolio(
                training, weights, initial_value=1., trading_days=forecast_days,
                num_simulations=num_simulations, model=model, seed=int(seeds[fold]),
                drift_weight=drift_weight, block_length=block_length, record_every=forecast_days,
            )
            forecasts[model] = score_forecast(paths[:, -1] - 1., actual)
        results.append({
            "fold": fold + 1, "training_start": training.index[0].strftime("%Y-%m-%d"),
            "training_end": training.index[-1].strftime("%Y-%m-%d"),
            "forecast_start": testing.index[0].strftime("%Y-%m-%d"),
            "forecast_end": testing.index[-1].strftime("%Y-%m-%d"),
            "actual_return": actual, "models": forecasts,
        })
    return {
        "weights": weights, "observations": len(returns), "training_days": training_days,
        "forecast_days": forecast_days, "max_folds": max_folds, "fold_count": folds,
        "num_simulations": num_simulations, "seed": seed, "drift_weight": drift_weight,
        "block_length": block_length,
        "models": {model: _summarize([row["models"][model] for row in results])
                   for model in SIMULATION_MODELS},
        "folds": results,
    }
