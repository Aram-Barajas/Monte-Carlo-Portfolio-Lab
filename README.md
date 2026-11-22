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

## Using the Interactive Dashboard

Start the application from the repository root:

```bash
python -m uvicorn backend.api:app --reload
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in your browser.

The dashboard supports both light and dark themes.

### Simulation Settings

| Setting | Description |
| --- | --- |
| Portfolio allocation (%) | Enter each ticker and its allocation percentage. Totals between 99.95% and 100.05% are automatically normalized to 100%. || History start | Beginning of the historical market data collection. |
| History end | End of the historical market data collection (exclusive). |
| Initial investment ($) | Starting amount invested in the portfolio. |
| Monthly contribution ($) | Additional money invested approximately every month. |
| Horizon (years) | Number of years into the future to simulate. |
| Simulations | Number of hypothetical future portfolio paths generated. |
| Confidence (%) | Confidence level used for Value at Risk and expected shortfall. |
| Random seed | Allows simulation results to be reproduced using the same inputs and historical data. Leave blank for new random draws. |

### Historical Data vs. Investment Horizon

The historical date range determines which past market data
is used to estimate returns, volatility, and relationships
between assets.

The investment horizon determines how far into the future
the portfolio will be simulated. These are independent settings.

For example:

- History start: January 1, 2023
- History end: January 1, 2026
- Investment horizon: 5 years
- Simulations: 1,000

The application uses approximately three calendar years of
historical market data to generate 1,000 hypothetical
five-year portfolio outcomes.

Shorter historical periods emphasize recent market conditions,
while longer periods may capture a wider variety of market
conditions.

Try different historical periods while keeping the investment
horizon unchanged to understand how historical assumptions
affect simulation results.

All selected assets must have sufficient overlapping
historical price data.

### Comparing Portfolios

Enable **Compare with a second portfolio** to compare Portfolio A with
Portfolio B. Portfolio B. Enter a separate allocation using the same
rounding tolerance as Portfolio A. Both
portfolios use the same initial investment, contributions, trading horizon,
historical date range, overlapping historical observations and simulated
market shocks. The comparison table shows risk and return metrics side by
side. The chart shows Portfolio A's percentile bands and the median line
for each portfolio. Other result panels show Portfolio A.

Comparison uses up to 20 distinct tickers across both allocations and may
require reducing the simulation count for large portfolios or long horizons.

### Example Portfolio

Enter one ticker and allocation percentage per line:

```text
VTI, 60
NVDA, 25
AMZN, 15
```

Aim for allocations totaling 100%. Small rounding differences
are automatically corrected.

Common ticker aliases, such as `BRK.B`, are converted to
their corresponding Yahoo Finance symbols automatically.

See the Allocation Normalization section for more details.


### Exporting Results

After running a simulation, users can download their
results as CSV files.

Available exports include:

- Portfolio summary and risk metrics
- Projected percentile bands
- Simulated ending values
- Individual asset performance and portfolio weights
- Asset correlations

When comparing portfolios, exports include results
for both Portfolio A and Portfolio B.

Exports use the most recent successful simulation.
Returns, probabilities, volatility, and weights are
represented as fractional values (0.10 means 10%).

Undefined correlations and Sharpe ratios are blank.
The summary includes simulation settings and the known
random seed, when available.

## Running Tests

```bash
python -m pytest -v
```
JavaScript export tests:

```bash
node --test tests/test_csv_export.cjs
```

Node.js is required for frontend testing only, not for
running the dashboard.

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

### Correlation Heatmap

The dashboard displays a color-coded correlation matrix
that visualizes the historical relationships between assets.

- Green: Positive correlation
- Terracotta: Negative correlation
- Neutral: Correlation near zero
- N/A: Undefined correlation

Correlation values range from -1 to +1.

In portfolio comparison mode, both portfolios display
individual correlation matrices calculated using
the same overlapping historical observations.

Historical correlations may change over time and do not
guarantee future diversification benefits.

## Monte Carlo Simulation Engine

The simulation engine generates potential future portfolio
trajectories using correlated historical log returns.

Features include:

- Configurable investment horizons
- Multiple asset allocations
- Recurring monthly contributions
- Reproducible random seeds
- Correlated return simulations
- Percentile-based outcome summaries
- Input validation and automated tests

The model assumes daily portfolio rebalancing, independent
daily log-return draws, and monthly contributions every
21 trading days.

Simulation results represent hypothetical scenarios rather
than guaranteed investment outcomes. Taxes, fees, inflation,
and changing market conditions are not explicitly modeled.

## Advanced Risk Metrics

The risk analysis engine evaluates historical portfolio
performance and potential downside risk from Monte Carlo
simulations.

Supported metrics include:

- Sharpe ratio
- Maximum drawdown
- Value at Risk (VaR)
- Expected shortfall (CVaR)
- Probability of simulated investment losses
- Mean and median ending portfolio values
- Total invested capital

Historical VaR and drawdown are expressed as fractional
losses, while simulated terminal VaR and expected shortfall
are expressed in currency units.

Simulated losses account for recurring contributions.
These metrics are historical or model-based estimates
and do not guarantee future results.

## REST API

Start the FastAPI server from the repository root:

```bash
python -m uvicorn backend.api:app --reload
```

Interactive API documentation: http://127.0.0.1:8000/docs

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Server health check |
| POST | `/api/market-data` | Adjusted historical prices |
| POST | `/api/portfolio` | Portfolio metrics, covariance, correlation and risk |
| POST | `/api/simulate` | Monte Carlo percentile bands and terminal risk |
| POST | `/api/compare` | Compare two allocations under shared assumptions |

Historical dates use YYYY-MM-DD, with an exclusive end date.
Portfolio weights are fractional allocations. Totals between
0.9995 and 1.0005 are normalized to 1.0 before calculations.
The API limits historical ranges, asset counts and simulation sizes.
API tests mock market data downloads, so they do not require live prices.

## Allocation Normalization

The application accepts portfolio allocation totals between
99.95% and 100.05% to accommodate rounding differences from
brokerage platforms.

Allocations within this range are automatically normalized
to 100%, preserving their relative proportions.

Invalid allocations, negative weights, duplicate assets,
and non-finite values are rejected.

Common ticker aliases are automatically converted:

- BRK.A to BRK-A
- BRK.B to BRK-B
- BF.B to BF-B

These improvements apply to individual portfolio simulations
and portfolio comparisons.