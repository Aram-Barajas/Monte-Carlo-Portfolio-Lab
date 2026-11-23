"""Trace the efficient portion of the historical risk-return frontier."""

from numbers import Integral

import numpy as np

from .covariance import calculate_covariance_matrix

from .optimization import (
    optimize_portfolio,
    _solve_quadratic,
    _final_weights
)

from .portfolio_metrics import (
    TRADING_DAYS,
    validate_returns
)


def calculate_efficient_frontier(
    returns,
    weights,
    max_weight=1.0,
    annual_risk_free_rate=0.0,
    points=25
):
    """Minimize variance for increasing feasible target returns."""

    if (
        isinstance(points, bool)
        or not isinstance(points, Integral)
        or not 2 <= points <= 50
    ):
        raise ValueError(
            "Frontier requires between 2 and 50 points."
        )

    returns = validate_returns(returns)

    result = optimize_portfolio(
        returns,
        weights,
        annual_risk_free_rate,
        max_weight
    )

    tickers = result["tickers"]

    count = len(tickers)

    mean = returns.mean().to_numpy() * TRADING_DAYS

    covariance = calculate_covariance_matrix(
        returns
    ).to_numpy()

    scale = float(np.max(np.abs(covariance)))

    matrix = covariance / scale if scale > 0 else covariance

    minimum = np.array([
        result["minimum_volatility"]["weights"][t]
        for t in tickers
    ])

    # Highest feasible return under the concentration cap.

    highest = np.zeros(count)

    remaining = 1.0

    for index in np.argsort(-mean):

        highest[index] = min(
            remaining,
            max_weight
        )

        remaining = max(
            0.0,
            remaining - highest[index]
        )

    highest = _final_weights(
        highest,
        max_weight
    )

    low = float(mean @ minimum)

    high = float(mean @ highest)

    span = high - low

    def summarize(w):

        daily = returns.to_numpy() @ w

        annual_return = float(
            daily.mean() * TRADING_DAYS
        )

        volatility = float(
            daily.std(ddof=1) * np.sqrt(TRADING_DAYS)
        )

        if not np.isfinite(
            [annual_return, volatility]
        ).all():

            raise ValueError(
                "Frontier metrics exceed numerical limits."
            )

        return {
            "weights": dict(zip(tickers, w.tolist())),

            "annualized_return": annual_return,

            "annualized_volatility": volatility
        }

    candidates = [summarize(minimum)]

    if span > 1e-10:

        if scale == 0:

            candidates.append(
                summarize(highest)
            )

        else:

            direction = (mean - low) / span

            for fraction in np.linspace(0, 1, points)[1:]:

                start = (
                    (1 - fraction) * minimum
                    + fraction * highest
                )

                allocation = _solve_quadratic(
                    matrix,

                    start,

                    [(0, max_weight)] * count,

                    [
                        {
                            "type": "eq",

                            "fun": lambda w: w.sum() - 1,

                            "jac": lambda w: np.ones(count)
                        },
                        {
                            "type": "ineq",

                            "fun": lambda w: direction @ w - fraction,

                            "jac": lambda w: direction
                        }
                    ]
                )

                allocation = _final_weights(
                    allocation,
                    max_weight
                )

                if direction @ allocation < fraction - 1e-7:

                    raise ValueError(
                        "Frontier optimization missed its target return."
                    )

                candidates.append(
                    summarize(allocation)
                )

    # Remove dominated sampled allocations.

    frontier = []

    best_risk = float("inf")

    for item in sorted(
        candidates,
        key=lambda p: p["annualized_return"],
        reverse=True
    ):

        if item["annualized_volatility"] < best_risk - 1e-9:

            frontier.append(item)

            best_risk = item["annualized_volatility"]

    return {
        **result,

        "frontier": list(reversed(frontier))
    }