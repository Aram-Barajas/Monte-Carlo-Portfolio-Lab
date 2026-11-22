"""REST API for the portfolio analysis engine."""

import json
from datetime import date

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, ConfigDict, model_validator

from .market_data import (
    normalize_tickers, validate_date_range,
    fetch_historical_prices, fetch_daily_returns
)
from .portfolio_metrics import (
    calculate_asset_metrics, calculate_portfolio_metrics,
    validate_weights
)
from .covariance import (
    calculate_covariance_matrix, calculate_correlation_matrix
)
from .monte_carlo import simulate_portfolio, summarize_simulations
from .risk_metrics import calculate_historical_risk, calculate_simulation_risk


app = FastAPI(
    title="Monte Carlo Portfolio Lab",
    version="1.0.0"
)


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

        validate_weights(self.weights, self.tickers)

        return self


class SimulationRequest(PortfolioRequest):
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


@app.post("/api/simulate")
def simulate(request: SimulationRequest):
    returns = load_market_data(request)

    try:
        analysis = analyze_portfolio(
            returns,
            request
        )

        paths = simulate_portfolio(
            returns,
            request.weights,
            initial_value=request.initial_value,
            trading_days=request.trading_days,
            num_simulations=request.num_simulations,
            monthly_contribution=request.monthly_contribution,
            seed=request.seed
        )

        return {
            "analysis": analysis,

            "trading_days": request.trading_days,

            "num_simulations": request.num_simulations,

            "percentiles": frame_records(
                summarize_simulations(paths),
                "trading_day"
            ),

            "simulation_risk": calculate_simulation_risk(
                paths,
                request.monthly_contribution,
                request.confidence
            ),

            "ending_values": paths[:, -1].tolist()
        }

    except ValueError as error:
        raise HTTPException(
            status_code=422,
            detail=str(error)
        ) from error