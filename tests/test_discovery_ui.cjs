const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const { buildDiscoveryPayload, requestDiscovery } = require("../frontend/discovery.js");
const allocation = { tickers: ["VTI", "NVDA"], weights: { VTI: .8, NVDA: .2 } };
const settings = { candidates: "vxus, brk.b\nBND", weight: "10", objective: "volatility_reduction", holdout: "25", rate: "3" };
const build = overrides => buildDiscoveryPayload(allocation, "2023-01-01", "2026-01-01", { ...settings, ...overrides });

test("discovery payload normalizes candidate aliases, limits and percentages", () => {
    assert.deepEqual(build(), { ...allocation, start: "2023-01-01", end: "2026-01-01",
        candidates: ["VXUS", "BRK-B", "BND"], candidate_weight: .1, objective: "volatility_reduction",
        holdout_fraction: .25, annual_risk_free_rate: .03 });
    for (const candidates of ["", "BRK.B,BRK-B", "BAD SYMBOL", "A,B,C,D,E,F,G,H,I"]) {
        assert.throws(() => build({ candidates }), /candidate tickers/);
    }
    assert.throws(() => build({ weight: 0 }), /Candidate allocation/);
    assert.throws(() => build({ holdout: 51 }), /Reserved validation history/);
    assert.throws(() => build({ objective: "buy" }), /objective/);
});

test("discovery requests use expected endpoint and surface API errors", async () => {
    const payload = build();
    const result = await requestDiscovery(payload, async (url, options) => {
        assert.equal(url, "/api/discover");
        assert.deepEqual(JSON.parse(options.body), payload);
        return { ok: true, json: async () => ({ evaluated: [], excluded: [] }) };
    });
    assert.deepEqual(result, { evaluated: [], excluded: [] });
    await assert.rejects(requestDiscovery(payload, async () => ({
        ok: false, json: async () => ({ detail: [{ msg: "Choose more history" }] })
    })), /Choose more history/);
});

test("dashboard displays rankings, exclusions, holdout metrics and preserves entered allocation", async () => {
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
    const metric = { total_return: .1, annualized_return: .2, annualized_volatility: .3, max_drawdown: .1, sharpe_ratio: null };
    const comparison = { portfolio: metric, candidate: metric, candidate_correlation: -.1,
        deltas: { volatility_reduction: .02, return_improvement: -.01, sharpe_improvement: null } };
    const result = { ...build(), first_price_date: "2023-01-03", last_price_date: "2025-12-31",
        training_period: { start: "2023-01-04", end: "2025-01-01", observations: 500 },
        holdout_period: { start: "2025-01-02", end: "2025-12-31", observations: 250 },
        baseline: { training: metric, holdout: metric }, excluded: [{ ticker: "BND", reason: "Missing prices" }],
        evaluated: [{ ticker: "VXUS", rank: 1, weights: { VTI: .72, NVDA: .18, VXUS: .1 },
            training: comparison, holdout: { ...comparison, deltas: { ...comparison.deltas, volatility_reduction: -.02 } } }] };
    let fail = false;
    let excludeAll = false;
    const context = vm.createContext({ $, element: (tag, value) => node(value),
        percent: value => (value * 100).toFixed(2) + "%", getAllocation: () => allocation,
        fetch: async () => ({ ok: !fail, json: async () => fail ? { detail: "Unavailable" } :
            excludeAll ? { ...result, evaluated: [] } : result }) });
    for (const [key, value] of Object.entries(settings)) $("discovery-" + key).value = value;
    $("start").value = "2023-01-01"; $("end").value = "2026-01-01";
    $("allocation").value = "VTI, 80\nNVDA, 20";
    vm.runInContext(fs.readFileSync(require.resolve("../frontend/discovery.js"), "utf8"), context);
    await $("run-discovery").handlers.click();
    assert.equal($("discovery-results").hidden, false);
    assert.equal($("discovery-ranking").children[0].children[6].textContent, "-2.00 pp");
    assert.equal($("discovery-ranking").children[0].children[4].textContent, "N/A");
    assert.equal($("discovery-weights").children[2].children[2].textContent, "10.00%");
    assert.equal($("discovery-excluded").children[0].children[1].textContent, "Missing prices");
    assert.equal($("discovery-holdout-table").children.length, 6);
    assert.equal($("allocation").value, "VTI, 80\nNVDA, 20");
    fail = true;
    await $("run-discovery").handlers.click();
    assert.match($("discovery-status").textContent, /Unavailable.*Previous results are unchanged/);
    assert.equal($("discovery-results").hidden, false);
    fail = false; excludeAll = true;
    await $("run-discovery").handlers.click();
    assert.equal($("discovery-inspector").hidden, true);
    assert.match($("discovery-ranking-note").textContent, /No candidates/);
});
