"""Transparent quality metadata; warnings do not discard historical observations."""

import numpy as np
import pandas as pd

from .portfolio_metrics import validate_returns


def describe_historical_data(returns):
    """Summarize a shared return frame without inventing missing market prices."""
    frame = validate_returns(returns)
    warnings = []
    if len(frame) < 252:
        warnings.append("Fewer than 252 daily observations; annualized estimates are especially unstable.")
    if len(frame) < 63:
        warnings.append("Fewer than 63 daily observations; long-horizon inference is fragile.")
    extremes = (frame.abs() >= .30).sum()
    extreme_assets = [str(ticker) for ticker, count in extremes.items() if count]
    if extreme_assets:
        warnings.append("Absolute daily returns of 30% or more were observed for " +
                        ", ".join(extreme_assets) +
                        ". Verify splits, corporate actions and data quality independently.")
    if isinstance(frame.index, pd.DatetimeIndex):
        start = frame.index.min().strftime("%Y-%m-%d")
        end = frame.index.max().strftime("%Y-%m-%d")
    else:
        start, end = None, None
    return {
        "observations": len(frame),
        "first_return_date": start,
        "last_return_date": end,
        "source_note": "Historical adjusted prices are sourced through yfinance; cached or revised data may differ from earlier runs.",
        "warnings": warnings,
    }
