"""Historical risk attribution, rolling statistics and crisis replay."""

from numbers import Integral

import numpy as np
import pandas as pd

from .benchmark import compare_benchmark
from .covariance import calculate_covariance_matrix
from .market_data import align_price_history
from .portfolio_metrics import (
    TRADING_DAYS, calculate_portfolio_returns, validate_weights,
)


# Inclusive closing-price endpoints, selected for illustrative study.
CRISIS_WINDOWS = {
    "gfc": ("Global financial crisis", "2007-10-09", "2009-03-09"),
    "covid": ("COVID-19 sell-off", "2020-02-19", "2020-03-23"),
    "bear_2022": ("2022 bear market", "2022-01-03", "2022-10-12"),
}


def calculate_risk_contributions(returns, weights):
    """Decompose annualized volatility into signed Euler contributions."""
    covariance = calculate_covariance_matrix(returns)
    w = validate_weights(weights, covariance.columns).to_numpy()
    portfolio = calculate_portfolio_returns(returns, weights)
    sigma = float(portfolio.std(ddof=1) * np.sqrt(TRADING_DAYS))
    asset_vol = np.sqrt(np.maximum(0, np.diag(covariance)))
    defined = sigma > 1e-12
    if defined:
        marginal = covariance.to_numpy() @ w / sigma
        component = w * marginal
        shares = component / sigma
        ratio = float(w @ asset_vol / sigma)
        if not np.isfinite(np.r_[marginal, component, shares, ratio]).all():
            raise ValueError("Risk contributions exceeded numerical limits.")
    else:
        ratio = None
    if not np.isfinite(sigma):
        raise ValueError("Portfolio volatility exceeded numerical limits.")
    return {
        "annualized_volatility": sigma,
        "diversification_ratio": ratio,
        "assets": [
            {
                "ticker": ticker,
                "weight": float(w[i]),
                "annualized_asset_volatility": float(asset_vol[i]),
                "marginal_contribution": float(marginal[i]) if defined else None,
                "component_contribution": float(component[i]) if defined else None,
                "risk_share": float(shares[i]) if defined else None,
            }
            for i, ticker in enumerate(covariance.columns)
        ],
    }


def calculate_rolling_risk(returns, weights, window=63):
    """Trailing compounded return and annualized sample volatility."""
    if isinstance(window, bool) or not isinstance(window, Integral) or not 2 <= window <= 252:
        raise ValueError("Rolling window must be 2 to 252 observations.")
    portfolio = calculate_portfolio_returns(returns, weights).sort_index()
    compounded = (1 + portfolio).rolling(window).apply(np.prod, raw=True) - 1
    volatility = portfolio.rolling(window).std(ddof=1) * np.sqrt(TRADING_DAYS)
    result = pd.DataFrame({
        "trailing_return": compounded,
        "annualized_volatility": volatility,
    }).iloc[window - 1:]
    if not np.isfinite(result.to_numpy()).all():
        raise ValueError("Rolling statistics exceeded numerical limits.")
    return result


def replay_crisis(prices, weights, scenario, initial_value=1000):
    """Replay fixed allocations against SPY over the full selected window."""
    if scenario not in CRISIS_WINDOWS:
        raise ValueError("Unknown crisis scenario.")
    title, start, end = CRISIS_WINDOWS[scenario]
    prices = align_price_history(prices, minimum_dates=3)
    if prices.index[0] != pd.Timestamp(start) or prices.index[-1] != pd.Timestamp(end):
        raise ValueError(
            f"Full crisis replay requires every asset and SPY to cover "
            f"{start} through {end}. Choose another scenario or allocation."
        )
    result = compare_benchmark(prices, weights, "SPY", initial_value=initial_value)
    return {"scenario": scenario, "title": title, "start": start, "end": end, **result}
