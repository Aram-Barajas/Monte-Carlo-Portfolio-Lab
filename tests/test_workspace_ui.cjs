const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const {
    getWorkspaceView, applyWorkspaceView, updateWorkspaceEmpty,
    buildOverviewPayload, requestOverview
} = require("../frontend/workspace.js");

function mockWorkspace() {
    const views = ["overview", "simulation", "backtesting", "optimization", "stress", "risk", "planning", "validation"];
    const links = views.map(view => ({ dataset: { workspaceTab: view }, attrs: {},
        setAttribute(key, value) { this.attrs[key] = value; },
        removeAttribute(key) { delete this.attrs[key]; } }));
    const controls = ["overview simulation backtesting optimization risk planning validation", "simulation backtesting stress planning", ...views]
        .map(value => ({ dataset: { controls: value }, hidden: false, value: "preserved" }));
    const panels = views.map(view => ({ dataset: { resultView: view }, hidden: false }));
    const nodes = Object.fromEntries([
        "empty", "workspace-empty-title", "workspace-empty-description", "overview-results",
        "results", "backtest-results", "benchmark-results", "frontier-results", "stress-results",
        "crisis-results", "advanced-risk-results", "robust-results", "planning-results", "validation-results"
    ].map(id => [id, { hidden: true, textContent: "" }]));
    return { links, controls, panels, nodes, doc: {
        querySelectorAll(selector) {
            return { "[data-workspace-tab]": links, "[data-controls]": controls,
                "[data-result-view]": panels }[selector];
        },
        getElementById(id) { return nodes[id]; }
    } };
}

test("URL fragments select valid workspaces", () => {
    assert.equal(getWorkspaceView("#optimization"), "optimization");
    for (const fragment of ["", "#unknown", "#constructor"]) {
        assert.equal(getWorkspaceView(fragment), "overview");
    }
});

test("navigation reveals only relevant controls and preserves results and inputs", () => {
    const { links, controls, panels, nodes, doc } = mockWorkspace();
    nodes.results.hidden = false;
    applyWorkspaceView("stress", doc);
    assert.equal(links[4].attrs["aria-current"], "page");
    assert.equal(controls[0].hidden, true); // dates
    assert.equal(controls[1].hidden, false); // capital
    assert.equal(controls[3].hidden, true); // simulation
    assert.deepEqual(panels.map(panel => panel.hidden), [true, true, true, true, false, true, true, true]);
    assert.equal(nodes.results.hidden, false);
    assert.equal(nodes.empty.hidden, false);
    applyWorkspaceView("simulation", doc);
    assert.equal(controls[0].value, "preserved");
    assert.equal(controls[3].hidden, false);
    assert.equal(nodes.empty.hidden, true);
    applyWorkspaceView("validation", doc);
    assert.equal(controls[0].hidden, false);
    assert.equal(controls[1].hidden, true);
    assert.equal(links[7].attrs["aria-current"], "page");
    applyWorkspaceView("planning", doc);
    assert.equal(controls[0].hidden, false);
    assert.equal(controls[1].hidden, false);
    assert.equal(links[6].attrs["aria-current"], "page");
    assert.equal(nodes.empty.hidden, false);
    assert.equal(links[4].attrs["aria-current"], undefined);
    applyWorkspaceView("risk", doc);
    assert.equal(controls[0].hidden, false);
    assert.equal(controls[1].hidden, true);
    assert.equal(links[5].attrs["aria-current"], "page");
    assert.equal(nodes.empty.hidden, false);
    nodes["advanced-risk-results"].hidden = false;
    updateWorkspaceEmpty("risk", doc);
    assert.equal(nodes.empty.hidden, true);
});

test("background requests do not hide another view's empty state", () => {
    const { nodes, doc } = mockWorkspace();
    applyWorkspaceView("optimization", doc);
    nodes["backtest-results"].hidden = false;
    nodes.empty.hidden = true;
    updateWorkspaceEmpty("optimization", doc);
    assert.equal(nodes.empty.hidden, false);
    applyWorkspaceView("backtesting", doc);
    assert.equal(nodes.empty.hidden, true);
});

test("overview retrieves only historical portfolio data", async () => {
    const allocation = { tickers: ["VTI"], weights: { VTI: 1 } };
    const payload = buildOverviewPayload(allocation, "2025-01-01", "2026-01-01");
    assert.deepEqual(payload, { ...allocation, start: "2025-01-01", end: "2026-01-01" });
    assert.throws(() => buildOverviewPayload(allocation, "", "2026-01-01"), /date range/);
    const result = await requestOverview(payload, async (url, options) => {
        assert.equal(url, "/api/portfolio");
        assert.equal(options.method, "POST");
        assert.deepEqual(JSON.parse(options.body), payload);
        return { ok: true, json: async () => ({ observations: 252 }) };
    });
    assert.equal(result.observations, 252);
    await assert.rejects(requestOverview(payload, async () => ({ ok: false,
        json: async () => ({ detail: [{ msg: "Missing data" }] }) })), /Missing data/);
});

test("historical overview renders independently and simulation updates both views", () => {
    function node(text) {
        return { textContent: text, children: [], hidden: true, clientWidth: 800,
            addEventListener() {}, setAttribute() {},
            append(...items) { this.children.push(...items); },
            replaceChildren(...items) { this.children = items; } };
    }
    const nodes = new Map();
    const find = id => { if (!nodes.has(id)) nodes.set(id, node()); return nodes.get(id); };
    const context = vm.createContext({
        document: { getElementById: find, createElement: () => node(), createElementNS: () => node(), documentElement: { dataset: {} } },
        window: { matchMedia: () => ({ matches: false }), addEventListener() {} },
        localStorage: { getItem: () => "light" }, attachChartInspection() {}
    });
    vm.runInContext(fs.readFileSync(require.resolve("../frontend/app.js"), "utf8"), context);
    find("simulation-model").value = "block_bootstrap";
    context.updateSimulationModelControls();
    assert.equal(find("block-length-control").hidden, false);
    assert.equal(find("block-length").disabled, false);
    for (const [id, value] of Object.entries({ allocation: "VTI, 100", start: "2025-01-01",
        end: "2026-01-01", initial: "1000", monthly: "100", years: "1", paths: "500",
        confidence: "95", seed: "", "block-length": "10", "drift-weight": "50",
        rebalancing: "threshold", "rebalance-threshold": "5", "trading-cost-bps": "20",
        "annual-inflation": "3" })) {
        find(id).value = value;
    }
    find("initial").checkValidity = () => true;
    const submitted = context.getPayload();
    assert.equal(submitted.model, "block_bootstrap");
    assert.equal(submitted.block_length, 10);
    assert.equal(submitted.drift_weight, .5);
    assert.equal(submitted.seed, null);
    assert.equal(submitted.rebalancing, "threshold");
    assert.equal(submitted.rebalance_threshold, .05);
    assert.equal(submitted.trading_cost_bps, 20);
    assert.equal(submitted.annual_inflation, .03);
    context.updateRebalancingControls();
    assert.equal(find("rebalance-threshold-control").hidden, false);
    find("rebalancing").value = "buy_hold";
    context.updateRebalancingControls();
    assert.equal(find("rebalance-threshold-control").hidden, true);
    find("simulation-model").value = "gaussian";
    context.updateSimulationModelControls();
    assert.equal(find("block-length-control").hidden, true);
    assert.equal(find("block-length").disabled, true);
    assert.equal(context.getPayload().block_length, 5);
    const analysis = { tickers: ["VTI"], weights: { VTI: 1 }, observations: 252,
        portfolio_metrics: { annualized_return: .1, annualized_volatility: .2 },
        historical_risk: { sharpe_ratio: .5, max_drawdown: .12 },
        asset_metrics: [{ ticker: "VTI", annualized_return: .1, annualized_volatility: .2 }],
        correlation: [{ ticker: "VTI", VTI: 1 }] };
    const payload = { start: "2025-01-01", end: "2026-01-01" };
    context.renderHistoricalOverview(analysis, null, payload, "Historical analysis");
    assert.equal(find("overview-results").hidden, false);
    assert.equal(find("results").hidden, true);
    assert.equal(find("historical").children.length, 4);
    assert.equal(find("assets").children.length, 1);
    assert.match(find("overview-summary").textContent, /2025-01-01/);
    const band = { p05: 1000, p25: 1000, median: 1000, p75: 1000, p95: 1000 };
    const simulation = { analysis, num_simulations: 500, trading_days: 252,
        model: "block_bootstrap", drift_weight: .5, block_length: 5, seed: 42,
        rebalancing: "monthly", trading_cost_bps: 20, annual_inflation: .03, median_trading_costs: 12,
        real_percentiles: [{ ...band, trading_day: 0 }, { p05: 900, p25: 900, median: 900, p75: 900, p95: 900, trading_day: 252 }],
        simulation_risk: { median_ending_value: 1000, total_invested: 1000, probability_of_loss: .1,
            confidence: .95, terminal_var: 100, terminal_expected_shortfall: 200, mean_ending_value: 1000 },
        percentiles: [{ ...band, trading_day: 0 }, { ...band, trading_day: 252 }] };
    context.render(simulation, simulation, 42, payload);
    assert.equal(find("results").hidden, false);
    assert.equal(find("overview-results").hidden, false);
    assert.equal(find("correlation-b-panel").hidden, false);
    assert.match(find("simulation-input-summary").textContent, /B: VTI/);
    assert.match(find("simulation-model-summary").textContent, /Historical block bootstrap.*50.00%.*5-day blocks.*42/);
    assert.match(find("simulation-policy-summary").textContent, /Monthly.*20 bps.*3.00%/);
    find("chart-dollar-mode").value = "real";
    context.updateChartDollars();
    assert.match(find("chart-dollar-note").textContent, /Starting-dollar/);
    assert.equal(vm.runInContext("currentBands.at(-1).median", context), 900);
    find("chart-dollar-mode").value = "nominal";
    context.updateChartDollars();
    assert.equal(vm.runInContext("currentBands.at(-1).median", context), 1000);
    context.renderHistoricalOverview(analysis, null, payload, "Historical analysis");
    assert.equal(find("correlation-b-panel").hidden, true);
    assert.equal(find("comparison-results").hidden, false);
});
