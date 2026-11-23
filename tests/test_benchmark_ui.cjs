const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const {
    buildBenchmarkPayload,
    requestBenchmark,
    formatPercentagePoints
} = require("../frontend/benchmark.js");

const {
    backtestChartLayout,
    buildBacktestPayload
} = require("../frontend/backtest.js");


const allocation = {
    tickers: ["VTI"],
    weights: { VTI: 1 }
};

const start = "2025-01-01";
const end = "2026-01-01";

const payload = buildBenchmarkPayload(
    allocation,
    start,
    end,
    "1000",
    " spy "
);


test("benchmark payload uses only historical settings", () => {

    assert.deepEqual(payload, {
        ...allocation,
        start,
        end,
        initial_value: 1000,
        benchmark: "SPY"
    });

    for (const ticker of [
        "",
        "BAD TICKER",
        "A".repeat(21)
    ]) {

        assert.throws(() => buildBenchmarkPayload(
            allocation,
            start,
            end,
            "1000",
            ticker
        ), /ticker/);
    }

    assert.throws(() => buildBenchmarkPayload(
        allocation,
        end,
        start,
        "1000",
        "SPY"
    ), /date range/);
});


test("benchmark requests use the correct endpoint and report errors", async () => {

    await requestBenchmark(
        payload,
        async (url, options) => {

            assert.equal(url, "/api/benchmark");
            assert.equal(options.method, "POST");

            assert.deepEqual(
                JSON.parse(options.body),
                payload
            );

            return {
                ok: true,
                json: async () => ({})
            };
        }
    );

    await assert.rejects(

        requestBenchmark(payload, async () => ({
            ok: false,

            json: async () => ({
                detail: [
                    { msg: "Invalid benchmark" }
                ]
            })
        })),

        /Invalid benchmark/
    );
});


test("percentage point differences have clear signs", () => {

    assert.equal(
        formatPercentagePoints(0.05),
        "+5.00 pp"
    );

    assert.equal(
        formatPercentagePoints(-0.11),
        "-11.00 pp"
    );

    assert.equal(
        formatPercentagePoints(-0.000001),
        "0.00 pp"
    );
});


const trajectory = [
    { date: "2025-01-02", value: 1000 },
    { date: "2025-01-03", value: 1200 },
    { date: "2025-01-06", value: 1100 }
];

const reference = trajectory.map(
    (row, index) => ({
        ...row,
        value: [1000, 1400, 1500][index]
    })
);


test("both chart series share the same value scale and date axis", () => {

    const chart = backtestChartLayout(
        trajectory,
        "value",
        400,
        reference
    );

    assert.deepEqual(
        chart.points[0],
        chart.referencePoints[0]
    );

    assert.equal(
        chart.referencePoints.at(-1).y,
        chart.top
    );

    assert.ok(
        chart.points.at(-1).y >
        chart.referencePoints.at(-1).y
    );

    assert.equal(
        chart.points[1].x,
        chart.referencePoints[1].x
    );
});


test("dashboard renders independent benchmark results and preserves them on error", async () => {

    function node(text) {

        return {
            textContent: text,
            children: [],
            handlers: {},
            hidden: true,

            addEventListener(name, handler) {
                this.handlers[name] = handler;
            },

            append(...children) {
                this.children.push(...children);
            },

            replaceChildren(...children) {
                this.children = children;
            },

            scrollIntoView() { }
        };
    }

    const nodes = new Map();

    const $ = id => {

        if (!nodes.has(id)) {
            nodes.set(id, node());
        }

        return nodes.get(id);
    };

    $("start").value = start;
    $("end").value = end;
    $("initial").value = "1000";
    $("benchmark-ticker").value = "SPY";

    const stats = {
        initial_value: 1000,
        ending_value: 1100,
        total_return: .1,
        cagr: .1,
        annualized_volatility: .2,
        max_drawdown: .1,
        sharpe_ratio: null,
        observations: 2,
        trajectory
    };

    const data = {
        portfolio: stats,

        benchmark: {
            ...stats,
            trajectory: reference
        },

        weights: allocation.weights,
        benchmark_ticker: "SPY",
        excess_total_return: -.05,
        excess_cagr: -.05
    };

    let fail = false;
    let drawn;

    vm.runInNewContext(

        fs.readFileSync(
            require.resolve("../frontend/benchmark.js"),
            "utf8"
        ),

        {
            $,
            buildBacktestPayload,

            getAllocation: () => allocation,
            getPortfolioPolicy: () => ({ rebalancing: "monthly", trading_cost_bps: 20, rebalance_threshold: .05 }),
            formatTradingPolicy: () => "Monthly | 20 bps per side",

            element: (tag, text) => node(text),

            money: value => "$" + value,

            percent: value =>
                (value * 100).toFixed(2) + "%",

            drawBacktestChart: (...args) => {
                drawn = args;
            },

            window: {
                addEventListener() { }
            },

            fetch: async () => ({
                ok: !fail,

                json: async () => fail
                    ? { detail: "Failed" }
                    : data
            })
        }
    );

    await $("run-benchmark").handlers.click();

    assert.equal(
        $("benchmark-results").hidden,
        false
    );

    assert.equal(
        $("backtest-results").hidden,
        true
    );

    assert.equal(
        $("benchmark-table").children.length,
        8
    );

    assert.match(
        $("benchmark-excess").textContent,
        /-5.00 pp/
    );

    assert.equal(
        $("benchmark-name").textContent,
        "SPY"
    );

    assert.equal(
        drawn[3],
        reference
    );

    fail = true;

    await $("run-benchmark").handlers.click();

    assert.equal(
        $("benchmark-table").children.length,
        8
    );

    assert.match(
        $("benchmark-status").textContent,
        /Previous benchmark results are unchanged/
    );

    assert.equal(
        $("run-benchmark").disabled,
        false
    );
});
