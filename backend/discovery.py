"""Screen hypothetical stock and ETF additions on shared historical dates."""

from numbers import Real

import numpy as np
import pandas as pd

from .market_data import align_price_history, calculate_daily_returns, normalize_tickers, _validate_prices
from .portfolio_metrics import TRADING_DAYS, validate_weights


DISCOVERY_OBJECTIVES = ("volatility_reduction", "sharpe_improvement", "return_improvement")
MAX_CANDIDATES = 8


def _metrics(daily, risk_free):
    values = daily.to_numpy(dtype=float)
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        annual_return = float(values.mean() * TRADING_DAYS)
        volatility = float(values.std(ddof=1) * np.sqrt(TRADING_DAYS))
        path = np.r_[1., np.cumprod(1 + values)]
        max_drawdown = float(np.max(1 - path / np.maximum.accumulate(path)))
        sharpe = (annual_return - risk_free) / volatility if volatility > 1e-12 else None
    result = {"annualized_return": annual_return, "annualized_volatility": volatility,
              "total_return": float(path[-1] - 1), "max_drawdown": max_drawdown, "sharpe_ratio": sharpe}
    if not np.isfinite(path).all() or not all(v is None or np.isfinite(v) for v in result.values()):
        raise ValueError("Historical performance exceeded numerical limits.")
    return result


def _period(frame):
    return {"start": frame.index[0].strftime("%Y-%m-%d"),
            "end": frame.index[-1].strftime("%Y-%m-%d"), "observations": len(frame)}


def _comparison(baseline_daily, candidate_daily, fraction, risk_free, baseline_metrics):
    # Current holdings funded proportionally; no leverage or new capital.
    proposed = (1 - fraction) * baseline_daily + fraction * candidate_daily
    metrics = _metrics(proposed, risk_free)
    correlation = None
    candidate_metrics = _metrics(candidate_daily, risk_free)
    if baseline_metrics["annualized_volatility"] > 1e-12 and candidate_metrics["annualized_volatility"] > 1e-12:
        correlation = float(baseline_daily.corr(candidate_daily))
        if not np.isfinite(correlation):
            raise ValueError("Historical correlation exceeded numerical limits.")
    sharpe_delta = None
    if metrics["sharpe_ratio"] is not None and baseline_metrics["sharpe_ratio"] is not None:
        sharpe_delta = metrics["sharpe_ratio"] - baseline_metrics["sharpe_ratio"]
    deltas = {
        "volatility_reduction": baseline_metrics["annualized_volatility"] - metrics["annualized_volatility"],
        "sharpe_improvement": sharpe_delta,
        "return_improvement": metrics["annualized_return"] - baseline_metrics["annualized_return"],
        "drawdown_reduction": baseline_metrics["max_drawdown"] - metrics["max_drawdown"],
        "total_return_change": metrics["total_return"] - baseline_metrics["total_return"],
    }
    if not all(v is None or np.isfinite(v) for v in deltas.values()):
        raise ValueError("Historical comparison exceeded numerical limits.")
    return {"candidate_correlation": correlation, "candidate": candidate_metrics,
            "portfolio": metrics, "deltas": deltas}


def screen_candidates(prices, weights, candidates, fetch_candidate, *,
                      candidate_weight=.1, objective="volatility_reduction",
                      holdout_fraction=.25, annual_risk_free_rate=0.):
    """Rank each independent addition on early dates and report later results.

    fetch_candidate takes one normalized symbol and returns its price frame.
    Errors or incomplete candidate histories are reported individually.
    """
    if (isinstance(candidate_weight, bool) or not isinstance(candidate_weight, Real)
            or not np.isfinite(candidate_weight) or not .01 <= candidate_weight <= .5):
        raise ValueError("Candidate allocation must be between 1% and 50%.")
    if objective not in DISCOVERY_OBJECTIVES:
        raise ValueError("Unknown screening objective.")
    if (isinstance(holdout_fraction, bool) or not isinstance(holdout_fraction, Real)
            or not np.isfinite(holdout_fraction) or not .1 <= holdout_fraction <= .5):
        raise ValueError("Holdout fraction must be between 10% and 50%.")
    if (isinstance(annual_risk_free_rate, bool) or not isinstance(annual_risk_free_rate, Real)
            or not np.isfinite(annual_risk_free_rate)):
        raise ValueError("Annual risk-free rate must be finite.")
    candidates = normalize_tickers(candidates)
    if len(candidates) > MAX_CANDIDATES or any(len(ticker) > 20 for ticker in candidates):
        raise ValueError("Provide one to eight distinct candidate tickers.")
    if not 1 <= len(weights) <= 19:
        raise ValueError("Screening supports up to 19 existing holdings.")

    prices = align_price_history(prices, minimum_dates=85)
    returns = calculate_daily_returns(prices)
    weights = validate_weights(weights, returns.columns).to_dict()
    split = int(len(returns) * (1 - holdout_fraction))
    if split < 63 or len(returns) - split < 21:
        raise ValueError("Choose more history: screening requires at least 63 training and 21 holdout returns.")
    baseline = returns.dot(pd.Series(weights))
    periods = {"training": baseline.iloc[:split], "holdout": baseline.iloc[split:]}
    baseline_metrics = {name: _metrics(daily, annual_risk_free_rate) for name, daily in periods.items()}
    evaluated, excluded = [], []
    for ticker in candidates:
        if ticker in weights:
            excluded.append({"ticker": ticker, "reason": "Already in the original portfolio."})
            continue
        try:
            candidate_prices = _validate_prices(fetch_candidate(ticker))
            if list(candidate_prices.columns) != [ticker]:
                raise ValueError("Historical data does not match the candidate ticker.")
            series = candidate_prices[ticker].loc[prices.index[0]:prices.index[-1]]
            if not series.dropna().index.equals(prices.index):
                raise ValueError("Candidate must have complete prices on the same portfolio dates and trading calendar.")
            candidate_returns = (series.reindex(prices.index).pct_change(fill_method=None)).iloc[1:]
            if not np.isfinite(candidate_returns.to_numpy()).all():
                raise ValueError("Candidate returns contain non-finite values.")
            candidate_periods = {"training": candidate_returns.iloc[:split], "holdout": candidate_returns.iloc[split:]}
            comparisons = {name: _comparison(daily, candidate_periods[name], candidate_weight,
                                             annual_risk_free_rate, baseline_metrics[name])
                           for name, daily in periods.items()}
            score = comparisons["training"]["deltas"][objective]
            evaluated.append({
                "ticker": ticker, "score": score,
                "weights": {**{name: weight * (1 - candidate_weight) for name, weight in weights.items()},
                            ticker: candidate_weight},
                **comparisons,
            })
        except RuntimeError:
            excluded.append({"ticker": ticker, "reason": "Market data provider unavailable for this ticker."})
        except ValueError as error:
            excluded.append({"ticker": ticker, "reason": str(error)})
    # Null scores (e.g. undefined Sharpe ratio) are visible but not ranked.
    evaluated.sort(key=lambda item: (item["score"] is None,
                                     -item["score"] if item["score"] is not None else 0,
                                     item["ticker"]))
    for index, item in enumerate(evaluated):
        item["rank"] = index + 1 if item["score"] is not None else None
    return {
        "weights": weights, "candidate_weight": candidate_weight, "objective": objective,
        "holdout_fraction": holdout_fraction, "annual_risk_free_rate": annual_risk_free_rate,
        "training_period": _period(periods["training"]), "holdout_period": _period(periods["holdout"]),
        "first_price_date": prices.index[0].strftime("%Y-%m-%d"),
        "last_price_date": prices.index[-1].strftime("%Y-%m-%d"),
        "baseline": baseline_metrics, "evaluated": evaluated, "excluded": excluded,
    }
