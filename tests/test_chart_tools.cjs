const test = require("node:test");
const assert = require("node:assert/strict");

const {
    nearestChartIndex,
    attachChartInspection
} = require("../frontend/chart-tools.js");

test("selects the nearest trading day", () => {
    assert.equal(nearestChartIndex(76, 76, 476, 401), 0);
    assert.equal(nearestChartIndex(276, 76, 476, 401), 200);
    assert.equal(nearestChartIndex(277.6, 76, 476, 401), 202);
    assert.equal(nearestChartIndex(476, 76, 476, 401), 400);
});

test("clamps positions and handles degenerate ranges", () => {
    assert.equal(nearestChartIndex(0, 76, 476, 401), 0);
    assert.equal(nearestChartIndex(600, 76, 476, 401), 400);
    assert.equal(nearestChartIndex(90, 76, 476, 1), 0);
    assert.equal(nearestChartIndex(90, 76, 76, 401), 0);
});

test("updates readouts, markers, and slider on chart interaction", () => {
    function node() {
        return {
            attrs: {},
            setAttribute(key, value) {
                this.attrs[key] = value;
            }
        };
    }

    const elements = new Map();

    const find = id => {
        if (!elements.has(id)) {
            elements.set(id, node());
        }

        return elements.get(id);
    };

    global.document = {
        getElementById: find
    };

    try {
        const slider = find("chart-day");

        slider.value = "2";

        const chart = {
            getScreenCTM: () => ({
                inverse: () => ({})
            }),

            createSVGPoint: () => ({
                matrixTransform() {
                    return this;
                }
            })
        };

        const bands = [0, 1, 2].map(day => ({
            trading_day: day,
            p05: 100 + day,
            p25: 200 + day,
            median: 300 + day,
            p75: 400 + day,
            p95: 500 + day
        }));

        const otherBands = bands.map(point => ({
            ...point,
            median: point.median + 100
        }));

        const svgNodes = [];

        const setup = {
            chart,
            bands,
            otherBands,

            left: 10,
            right: 30,
            top: 0,
            bottom: 100,

            x: day => 10 + day * 10,
            y: value => 100 - value / 10,

            svg() {
                const item = node();

                svgNodes.push(item);

                return item;
            }
        };

        attachChartInspection(setup);

        assert.equal(
            find("chart-value-median").textContent,
            "$302"
        );

        assert.equal(
            find("chart-value-b").textContent,
            "$402"
        );

        assert.equal(
            find("chart-value-b-row").hidden,
            false
        );

        chart.onpointermove({
            clientX: 20,
            clientY: 50,
            pointerType: "mouse"
        });

        assert.equal(slider.value, "1");

        assert.equal(
            find("chart-value-p05").textContent,
            "$101"
        );

        assert.equal(
            find("chart-value-p95").textContent,
            "$501"
        );

        assert.equal(svgNodes[0].attrs.x1, 20);
        assert.equal(svgNodes[1].attrs.cy, 69.9);
        assert.equal(svgNodes[2].attrs.cy, 59.9);

        chart.onpointerdown({
            clientX: 10,
            clientY: 50,
            pointerType: "touch"
        });

        assert.equal(slider.value, "0");

        slider.value = "2";
        slider.oninput();

        assert.match(
            slider.attrs["aria-valuetext"],
            /Day 2/
        );

        slider.value = "1";

        attachChartInspection({
            ...setup,
            otherBands: null
        });

        assert.equal(slider.value, "1");

        assert.equal(
            find("chart-value-b-row").hidden,
            true
        );

        assert.equal(
            find("chart-value-b").textContent,
            ""
        );

    } finally {
        delete global.document;
    }
});