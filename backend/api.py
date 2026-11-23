"""REST API for the portfolio analysis engine."""

import json
from datetime import date, timedelta
from pathlib import Path
from secrets import randbits
from typing import Literal
import numpy as np

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ConfigDict, model_validator

from .market_data import (
    normalize_tickers, validate_date_range,
    fetch_historical_prices, fetch_daily_returns
)
from .portfolio_metrics import (
    calculate_asset_metrics,
    calculate_portfolio_metrics,
    normalize_rounded_weights
)
from .covariance import (
    calculate_covariance_matrix, calculate_correlation_matrix
)
from .monte_carlo import simulate_portfolio, summarize_simulations
from .risk_metrics import calculate_historical_risk, calculate_simulation_risk
from .backtest import backtest_portfolio
from .stress_test import stress_test_portfolio
from .benchmark import compare_benchmark
from .optimization import optimize_portfolio
from .frontier import calculate_efficient_frontier
from .robust_optimization import optimize_robust_portfolio
from .planning import plan_portfolio
from .model_validation import validate_models, MAX_VALIDATION_DRAWS
from .discovery import screen_candidates, MAX_CANDIDATES
from .portfolio_policy import inflation_factors
from .advanced_risk import (
    CRISIS_WINDOWS, calculate_risk_contributions, calculate_rolling_risk,
    replay_crisis,
)

app = FastAPI(
    title="Monte Carlo Portfolio Lab",
    version="1.0.0"
)

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/", include_in_schema=False)
def dashboard():
    return FileResponse(FRONTEND_DIR / "index.html")


class MarketRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        allow_inf_nan=False
    )

    tickers: list[str] = Field(min_length=1, max_length=20)
    start: str
    end: str

    @model_validator(mode="after")
    def validate_market(self):
        self.tickers = normalize_tickers(self.tickers)
        validate_date_range(self.start, self.end)

        days = (
            date.fromisoformat(self.end)
            - date.fromisoformat(self.start)
        ).days

        if days > 7305:
            raise ValueError(
                "Historical range cannot exceed 20 years (7305 days)."
            )

        if any(len(ticker) > 20 for ticker in self.tickers):
            raise ValueError(
                "Ticker symbols must not exceed 20 characters."
            )

        return self


class PortfolioRequest(MarketRequest):
    weights: dict[str, float]
    confidence: float = Field(default=0.95, gt=0, lt=1)
    annual_risk_free_rate: float = 0.0

    @model_validator(mode="after")
    def validate_allocation(self):
        symbols = normalize_tickers(list(self.weights))

        self.weights = dict(
            zip(symbols, self.weights.values())
        )

        self.weights = normalize_rounded_weights(
         self.weights,
         self.tickers
).to_dict()

        return self


class DiscoveryRequest(PortfolioRequest):
    candidates: list[str] = Field(min_length=1, max_length=MAX_CANDIDATES)
    candidate_weight: float = Field(default=.1, ge=.01, le=.5)
    objective: Literal["volatility_reduction", "sharpe_improvement", "return_improvement"] = "volatility_reduction"
    holdout_fraction: float = Field(default=.25, ge=.1, le=.5)

    @model_validator(mode="after")
    def validate_candidates(self):
        self.candidates = normalize_tickers(self.candidates)
        if len(self.tickers) > 19:
            raise ValueError("Screening supports up to 19 existing holdings.")
        if any(len(ticker) > 20 for ticker in self.candidates):
            raise ValueError("Ticker symbols must not exceed 20 characters.")
        return self


class RiskAnalysisRequest(PortfolioRequest):
    rolling_window: int = Field(default=63, ge=2, le=252)


class CrisisReplayRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    tickers: list[str] = Field(min_length=1, max_length=20)
    weights: dict[str, float]
    scenario: Literal["gfc", "covid", "bear_2022"]
    initial_value: float = Field(default=1000, gt=0, le=1_000_000_000)


class OptimizationRequest(PortfolioRequest):

    max_weight: float = Field(
        default=1.0,
        gt=0,
        le=1
    )

    @model_validator(mode="after")
    def validate_limit(self):

        if self.max_weight < 1 / len(self.tickers):

            raise ValueError(
                "Maximum weight is too low for the asset count."
            )

        return self

class RobustOptimizationRequest(OptimizationRequest):
    max_turnover: float = Field(default=1.0, ge=0, le=1)
    risk_aversion: float = Field(default=5.0, ge=.1, le=100)
    mean_shrinkage: float = Field(default=.5, ge=0, le=1)
    covariance_shrinkage: float = Field(default=.25, ge=0, le=1)
    holdout_fraction: float = Field(default=.25, ge=.1, le=.5)

    @model_validator(mode="after")
    def validate_turnover(self):
        required = sum(max(0, weight - self.max_weight) for weight in self.weights.values())
        if required > self.max_turnover + 1e-8:
            raise ValueError("Turnover limit is too low to satisfy the maximum asset weight.")
        return self


class FrontierRequest(OptimizationRequest):

    points: int = Field(
        default=25,
        ge=2,
        le=50
    )

class StressTestRequest(BaseModel):

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        allow_inf_nan=False
    )

    weights: dict[str, float] = Field(
        min_length=1,
        max_length=20
    )

    initial_value: float = Field(
        default=1000,
        gt=0,
        le=1_000_000_000
    )

    scenarios: dict[str, dict[str, float]] | None = Field(
        default=None,
        min_length=1,
        max_length=10
    )

    @model_validator(mode="after")
    def normalize_allocations(self):

        tickers = normalize_tickers(
            list(self.weights)
        )

        if any(len(ticker) > 20 for ticker in tickers):
            raise ValueError(
                "Ticker symbols must not exceed 20 characters."
            )

        self.weights = normalize_rounded_weights(
            dict(
                zip(tickers, self.weights.values())
            ),
            tickers
        ).to_dict()

        if self.scenarios is not None:

            for name, shocks in self.scenarios.items():

                symbols = normalize_tickers(
                    list(shocks)
                )

                self.scenarios[name] = dict(
                    zip(symbols, shocks.values())
                )

        return self

class TradingPolicyRequest(PortfolioRequest):
    rebalancing: Literal["daily", "monthly", "quarterly", "annual", "buy_hold", "threshold"] = "daily"
    trading_cost_bps: float = Field(default=0, ge=0, le=500)
    rebalance_threshold: float = Field(default=.05, ge=.001, le=1)

    def trading_policy(self):
        return {"rebalancing": self.rebalancing, "trading_cost_bps": self.trading_cost_bps,
                "rebalance_threshold": self.rebalance_threshold}


class BacktestRequest(TradingPolicyRequest):
    initial_value: float = Field(
        default=1000,
        gt=0,
        le=1_000_000_000
    )

class BenchmarkRequest(BacktestRequest):
    benchmark: str

    @model_validator(mode="after")
    def validate_benchmark(self):

        self.benchmark = normalize_tickers(
            [self.benchmark]
        )[0]

        if len(self.benchmark) > 20:
            raise ValueError(
                "Ticker symbols must not exceed 20 characters."
            )

        if len(set(self.tickers + [self.benchmark])) > 20:
            raise ValueError(
                "Benchmark comparison supports up to "
                "20 distinct tickers total."
            )

        return self

class SimulationRequest(TradingPolicyRequest):
    model: Literal["gaussian", "gaussian_uncertain", "block_bootstrap"] = "gaussian"
    block_length: int = Field(default=5, ge=1, le=252)
    drift_weight: float = Field(default=1.0, ge=0, le=1)
    annual_inflation: float = Field(default=0, ge=-.05, le=.25)

    initial_value: float = Field(
        default=1000, ge=0, le=1_000_000_000
    )

    monthly_contribution: float = Field(
        default=0, ge=0, le=1_000_000_000
    )

    trading_days: int = Field(default=252, ge=1, le=2520)
    num_simulations: int = Field(default=1000, ge=1, le=5000)

    seed: int | None = Field(
        default=None, ge=0, le=2**32 - 1
    )

    @model_validator(mode="after")
    def validate_simulation_size(self):
        if (
            self.num_simulations * (self.trading_days + 1)
            > 5_000_000

            or self.num_simulations
            * self.trading_days
            * len(self.tickers)
            > 20_000_000
        ):
            raise ValueError(
                "Simulation is too large. Reduce paths, days, or assets."
            )

        return self


class ModelValidationRequest(PortfolioRequest):
    training_days: int = Field(default=252, ge=63, le=1260)
    forecast_days: int = Field(default=21, ge=5, le=252)
    max_folds: int = Field(default=12, ge=3, le=24)
    num_simulations: int = Field(default=500, ge=100, le=1000)
    drift_weight: float = Field(default=1., ge=0, le=1)
    block_length: int = Field(default=21, ge=1, le=252)
    seed: int | None = Field(default=None, ge=0, le=2**32 - 1)

    @model_validator(mode="after")
    def validate_work(self):
        if self.block_length > self.training_days:
            raise ValueError("Block length cannot exceed the training window.")
        if self.max_folds * self.num_simulations * self.forecast_days * len(self.tickers) * 3 > MAX_VALIDATION_DRAWS:
            raise ValueError("Validation is too large. Reduce folds, forecast days, paths, or assets.")
        return self


class PlanningRequest(PortfolioRequest):
    years: int = Field(default=20, ge=1, le=40)
    num_simulations: int = Field(default=500, ge=1, le=2000)
    initial_value: float = Field(default=1000, ge=0, le=1_000_000_000)
    monthly_contribution: float = Field(default=100, ge=0, le=1_000_000_000)
    contribution_growth: float = Field(default=0, ge=-.1, le=.25)
    annual_inflation: float = Field(default=.025, ge=-.05, le=.25)
    goal: float = Field(default=100000, ge=.01, le=1_000_000_000)
    target_probability: float = Field(default=.8, ge=.5, le=.99)
    model: Literal["gaussian", "gaussian_uncertain", "block_bootstrap"] = "gaussian_uncertain"
    drift_weight: float = Field(default=.5, ge=0, le=1)
    block_length: int = Field(default=21, ge=1, le=252)
    seed: int | None = Field(default=None, ge=0, le=2**32 - 1)

    @model_validator(mode="after")
    def validate_plan_size(self):
        if self.num_simulations * self.years * 252 * len(self.tickers) > 20_000_000:
            raise ValueError("Planning simulation is too large. Reduce years, paths, or assets.")
        return self


class ComparisonRequest(SimulationRequest):
    comparison_weights: dict[str, float]

    @model_validator(mode="after")
    def validate_comparison(self):
        symbols = normalize_tickers(list(self.comparison_weights))
        self.comparison_weights = dict(zip(symbols, self.comparison_weights.values()))
        self.comparison_weights = normalize_rounded_weights(
            self.comparison_weights,
            symbols
).to_dict()

        combined = set(self.tickers) | set(symbols)
        if len(combined) > 20 or any(len(ticker) > 20 for ticker in combined):
            raise ValueError("Comparison supports up to 20 distinct tickers total.")
        if self.num_simulations * self.trading_days * len(combined) > 20_000_000:
            raise ValueError("Comparison is too large. Reduce paths, days, or assets.")
        return self


def frame_records(frame, index_name):
    """Convert a DataFrame into JSON records."""

    return json.loads(
        frame.rename_axis(index_name)
        .reset_index()
        .to_json(
            orient="records",
            date_format="iso",
            double_precision=15
        )
    )


def load_market_data(request, *, prices=False):
    """Fetch data and handle data-source errors."""

    fetch = (
        fetch_historical_prices
        if prices
        else fetch_daily_returns
    )

    try:
        return fetch(
            request.tickers,
            request.start,
            request.end
        )

    except ValueError as error:
        raise HTTPException(
            status_code=422,
            detail=str(error)
        ) from error

    except RuntimeError as error:
        raise HTTPException(
            status_code=502,
            detail="Unable to retrieve market data."
        ) from error


def analyze_portfolio(returns, request):
    """Reuse the existing financial analysis functions."""

    return {
        "tickers": request.tickers,

        "weights": request.weights,

        "observations": len(returns),

        "asset_metrics": frame_records(
            calculate_asset_metrics(returns),
            "ticker"
        ),

        "portfolio_metrics": calculate_portfolio_metrics(
            returns,
            request.weights
        ),

        "covariance": frame_records(
            calculate_covariance_matrix(returns),
            "ticker"
        ),

        "correlation": frame_records(
            calculate_correlation_matrix(returns),
            "ticker"
        ),

        "historical_risk": calculate_historical_risk(
            returns,
            request.weights,
            request.confidence,
            request.annual_risk_free_rate
        )
    }


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/market-data")
def market_data(request: MarketRequest):
    prices = load_market_data(
        request,
        prices=True
    )

    prices.index = prices.index.strftime("%Y-%m-%d")

    return {
        "tickers": request.tickers,

        "prices": frame_records(
            prices,
            "date"
        )
    }


@app.post("/api/portfolio")
def portfolio(request: PortfolioRequest):
    returns = load_market_data(request)

    try:
        return analyze_portfolio(
            returns,
            request
        )

    except ValueError as error:
        raise HTTPException(
            status_code=422,
            detail=str(error)
        ) from error


def simulation_result(returns, request, shared_returns=None):
    analysis = analyze_portfolio(returns, request)
    simulation_returns = returns if shared_returns is None else shared_returns
    weights = {ticker: request.weights.get(ticker, 0.0) for ticker in simulation_returns.columns}
    paths, costs = simulate_portfolio(
        simulation_returns, weights,
        initial_value=request.initial_value,
        trading_days=request.trading_days,
        num_simulations=request.num_simulations,
        monthly_contribution=request.monthly_contribution,
        seed=request.seed,
        model=request.model,
        block_length=request.block_length,
        drift_weight=request.drift_weight,
        return_costs=True,
        **request.trading_policy()
    )
    bands = summarize_simulations(paths)
    real_bands = bands.div(inflation_factors(request.annual_inflation, request.trading_days), axis=0)
    if not np.isfinite(real_bands.to_numpy()).all():
        raise ValueError("Inflation-adjusted results exceeded numerical limits.")
    return {
        "analysis": analysis,
        "trading_days": request.trading_days,
        "num_simulations": request.num_simulations,
        "model": request.model,
        "block_length": request.block_length if request.model == "block_bootstrap" else None,
        "drift_weight": request.drift_weight,
        "seed": request.seed,
        **request.trading_policy(),
        "rebalance_threshold": request.rebalance_threshold if request.rebalancing == "threshold" else None,
        "annual_inflation": request.annual_inflation,
        "median_trading_costs": float(np.median(costs)),
        "percentiles": frame_records(bands, "trading_day"),
        "real_percentiles": frame_records(real_bands, "trading_day"),
        "simulation_risk": calculate_simulation_risk(
            paths, request.monthly_contribution, request.confidence
        ),
        "ending_values": paths[:, -1].tolist()
    }


@app.post("/api/simulate")
def simulate(request: SimulationRequest):
    returns = load_market_data(request)
    try:
        if request.seed is None:
            request = request.model_copy(update={"seed": randbits(32)})
        return simulation_result(returns, request)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/api/validate-models")
def model_validation(request: ModelValidationRequest):
    returns = load_market_data(request)
    try:
        result = validate_models(returns, request.weights, **request.model_dump(exclude={
            "tickers", "weights", "start", "end", "confidence", "annual_risk_free_rate",
        }))
        return {"start": request.start, "end": request.end, **result}
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/api/plan")
def plan(request: PlanningRequest):
    returns = load_market_data(request)
    try:
        result = plan_portfolio(
            returns, request.weights, **request.model_dump(exclude={
                "tickers", "weights", "start", "end", "confidence", "annual_risk_free_rate",
            })
        )
        return {"start": request.start, "end": request.end, **result}
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/api/compare")
def compare(request: ComparisonRequest):
    # Download a single aligned return history for the union of assets.
    combined = list(dict.fromkeys(request.tickers + list(request.comparison_weights)))
    market = MarketRequest(tickers=combined, start=request.start, end=request.end)
    returns = load_market_data(market)

    # Using the same seed and asset ordering gives both portfolios the same shocks.
    seed = request.seed if request.seed is not None else randbits(32)
    first = request.model_copy(update={"seed": seed})
    second = request.model_copy(update={
        "tickers": list(request.comparison_weights),
        "weights": request.comparison_weights,
        "seed": seed
    })
    try:
        return {
            "seed": seed,
            "portfolio_a": simulation_result(returns[first.tickers], first, returns),
            "portfolio_b": simulation_result(returns[second.tickers], second, returns)
        }
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

@app.post("/api/backtest")
def backtest(request: BacktestRequest):
    prices = load_market_data(
        request,
        prices=True
    )

    try:
        result = backtest_portfolio(
            prices,
            request.weights,
            initial_value=request.initial_value,
            confidence=request.confidence,
            annual_risk_free_rate=request.annual_risk_free_rate,
            **request.trading_policy()
        )

        trajectory = result.pop("trajectory")

        trajectory.index = trajectory.index.strftime(
            "%Y-%m-%d"
        )

        return {
            "tickers": request.tickers,
            "weights": request.weights,
            **result,
            "trajectory": frame_records(
                trajectory,
                "date"
            )
        }

    except ValueError as error:
        raise HTTPException(
            status_code=422,
            detail=str(error)
        ) from error

@app.post("/api/benchmark")
def benchmark(request: BenchmarkRequest):

    combined = list(
        dict.fromkeys(
            request.tickers + [request.benchmark]
        )
    )

    market = MarketRequest(
        tickers=combined,
        start=request.start,
        end=request.end
    )

    prices = load_market_data(
        market,
        prices=True
    )

    try:

        result = compare_benchmark(
            prices,
            request.weights,
            request.benchmark,
            initial_value=request.initial_value,
            confidence=request.confidence,
            annual_risk_free_rate=request.annual_risk_free_rate,
            **request.trading_policy()
        )

        for name in ("portfolio", "benchmark"):

            trajectory = result[name]["trajectory"]

            trajectory.index = trajectory.index.strftime(
                "%Y-%m-%d"
            )

            result[name]["trajectory"] = frame_records(
                trajectory,
                "date"
            )

        return {
            "tickers": request.tickers,
            "weights": request.weights,
            **result
        }

    except ValueError as error:

        raise HTTPException(
            status_code=422,
            detail=str(error)
        ) from error


@app.post("/api/discover")
def discover(request: DiscoveryRequest):
    prices = load_market_data(request, prices=True)
    try:
        result = screen_candidates(
            prices, request.weights, request.candidates,
            lambda ticker: fetch_historical_prices([ticker], request.start, request.end),
            candidate_weight=request.candidate_weight, objective=request.objective,
            holdout_fraction=request.holdout_fraction, annual_risk_free_rate=request.annual_risk_free_rate,
        )
        return {"start": request.start, "end": request.end, **result}
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/api/risk-analysis")
def risk_analysis(request: RiskAnalysisRequest):
    returns = load_market_data(request).sort_index()
    try:
        contribution = calculate_risk_contributions(returns, request.weights)
        rolling = calculate_rolling_risk(returns, request.weights, request.rolling_window)
        rolling.index = rolling.index.strftime("%Y-%m-%d")
        return {
            "tickers": request.tickers,
            "weights": request.weights,
            "observations": len(returns),
            "first_return_date": returns.index[0].strftime("%Y-%m-%d"),
            "last_return_date": returns.index[-1].strftime("%Y-%m-%d"),
            "rolling_window": request.rolling_window,
            **contribution,
            "rolling": frame_records(rolling, "date"),
        }
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/api/crisis-replay")
def crisis_replay(request: CrisisReplayRequest):
    _, start, end = CRISIS_WINDOWS[request.scenario]
    try:
        settings = BenchmarkRequest(
            tickers=request.tickers, weights=request.weights,
            start=start, end=(date.fromisoformat(end) + timedelta(days=1)).isoformat(),
            benchmark="SPY", initial_value=request.initial_value,
        )
        market = MarketRequest(
            tickers=list(dict.fromkeys(settings.tickers + ["SPY"])),
            start=settings.start, end=settings.end,
        )
        result = replay_crisis(load_market_data(market, prices=True), settings.weights,
                               request.scenario, settings.initial_value)
        for name in ("portfolio", "benchmark"):
            trajectory = result[name]["trajectory"]
            trajectory.index = trajectory.index.strftime("%Y-%m-%d")
            result[name]["trajectory"] = frame_records(trajectory, "date")
        return {"tickers": settings.tickers, "weights": settings.weights, **result}
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/api/optimize")
def optimize(request: OptimizationRequest):

    returns = load_market_data(request)

    try:

        return optimize_portfolio(
            returns,

            request.weights,

            annual_risk_free_rate=request.annual_risk_free_rate,

            max_weight=request.max_weight
        )

    except ValueError as error:

        raise HTTPException(
            status_code=422,
            detail=str(error)
        ) from error

@app.post("/api/robust-optimize")
def robust_optimize(request: RobustOptimizationRequest):
    returns = load_market_data(request)
    try:
        return optimize_robust_portfolio(
            returns, request.weights, max_weight=request.max_weight,
            max_turnover=request.max_turnover, risk_aversion=request.risk_aversion,
            mean_shrinkage=request.mean_shrinkage, covariance_shrinkage=request.covariance_shrinkage,
            holdout_fraction=request.holdout_fraction, annual_risk_free_rate=request.annual_risk_free_rate,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/api/frontier")
def frontier(request: FrontierRequest):

    returns = load_market_data(request)

    try:

        return calculate_efficient_frontier(
            returns,

            request.weights,

            max_weight=request.max_weight,

            annual_risk_free_rate=request.annual_risk_free_rate,

            points=request.points
        )

    except ValueError as error:

        raise HTTPException(
            status_code=422,
            detail=str(error)
        ) from error

@app.post("/api/stress-test")
def stress_test(request: StressTestRequest):

    try:
        return stress_test_portfolio(
            request.weights,
            initial_value=request.initial_value,
            scenarios=request.scenarios
        )

    except ValueError as error:
        raise HTTPException(
            status_code=422,
            detail=str(error)
        ) from error
