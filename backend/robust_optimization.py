"""Regularized mean-variance optimization with chronological holdout evaluation."""

from numbers import Real

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from .covariance import calculate_covariance_matrix
from .optimization import _final_weights
from .portfolio_metrics import TRADING_DAYS, validate_returns, validate_weights


def _bounded(value, low, high, name):
    if (isinstance(value, bool) or not isinstance(value, Real)
            or not np.isfinite(value) or not low <= value <= high):
        raise ValueError(f"{name} must be between {low} and {high}.")


def _turnover(candidate, current):
    return float(np.abs(candidate - current).sum() / 2)


def _solve_utility(mean, covariance, current, cap, turnover_limit, risk_aversion):
    """Maximize mean minus a variance penalty, subject to linear constraints."""
    count = len(current)
    # Clip excess weights, then redistribute the deficit over available space.
    feasible = np.minimum(current, cap)
    deficit = 1 - feasible.sum()
    if deficit > 0:
        space = cap - feasible
        if space.sum() <= 0:
            feasible = np.full(count, 1 / count)
        else:
            feasible += deficit * space / space.sum()
    feasible = _final_weights(feasible, cap)
    if _turnover(feasible, current) > turnover_limit + 1e-8:
        raise ValueError("Turnover limit is too low to satisfy the maximum asset weight.")
    if turnover_limit == 0 or cap == 1 / count:
        return feasible

    # Auxiliary variables bound absolute allocation changes: u >= |w-current|.
    # Their sum is at most twice the one-way turnover budget.
    identity = np.eye(count)
    constraints = [
        {"type": "eq", "fun": lambda x: x[:count].sum() - 1,
         "jac": lambda x: np.r_[np.ones(count), np.zeros(count)]},
        {"type": "ineq", "fun": lambda x: x[count:] - (x[:count] - current),
         "jac": lambda x: np.hstack((-identity, identity))},
        {"type": "ineq", "fun": lambda x: x[count:] + (x[:count] - current),
         "jac": lambda x: np.hstack((identity, identity))},
        {"type": "ineq", "fun": lambda x: 2 * turnover_limit - x[count:].sum(),
         "jac": lambda x: np.r_[np.zeros(count), -np.ones(count)]},
    ]
    scale = max(float(np.max(np.abs(mean))),
                risk_aversion * float(np.max(np.abs(covariance))), 1e-12)
    if not np.isfinite(scale):
        raise ValueError("Optimization estimates exceed numerical limits.")
    mu = mean / scale
    matrix = (covariance / scale) * risk_aversion
    result = minimize(
        lambda x: float(.5 * x[:count] @ matrix @ x[:count] - mu @ x[:count]),
        np.r_[feasible, np.abs(feasible - current)],
        jac=lambda x: np.r_[matrix @ x[:count] - mu, np.zeros(count)],
        method="SLSQP", bounds=[(0, cap)] * count + [(0, 1)] * count,
        constraints=constraints, options={"ftol": 1e-12, "maxiter": 1000},
    )
    if not result.success or not np.isfinite(result.x).all():
        raise ValueError("Robust optimization did not converge.")
    weights = _final_weights(result.x[:count], cap)
    if _turnover(weights, current) > turnover_limit + 1e-8:
        raise ValueError("Optimizer exceeded the turnover limit.")
    return weights


def _performance(returns, allocation, annual_risk_free_rate):
    """Evaluate a fixed target allocation on unregularized observed returns."""
    daily = returns.to_numpy() @ allocation
    annual_return = float(daily.mean() * TRADING_DAYS)
    volatility = float(daily.std(ddof=1) * np.sqrt(TRADING_DAYS))
    with np.errstate(over="ignore", invalid="ignore"):
        total_return = float(np.prod(1 + daily) - 1)
    sharpe = (annual_return - annual_risk_free_rate) / volatility if volatility > 1e-12 else None
    if not np.isfinite([annual_return, volatility, total_return]).all() or (
        sharpe is not None and not np.isfinite(sharpe)
    ):
        raise ValueError("Portfolio performance exceeds numerical limits.")
    return {"annualized_return": annual_return, "annualized_volatility": volatility,
            "total_return": total_return, "sharpe_ratio": sharpe}


def optimize_robust_portfolio(
    returns, weights, *, max_weight=1.0, max_turnover=1.0,
    risk_aversion=5.0, mean_shrinkage=.5, covariance_shrinkage=.25,
    holdout_fraction=.25, annual_risk_free_rate=0.0,
):
    """Fit two allocation models on early dates and evaluate on later dates."""
    returns = validate_returns(returns)
    if not isinstance(returns.index, pd.DatetimeIndex) or returns.index.hasnans:
        raise ValueError("Robust optimization requires dated historical returns.")
    returns = returns.sort_index()
    tickers = list(returns.columns)
    current = validate_weights(weights, tickers).to_numpy()
    _bounded(max_weight, 1 / len(tickers), 1, "Maximum asset weight")
    _bounded(max_turnover, 0, 1, "Maximum turnover")
    _bounded(risk_aversion, .1, 100, "Risk aversion")
    _bounded(mean_shrinkage, 0, 1, "Mean shrinkage")
    _bounded(covariance_shrinkage, 0, 1, "Covariance shrinkage")
    _bounded(holdout_fraction, .1, .5, "Holdout fraction")
    if isinstance(annual_risk_free_rate, bool) or not isinstance(annual_risk_free_rate, Real) or not np.isfinite(annual_risk_free_rate):
        raise ValueError("Annual risk-free rate must be finite.")
    split = int(len(returns) * (1 - holdout_fraction))
    if split < 63 or len(returns) - split < 21:
        raise ValueError("Choose more history: at least 63 training and 21 holdout returns are required.")
    training, holdout = returns.iloc[:split], returns.iloc[split:]
    mean = training.mean().to_numpy() * TRADING_DAYS
    covariance = calculate_covariance_matrix(training).to_numpy()
    if not np.isfinite(mean).all():
        raise ValueError("Historical return estimates exceed numerical limits.")
    # Fixed, user-selected shrinkage toward simple, transparent targets.
    shrunk_mean = (1 - mean_shrinkage) * mean + mean_shrinkage * mean.mean()
    shrunk_covariance = (1 - covariance_shrinkage) * covariance + covariance_shrinkage * np.diag(np.diag(covariance))
    traditional = _solve_utility(mean, covariance, current, max_weight, max_turnover, risk_aversion)
    robust = _solve_utility(shrunk_mean, shrunk_covariance, current, max_weight, max_turnover, risk_aversion)

    def summarize(allocation):
        return {
            "weights": dict(zip(tickers, allocation.tolist())),
            "turnover": _turnover(allocation, current),
            "training": _performance(training, allocation, annual_risk_free_rate),
            "holdout": _performance(holdout, allocation, annual_risk_free_rate),
        }

    def period(frame):
        return {"start": frame.index[0].strftime("%Y-%m-%d"),
                "end": frame.index[-1].strftime("%Y-%m-%d"), "observations": len(frame)}

    return {
        "tickers": tickers, "training_period": period(training), "holdout_period": period(holdout),
        "max_weight": max_weight, "max_turnover": max_turnover, "risk_aversion": risk_aversion,
        "mean_shrinkage": mean_shrinkage, "covariance_shrinkage": covariance_shrinkage,
        "holdout_fraction": holdout_fraction, "annual_risk_free_rate": annual_risk_free_rate,
        "current_respects_max_weight": bool(np.all(current <= max_weight + 1e-8)),
        "current": summarize(current), "traditional": summarize(traditional), "robust": summarize(robust),
    }
