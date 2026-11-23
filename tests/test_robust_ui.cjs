const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const { buildRobustPayload, requestRobust } = require("../frontend/robust-optimization.js");
const allocation = { tickers: ["A", "B"], weights: { A: .6, B: .4 } };
const settings = { cap: "70", turnover: "25", aversion: "5", mean: "50", covariance: "25", holdout: "25", rate: "4" };

test("robust optimization payload converts percentages and checks constraints", () => {
    const build = overrides => buildRobustPayload(allocation, "2023-01-01", "2026-01-01", { ...settings, ...overrides });
    assert.deepEqual(build(), { ...allocation, start: "2023-01-01", end: "2026-01-01",
        max_weight: .7, max_turnover: .25, risk_aversion: 5, mean_shrinkage: .5,
        covariance_shrinkage: .25, holdout_fraction: .25, annual_risk_free_rate: .04 });
    assert.throws(() => build({ cap: 49 }), /too low/);
    assert.throws(() => build({ cap: 50, turnover: 5 }), /Turnover limit/);
    assert.throws(() => build({ mean: "" }), /Mean shrinkage/);
    assert.throws(() => build({ holdout: 51 }), /validation history/);
    assert.equal(build({ turnover: 0 }).max_turnover, 0);
});

test("robust API submits payload and reports validation errors", async () => {
    const payload = buildRobustPayload(allocation, "2023-01-01", "2026-01-01", settings);
    const data = await requestRobust(payload, async (url, options) => {
        assert.equal(url, "/api/robust-optimize");
        assert.deepEqual(JSON.parse(options.body), payload);
        return { ok: true, json: async () => ({ robust: {} }) };
    });
    assert.deepEqual(data, { robust: {} });
    await assert.rejects(requestRobust(payload, async () => ({
        ok: false, json: async () => ({ detail: [{ msg: "Insufficient history" }] })
    })), /Insufficient history/);
});

test("dashboard renders validation results and retains them after failed requests", async () => {
    const nodes = new Map();
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
    const performance = { total_return: -.1, annualized_return: -.2, annualized_volatility: .3, sharpe_ratio: null };
    const strategy = { weights: allocation.weights, turnover: .1, training: performance, holdout: performance };
    const data = { ...buildRobustPayload(allocation, "2023-01-01", "2026-01-01", settings),
        training_period: { start: "2023-01-03", end: "2025-01-01", observations: 500 },
        holdout_period: { start: "2025-01-02", end: "2025-12-31", observations: 250 },
        current_respects_max_weight: false, current: strategy, traditional: strategy, robust: strategy };
    let fail = false;
    const context = vm.createContext({ $, element: (tag, value) => node(value),
        percent: value => (value * 100).toFixed(2) + "%", getAllocation: () => allocation,
        fetch: async () => ({ ok: !fail, json: async () => fail ? { detail: "Unavailable" } : data }) });
    vm.runInContext(fs.readFileSync(require.resolve("../frontend/robust-optimization.js"), "utf8"), context);
    for (const [id, value] of Object.entries({ start: "2023-01-01", end: "2026-01-01",
        "frontier-cap": settings.cap, "frontier-rate": settings.rate, "robust-turnover": settings.turnover,
        "robust-aversion": settings.aversion, "robust-mean": settings.mean,
        "robust-covariance": settings.covariance, "robust-holdout": settings.holdout })) $(id).value = value;
    await $("run-robust").handlers.click();
    assert.equal($("robust-results").hidden, false);
    assert.match($("robust-summary").textContent, /Training:.*Validation:/);
    assert.match($("robust-warning").textContent, /exceeds/);
    assert.equal($("robust-validation").children[0].children[3].textContent, "-10.00%");
    assert.equal($("robust-validation").children[3].children[3].textContent, "N/A");
    fail = true;
    await $("run-robust").handlers.click();
    assert.equal($("robust-results").hidden, false);
    assert.match($("robust-status").textContent, /Unavailable.*Previous results are unchanged/);
});
