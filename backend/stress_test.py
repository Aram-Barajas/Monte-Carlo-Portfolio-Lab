"""Evaluate hypothetical, instantaneous portfolio price shocks."""

from collections.abc import Mapping
from math import fsum, isfinite
from numbers import Real

from .portfolio_metrics import validate_weights


def stress_test_portfolio(
    weights,
    initial_value=1000,
    scenarios=None
):
    """Apply fractional shocks to a long-only portfolio."""

    if (
        not isinstance(weights, Mapping)
        or not 1 <= len(weights) <= 20
    ):
        raise ValueError(
            "Provide between 1 and 20 portfolio weights."
        )

    tickers = list(weights)

    ordered = validate_weights(
        weights,
        tickers
    )

    ordered = ordered / ordered.sum()

    if (
        isinstance(initial_value, bool)
        or not isinstance(initial_value, Real)
        or not isfinite(initial_value)
        or not 0 < initial_value <= 1_000_000_000
    ):
        raise ValueError(
            "Initial value must be positive and at most $1 billion."
        )

    initial_value = float(initial_value)

    # Default hypothetical market shocks.

    if scenarios is None:
        scenarios = {
            f"Uniform {shock:.0%} shock": {
                ticker: shock
                for ticker in tickers
            }
            for shock in (
                -0.10,
                -0.20,
                -0.35,
                -0.50
            )
        }

    if (
        not isinstance(scenarios, Mapping)
        or not 1 <= len(scenarios) <= 10
    ):
        raise ValueError(
            "Provide between 1 and 10 stress scenarios."
        )

    results = []

    for name, shocks in scenarios.items():

        if (
            not isinstance(name, str)
            or not name.strip()
            or len(name) > 80
        ):
            raise ValueError(
                "Scenario names must contain 1 to 80 characters."
            )

        if (
            not isinstance(shocks, Mapping)
            or set(shocks) != set(tickers)
        ):
            raise ValueError(
                "Each scenario must specify one shock per portfolio ticker."
            )

        assets = []

        for ticker, weight in ordered.items():

            shock = shocks[ticker]

            if (
                isinstance(shock, bool)
                or not isinstance(shock, Real)
                or not isfinite(shock)
                or not -1 <= shock <= 1
            ):
                raise ValueError(
                    "Shocks must be finite fractions between -1 and 1."
                )

            contribution = float(weight * shock)

            assets.append({
                "ticker": ticker,

                "weight": float(weight),

                "shock": float(shock),

                "return_contribution": contribution,

                "value_change": initial_value * contribution
            })

        # Calculate the weighted portfolio shock.

        portfolio_return = max(
            -1.0,
            min(
                1.0,
                fsum(
                    asset["return_contribution"]
                    for asset in assets
                )
            )
        )

        ending_value = (
            initial_value *
            (1 + portfolio_return)
        )

        results.append({
            "name": name,

            "portfolio_return": portfolio_return,

            "ending_value": ending_value,

            "value_change":
                initial_value * portfolio_return,

            "assets": assets
        })

    return {
        "initial_value": initial_value,

        "weights": ordered.to_dict(),

        "scenarios": results
    }