const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const {
    buildStressPayload,
    requestStressTest
} = require("../frontend/stress-test.js");


const allocation = {
    tickers: ["VTI", "NVDA"],

    weights: {
        VTI: 0.6,
        NVDA: 0.4
    }
};


test("default stress payload omits simulation settings", () => {

    assert.deepEqual(
        buildStressPayload(allocation, "10000"),
        {
            weights: allocation.weights,
            initial_value: 10000
        }
    );
});


test("converts custom percentages into fractional asset shocks", () => {

    assert.deepEqual(
        buildStressPayload(
            allocation,
            "10000",
            "vti, -10\nNVDA, -35"
        ).scenarios,
        {
            "Custom asset shock": {
                VTI: -0.1,
                NVDA: -0.35
            }
        }
    );
});


test("rejects invalid investments and custom shocks", () => {

    for (const value of [
        "", "0", "-10", "Infinity", "1000000001"
    ]) {

        assert.throws(
            () => buildStressPayload(allocation, value),
            /Initial investment/
        );
    }

    for (const text of [
        "",
        "VTI, 101",
        "NVDA, -101",
        "VTI, NaN",
        "VTI, -10\nVTI, -20"
    ]) {

        assert.throws(
            () => buildStressPayload(
                allocation,
                "1000",
                text
            )
        );
    }
});


test("sends stress API payload and reports validation errors", async () => {

    const payload = buildStressPayload(
        allocation,
        "10000"
    );

    const body = await requestStressTest(
        payload,
        async (url, options) => {

            assert.equal(url, "/api/stress-test");
            assert.equal(options.method, "POST");

            assert.deepEqual(
                JSON.parse(options.body),
                payload
            );

            return {
                ok: true,
                json: async () => ({ scenarios: [] })
            };
        }
    );

    assert.deepEqual(body, { scenarios: [] });

    await assert.rejects(
        requestStressTest(payload, async () => ({
            ok: false,

            json: async () => ({
                detail: [
                    { msg: "Missing ticker" }
                ]
            })
        })),

        /Missing ticker/
    );
});


test("dashboard renders results, handles scenario selection and preserves results on errors", async () => {

    function node(text) {

        return {
            textContent: text,
            children: [],
            handlers: {},

            addEventListener(name, handler) {
                this.handlers[name] = handler;
            },

            replaceChildren(...children) {
                this.children = children;
            },

            append(...children) {
                this.children.push(...children);
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

    $("initial").value = "10000";

    $("stress-custom-enabled").checked = false;

    const scenarios = [-0.1, -0.2].map(shock => ({
        name: String(shock),

        portfolio_return: shock,

        ending_value: 10000 * (1 + shock),

        value_change: 10000 * shock,

        assets: [
            {
                ticker: "VTI",
                weight: 1,
                shock,
                value_change: 10000 * shock
            }
        ]
    }));

    let fail = false;

    vm.runInNewContext(
        fs.readFileSync(
            require.resolve("../frontend/stress-test.js"),
            "utf8"
        ),
        {
            $,

            element: (tag, text) => node(text),

            getAllocation: () => allocation,

            money: value => "$" + value,

            percent: value =>
                (value * 100).toFixed(2) + "%",

            fetch: async () => ({
                ok: !fail,

                json: async () => fail
                    ? { detail: "Request failed" }
                    : {
                        initial_value: 10000,
                        weights: allocation.weights,
                        scenarios
                    }
            })
        }
    );

    await $("run-stress-test").handlers.click();

    assert.equal(
        $("stress-results").hidden,
        false
    );

    assert.equal(
        $("stress-scenarios").children.length,
        2
    );

    assert.equal(
        $("stress-assets").children[0].children[2].textContent,
        "-10.00%"
    );

    $("stress-scenario-select").value = "1";

    $("stress-scenario-select").handlers.change();

    assert.equal(
        $("stress-assets").children[0].children[2].textContent,
        "-20.00%"
    );

    $("stress-custom-enabled").checked = true;

    $("stress-custom-enabled").handlers.change();

    assert.equal(
        $("stress-custom-input").hidden,
        false
    );

    $("stress-shocks").value = "VTI, -10\nNVDA, -20";

    fail = true;

    await $("run-stress-test").handlers.click();

    assert.equal(
        $("stress-status").textContent,
        "Request failed"
    );

    assert.equal(
        $("stress-scenarios").children.length,
        2
    );

    assert.equal(
        $("run-stress-test").disabled,
        false
    );
});