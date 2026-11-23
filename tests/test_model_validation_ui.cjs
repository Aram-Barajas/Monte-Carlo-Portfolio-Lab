const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const { buildValidationPayload, requestValidation, validationChartLayout } = require("../frontend/model-validation.js");
const allocation = { tickers: ["VTI", "NVDA"], weights: { VTI: .8, NVDA: .2 } };
const settings = { training: "252", horizon: "21", folds: "12", paths: "500",
    drift: "100", block: "21", seed: "42" };
const build = overrides => buildValidationPayload(allocation, "2023-01-01", "2026-01-01", { ...settings, ...overrides });

test("validation payload checks historical windows and computational budget", () => {
    assert.deepEqual(build(), { ...allocation, start: "2023-01-01", end: "2026-01-01",
        training_days: 252, forecast_days: 21, max_folds: 12, num_simulations: 500, block_length: 21, drift_weight: 1, seed: 42 });
    assert.equal(build({ seed: "" }).seed, null);
    assert.throws(() => build({ folds: 2 }), /Maximum folds/);
    assert.throws(() => build({ training: 63, block: 64 }), /Block length cannot exceed/);
    assert.throws(() => build({ folds: 24, horizon: 252, paths: 1000 }), /too large/);
    assert.throws(() => build({ paths: 99 }), /Paths/);
});

test("validation endpoint submits parameters and surfaces errors", async () => {
    const payload = build();
    const data = await requestValidation(payload, async (url, options) => {
        assert.equal(url, "/api/validate-models");
        assert.deepEqual(JSON.parse(options.body), payload);
        return { ok: true, json: async () => ({ fold_count: 12 }) };
    });
    assert.equal(data.fold_count, 12);
    await assert.rejects(requestValidation(payload, async () => ({
        ok: false, json: async () => ({ detail: [{ msg: "Choose more history" }] })
    })), /Choose more history/);
});

test("chart includes actual outcomes outside simulated interval", () => {
    const models = { gaussian: { p05: -.1, p95: .1, median: 0 } };
    const folds = [{ actual_return: -.3, models }, { actual_return: .4, models }, { actual_return: .1, models }];
    const layout = validationChartLayout(folds, "gaussian", 360);
    assert.equal(layout.minimum, -.3);
    assert.equal(layout.maximum, .4);
    assert.equal(layout.x(2), layout.right);
    assert.ok(Math.abs(layout.y(.4) - layout.top) < 1e-9);
    assert.equal(layout.y(-.3), layout.bottom);
});

test("dashboard switches models and retains previous validation results on error", async () => {
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
    const scores = { coverage_50: .5, coverage_90: 1, coverage_90_wilson_reference: [.44, 1], below_05: 0, above_95: 0,
        mean_width_90: .2, mean_absolute_error: .05, median_bias: -.01, mean_crps: .03,
        mean_brier_loss: .1, pit_histogram: [0, 0, 0, 0, 0, 3, 0, 0, 0, 0] };
    const forecast = { p05: -.1, p95: .1, median: .02, probability_loss: .4, crps: .04 };
    const forecastModels = { gaussian: forecast, gaussian_uncertain: { ...forecast, median: .03 }, block_bootstrap: forecast };
    const data = { ...build(), fold_count: 3, observations: 750,
        models: { gaussian: scores, gaussian_uncertain: { ...scores, pit_histogram: [1, 2, 0, 0, 0, 0, 0, 0, 0, 0] }, block_bootstrap: scores },
        folds: [1, 2, 3].map(fold => ({ fold, training_start: "2023-01-01", training_end: "2024-01-01",
            forecast_start: "2024-01-02", forecast_end: "2024-02-01", actual_return: .1, models: forecastModels })) };
    let fail = false;
    const context = vm.createContext({ $, element: (tag, value) => node(value),
        percent: value => (value * 100).toFixed(2) + "%", getAllocation: () => allocation,
        document: { createElementNS: () => node() }, window: { addEventListener() {} },
        fetch: async () => ({ ok: !fail, json: async () => fail ? { detail: "Unavailable" } : data }) });
    for (const [key, value] of Object.entries(settings)) $("validation-" + key).value = value;
    $("start").value = "2023-01-01"; $("end").value = "2026-01-01";
    $("validation-model").value = "gaussian";
    vm.runInContext(fs.readFileSync(require.resolve("../frontend/model-validation.js"), "utf8"), context);
    await $("run-validation").handlers.click();
    assert.equal($("validation-results").hidden, false);
    assert.equal($("validation-scores").children.length, 10);
    assert.equal($("validation-fold-table").children[0].children[4].textContent, "2.00%");
    assert.equal($("validation-pit").children[5].children[1].textContent, "3");
    $("validation-model").value = "gaussian_uncertain";
    $("validation-model").handlers.change();
    assert.equal($("validation-fold-table").children[0].children[4].textContent, "3.00%");
    assert.equal($("validation-pit").children[0].children[1].textContent, "1");
    fail = true;
    await $("run-validation").handlers.click();
    assert.equal($("validation-results").hidden, false);
    assert.match($("validation-status").textContent, /Unavailable.*Previous results are unchanged/);
});
