"""Goal-based accumulation planning using common simulated market paths."""

from decimal import Decimal
from math import ceil
from numbers import Integral, Real
from secrets import randbits

import numpy as np

from .monte_carlo import DAYS_PER_MONTH, simulate_portfolio, SIMULATION_MODELS
from .portfolio_metrics import TRADING_DAYS


def _bounded(value, low, high, name):
    if (isinstance(value, bool) or not isinstance(value, Real)
            or not np.isfinite(value) or not low <= value <= high):
        raise ValueError(f"{name} must be between {low} and {high}.")


def evaluate_goal_paths(monthly_growth, *, initial_value, monthly_contribution,
                        contribution_growth, annual_inflation, goal, target_probability):
    """Evaluate monthly gross returns and solve the empirical goal threshold."""
    monthly_growth = np.asarray(monthly_growth, dtype=float)
    if (monthly_growth.ndim != 2 or not monthly_growth.size
            or monthly_growth.shape[1] % 12
            or not np.isfinite(monthly_growth).all() or (monthly_growth <= 0).any()):
        raise ValueError("Planning requires positive, finite growth for complete simulated years.")
    _bounded(initial_value, 0, 1e9, "Initial investment")
    _bounded(monthly_contribution, 0, 1e9, "Monthly contribution")
    _bounded(contribution_growth, -.1, .25, "Annual contribution growth")
    _bounded(annual_inflation, -.05, .25, "Annual inflation")
    _bounded(goal, .01, 1e9, "Goal")
    _bounded(target_probability, .5, .99, "Target probability")

    count, months = monthly_growth.shape
    years = months // 12
    initial = np.full(count, initial_value, dtype=float)
    contribution_factor = np.zeros(count)
    nominal_contributed = 0.0
    annual = []

    def snapshot(year):
        balance = initial + monthly_contribution * contribution_factor
        real = balance / (1 + annual_inflation) ** year
        if not np.isfinite(real).all():
            raise ValueError("Planning values exceeded numerical limits.")
        p05, median, p95 = np.percentile(real, [5, 50, 95])
        return {"year": year, "p05": float(p05), "median": float(median),
                "p95": float(p95), "goal_probability": float(np.mean(real >= goal)),
                "nominal_contributed": float(initial_value + nominal_contributed)}

    annual.append(snapshot(0))
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            for month in range(months):
                growth = monthly_growth[:, month]
                escalation = (1 + contribution_growth) ** (month // 12)
                # Contributions arrive after each month's returns.
                initial *= growth
                contribution_factor = contribution_factor * growth + escalation
                nominal_contributed += monthly_contribution * escalation
                if (month + 1) % 12 == 0:
                    annual.append(snapshot((month + 1) // 12))

            deflator = (1 + annual_inflation) ** years
            nominal_goal = goal * deflator
            required = np.maximum(0, (nominal_goal - initial) / contribution_factor)
            if not np.isfinite(required).all():
                raise ValueError("Required contribution exceeded numerical limits.")
            # Nearest-rank order statistic, not an interpolated percentile.
            rank = ceil(Decimal(str(target_probability)) * count) - 1
            starting_monthly_required = ceil(Decimal(str(np.sort(required)[rank])) * 100) / 100
            ending_real = (initial + monthly_contribution * contribution_factor) / deflator
            met = required <= monthly_contribution
            annual[-1]["goal_probability"] = float(met.mean())
            missed = np.maximum(0, goal - ending_real[~met])
            sensitivity_values = sorted(set([0., monthly_contribution / 2, monthly_contribution,
                                             monthly_contribution * 1.5, monthly_contribution * 2,
                                             starting_monthly_required]))
            sensitivity = [
                {"monthly_contribution": amount, "goal_probability": float(np.mean(required <= amount)),
                 "median_ending_real": float(np.median((initial + amount * contribution_factor) / deflator))}
                for amount in sensitivity_values
            ]
    except FloatingPointError as error:
        raise ValueError("Planning values exceeded numerical limits.") from error
    if not np.isfinite([nominal_goal, starting_monthly_required, nominal_contributed,
                        *[row["median_ending_real"] for row in sensitivity]]).all():
        raise ValueError("Planning values exceeded numerical limits.")
    return {
        "annual": annual, "nominal_goal": nominal_goal,
        "goal_probability": annual[-1]["goal_probability"],
        "required_monthly_contribution": starting_monthly_required,
        "required_contribution_probability": float(np.mean(required <= starting_monthly_required)),
        "median_shortfall_when_missed": float(np.median(missed)) if missed.size else None,
        "sensitivity": sensitivity,
    }


def plan_portfolio(returns, weights, *, years=20, num_simulations=500,
                   initial_value=1000, monthly_contribution=100, contribution_growth=0,
                   annual_inflation=.025, goal=100000, target_probability=.8,
                   model="gaussian_uncertain", drift_weight=.5, block_length=21, seed=None):
    """Generate monthly snapshots of fixed-weight daily market growth."""
    for name, value, low, high in (("Years", years, 1, 40), ("Paths", num_simulations, 1, 2000)):
        if isinstance(value, bool) or not isinstance(value, Integral) or not low <= value <= high:
            raise ValueError(f"{name} must be an integer from {low} to {high}.")
    if num_simulations * years * TRADING_DAYS * len(weights) > 20_000_000:
        raise ValueError("Planning simulation is too large. Reduce years, paths, or assets.")
    if model not in SIMULATION_MODELS:
        raise ValueError("Unknown simulation model.")
    seed = randbits(32) if seed is None else seed
    growth_paths = simulate_portfolio(
        returns, weights, initial_value=1, trading_days=years * TRADING_DAYS,
        num_simulations=num_simulations, seed=seed, model=model,
        drift_weight=drift_weight, block_length=block_length, record_every=DAYS_PER_MONTH,
    )
    if (growth_paths <= 0).any():
        raise ValueError("Simulated growth underflowed. Try a shorter horizon or different model.")
    with np.errstate(over="ignore", divide="ignore", invalid="ignore"):
        monthly_growth = growth_paths[:, 1:] / growth_paths[:, :-1]
    result = evaluate_goal_paths(monthly_growth, initial_value=initial_value,
                                 monthly_contribution=monthly_contribution, contribution_growth=contribution_growth,
                                 annual_inflation=annual_inflation, goal=goal, target_probability=target_probability)
    return {
        "weights": weights, "years": years, "num_simulations": num_simulations, "seed": seed,
        "initial_value": initial_value, "monthly_contribution": monthly_contribution,
        "contribution_growth": contribution_growth, "annual_inflation": annual_inflation,
        "goal": goal, "target_probability": target_probability, "model": model, "drift_weight": drift_weight,
        "block_length": block_length if model == "block_bootstrap" else None,
        "observations": len(returns), **result,
    }
