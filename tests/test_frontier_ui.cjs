const test = require("node:test");
const assert = require("node:assert/strict");

const fs = require("node:fs");
const vm = require("node:vm");

const {
    buildFrontierPayload,
    requestFrontier,
    frontierLayout
} = require("../frontend/frontier.js");


const allocation = {
    tickers: ["A", "B"],
    weights: { A: .5, B: .5 }
};

const start = "2025-01-01";
const end = "2026-01-01";

const payload = buildFrontierPayload(
    allocation,
    start,
    end,
    "60",
    "4"
);


test("frontier payload converts percentages and validates settings", () => {

    assert.deepEqual(payload, {
        ...allocation,
        start,
        end,
        max_weight: .6,
        annual_risk_free_rate: .04,
        points: 25
    });

    for (const cap of [
        "",
        "0",
        "101",
        "Infinity"
    ]) {

        assert.throws(() => buildFrontierPayload(
            allocation,
            start,
            end,
            cap,
            "4"
        ), /weight/);
    }

    assert.throws(() => buildFrontierPayload(
        allocation,
        end,
        start,
        "60",
        "4"
    ), /date/);

    assert.throws(() => buildFrontierPayload(
        allocation,
        start,
        end,
        "60",
        ""
    ), /risk-free/);
});


test("frontier endpoint and error handling", async () => {

    await requestFrontier(
        payload,
        async (url, options) => {

            assert.equal(url, "/api/frontier");

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
        requestFrontier(payload, async () => ({
            ok: false,

            json: async () => ({
                detail: [{ msg: "Invalid cap" }]
            })
        })),

        /Invalid cap/
    );
});


const first = {
    weights: { A: .6, B: .4 },

    annualized_return: -.1,

    annualized_volatility: .1
};

const second = {
    weights: { A: .4, B: .6 },

    annualized_return: .2,

    annualized_volatility: .2
};

const data = {
    frontier: [first, second],

    current: first,

    maximum_sharpe: second,

    current_respects_max_weight: true,

    observations: 252,

    max_weight: .6,

    annual_risk_free_rate: .04
};


test("risk and return axes place both portfolios correctly", () => {

    const layout = frontierLayout(
        data,
        400
    );

    assert.ok(
        layout.curve[0].x < layout.curve[1].x
    );

    assert.ok(
        layout.curve[0].y > layout.curve[1].y
    );

    assert.deepEqual(
        layout.sharpe,
        layout.curve[1]
    );

    const flat = {
        annualized_return: 0,
        annualized_volatility: 0
    };

    const single = frontierLayout({
        frontier: [flat],

        current: flat,

        maximum_sharpe: null
    }, 280);

    assert.ok(
        Number.isFinite(single.curve[0].x) &&
        Number.isFinite(single.curve[0].y)
    );
});


test("frontier dashboard renders and inspects weights, preserving results on error", async () => {

    function node(text) {

        return {
            textContent: text,
            children: [],
            handlers: {},
            hidden: true,
            clientWidth: 400,

            addEventListener(name, handler) {
                this.handlers[name] = handler;
            },

            append(...args) {
                this.children.push(...args);
            },

            replaceChildren(...args) {
                this.children = args;
            },

            setAttribute() { },

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

    $("frontier-cap").value = "60";
    $("frontier-rate").value = "4";

    let fail = false;

    vm.runInNewContext(

        fs.readFileSync(
            require.resolve("../frontend/frontier.js"),
            "utf8"
        ),

        {
            $,

            getAllocation: () => allocation,

            element: (tag, text) => node(text),

            percent: v =>
                (v * 100).toFixed(2) + "%",

            document: {
                createElementNS: () => node()
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

    await $("run-frontier").handlers.click();

    assert.equal(
        $("frontier-results").hidden,
        false
    );

    assert.equal(
        $("frontier-select").children.length,
        2
    );

    assert.equal(
        $("frontier-weights").children[0].children[1].textContent,
        "60.00%"
    );

    $("frontier-select").value = "1";

    $("frontier-select").handlers.change();

    assert.equal(
        $("frontier-weights").children[0].children[1].textContent,
        "40.00%"
    );

    fail = true;

    await $("run-frontier").handlers.click();

    assert.equal(
        $("frontier-select").value,
        "1"
    );

    assert.match(
        $("frontier-status").textContent,
        /Previous frontier results are unchanged/
    );

    assert.equal(
        $("run-frontier").disabled,
        false
    );
});