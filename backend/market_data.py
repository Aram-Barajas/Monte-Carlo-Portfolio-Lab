"""Retrieve adjusted market prices and calculate aligned daily returns."""

import re
from datetime import date

import numpy as np
import pandas as pd
from .market_cache import MarketDataCache


_price_cache = MarketDataCache()

TICKER_ALIASES = {
    "BRK.A": "BRK-A",
    "BRK.B": "BRK-B",
    "BF.B": "BF-B"
}


def normalize_tickers(tickers):
    """Accept and normalize unique ticker symbols."""

    if isinstance(tickers, str):
        tickers = [tickers]

    if not isinstance(tickers, (list, tuple)) or not tickers:
        raise ValueError("Provide at least one ticker symbol.")

    symbols = []

    for ticker in tickers:

        if not isinstance(ticker, str):
            raise ValueError("Ticker symbols must be strings.")

        symbol = ticker.strip().upper()

        symbol = TICKER_ALIASES.get(symbol, symbol)

        if not re.fullmatch(r"[A-Z0-9^][A-Z0-9.\-=^]*", symbol):
            raise ValueError(f"Invalid ticker symbol: {ticker!r}")

        if symbol in symbols:
            raise ValueError(f"Duplicate ticker symbol: {symbol}")

        symbols.append(symbol)

    return symbols


def validate_date_range(start, end):
    """Validate an inclusive start date and exclusive end date."""

    try:
        first = date.fromisoformat(start)
        last = date.fromisoformat(end)

        if first.isoformat() != start or last.isoformat() != end:
            raise ValueError

    except (TypeError, ValueError):
        raise ValueError(
            "Dates must use YYYY-MM-DD format."
        ) from None

    if first >= last:
        raise ValueError("End date must be after start date.")


def _validate_prices(prices):

    if not isinstance(prices, pd.DataFrame) or prices.empty:
        raise ValueError("No historical price data available.")

    if not isinstance(prices.index, pd.DatetimeIndex):
        raise ValueError("Prices must have a DatetimeIndex.")

    prices = prices.copy()
    prices.index = prices.index.tz_localize(None).normalize()

    if prices.index.hasnans or prices.index.has_duplicates:
        raise ValueError(
            "Prices contain invalid or duplicate dates."
        )

    if prices.columns.has_duplicates:
        raise ValueError("Prices contain duplicate ticker columns.")

    prices = prices.apply(
        pd.to_numeric,
        errors="raise"
    ).astype(float)

    values = prices.to_numpy()

    if np.isinf(values).any() or (values <= 0).any():
        raise ValueError("Prices must be positive and finite.")

    missing = prices.columns[
        prices.isna().all()
    ].tolist()

    if missing:
        raise ValueError(
            f"No historical data for: {', '.join(map(str, missing))}"
        )

    return prices.sort_index()


def fetch_historical_prices(
    tickers,
    start,
    end,
    *,
    downloader=None
):
    """Download daily adjusted closing prices."""

    symbols = normalize_tickers(tickers)
    validate_date_range(start, end)

    # Custom downloaders are isolated from the production cache.
    if downloader is not None:
        return _download_historical_prices(
            symbols,
            start,
            end,
            downloader=downloader
        )

    ordered_symbols = sorted(symbols)

    key = (
        tuple(ordered_symbols),
        start,
        end
    )

    prices = _price_cache.get(key)

    if prices is None:
        prices = _download_historical_prices(
            ordered_symbols,
            start,
            end
        )

        _price_cache.put(key, prices)

    return prices.loc[:, symbols].copy(deep=True)


def _download_historical_prices(
    symbols,
    start,
    end,
    *,
    downloader=None
):
    """Retrieve and validate prices before they enter the cache."""

    if downloader is None:
        import yfinance as yf

    try:
        data = downloader(
            tickers=symbols,
            start=start,
            end=end,
            interval="1d",
            auto_adjust=True,
            group_by="column",
            multi_level_index=True,
            ignore_tz=True,
            keepna=True,
            progress=False,
            threads=False,
            timeout=10,
        )

    except Exception as error:
        raise RuntimeError(
            "Unable to download historical market data."
        ) from error

    if not isinstance(data, pd.DataFrame) or data.empty:
        raise ValueError("No historical price data available.")

    if isinstance(data.columns, pd.MultiIndex):

        if "Close" not in data.columns.get_level_values(0):
            raise ValueError(
                "Market data is missing adjusted closing prices."
            )

        prices = data.xs("Close", axis=1, level=0)

    elif len(symbols) == 1 and "Close" in data.columns:

        prices = data[["Close"]].rename(
            columns={"Close": symbols[0]}
        )

    else:
        raise ValueError("Unexpected market data column format.")

    missing = [
        symbol for symbol in symbols
        if symbol not in prices.columns
    ]

    if missing:
        raise ValueError(
            f"No historical data for: {', '.join(missing)}"
        )

    prices = _validate_prices(prices.loc[:, symbols])

    return _validate_prices(
        prices.loc[
            (prices.index >= start) &
            (prices.index < end)
        ]
    )


def calculate_daily_returns(prices):
    """Calculate fractional returns without filling gaps."""

    prices = _validate_prices(prices)

    returns = (
        prices / prices.shift(1) - 1
    ).dropna(how="any")

    if returns.empty:
        raise ValueError("Insufficient overlapping price history.")

    if not np.isfinite(returns.to_numpy()).all():
        raise ValueError("Returns contain non-finite values.")

    return returns


def fetch_daily_returns(
    tickers,
    start,
    end,
    *,
    downloader=None
):
    prices = fetch_historical_prices(
        tickers,
        start,
        end,
        downloader=downloader
    )

    return calculate_daily_returns(prices)