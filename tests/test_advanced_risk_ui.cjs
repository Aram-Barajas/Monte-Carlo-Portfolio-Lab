const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const { buildRiskPayload, buildCrisisPayload, requestAdvancedRisk, riskSeries } = require("../frontend/advanced-risk.js");
const { backtestChartLayout } = require("../frontend/backtest.js");
const allocation = { tickers: ["VTI"], weights: { VTI: 1 } };

test("risk and crisis payloads use independent settings", () => {
    assert.deepEqual(buildRiskPayload(allocation, "2023-01-01", "2026-01-01", "63"),
        { ...allocation, start: "2023-01-01", end: "2026-01-01", rolling_window: 63 });
    assert.deepEqual(buildCrisisPayload(allocation, "covid", "1000"),
        { ...allocation, scenario: "covid", initial_value: 1000 });
    assert.throws(() => buildRiskPayload(allocation, "", "2026-01-01", 63), /date range/);
    assert.throws(() => buildRiskPayload(allocation, "2023-01-01", "2026-01-01", 0), /rolling window/);
    assert.throws(() => buildCrisisPayload(allocation, "invalid", 1000), /crisis/);
    assert.throws(() => buildCrisisPayload(allocation, "covid", 0), /initial investment/);
});

test("risk API displays provider validation errors", async () => {
    const payload = buildCrisisPayload(allocation, "covid", 1000);
    const response = await requestAdvancedRisk("/api/crisis-replay", payload, async (url, options) => {
        assert.equal(url, "/api/crisis-replay");
        assert.deepEqual(JSON.parse(options.body), payload);
        return { ok: true, json: async () => ({ scenario: "covid" }) };
    });
    assert.equal(response.scenario, "covid");
    await assert.rejects(requestAdvancedRisk("/api/crisis-replay", payload,
        async () => ({ ok: false, json: async () => ({ detail: "Full crisis coverage required" }) })), /coverage/);
});

test("rolling chart preserves negative returns and percent-scale values", () => {
    const series = riskSeries([
        { date: "2025-01-01", trailing_return: -.12 },
        { date: "2025-01-02", trailing_return: .05 }
    ], "trailing_return");
    const layout = backtestChartLayout(series, "rate", 360);
    assert.equal(layout.ticks[0].value, -.12);
    assert.ok(Math.abs(layout.ticks.at(-1).value - .05) < 1e-10);
    assert.ok(layout.points.every(point => point.y >= layout.top && point.y <= layout.bottom));
});

test("dashboard renders signed contributions and preserves prior results on errors", async () => {
    const nodes = new Map(), draws = [];
    function node(text) {
        return { textContent: text, hidden: true, children: [], handlers: {},
            addEventListener(name, handler) { this.handlers[name] = handler; },
            replaceChildren(...children) { this.children = children; },
            append(...children) { this.children.push(...children); } };
    }
    const $ = id => {
        if (!nodes.has(id)) nodes.set(id, node());
        return nodes.get(id);
    };
    const risk = { weights: allocation.weights, observations: 2, first_return_date: "2025-01-02",
        last_return_date: "2025-01-03", annualized_volatility: .2, diversification_ratio: 1.5,
        assets: [{ ticker: "VTI", weight: 1, annualized_asset_volatility: .2,
            component_contribution: -.02, risk_share: -.1 }],
        rolling_window: 2, rolling: [{ date: "2025-01-03", trailing_return: -.1, annualized_volatility: .2 }] };
    const portfolio = { ending_value: 800, total_return: -.2, max_drawdown: .2,
        annualized_volatility: .3, trajectory: [{ date: "2020-02-19", value: 1000 }, { date: "2020-03-23", value: 800 }] };
    const crisis = { title: "COVID-19 sell-off", start: "2020-02-19", end: "2020-03-23",
        weights: allocation.weights, portfolio, benchmark: portfolio };
    let fail = false;
    const context = vm.createContext({ $, element: (tag, value) => node(value), metrics() {},
        percent: value => (value * 100).toFixed(2) + "%", money: value => "$" + value,
        getAllocation: () => allocation, drawBacktestChart: (...args) => draws.push(args),
        window: { addEventListener() {} }, fetch: async endpoint => ({
            ok: !fail, json: async () => fail ? { detail: "Incomplete history" } :
                endpoint === "/api/risk-analysis" ? risk : crisis
        }) });
    vm.runInContext(fs.readFileSync(require.resolve("../frontend/advanced-risk.js"), "utf8"), context);
    for (const [id, value] of Object.entries({ start: "2025-01-01", end: "2026-01-01",
        "rolling-window": "2", "crisis-scenario": "covid", initial: "1000" })) $(id).value = value;
    await $("run-risk-analysis").handlers.click();
    assert.equal($("advanced-risk-results").hidden, false);
    assert.equal($("risk-contributions").children[0].children[4].textContent, "-10.00%");
    assert.equal($("rolling-charts").hidden, true);
    assert.match($("rolling-summary").textContent, /Only one complete window/);
    await $("run-crisis").handlers.click();
    assert.equal($("crisis-results").hidden, false);
    assert.equal(draws.at(-1)[3].length, 2);
    fail = true;
    await $("run-crisis").handlers.click();
    assert.equal($("crisis-results").hidden, false);
    assert.match($("crisis-status").textContent, /Incomplete history.*Previous results are unchanged/);
});
