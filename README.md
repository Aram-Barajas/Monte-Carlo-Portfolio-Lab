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

### Shared Historical Price History

Historical analytics use consecutive complete price observations within the
common date range of all selected assets. If an asset has a shorter history,
leading and trailing observations outside that shared range are trimmed.

Missing prices **inside** the shared range are rejected with the affected
tickers and first missing date. Prices are not forward-filled, and returns
around a gap are not silently dropped or treated as a single daily return.
Choose assets with matching trading calendars or a complete date range.

This policy applies to portfolio analysis, simulation, portfolio comparison,
backtesting, benchmark comparison, optimization and the efficient frontier.
The raw market-data endpoint still returns the downloaded price observations,
including missing values. Historical analytics require at least two return
observations (three complete shared price dates).

The model uses 252 trading days per year, appropriate as an approximation for
US stock and ETF trading. Ordinary weekends and holidays with no price rows
are not treated as missing observations. Mixed trading calendars (such as
stocks and continuously traded crypto) may be rejected. A consistent
calendar other than a stock-market calendar is not yet modeled separately.
Dates absent for every asset are not detectable without exchange calendars.

### Market Data Caching

Historical adjusted closing prices are cached in server memory
for 15 minutes, with up to 32 unique ticker sets and date ranges.

Changing allocations, contributions, or simulation settings can
reuse these prices without another market data download.

Expired data is refreshed on the next request. The least recently
used entries are evicted when the cache is full. Failed downloads
are not cached, and callers receive independent copies of prices.

The cache is local to each server process and resets on restart.

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
| Portfolio allocation (%) | Enter each ticker and its allocation percentage. Totals between 99.95% and 100.05% are automatically normalized to 100%. |
| History start | Beginning of the historical market data collection. |
| History end | End of the historical market data collection (exclusive). |
| Initial investment ($) | Starting amount invested in the portfolio. |
| Monthly contribution ($) | Additional money invested approximately every month. |
| Horizon (years) | Number of years into the future to simulate. |
| Simulations | Number of hypothetical future portfolio paths generated. |
| Confidence (%) | Confidence level used for Value at Risk and expected shortfall. |
| Random seed | Allows simulation results to be reproduced using the same inputs and historical data. Leave blank for new random draws. |
| Simulation model | Choose fixed-mean Gaussian, uncertain-mean Gaussian, or historical block bootstrap. |
| Historical block length | Number of consecutive historical returns sampled together (bootstrap only). |
| Historical log-return drift retained | Retain 100%, 50%, or 0% of the historical mean log return to examine sensitivity to estimated growth. |
| Rebalancing policy | Daily, monthly, quarterly, annual, buy and hold, or threshold-based. Shared by Simulation and Backtesting. |
| Rebalance threshold | Maximum absolute deviation from target weights, in percentage points, before rebalancing. Used only for the threshold policy. |
| Trading cost | Cost per side of traded notional, in basis points (100 bps = 1%). |
| Assumed annual inflation | Constant annual change in purchasing power, from -5% to 25%. Used for simulation real-dollar projections. |

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
Portfolio B. Enter a separate allocation using the same
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


### Interactive Projection Chart

Hover over the chart, tap it on a touchscreen, or use the
trading-day slider to inspect projected values at a selected
point in the investment horizon.

The chart displays the 5th, 25th, 50th (median), 75th and
95th percentiles of Portfolio A. In comparison mode, it
also displays Portfolio B's median.

The slider supports keyboard navigation and initially
selects the final simulated trading day. These values are
hypothetical outcomes, not guaranteed future returns.

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

## Research Workspace

Use the navigation to switch between Overview, Simulation, Backtesting,
Optimization, Stress testing and Risk analytics. Each view displays its own controls and
results. Portfolio A and applicable dates/capital are shared; switching
views preserves entered settings and completed results until page reload.
Browser back and forward navigation works through URL fragments.

Overview can analyze historical data without running a Monte Carlo simulation.
Successful simulations also populate the historical overview with their
submitted analysis (including Portfolio B correlations when comparing).
Result panels reflect the last completed request, not unsaved input changes.
CSV export is available from a collapsible control in Simulation.

## Running Tests

```bash
python -m pytest -v
```
JavaScript export tests:

```bash
node --test tests/test_*.cjs
```
Node.js is required for frontend testing only, not for
running the dashboard.

### Financial Validation

Regression tests verify that incomplete historical data cannot silently
discard returns and that compounded returns reproduce the price ratio over
complete shared histories. API tests exercise the actual alignment logic
using mocked price downloads. Independent reference tests compare correlated
portfolio optimization and efficient frontier solutions with closed-form
solutions, and check backtest growth and contribution timing against known
values. These tests validate calculations on controlled inputs; they do not
establish forecast accuracy or validate a live data provider.

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

All three models use the selected rebalancing policy and monthly contributions
every 21 trading days. The default remains daily rebalancing with zero costs.

### Return-generation models

- **Gaussian (fixed historical mean):** independent multivariate normal
  log-return draws using the estimated historical mean and covariance.
- **Gaussian (uncertain mean):** each simulated path draws a fixed mean from
  a Gaussian approximation with mean equal to the historical estimate and
  covariance equal to the daily sample covariance divided by the number of
  historical returns. Future daily shocks are independently drawn conditional
  on that mean. This illustrates mean-estimation uncertainty under IID normal
  assumptions, but does not account for covariance estimation error or regime
  changes. It is not a calibrated predictive distribution.
- **Historical block bootstrap:** samples contiguous blocks of joint historical
  log-return rows with replacement, wrapping from the last observation to the
  first. This preserves cross-asset relationships and short-run dependence
  within blocks. The block length is configurable (default 5 trading days,
  between 1 and 252, and no greater than the available history). Block length
  1 is independent empirical resampling. Blocks may join artificial boundary
  transitions, cannot directly sample unseen shocks, and depend on the chosen
  historical period. This model does not independently account for parameter
  uncertainty. See D. N. Politis and J. P. Romano, *A Circular Block-Resampling
  Procedure for Stationary Data* (1992).

### Drift sensitivity and interpretation

`drift_weight` is a fraction from 0 to 1. In Gaussian models it scales the
mean log return; in the uncertain-mean model it also scales the sampled mean
uncertainty. In the block bootstrap it shifts each historical log return by
`(drift_weight - 1) * historical_mean`, preserving deviations about the mean.
This is a scenario sensitivity setting, not a statistically fitted shrinkage
estimator. Zero mean log return does not imply zero mean simple return.

The `/api/simulate` and `/api/compare` endpoints accept `model` (`gaussian`,
`gaussian_uncertain`, `block_bootstrap`), `drift_weight` (default 1.0), and
`block_length` (default 5, used only by the bootstrap model). Responses and
summary CSVs retain these submitted assumptions and the actual random seed.
A blank seed generates a new seed that is reported for reproducibility with
the same data, implementation and settings. Comparison mode shares shocks,
including sampled blocks or uncertain means, across both allocations.

The 5th–95th percentile band is the central 90% of simulated values at each
date under the chosen assumptions, not a confidence interval for future value.
The loss frequency is the fraction of simulated paths ending below nominal
contributed capital, not an estimated probability of real-world loss. The
separate risk confidence setting controls VaR and expected shortfall, not the
scenario percentile bands. Compare models and historical windows to examine
sensitivity; none of the models guarantees forecast accuracy.

Simulation results represent hypothetical scenarios rather than guaranteed
investment outcomes. Taxes, separate fund fees and changing market conditions
are not explicitly modeled.

### Trading Assumptions and Real-Dollar Projections

Simulation, portfolio comparison, historical backtesting, and benchmark
comparison share the same portfolio evolution engine. Initial capital is
assumed already invested in the submitted target allocation, without an
initial purchase fee or final liquidation fee. Holdings drift with market
returns unless rebalanced. Contributions, when enabled, are invested at target
weights after each 21st trading day's market movement; purchase costs are
deducted from the contribution budget before buying.

- Daily, monthly, quarterly and annual schedules rebalance after the market
  return and contributions on multiples of 1, 21, 63 and 252 trading days.
- Buy and hold does not sell or rebalance existing positions; new contributions
  still purchase assets in target proportions.
- Threshold-based checks weights after returns and contributions each day,
  restoring target weights if any asset differs from its target by at least
  the specified number of percentage points. This is an absolute drift, not
  a relative percentage change in the weight.

Trading cost is charged on both purchases and sales of rebalanced holdings.
If the rate is `c`, the post-trade holdings equal the target weights times
the portfolio value after fees. The fee equals `c` times the absolute sum of
actual changes in individual holdings. The engine solves this self-financing
equation iteratively. It also charges `c` on contribution purchases. Reported
cumulative trading costs are nominal sums, not estimates of forgone growth.
The benchmark assumes a cost-free buy-and-hold position in one asset.
Historical performance metrics use realized net portfolio returns. Overview,
optimization and efficient frontier still use fixed-weight daily analytics;
stress tests are instantaneous shocks, so trading assumptions do not apply.

The `/api/simulate`, `/api/compare`, `/api/backtest` and `/api/benchmark`
endpoints accept `rebalancing` (`daily`, `monthly`, `quarterly`, `annual`,
`buy_hold`, `threshold`), `trading_cost_bps` (0–500, default 0), and
`rebalance_threshold` (0.001–1, default 0.05). Simulation and comparison also
accept `annual_inflation` (-0.05–0.25, default 0). Inflation-adjusted values
at trading day `t` divide nominal values by `(1 + annual_inflation)^(t/252)`.
This assumes constant inflation, not historical CPI or an inflation forecast.
Nominal contribution amounts are not increased with inflation.

The simulation dashboard can switch its chart between nominal and starting
dollars, reports the real median ending value and median cumulative trading
costs, and exports real percentile bands separately. Terminal loss frequency,
VaR and expected shortfall remain nominal after trading costs, not real-dollar
risk estimates. CSV summary exports retain all submitted assumptions.

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

## Historical Portfolio Backtesting

Select **Run historical backtest** in the dashboard to replay
Portfolio A using the selected historical dates and initial
investment.

The dashboard displays historical value, drawdown, and summary
metrics separately from the Monte Carlo projections.

Portfolio B, monthly contributions, horizon, and simulation count
do not affect backtesting.

The results show the submitted allocation and actual overlapping
historical dates.

The backtesting engine replays adjusted historical closing prices using
the selected rebalancing and trading-cost assumptions.

Supported metrics include:

- Historical portfolio value
- Total cumulative return
- Compound annual growth rate (CAGR)
- Annualized volatility
- Sharpe ratio
- Maximum drawdown

The engine starts with a lump-sum investment at the first common
price date. CAGR is annualized using 252 trading days and the
number of observed daily returns.

The engine uses overlapping price history and rejects missing
prices inside that period.

Backtesting does not include recurring contributions, taxes,
separate fund fees or inflation. Selecting today's portfolio with hindsight
can bias historical results.

Historical performance does not guarantee future results.

The engine is available through POST /api/backtest and the
interactive API documentation.

## Historical Benchmark Comparison

The benchmark engine compares a portfolio against a reference
asset, such as a broad-market ETF (VTI or SPY), over identical
historical dates.

Both investments start with the same capital and use the same
overlapping adjusted price history. The portfolio follows the selected
rebalancing and trading-cost assumptions, while the benchmark is a
cost-free buy-and-hold position in the selected reference asset.

Supported metrics include:

- Historical investment value
- Total return
- Compound annual growth rate (CAGR)
- Annualized volatility
- Sharpe ratio
- Maximum drawdown
- Differences in total return and CAGR

Return differences are expressed as fractional values.
A difference of 0.05 means 5 percentage points of
outperformance, not risk-adjusted alpha.

The comparison supports up to 20 distinct tickers, including
the benchmark.

The engine rejects gaps within overlapping price history.
Contributions, taxes, separate fund fees and inflation are not included.

Historical comparisons do not predict future performance.

The engine is available through POST /api/benchmark
and the interactive API documentation.
Enter a reference ticker (SPY by default) and select
**Compare against benchmark** in the dashboard.

The comparison uses Portfolio A, the historical dates,
and the initial investment.

The chart shows both historical value trajectories on
the same scale, followed by a side-by-side metrics table.

Portfolio B and monthly contributions do not affect
this comparison.

## Portfolio Optimization

The optimization engine uses historical arithmetic mean
returns and annualized sample covariance to compare three
portfolio strategies:

- Current portfolio allocation
- Minimum-volatility allocation
- Maximum-Sharpe allocation

The engine uses SciPy constrained optimization and assumes
daily rebalancing and 252 trading days per year.

### Allocation Constraints

Optimized portfolios must satisfy the following:

- Nonnegative allocation weights
- Allocations totaling 100%
- Optional maximum allocation per asset

The maximum asset weight is expressed as a fraction.
For example, 0.60 limits any individual asset to 60%
of the optimized portfolio.

The original allocation is reported unchanged, even if
it exceeds the selected concentration limit.

### Optimization Limitations

Maximum-Sharpe results are unavailable when no feasible
portfolio has positive estimated excess return or when
the objective implies zero volatility.

Historical estimates may change over time. Optimized
allocations may be concentrated, unstable, or overfit
to the selected historical period.

Taxes, fees, turnover, and changing market conditions
are not explicitly modeled.

Results are intended for educational research rather
than trading instructions.

The engine is available through POST /api/optimize
and the interactive API documentation.

The dashboard's Optimization workspace exposes the efficient frontier,
including minimum-volatility and maximum-Sharpe reference allocations.

### Robust allocation research

The same workspace also compares the current allocation, a traditional
mean-variance allocation, and a shrinkage-regularized allocation.
Both optimizers maximize annualized arithmetic mean return minus
half the risk-aversion parameter times annualized portfolio variance.
They share long-only, fully invested, maximum asset weight and
one-way turnover constraints. One-way turnover is half the sum of
absolute weight changes from the original allocation (e.g., 10% moved
from one asset to another is 10% turnover). An infeasible combination
of allocation cap and turnover limit is rejected.

The robust model shrinks historical means toward their cross-asset
average and covariance toward its diagonal (zero off-diagonal entries).
The two shrinkage settings range from 0% to 100%. This regularizes
noisy historical estimates; it is not a worst-case guarantee or an
automatically estimated shrinkage intensity. Risk aversion controls
the variance penalty; the risk-free rate is used for Sharpe reporting.

The earlier portion of the selected history is used for fitting.
A later, chronological 10-50% holdout is reserved for evaluation only.
At least 63 training observations and 21 holdout observations are required.
Both periods report compounded total return, annualized arithmetic return,
annualized sample volatility and Sharpe ratio using unmodified historical
returns and daily fixed target weights. The holdout allocation is not
re-fitted on validation data. The current allocation is shown unchanged
even if outside the optimization cap. Turnover measures the initial
allocation change, not daily rebalancing activity; fees and taxes are not
modeled. Selecting parameters based on holdout results or selecting
today's assets introduces potential hindsight and overfitting.

Use POST /api/robust-optimize or **Compare robust allocations**.
These are hypothetical research allocations, not trade recommendations.

## Efficient Frontier

Select **Build efficient frontier** to examine the historically
estimated tradeoff between annualized return and volatility
for Portfolio A.

Enter a maximum allocation percentage and an assumed
annual risk-free rate.

The engine minimizes variance at increasing feasible
return targets using the same long-only allocation
constraints as portfolio optimization.

The chart displays the current portfolio and maximum-Sharpe
portfolio when available.

Users can select individual frontier points to inspect
their corresponding asset allocations.

The API supports 2 to 50 requested sample points through
POST /api/frontier, with 25 points by default.

Degenerate histories may produce fewer points.

Historical estimates do not guarantee future returns.
Recurring contributions, taxes and trading costs are not
included.

## Portfolio Stress Testing

Select **Run portfolio stress test** to evaluate Portfolio A
under instantaneous hypothetical price shocks.

The dashboard uses the initial investment and portfolio
allocation, not historical dates, contributions or simulation
settings.

Default scenarios apply uniform declines of 10%, 20%, 35%
and 50%.

Enable custom asset shocks to enter one percentage change
per ticker between -100% and +100%.

Supported results include:

- Portfolio percentage change
- Estimated dollar gain or loss
- Ending portfolio value
- Individual asset contributions

The REST API accepts fractional weights and shocks and
supports up to 10 custom scenarios in a single request.

No historical market data download is required.

Uniform shocks cannot distinguish between portfolio allocations.
Asset-specific shocks can illustrate differences in exposure.

These scenarios are not forecasts or estimates of the
probability of a market crash.

## Advanced Risk Analytics

The Risk analytics workspace separates allocation weight from historical
volatility contribution. With annualized covariance matrix C, weights w
and portfolio volatility sigma, an asset's component contribution is
w[i] * (Cw)[i] / sigma. Contributions sum to portfolio volatility;
their shares sum to 100%. Negative shares can occur when an asset's
co-movement reduces total risk. When volatility is effectively zero,
risk shares and the diversification ratio are undefined. The ratio is
weighted average asset volatility divided by portfolio volatility.

Rolling charts show trailing compounded returns (not annualized) and
annualized sample volatility using 252 trading days. Choose 21, 63, 126
or 252 observations. The charts use overlapping daily-rebalanced
historical returns; short histories may support attribution but not
the requested rolling window.

The Stress testing workspace also supports historical crisis replays:

| Scenario | Inclusive closing-price dates |
| --- | --- |
| Global financial crisis | 2007-10-09 to 2009-03-09 |
| COVID-19 sell-off | 2020-02-19 to 2020-03-23 |
| 2022 bear market | 2022-01-03 to 2022-10-12 |

Each uses Portfolio A's current allocation and initial capital,
rebalanced daily, compared against buy-and-hold SPY, without new
contributions or trading costs. The selected crisis overrides the
normal history dates. All assets must cover both preset endpoints with
no gaps in the returned shared price dates; dates absent from the entire
provider dataset cannot be independently detected. Newer assets may
not have sufficient history. Replaying today's assets in the past
introduces hindsight and survivorship bias. These selected windows
are illustrative, not predictions or exhaustive crisis scenarios.

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
| POST | `/api/backtest` | Replay a portfolio over historical market prices |
| POST | `/api/stress-test` | Evaluate hypothetical asset price shocks |
| POST | `/api/risk-analysis` | Euler volatility attribution and rolling historical statistics |
| POST | `/api/crisis-replay` | Replay predefined historical crisis windows against SPY |
| POST | `/api/benchmark` | Compare historical performance with a reference asset |
| POST | `/api/optimize` | Compare minimum-volatility and maximum-Sharpe allocations |
| POST | `/api/robust-optimize` | Compare sample and shrinkage-based allocation models with chronological holdout |
| POST | `/api/frontier` | Calculate historically estimated efficient allocations |

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
