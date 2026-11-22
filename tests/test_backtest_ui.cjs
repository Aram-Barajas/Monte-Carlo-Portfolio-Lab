const test = require("node:test");
const assert = require("node:assert/strict");

const {
    buildBacktestPayload,
    requestBacktest,
    backtestChartLayout
} = require("../frontend/backtest.js");


const allocation = {
    tickers: ["VTI"],
    weights: {
        VTI: 1
    }
};


const trajectory = [
    {
        date: "2025-01-02",
        value: 1000,
        drawdown: 0
    },
    {
        date: "2025-01-03",
        value: 1100,
        drawdown: 0
    },
    {
        date: "2025-01-06",
        value: 990,
        drawdown: 0.1
    }
];


test("backtest payload includes only supported settings", () => {
    const payload = buildBacktestPayload(
        allocation,
        "2025-01-01",
        "2026-01-01",
        "1000"
    );

    assert.deepEqual(payload, {
        ...allocation,
        start: "2025-01-01",
        end: "2026-01-01",
        initial_value: 1000
    });
});


test("rejects invalid historical dates and investments", () => {
    assert.throws(() => buildBacktestPayload(
        allocation,
        "2026-01-01",
        "2025-01-01",
        "1000"
    ), /date range/);

    for (const value of [
        "", "0", "-1", "Infinity", "1000000001"
    ]) {
        assert.throws(() => buildBacktestPayload(
            allocation,
            "2025-01-01",
            "2026-01-01",
            value
        ), /Initial investment/);
    }
});


test("sends the historical backtest API request", async () => {
    const payload = buildBacktestPayload(
        allocation,
        "2025-01-01",
        "2026-01-01",
        "1000"
    );

    const result = await requestBacktest(
        payload,
        async (url, options) => {
            assert.equal(url, "/api/backtest");
            assert.equal(options.method, "POST");

            assert.deepEqual(
                JSON.parse(options.body),
                payload
            );

            return {
                ok: true,
                json: async () => ({ trajectory })
            };
        }
    );

    assert.deepEqual(result, { trajectory });
});


test("reports API validation errors", async () => {
    await assert.rejects(
        requestBacktest({}, async () => ({
            ok: false,

            json: async () => ({
                detail: [
                    { msg: "Invalid allocation" }
                ]
            })
        })),

        /Invalid allocation/
    );
});


test("chart points respect date spacing and value direction", () => {
    const chart = backtestChartLayout(
        trajectory,
        "value",
        400
    );

    const [first, second, third] = chart.points;

    assert.equal(first.x, chart.left);
    assert.equal(third.x, chart.right);

    assert.equal(
        second.x,
        chart.left + (chart.right - chart.left) / 4
    );

    assert.ok(second.y < first.y);
    assert.ok(third.y > first.y);
});


test("drawdown is below zero and flat histories remain finite", () => {
    const chart = backtestChartLayout(
        trajectory,
        "drawdown",
        400
    );

    assert.equal(chart.points[0].y, chart.top);
    assert.equal(chart.points[2].y, chart.bottom);

    const flat = backtestChartLayout(
        trajectory.map(row => ({
            ...row,
            drawdown: 0
        })),
        "drawdown",
        280
    );

    assert.ok(
        flat.points.every(point => Number.isFinite(point.y))
    );

    assert.equal(flat.points[2].y, flat.top);
});