// Historical portfolio backtesting dashboard.

function buildBacktestPayload(allocation, start, end, initial, policy = {}) {
    if (!start || !end || start >= end) {
        throw new Error("Select a valid historical date range.");
    }

    const initialValue = Number(initial);

    if (
        !initial ||
        !Number.isFinite(initialValue) ||
        initialValue <= 0 ||
        initialValue > 1000000000
    ) {
        throw new Error(
            "Initial investment must be between $0 (exclusive) and $1 billion."
        );
    }

    return {
        ...allocation,
        start,
        end,
        initial_value: initialValue,
        ...policy
    };
}


async function requestBacktest(payload, fetcher = fetch) {
    const response = await fetcher("/api/backtest", {
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
            detail || "Backtest request failed."
        );
    }

    return data;
}


function backtestChartLayout(
    trajectory,
    key,
    width,
    reference = []
) {
    const left = 70;
    const right = width - 24;

    const top = 15;
    const bottom = 215;

    const isDrawdown = key === "drawdown";

    const values = trajectory.map(row =>
        isDrawdown ? -row.drawdown : row.value
    );

    const referenceValues = reference.map(row =>
        isDrawdown ? -row.drawdown : row.value
    );

    const allValues = [
        ...values,
        ...referenceValues
    ];

    const dates = trajectory.map(row =>
        Date.parse(row.date)
    );

    const first = dates[0];
    const last = dates.at(-1);

    const min = isDrawdown
        ? Math.min(-0.01, ...allValues)
        : 0;

    const max = isDrawdown
        ? 0
        : Math.max(1, ...allValues);

    const x = date =>
        left +
        (date - first) / (last - first || 1) *
        (right - left);

    const y = value =>
        bottom -
        (value - min) / (max - min) *
        (bottom - top);

    return {
        left,
        right,
        top,
        bottom,

        points: values.map((value, index) => ({
            x: x(dates[index]),
            y: y(value)
        })),

        referencePoints: referenceValues.map(
            (value, index) => ({
                x: x(Date.parse(reference[index].date)),
                y: y(value)
            })
        ),

        ticks: Array.from(
            { length: 5 },
            (_, index) => {

                const value =
                    min + (max - min) * index / 4;

                return {
                    value,
                    y: y(value)
                };
            }
        )
    };
}


function drawBacktestChart(
    chart,
    trajectory,
    key,
    reference = []
) {
    const width = Math.max(
        280,
        chart.clientWidth
    );

    const layout = backtestChartLayout(
        trajectory,
        key,
        width,
        reference
    );

    chart.setAttribute(
        "viewBox",
        `0 0 ${width} 245`
    );

    chart.replaceChildren();

    function svg(tag, attrs, text) {
        const node = document.createElementNS(
            "http://www.w3.org/2000/svg",
            tag
        );

        for (const [name, value] of Object.entries(attrs)) {
            node.setAttribute(name, value);
        }

        if (text !== undefined) {
            node.textContent = text;
        }

        chart.append(node);
    }

    const compactMoney = new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: "USD",
        notation: "compact",
        maximumFractionDigits: 1
    });

    // Horizontal grid lines and labels.

    for (const tick of layout.ticks) {
        svg("line", {
            x1: layout.left,
            x2: layout.right,
            y1: tick.y,
            y2: tick.y
        });

        svg("text", {
            x: layout.left - 8,
            y: tick.y + 4,
            "text-anchor": "end"
        }, key === "drawdown"
            ? (tick.value * 100).toFixed(1) + "%"
            : compactMoney.format(tick.value)
        );
    }

    // Historical portfolio trajectory.

    svg("polyline", {
        points: layout.points.map(point =>
            `${point.x},${point.y}`
        ).join(" "),

        class: key === "drawdown"
            ? "backtest-drawdown"
            : "backtest-value"
    });

    if (layout.referencePoints.length) {

        svg("polyline", {

            points: layout.referencePoints.map(
                point => `${point.x},${point.y}`
            ).join(" "),

            class: "benchmark-value"
        });
    }

    // Historical date labels.

    svg("text", {
        x: layout.left,
        y: 238,
        "text-anchor": "start"
    }, trajectory[0].date);

    svg("text", {
        x: layout.right,
        y: 238,
        "text-anchor": "end"
    }, trajectory.at(-1).date);
}


function initBacktestDashboard() {
    let lastBacktest = null;

    const button = $("run-backtest");
    const status = $("backtest-status");

    function draw() {
        if (!lastBacktest) {
            return;
        }

        drawBacktestChart(
            $("backtest-value-chart"),
            lastBacktest.trajectory,
            "value"
        );

        drawBacktestChart(
            $("backtest-drawdown-chart"),
            lastBacktest.trajectory,
            "drawdown"
        );
    }

    button.addEventListener("click", async () => {
        button.disabled = true;

        status.className = "muted";

        try {
            const payload = buildBacktestPayload(
                getAllocation("allocation"),
                $("start").value,
                $("end").value,
                $("initial").value,
                getPortfolioPolicy()
            );

            status.textContent =
                "Replaying historical market prices...";

            const data = await requestBacktest(payload);

            metrics("backtest-metrics", [
                [
                    "Initial investment",
                    money(data.initial_value)
                ],
                [
                    "Ending value",
                    money(data.ending_value)
                ],
                ["Cumulative trading costs", money(data.trading_costs ?? 0)],
                [
                    "Cumulative return",
                    percent(data.total_return)
                ],
                [
                    "Compound annual growth rate (CAGR)",
                    percent(data.cagr)
                ],
                [
                    "Annualized volatility",
                    percent(data.annualized_volatility)
                ],
                [
                    "Maximum drawdown",
                    percent(data.max_drawdown)
                ],
                [
                    "Sharpe ratio",
                    data.sharpe_ratio === null
                        ? "N/A"
                        : data.sharpe_ratio.toFixed(2)
                ]
            ], true);

            $("backtest-period").textContent =
                `${data.trajectory[0].date} to ` +
                `${data.trajectory.at(-1).date} | ` +
                `${data.observations.toLocaleString()} daily returns`;

            $("backtest-allocation").textContent =
                Object.entries(data.weights)
                    .map(([ticker, weight]) =>
                        `${ticker}: ${percent(weight)}`
                    ).join(" | ") + ` | ${formatTradingPolicy(data)}`;

            lastBacktest = data;

            $("backtest-results").hidden = false;
            $("empty").hidden = true;

            draw();

            status.textContent =
                "Backtest complete. Results reflect the submitted Portfolio A settings.";

            $("backtest-results").scrollIntoView({
                block: "start"
            });

        } catch (error) {
            status.className = "muted error";

            status.textContent =
                error.message +
                " Previous backtest results are unchanged.";

        } finally {
            button.disabled = false;
        }
    });

    window.addEventListener("resize", draw);
}


if (typeof module !== "undefined" && module.exports) {
    module.exports = {
        buildBacktestPayload,
        requestBacktest,
        backtestChartLayout
    };

} else {
    initBacktestDashboard();
}
