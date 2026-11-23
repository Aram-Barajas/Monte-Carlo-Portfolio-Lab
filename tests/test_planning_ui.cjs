const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const { buildPlanningPayload, requestPlanning, planningChartLayout } = require("../frontend/planning.js");
const allocation = { tickers: ["VTI"], weights: { VTI: 1 } };
const settings = { years: "20", paths: "500", monthly: "100", goal: "100000",
    growth: "3", inflation: "2.5", probability: "80", model: "gaussian_uncertain",
    drift: "50", block: "21", seed: "42" };

test("goal planning payload validates dates, percentages and simulation size", () => {
    const build = overrides => buildPlanningPayload(allocation, "2023-01-01", "2026-01-01", "1000", { ...settings, ...overrides });
    assert.deepEqual(build(), { ...allocation, start: "2023-01-01", end: "2026-01-01",
        years: 20, num_simulations: 500, initial_value: 1000, monthly_contribution: 100,
        goal: 100000, contribution_growth: .03, annual_inflation: .025, target_probability: .8,
        model: "gaussian_uncertain", drift_weight: .5, block_length: 21, seed: 42 });
    assert.equal(build({ seed: "" }).seed, null);
    assert.equal(build({ model: "block_bootstrap", block: "5" }).block_length, 5);
    assert.throws(() => build({ goal: 0 }), /Goal/);
    assert.throws(() => build({ years: 41 }), /Years/);
    assert.throws(() => build({ probability: 100 }), /Desired success/);
    assert.throws(() => build({ years: 40, paths: 2000 }), /too large/);
});

test("goal API uses correct endpoint and reports errors", async () => {
    const payload = buildPlanningPayload(allocation, "2023-01-01", "2026-01-01", "1000", settings);
    const result = await requestPlanning(payload, async (url, options) => {
        assert.equal(url, "/api/plan");
        assert.deepEqual(JSON.parse(options.body), payload);
        return { ok: true, json: async () => ({ goal_probability: .8 }) };
    });
    assert.equal(result.goal_probability, .8);
    await assert.rejects(requestPlanning(payload, async () => ({
        ok: false, json: async () => ({ detail: [{ msg: "Reduce paths" }] })
    })), /Reduce paths/);
});

test("chart includes goal even above every simulated value", () => {
    const annual = [{ year: 0, p05: 1000, median: 1000, p95: 1000 },
        { year: 20, p05: 2000, median: 5000, p95: 10000 }];
    const layout = planningChartLayout(annual, 100000, 360);
    assert.equal(layout.max, 100000);
    assert.equal(layout.x(0), layout.left);
    assert.equal(layout.x(20), layout.right);
    assert.equal(layout.y(100000), layout.top);
    assert.equal(layout.y(0), layout.bottom);
});

test("dashboard updates modeled goal and preserves prior results on failed requests", async () => {
    const nodes = new Map();
    function node(text) {
        return { textContent: text, hidden: true, children: [], handlers: {}, clientWidth: 360,
            setAttribute() {}, addEventListener(name, handler) { this.handlers[name] = handler; },
            replaceChildren(...children) { this.children = children; },
            append(...children) { this.children.push(...children); } };
    }
    const $ = id => {
        if (!nodes.has(id)) nodes.set(id, node());
        return nodes.get(id);
    };
    const row = { year: 20, p05: 2000, median: 5000, p95: 10000, goal_probability: .1, nominal_contributed: 3500 };
    const data = { ...buildPlanningPayload(allocation, "2023-01-01", "2026-01-01", "1000", settings),
        observations: 750, goal_probability: .1, required_monthly_contribution: 250,
        required_contribution_probability: .8, nominal_goal: 150000, median_shortfall_when_missed: 95000,
        annual: [{ ...row, year: 0 }, row], sensitivity: [{ monthly_contribution: 250, goal_probability: .8, median_ending_real: 125000 }] };
    let fail = false;
    const context = vm.createContext({ $, element: (tag, value) => node(value),
        metrics: (id, rows) => { $(id).children = rows; }, money: value => "$" + value,
        percent: value => (value * 100).toFixed(2) + "%", getAllocation: () => allocation,
        document: { createElementNS: () => node() }, window: { addEventListener() {} },
        fetch: async () => ({ ok: !fail, json: async () => fail ? { detail: "Unavailable" } : data }) });
    for (const [key, value] of Object.entries(settings)) $("plan-" + key).value = value;
    $("start").value = "2023-01-01"; $("end").value = "2026-01-01"; $("initial").value = "1000";
    vm.runInContext(fs.readFileSync(require.resolve("../frontend/planning.js"), "utf8"), context);
    await $("run-plan").handlers.click();
    assert.equal($("planning-results").hidden, false);
    assert.equal($("plan-annual").children.length, 2);
    assert.equal($("plan-sensitivity").children[0].children[1].textContent, "80.00%");
    assert.match($("plan-summary").textContent, /20 years.*seed 42/);
    assert.ok($("plan-chart").children.length > 0);
    $("plan-model").value = "block_bootstrap";
    $("plan-model").handlers.change();
    assert.equal($("plan-block").hidden, false);
    fail = true;
    await $("run-plan").handlers.click();
    assert.equal($("planning-results").hidden, false);
    assert.match($("plan-status").textContent, /Unavailable.*Previous results are unchanged/);
});
