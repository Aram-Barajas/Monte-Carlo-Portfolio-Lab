"""Compare historical portfolio performance against a reference asset."""

from collections.abc import Mapping

import numpy as np
import pandas as pd

from .backtest import align_backtest_prices, backtest_portfolio


def compare_benchmark(
    prices,
    weights,
    benchmark,
    initial_value=1000,
    confidence=0.95,
    annual_risk_free_rate=0.0,
    *,
    rebalancing="daily",
    trading_cost_bps=0,
    rebalance_threshold=.05
):
    """Replay both investments over identical historical dates."""

    if not isinstance(weights, Mapping) or not weights:
        raise ValueError("Provide portfolio weights.")

    if not isinstance(benchmark, str) or not benchmark:
        raise ValueError("Provide a benchmark ticker.")

    tickers = list(weights)
    combined = list(dict.fromkeys(tickers + [benchmark]))

    if (
        not isinstance(prices, pd.DataFrame)
        or set(prices.columns) != set(combined)
    ):
        raise ValueError(
            "Price columns must match portfolio and benchmark tickers."
        )

    prices = align_backtest_prices(prices)

    settings = {
        "initial_value": initial_value,
        "confidence": confidence,
        "annual_risk_free_rate": annual_risk_free_rate
    }

    portfolio = backtest_portfolio(
        prices[tickers],
        weights,
        **settings,
        rebalancing=rebalancing,
        trading_cost_bps=trading_cost_bps,
        rebalance_threshold=rebalance_threshold
    )

    reference = backtest_portfolio(
        prices[[benchmark]],
        {benchmark: 1.0},
        **settings,
        rebalancing="buy_hold"
    )

    excess_return = (
        portfolio["total_return"]
        - reference["total_return"]
    )

    excess_cagr = (
        portfolio["cagr"]
        - reference["cagr"]
    )

    if not np.isfinite([excess_return, excess_cagr]).all():
        raise ValueError(
            "Benchmark comparison exceeded numerical limits."
        )

    return {
        "benchmark_ticker": benchmark,
        "portfolio": portfolio,
        "benchmark": reference,
        "excess_total_return": excess_return,
        "excess_cagr": excess_cagr
    }
