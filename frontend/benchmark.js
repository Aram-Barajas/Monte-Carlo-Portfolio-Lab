// Historical benchmark comparison dashboard.

const benchmarkBacktestPayload =
    typeof module !== "undefined" && module.exports
        ? require("./backtest.js").buildBacktestPayload
        : buildBacktestPayload;


function buildBenchmarkPayload(
    allocation,
    start,
    end,
    initial,
    ticker
) {
    const benchmark = ticker.trim().toUpperCase();

    if (!/^[A-Z0-9^][A-Z0-9.\-=^]{0,19}$/.test(benchmark)) {
        throw new Error(
            "Enter a valid benchmark ticker, e.g. SPY."
        );
    }

    return {
        ...benchmarkBacktestPayload(
            allocation,
            start,
            end,
            initial
        ),
        benchmark
    };
}


async function requestBenchmark(payload, fetcher = fetch) {

    const response = await fetcher("/api/benchmark", {
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
            detail || "Benchmark comparison failed."
        );
    }

    return data;
}


function formatPercentagePoints(value) {

    const rounded = Number(
        (value * 100).toFixed(2)
    );

    return `${rounded > 0 ? "+" : ""}${rounded.toFixed(2)} pp`;
}


function initBenchmarkDashboard() {

    let lastBenchmark = null;

    const button = $("run-benchmark");
    const status = $("benchmark-status");

    function draw() {

        if (!lastBenchmark) {
            return;
        }

        drawBacktestChart(
            $("benchmark-chart"),
            lastBenchmark.portfolio.trajectory,
            "value",
            lastBenchmark.benchmark.trajectory
        );
    }

    button.addEventListener("click", async () => {

        button.disabled = true;

        status.className = "muted";

        try {

            const payload = buildBenchmarkPayload(
                getAllocation("allocation"),
                $("start").value,
                $("end").value,
                $("initial").value,
                $("benchmark-ticker").value
            );

            status.textContent =
                "Comparing historical performance...";

            const data = await requestBenchmark(payload);

            const a = data.portfolio;
            const b = data.benchmark;

            const sharpe = value =>
                value === null
                    ? "N/A"
                    : value.toFixed(2);

            const rows = [
                [
                    "Initial investment",
                    money(a.initial_value),
                    money(b.initial_value)
                ],
                [
                    "Ending value",
                    money(a.ending_value),
                    money(b.ending_value)
                ],
                [
                    "Total return",
                    percent(a.total_return),
                    percent(b.total_return)
                ],
                [
                    "CAGR",
                    percent(a.cagr),
                    percent(b.cagr)
                ],
                [
                    "Annualized volatility",
                    percent(a.annualized_volatility),
                    percent(b.annualized_volatility)
                ],
                [
                    "Maximum drawdown",
                    percent(a.max_drawdown),
                    percent(b.max_drawdown)
                ],
                [
                    "Sharpe ratio",
                    sharpe(a.sharpe_ratio),
                    sharpe(b.sharpe_ratio)
                ]
            ];

            const tableRows = rows.map(
                ([label, first, second]) => {

                    const row = element("tr");

                    const heading = element(
                        "th",
                        label
                    );

                    heading.scope = "row";

                    row.append(
                        heading,
                        element("td", first),
                        element("td", second)
                    );

                    return row;
                }
            );

            $("benchmark-table").replaceChildren(
                ...tableRows
            );

            $("benchmark-name").textContent =
                data.benchmark_ticker;

            $("benchmark-legend-name").textContent =
                data.benchmark_ticker;

            $("benchmark-period").textContent =
                `${a.trajectory[0].date} to ` +
                `${a.trajectory.at(-1).date} | ` +
                `${a.observations.toLocaleString()} daily returns`;

            $("benchmark-allocation").textContent =
                Object.entries(data.weights)
                    .map(([ticker, weight]) =>
                        `${ticker}: ${percent(weight)}`
                    ).join(" | ");

            $("benchmark-excess").textContent =
                `Portfolio A minus ${data.benchmark_ticker}: ` +
                `${formatPercentagePoints(data.excess_total_return)} total return | ` +
                `${formatPercentagePoints(data.excess_cagr)} CAGR`;

            lastBenchmark = data;

            $("benchmark-results").hidden = false;
            $("empty").hidden = true;

            draw();

            status.textContent =
                "Comparison complete. Results reflect submitted settings.";

            $("benchmark-results").scrollIntoView({
                block: "start"
            });

        } catch (error) {

            status.className = "muted error";

            status.textContent =
                error.message +
                " Previous benchmark results are unchanged.";

        } finally {

            button.disabled = false;
        }
    });

    window.addEventListener("resize", draw);
}


if (typeof module !== "undefined" && module.exports) {

    module.exports = {
        buildBenchmarkPayload,
        requestBenchmark,
        formatPercentagePoints
    };

} else {

    initBenchmarkDashboard();
}