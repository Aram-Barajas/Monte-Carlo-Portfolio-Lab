// Risk attribution and historical crisis replay.

function buildRiskPayload(allocation, start, end, window) {
    const rolling_window = Number(window);
    if (!start || !end || start >= end) throw new Error("Select a valid historical date range.");
    if (!Number.isInteger(rolling_window) || rolling_window < 2 || rolling_window > 252) {
        throw new Error("Select a valid rolling window.");
    }
    return { ...allocation, start, end, rolling_window };
}

function buildCrisisPayload(allocation, scenario, initial) {
    const initial_value = Number(initial);
    if (!["gfc", "covid", "bear_2022"].includes(scenario)) throw new Error("Select a crisis.");
    if (!Number.isFinite(initial_value) || initial_value <= 0 || initial_value > 1e9) {
        throw new Error("Enter a positive initial investment of up to $1 billion.");
    }
    return { ...allocation, scenario, initial_value };
}

async function requestAdvancedRisk(endpoint, payload, fetcher = fetch) {
    const response = await fetcher(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
    });
    const data = await response.json();
    if (!response.ok) {
        const detail = Array.isArray(data.detail) ? data.detail.map(item => item.msg).join("; ") : data.detail;
        throw new Error(detail || "Risk analysis failed.");
    }
    return data;
}

function riskSeries(rows, key) {
    return rows.map(row => ({ date: row.date, value: row[key] }));
}

function initAdvancedRisk() {
    let risk = null, crisis = null;
    const nullablePercent = value => value == null ? "N/A" : percent(value);
    const allocationSummary = weights => Object.entries(weights).map(([ticker, weight]) => ticker + " " + percent(weight)).join(", ");

    function rows(target, values) {
        $(target).replaceChildren(...values.map(values => {
            const row = element("tr");
            row.append(...values.map(value => element("td", value)));
            return row;
        }));
    }

    function draw() {
        if (risk && risk.rolling.length > 1 && !$("advanced-risk-results").hidden) {
            drawBacktestChart($("rolling-return-chart"), riskSeries(risk.rolling, "trailing_return"), "rate");
            drawBacktestChart($("rolling-volatility-chart"), riskSeries(risk.rolling, "annualized_volatility"), "rate");
        }
        if (crisis && !$("crisis-results").hidden) {
            drawBacktestChart($("crisis-chart"), crisis.portfolio.trajectory, "value", crisis.benchmark.trajectory);
        }
    }

    function renderRisk(data) {
        $("advanced-risk-summary").textContent = data.first_return_date + " to " + data.last_return_date +
            " | " + data.observations + " daily returns | " + allocationSummary(data.weights);
        metrics("advanced-risk-metrics", [
            ["Annualized portfolio volatility", percent(data.annualized_volatility)],
            ["Diversification ratio", data.diversification_ratio == null ? "N/A" : data.diversification_ratio.toFixed(2)]
        ]);
        rows("risk-contributions", data.assets.map(asset => [
            asset.ticker, percent(asset.weight), percent(asset.annualized_asset_volatility),
            asset.component_contribution == null ? "N/A" : (asset.component_contribution * 100).toFixed(2),
            nullablePercent(asset.risk_share)
        ]));
        const last = data.rolling.at(-1);
        $("rolling-summary").textContent = last
            ? data.rolling_window + "-day window | Latest trailing return: " + percent(last.trailing_return) +
              " | Latest annualized volatility: " + percent(last.annualized_volatility)
            : "Not enough observations for the selected " + data.rolling_window + "-day rolling window.";
        $("rolling-charts").hidden = data.rolling.length < 2;
        if (data.rolling.length === 1) $("rolling-summary").textContent += " | Only one complete window; no trend chart.";
        $("advanced-risk-results").hidden = false;
        risk = data;
        draw();
    }

    function renderCrisis(data) {
        $("crisis-summary").textContent = data.title + " | " + data.start + " to " + data.end +
            " | " + allocationSummary(data.weights);
        rows("crisis-metrics", [
            ["Ending value", money(data.portfolio.ending_value), money(data.benchmark.ending_value)],
            ["Total return", percent(data.portfolio.total_return), percent(data.benchmark.total_return)],
            ["Maximum drawdown", percent(data.portfolio.max_drawdown), percent(data.benchmark.max_drawdown)],
            ["Annualized volatility", percent(data.portfolio.annualized_volatility), percent(data.benchmark.annualized_volatility)]
        ]);
        $("crisis-results").hidden = false;
        crisis = data;
        draw();
    }

    function bind(buttonId, statusId, endpoint, payload, render) {
        const button = $(buttonId), status = $(statusId);
        button.addEventListener("click", async () => {
            button.disabled = true;
            status.className = "muted";
            try {
                status.textContent = "Analyzing historical data...";
                render(await requestAdvancedRisk(endpoint, payload()));
                status.textContent = "Analysis complete. Results reflect submitted settings.";
            } catch (error) {
                status.className = "muted error";
                status.textContent = error.message + " Previous results are unchanged.";
            } finally {
                button.disabled = false;
            }
        });
    }
    bind("run-risk-analysis", "advanced-risk-status", "/api/risk-analysis",
        () => buildRiskPayload(getAllocation("allocation"), $("start").value, $("end").value, $("rolling-window").value), renderRisk);
    bind("run-crisis", "crisis-status", "/api/crisis-replay",
        () => buildCrisisPayload(getAllocation("allocation"), $("crisis-scenario").value, $("initial").value), renderCrisis);
    window.addEventListener("resize", draw);
}

if (typeof module !== "undefined" && module.exports) {
    module.exports = { buildRiskPayload, buildCrisisPayload, requestAdvancedRisk, riskSeries };
} else {
    initAdvancedRisk();
}
