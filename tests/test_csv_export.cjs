const test = require("node:test");
const assert = require("node:assert/strict");

const {
    csvText,
    buildCsvRows
} = require("../frontend/export.js");


const result = {
    trading_days: 1,
    num_simulations: 2,

    analysis: {
        tickers: ["VTI"],
        weights: { VTI: 1 },
        observations: 20,

        asset_metrics: [
            {
                ticker: "VTI",
                annualized_return: .08,
                annualized_volatility: .2
            }
        ],

        correlation: [
            {
                ticker: "VTI",
                VTI: null
            }
        ],

        portfolio_metrics: {
            annualized_return: .08,
            annualized_volatility: .2
        },

        historical_risk: {
            sharpe_ratio: null,
            max_drawdown: .1,
            daily_var: .01,
            daily_expected_shortfall: .02
        }
    },

    percentiles: [
        {
            trading_day: 0,
            p05: 1000,
            p25: 1000,
            median: 1000,
            p75: 1000,
            p95: 1000
        },
        {
            trading_day: 1,
            p05: 990,
            p25: 995,
            median: 1005,
            p75: 1010,
            p95: 1020
        }
    ],

    simulation_risk: {
        confidence: .95,
        total_invested: 1000,
        mean_ending_value: 1005,
        median_ending_value: 1005,
        probability_of_loss: .5,
        terminal_var: 10,
        terminal_expected_shortfall: 10
    },

    ending_values: [990, 1020]
};


const snapshot = {
    data: result,
    comparing: false,

    payload: {
        start: "2023-01-01",
        end: "2026-01-01",
        initial_value: 1000,
        monthly_contribution: 0,
        seed: 42
    }
};


test("CSV formatting and formula protection", () => {

    assert.equal(
        csvText([
            ["a,b", 'a"b', "=1+1", -2, null]
        ]),
        '"a,b","a""b","\'=1+1",-2,\r\n'
    );
});


test("Projection export includes initial and final day", () => {

    const rows = buildCsvRows(
        snapshot,
        "projections"
    );

    assert.equal(rows.length, 3);

    assert.deepEqual(
        rows[2],
        ["A", 1, 990, 995, 1005, 1010, 1020]
    );
});


test("Comparison export includes both portfolios", () => {

    const comparison = {
        ...snapshot,
        comparing: true,

        data: {
            portfolio_a: result,
            portfolio_b: result,
            seed: 24
        }
    };

    const rows = buildCsvRows(
        comparison,
        "ending-values"
    );

    assert.deepEqual(
        rows.slice(1),
        [
            ["A", 1, 990],
            ["A", 2, 1020],
            ["B", 1, 990],
            ["B", 2, 1020]
        ]
    );

    const summary = buildCsvRows(
        comparison,
        "summary"
    );

    assert.equal(
        summary[2][summary[0].indexOf("seed")],
        24
    );
});


test("Undefined correlations and normalized weights", () => {

    assert.deepEqual(
        buildCsvRows(snapshot, "correlations")[1],
        ["A", "VTI", "VTI", null]
    );

    assert.equal(
        buildCsvRows(snapshot, "assets")[1][2],
        1
    );
});


test("Summary includes submitted settings and risk values", () => {

    const [header, row] = buildCsvRows(
        snapshot,
        "summary"
    );

    assert.equal(
        row.length,
        header.length
    );

    assert.equal(
        row[header.indexOf("history_start")],
        "2023-01-01"
    );

    assert.equal(
        row[header.indexOf("probability_of_loss")],
        .5
    );

    assert.equal(
        row[header.indexOf("sharpe_ratio")],
        null
    );

    assert.throws(
        () => buildCsvRows(snapshot, "unknown")
    );
});

test("Summary exports the actual model, drift, block length and generated seed", () => {
    const [header, row] = buildCsvRows({
        ...snapshot,
        data: { ...result, seed: 125, model: "block_bootstrap", block_length: 10, drift_weight: .5 },
        payload: { ...snapshot.payload, seed: null }
    }, "summary");
    assert.equal(row[header.indexOf("seed")], 125);
    assert.equal(row[header.indexOf("model")], "block_bootstrap");
    assert.equal(row[header.indexOf("block_length")], 10);
    assert.equal(row[header.indexOf("drift_weight")], .5);
});

test("Real projection CSV and summary retain trading assumptions", () => {
    const real = { ...snapshot, data: { ...result, rebalancing: "monthly", trading_cost_bps: 20,
        annual_inflation: .03, median_trading_costs: 5,
        real_percentiles: result.percentiles.map(point => ({ ...point, median: point.median - 10 })) } };
    const [heading, ...rows] = buildCsvRows(real, "real-projections");
    assert.ok(heading.includes("real_median"));
    assert.equal(rows.at(-1)[heading.indexOf("real_median")], 995);
    const [summary, row] = buildCsvRows(real, "summary");
    assert.equal(row[summary.indexOf("rebalancing")], "monthly");
    assert.equal(row[summary.indexOf("trading_cost_bps")], 20);
    assert.equal(row[summary.indexOf("annual_inflation")], .03);
    assert.equal(row[summary.indexOf("median_trading_costs")], 5);
    assert.equal(row[summary.indexOf("real_median_ending_value")], 995);
});
