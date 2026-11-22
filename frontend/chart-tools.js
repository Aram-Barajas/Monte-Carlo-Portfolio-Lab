// Interactive inspection of the projected portfolio chart.

function nearestChartIndex(position, left, right, count) {
    if (count <= 1 || right <= left) {
        return 0;
    }

    const fraction = Math.max(
        0,
        Math.min(1, (position - left) / (right - left))
    );

    return Math.round(fraction * (count - 1));
}

function attachChartInspection({
    chart, bands, otherBands, left, right,
    top, bottom, x, y, svg
}) {
    const slider = document.getElementById("chart-day");
    const find = id => document.getElementById(id);

    const guide = svg("line", {
        y1: top,
        y2: bottom,
        class: "chart-guide"
    });

    const marker = svg("circle", {
        r: 5,
        class: "chart-marker"
    });

    const comparisonMarker = otherBands
        ? svg("circle", {
            r: 5,
            class: "chart-marker chart-marker-b"
        })
        : null;

    find("chart-value-b-row").hidden = !otherBands;

    const format = new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: "USD",
        maximumFractionDigits: 0
    });

    function select(index) {
        index = Math.max(
            0,
            Math.min(bands.length - 1, index)
        );

        const point = bands[index];
        const day = point.trading_day;
        const position = x(day);

        const time =
            `Day ${day.toLocaleString("en-US")} | ` +
            `${(day / 252).toFixed(2)} years`;

        slider.value = String(index);

        slider.setAttribute(
            "aria-valuetext",
            `${time}, median ${format.format(point.median)}`
        );

        find("chart-day-label").textContent = time;

        for (const key of [
            "p05", "p25", "median", "p75", "p95"
        ]) {
            find("chart-value-" + key).textContent =
                format.format(point[key]);
        }

        guide.setAttribute("x1", position);
        guide.setAttribute("x2", position);

        marker.setAttribute("cx", position);
        marker.setAttribute("cy", y(point.median));

        if (comparisonMarker) {
            const other = otherBands[index];

            comparisonMarker.setAttribute("cx", position);
            comparisonMarker.setAttribute("cy", y(other.median));

            find("chart-value-b").textContent =
                format.format(other.median);

        } else {
            find("chart-value-b").textContent = "";
        }
    }

    function inspectPointer(event) {
        const matrix = chart.getScreenCTM();

        if (!matrix) {
            return;
        }

        const point = chart.createSVGPoint();

        point.x = event.clientX;
        point.y = event.clientY;

        const local = point.matrixTransform(
            matrix.inverse()
        );

        if (
            local.x < left ||
            local.x > right ||
            local.y < top ||
            local.y > bottom
        ) {
            return;
        }

        select(
            nearestChartIndex(
                local.x,
                left,
                right,
                bands.length
            )
        );
    }

    chart.onpointermove = event => {
        if (event.pointerType !== "touch") {
            inspectPointer(event);
        }
    };

    chart.onpointerdown = inspectPointer;

    slider.oninput = () =>
        select(Number(slider.value));

    select(Number(slider.value));
}

if (typeof module !== "undefined" && module.exports) {
    module.exports = {
        nearestChartIndex,
        attachChartInspection
    };
}