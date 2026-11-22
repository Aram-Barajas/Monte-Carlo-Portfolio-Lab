# Monte-Carlo-Portfolio-Lab
A financial analytics platform that uses Monte Carlo simulations and historical market data to model stock portfolio performance, evaluate investment risk, and compare investment strategies through interactive visualizations.

## Historical Market Data

The market data engine retrieves adjusted historical stock and
ETF prices using yfinance.

Features include:

- Multiple ticker support
- Ticker and date validation
- Daily return calculations
- Missing data handling
- Automated testing

## Installation

```bash
python -m pip install -r requirements.txt
```

## Running Tests

```bash
python -m pytest -v
```

## Example Usage

```python
from backend.market_data import fetch_daily_returns

returns = fetch_daily_returns(
    ["NVDA", "AMZN", "VTI"],
    "2025-01-01",
    "2026-01-01"
)

print(returns.head())
```

This project is intended for educational and research purposes.
Historical market performance does not guarantee future results.

## Portfolio Metrics

The portfolio analytics engine calculates:

- Annualized historical returns
- Annualized volatility
- Weighted daily portfolio returns
- Portfolio-level return and volatility

Portfolio weights must be nonnegative and sum to 100%.
Calculations assume daily rebalancing and 252 annual
trading days by default.

## Covariance and Correlation Analysis

The application measures relationships between asset returns
using covariance and Pearson correlation matrices.

Features include:

- Annualized sample covariance matrices
- Pearson correlation matrices
- Portfolio variance using matrix multiplication
- Correlation-aware portfolio volatility
- Validation of portfolio allocations

Correlation is undefined for assets with constant returns.
Historical correlations may change over time.