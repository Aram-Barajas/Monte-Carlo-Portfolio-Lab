// Efficient frontier visualization and allocation inspector.

function buildFrontierPayload(
    allocation,
    start,
    end,
    cap,
    riskFree
) {
    const maxWeight = Number(cap) / 100;
    const rate = Number(riskFree) / 100;

    if (!start || !end || start >= end) {
        throw new Error(
            "Select a valid historical date range."
        );
    }

    if (
        !cap.trim() ||
        !Number.isFinite(maxWeight) ||
        maxWeight <= 0 ||
        maxWeight > 1
    ) {
        throw new Error(
            "Maximum asset weight must be between 0 and 100% (exclusive of 0)."
        );
    }

    if (
        !riskFree.trim() ||
        !Number.isFinite(rate)
    ) {
        throw new Error(
            "Enter a finite risk-free rate."
        );
    }

    return {
        ...allocation,
        start,
        end,
        max_weight: maxWeight,
        annual_risk_free_rate: rate,
        points: 25
    };
}


async function requestFrontier(payload, fetcher = fetch) {

    const response = await fetcher("/api/frontier", {
        method: "POST",

        headers: {
            "Content-Type": "application/json"
        },

        body: JSON.stringify(payload)
    });

    const data = await response.json();

    if (!response.ok) {

        const detail = Array.isArray(data.detail)
            ? data.detail.map(item => item.msg).join("; ")
            : data.detail;

        throw new Error(
            detail || "Efficient frontier request failed."
        );
    }

    return data;
}


function frontierLayout(data, width) {

    const left = 64;
    const right = width - 20;
    const top = 20;
    const bottom = 235;

    const portfolios = [
        ...data.frontier,
        data.current,
        data.maximum_sharpe
    ].filter(Boolean);

    const maxRisk = Math.max(
        .01,
        ...portfolios.map(p => p.annualized_volatility)
    ) * 1.08;

    const returns = portfolios.map(
        p => p.annualized_return
    );

    const low = Math.min(...returns);
    const high = Math.max(...returns);

    const padding = Math.max(
        .005,
        (high - low) * .08
    );

    const minReturn = low - padding;
    const maxReturn = high + padding;

    const x = risk =>
        left +
        risk / maxRisk *
        (right - left);

    const y = value =>
        bottom -
        (value - minReturn) /
        (maxReturn - minReturn) *
        (bottom - top);

    function point(p) {

        return {
            x: x(p.annualized_volatility),
            y: y(p.annualized_return)
        };
    }

    return {
        left,
        right,
        top,
        bottom,

        curve: data.frontier.map(point),

        current: point(data.current),

        sharpe: data.maximum_sharpe
            ? point(data.maximum_sharpe)
            : null,

        xTicks: Array.from(
            { length: 5 },
            (_, i) => ({
                value: maxRisk * i / 4,
                x: x(maxRisk * i / 4)
            })
        ),

        yTicks: Array.from(
            { length: 5 },
            (_, i) => {

                const value =
                    minReturn +
                    (maxReturn - minReturn) * i / 4;

                return {
                    value,
                    y: y(value)
                };
            }
        )
    };
}


function drawFrontier(chart, data, selected) {

    const width = Math.max(
        280,
        chart.clientWidth
    );

    const layout = frontierLayout(
        data,
        width
    );

    chart.setAttribute(
        "viewBox",
        `0 0 ${width} 285`
    );

    chart.replaceChildren();

    function svg(tag, attrs, text) {

        const node = document.createElementNS(
            "http://www.w3.org/2000/svg",
            tag
        );

        for (const [key, value] of Object.entries(attrs)) {
            node.setAttribute(key, value);
        }

        if (text !== undefined) {
            node.textContent = text;
        }

        chart.append(node);
    }

    for (const tick of layout.yTicks) {

        svg("line", {
            x1: layout.left,
            x2: layout.right,
            y1: tick.y,
            y2: tick.y
        });

        svg("text", {
            x: layout.left - 6,
            y: tick.y + 4,
            "text-anchor": "end"
        }, percent(tick.value));
    }

    for (const tick of layout.xTicks) {

        svg("text", {
            x: tick.x,
            y: 254,
            "text-anchor": "middle"
        }, percent(tick.value));
    }

    svg("text", {
        x: (layout.left + layout.right) / 2,
        y: 277,
        "text-anchor": "middle"
    }, "Annualized volatility");

    svg("polyline", {

        points: layout.curve.map(
            p => `${p.x},${p.y}`
        ).join(" "),

        class: "frontier-line"
    });

    function marker(p, className, r) {

        svg("circle", {
            cx: p.x,
            cy: p.y,
            r,
            class: className
        });
    }

    layout.curve.forEach(
        p => marker(p, "frontier-point", 2.5)
    );

    marker(
        layout.current,
        "frontier-current",
        5
    );

    if (layout.sharpe) {

        marker(
            layout.sharpe,
            "frontier-sharpe",
            5
        );
    }

    marker(
        layout.curve[selected],
        "frontier-selected",
        7
    );
}


function initFrontierDashboard() {

    const button = $("run-frontier");
    const status = $("frontier-status");

    const select = $("frontier-select");

    let last = null;

    function inspect() {

        if (!last) return;

        const index = Number(select.value);

        const point = last.frontier[index];

        $("frontier-point-summary").textContent =
            `Annual return: ${percent(point.annualized_return)} | ` +
            `Volatility: ${percent(point.annualized_volatility)}`;

        $("frontier-weights").replaceChildren(

            ...Object.entries(point.weights).map(
                ([ticker, weight]) => {

                    const row = element("tr");

                    const header = element(
                        "th",
                        ticker
                    );

                    header.scope = "row";

                    row.append(
                        header,
                        element("td", percent(weight))
                    );

                    return row;
                }
            )
        );

        drawFrontier(
            $("frontier-chart"),
            last,
            index
        );
    }

    select.addEventListener("change", inspect);

    window.addEventListener("resize", inspect);

    button.addEventListener("click", async () => {

        button.disabled = true;
        status.className = "muted";

        try {

            const payload = buildFrontierPayload(
                getAllocation("allocation"),

                $("start").value,

                $("end").value,

                $("frontier-cap").value,

                $("frontier-rate").value
            );

            status.textContent =
                "Calculating efficient portfolios...";

            const data = await requestFrontier(
                payload
            );

            const options = data.frontier.map(
                (point, i) => {

                    const option = element(
                        "option",

                        `${i + 1}: ` +
                        `${percent(point.annualized_return)} return | ` +
                        `${percent(point.annualized_volatility)} risk`
                    );

                    option.value = String(i);

                    return option;
                }
            );

            select.replaceChildren(...options);

            select.value = "0";

            $("frontier-summary").textContent =
                `${data.observations.toLocaleString()} daily returns | ` +
                `${data.frontier.length} frontier points | ` +
                `${percent(data.max_weight)} cap | ` +
                `${percent(data.annual_risk_free_rate)} risk-free rate`;

            $("frontier-warning").textContent = [

                data.current_respects_max_weight
                    ? ""
                    : "Current allocation exceeds the selected cap.",

                data.maximum_sharpe_unavailable_reason || ""

            ].filter(Boolean).join(" ");

            $("frontier-sharpe-legend").hidden =
                !data.maximum_sharpe;

            last = data;

            $("frontier-results").hidden = false;
            $("empty").hidden = true;

            inspect();

            status.textContent =
                "Frontier complete. Results reflect submitted settings.";

            $("frontier-results").scrollIntoView({
                block: "start"
            });

        } catch (error) {

            status.className = "muted error";

            status.textContent =
                error.message +
                " Previous frontier results are unchanged.";

        } finally {

            button.disabled = false;
        }
    });
}


if (typeof module !== "undefined" && module.exports) {

    module.exports = {
        buildFrontierPayload,
        requestFrontier,
        frontierLayout
    };

} else {

    initFrontierDashboard();
}