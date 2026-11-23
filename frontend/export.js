// Export the last completed simulation.

function csvCell(value) {
    if (value === null || value === undefined) {
        return "";
    }

    if (typeof value === "number") {
        return Number.isFinite(value) ? String(value) : "";
    }

    let text = String(value);

    // Prevent spreadsheet formula injection.

    if (/^\s*[=+\-@]|^[\t\r\n]/.test(text)) {
        text = "'" + text;
    }

    return '"' + text.replace(/"/g, '""') + '"';
}


function csvText(rows) {
    return rows.map(
        row => row.map(csvCell).join(",")
    ).join("\r\n") + "\r\n";
}


function buildCsvRows(snapshot, format) {
    const { data, payload, comparing } = snapshot;

    const portfolios = comparing
        ? [
            ["A", data.portfolio_a],
            ["B", data.portfolio_b]
        ]
        : [["A", data]];

    const seed = comparing
        ? data.seed
        : data.seed ?? payload.seed;

    // Projected percentile bands.

    if (format === "projections" || format === "real-projections") {
        const real = format === "real-projections";
        return [
            [
                "portfolio",
                "trading_day",
                ...["p05", "p25", "median", "p75", "p95"].map(key => real ? `real_${key}` : key)
            ],

            ...portfolios.flatMap(([name, result]) =>
                (real ? result.real_percentiles : result.percentiles).map(point => [
                    name,
                    point.trading_day,
                    point.p05,
                    point.p25,
                    point.median,
                    point.p75,
                    point.p95
                ])
            )
        ];
    }

    // Final value from each simulation.

    if (format === "ending-values") {
        return [
            [
                "portfolio",
                "simulation",
                "ending_value"
            ],

            ...portfolios.flatMap(([name, result]) =>
                result.ending_values.map((value, index) => [
                    name,
                    index + 1,
                    value
                ])
            )
        ];
    }

    // Individual asset performance.

    if (format === "assets") {
        return [
            [
                "portfolio",
                "ticker",
                "weight",
                "annualized_return",
                "annualized_volatility"
            ],

            ...portfolios.flatMap(([name, result]) =>
                result.analysis.asset_metrics.map(asset => [
                    name,
                    asset.ticker,
                    result.analysis.weights[asset.ticker],
                    asset.annualized_return,
                    asset.annualized_volatility
                ])
            )
        ];
    }

    // Asset correlations.

    if (format === "correlations") {
        return [
            [
                "portfolio",
                "ticker_a",
                "ticker_b",
                "correlation"
            ],

            ...portfolios.flatMap(([name, result]) =>
                result.analysis.correlation.flatMap(row =>
                    result.analysis.tickers.map(ticker => [
                        name,
                        row.ticker,
                        ticker,
                        row[ticker]
                    ])
                )
            )
        ];
    }

    // Portfolio summary and risk metrics.

    if (format === "summary") {
        return [
            [
                "portfolio",
                "history_start",
                "history_end_exclusive",
                "initial_value",
                "monthly_contribution",
                "trading_days",
                "num_simulations",
                "seed",
                "model",
                "block_length",
                "drift_weight",
                "rebalancing",
                "trading_cost_bps",
                "rebalance_threshold",
                "annual_inflation",
                "median_trading_costs",
                "real_median_ending_value",
                "observations",
                "confidence",
                "annual_risk_free_rate",
                "total_invested",
                "mean_ending_value",
                "median_ending_value",
                "ending_p05",
                "ending_p95",
                "probability_of_loss",
                "annualized_return",
                "annualized_volatility",
                "sharpe_ratio",
                "max_drawdown",
                "daily_var",
                "daily_expected_shortfall",
                "terminal_var",
                "terminal_expected_shortfall"
            ],

            ...portfolios.map(([name, result]) => {
                const analysis = result.analysis;
                const risk = result.simulation_risk;
                const history = analysis.historical_risk;
                const metrics = analysis.portfolio_metrics;

                const ending = result.percentiles.at(-1);

                return [
                    name,
                    payload.start,
                    payload.end,
                    payload.initial_value,
                    payload.monthly_contribution,
                    result.trading_days,
                    result.num_simulations,
                    seed,
                    result.model ?? payload.model ?? "gaussian",
                    (result.model ?? payload.model) === "block_bootstrap" ? result.block_length ?? payload.block_length : null,
                    result.drift_weight ?? payload.drift_weight ?? 1,
                    result.rebalancing ?? "daily",
                    result.trading_cost_bps ?? 0,
                    result.rebalance_threshold ?? null,
                    result.annual_inflation ?? 0,
                    result.median_trading_costs ?? 0,
                    (result.real_percentiles ?? result.percentiles).at(-1).median,
                    analysis.observations,
                    risk.confidence,
                    payload.annual_risk_free_rate ?? 0,
                    risk.total_invested,
                    risk.mean_ending_value,
                    risk.median_ending_value,
                    ending.p05,
                    ending.p95,
                    risk.probability_of_loss,
                    metrics.annualized_return,
                    metrics.annualized_volatility,
                    history.sharpe_ratio,
                    history.max_drawdown,
                    history.daily_var,
                    history.daily_expected_shortfall,
                    risk.terminal_var,
                    risk.terminal_expected_shortfall
                ];
            })
        ];
    }

    throw new Error("Unknown CSV export format.");
}


function downloadSimulationCsv(snapshot, format) {
    const csv = csvText(
        buildCsvRows(snapshot, format)
    );

    const file = new Blob(
        ["\uFEFF", csv],
        {
            type: "text/csv;charset=utf-8"
        }
    );

    const url = URL.createObjectURL(file);

    const link = document.createElement("a");

    link.href = url;
    link.download = `portfolio-${format}.csv`;

    document.body.append(link);

    link.click();

    link.remove();

    setTimeout(
        () => URL.revokeObjectURL(url),
        1000
    );
}


// Allow the functions to be used by automated tests.

if (typeof module !== "undefined" && module.exports) {
    module.exports = {
        csvText,
        buildCsvRows
    };
}
