"""Long-only mean-variance portfolio optimization using historical returns."""

from numbers import Real

import numpy as np

from scipy.optimize import minimize

from .covariance import calculate_covariance_matrix

from .portfolio_metrics import (
    TRADING_DAYS,
    validate_returns,
    validate_weights
)


def _solve_quadratic(matrix, start, bounds, constraints):
    """Minimize portfolio variance subject to linear constraints."""

    result = minimize(
        lambda w: float(w @ matrix @ w),

        start,

        jac=lambda w: 2 * matrix @ w,

        method="SLSQP",

        bounds=bounds,

        constraints=constraints,

        options={
            "ftol": 1e-12,
            "maxiter": 1000
        }
    )

    if (
        not result.success
        or not np.isfinite(result.x).all()
    ):
        raise ValueError(
            "Portfolio optimization did not converge."
        )

    return result.x


def _final_weights(values, cap):
    """Remove small solver rounding errors and verify feasibility."""

    if (
        not np.isfinite(values).all()
        or np.any(values < -1e-8)
    ):
        raise ValueError(
            "Optimizer returned invalid weights."
        )

    values = np.maximum(values, 0)

    total = values.sum()

    if not np.isfinite(total) or total <= 0:
        raise ValueError(
            "Optimizer returned invalid weights."
        )

    values = values / total

    if np.any(values > cap + 1e-8):
        raise ValueError(
            "Optimizer exceeded the allocation limit."
        )

    return values


def optimize_portfolio(
    returns,
    weights,
    annual_risk_free_rate=0.0,
    max_weight=1.0
):
    """Compare current, minimum-volatility and maximum-Sharpe allocations."""

    returns = validate_returns(returns)

    tickers = list(returns.columns)

    current = validate_weights(
        weights,
        tickers
    ).to_numpy()

    count = len(tickers)

    if (
        isinstance(max_weight, bool)
        or not isinstance(max_weight, Real)
        or not np.isfinite(max_weight)
        or not 1 / count <= max_weight <= 1
    ):
        raise ValueError(
            "Maximum weight must be between 1 / asset count and 1."
        )

    if (
        isinstance(annual_risk_free_rate, bool)
        or not isinstance(annual_risk_free_rate, Real)
        or not np.isfinite(annual_risk_free_rate)
    ):
        raise ValueError(
            "Annual risk-free rate must be finite."
        )

    mean = (
        returns.mean().to_numpy()
        * TRADING_DAYS
    )

    covariance = calculate_covariance_matrix(
        returns
    ).to_numpy()

    excess = mean - annual_risk_free_rate

    if not np.isfinite(excess).all():
        raise ValueError(
            "Historical return estimates exceed numerical limits."
        )

    # Scaling improves numerical conditioning.

    scale = float(
        np.max(np.abs(covariance))
    )

    matrix = (
        covariance / scale
        if scale > 0
        else covariance
    )

    equal = np.full(
        count,
        1 / count
    )

    def summarize(allocation):

        daily = returns.to_numpy() @ allocation

        annual_return = float(
            daily.mean() * TRADING_DAYS
        )

        volatility = float(
            daily.std(ddof=1) * np.sqrt(TRADING_DAYS)
        )

        sharpe = (
            (annual_return - annual_risk_free_rate)
            / volatility
            if volatility > 1e-12
            else None
        )

        if (
            not np.isfinite(
                [annual_return, volatility]
            ).all()

            or (
                sharpe is not None
                and not np.isfinite(sharpe)
            )
        ):
            raise ValueError(
                "Portfolio metrics exceed numerical limits."
            )

        return {
            "weights": dict(
                zip(tickers, allocation.tolist())
            ),

            "annualized_return": annual_return,

            "annualized_volatility": volatility,

            "sharpe_ratio": sharpe
        }

    fixed = max_weight == 1 / count

    # Minimum-volatility portfolio.

    if fixed or scale == 0:

        minimum = equal

    else:

        minimum = _solve_quadratic(
            matrix,

            equal,

            [(0, max_weight)] * count,

            [
                {
                    "type": "eq",

                    "fun": lambda w: w.sum() - 1,

                    "jac": lambda w: np.ones(count)
                }
            ]
        )

        minimum = _final_weights(
            minimum,
            max_weight
        )

    minimum_summary = summarize(minimum)

    # Find the largest feasible excess return.

    highest = np.zeros(count)

    remaining = 1.0

    for index in np.argsort(-excess):

        highest[index] = min(
            max_weight,
            remaining
        )

        remaining = max(
            0.0,
            remaining - highest[index]
        )

    highest = _final_weights(
        highest,
        max_weight
    )

    highest_excess = float(
        excess @ highest
    )

    maximum = None
    reason = None

    # Maximum-Sharpe portfolio.

    if highest_excess <= 1e-12:

        reason = (
            "No feasible portfolio has a positive "
            "estimated excess return."
        )

    elif scale == 0:

        reason = (
            "Historical volatility is zero; "
            "Sharpe ratio is undefined."
        )

    elif (
        minimum_summary["sharpe_ratio"] is None
        and minimum_summary["annualized_return"]
        > annual_risk_free_rate
    ):

        reason = (
            "A zero-volatility solution makes "
            "the Sharpe objective undefined."
        )

    else:

        if fixed:

            candidate = equal

        else:

            # Transform the positive-excess Sharpe problem
            # into a constrained convex quadratic problem.

            direction = excess / highest_excess

            cap_matrix = (
                max_weight * np.ones((count, count))
                - np.eye(count)
            )

            solution = _solve_quadratic(
                matrix,

                highest,

                [(0, None)] * count,

                [
                    {
                        "type": "eq",

                        "fun": lambda y: direction @ y - 1,

                        "jac": lambda y: direction
                    },
                    {
                        "type": "ineq",

                        "fun": lambda y: cap_matrix @ y,

                        "jac": lambda y: cap_matrix
                    }
                ]
            )

            if not np.isclose(
                direction @ solution,
                1,
                rtol=0,
                atol=1e-7
            ):
                raise ValueError(
                    "Optimizer returned an infeasible Sharpe solution."
                )

            candidate = _final_weights(
                solution,
                max_weight
            )

        candidate_summary = summarize(
            candidate
        )

        if candidate_summary["sharpe_ratio"] is None:

            reason = (
                "A zero-volatility solution makes "
                "the Sharpe objective undefined."
            )

        elif candidate_summary["sharpe_ratio"] <= 0:

            raise ValueError(
                "Optimizer returned a nonpositive excess return."
            )

        else:

            maximum = candidate_summary

    return {
        "tickers": tickers,

        "observations": len(returns),

        "annual_risk_free_rate": annual_risk_free_rate,

        "max_weight": max_weight,

        "current_respects_max_weight": bool(
            np.all(current <= max_weight + 1e-8)
        ),

        "current": summarize(current),

        "minimum_volatility": minimum_summary,

        "maximum_sharpe": maximum,

        "maximum_sharpe_unavailable_reason": reason
    }