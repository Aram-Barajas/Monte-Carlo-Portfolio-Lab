// Robust mean-variance allocation research and chronological holdout results.

function buildRobustPayload(allocation, start, end, settings) {
    if (!start || !end || start >= end) throw new Error("Select a valid historical date range.");
    function bounded(key, low, high, label) {
        const raw = settings[key];
        const value = Number(raw);
        if (raw == null || String(raw).trim() === "" || !Number.isFinite(value) || value < low || value > high) {
            throw new Error(label + " must be between " + low + " and " + high + ".");
        }
        return value;
    }
    const cap = bounded("cap", 0.01, 100, "Maximum asset weight") / 100;
    if (cap < 1 / allocation.tickers.length) throw new Error("Maximum asset weight is too low for this asset count.");
    const turnover = bounded("turnover", 0, 100, "Maximum turnover") / 100;
    const required = Object.values(allocation.weights).reduce((sum, weight) => sum + Math.max(0, weight - cap), 0);
    if (required > turnover + 1e-8) throw new Error("Turnover limit is too low to satisfy the maximum asset weight.");
    const rate = settings.rate;
    if (rate == null || String(rate).trim() === "" || !Number.isFinite(Number(rate))) {
        throw new Error("Enter a finite risk-free rate.");
    }
    return {
        ...allocation, start, end, max_weight: cap, max_turnover: turnover, annual_risk_free_rate: Number(rate) / 100,
        risk_aversion: bounded("aversion", .1, 100, "Risk aversion"),
        mean_shrinkage: bounded("mean", 0, 100, "Mean shrinkage") / 100,
        covariance_shrinkage: bounded("covariance", 0, 100, "Covariance shrinkage") / 100,
        holdout_fraction: bounded("holdout", 10, 50, "Reserved validation history") / 100
    };
}

async function requestRobust(payload, fetcher = fetch) {
    const response = await fetcher("/api/robust-optimize", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload)
    });
    const data = await response.json();
    if (!response.ok) {
        const detail = Array.isArray(data.detail) ? data.detail.map(item => item.msg).join("; ") : data.detail;
        throw new Error(detail || "Robust allocation research failed.");
    }
    return data;
}

function initRobustDashboard() {
    const button = $("run-robust"), status = $("robust-status");
    const nullable = value => value == null ? "N/A" : value.toFixed(2);
    function rows(id, values) {
        $(id).replaceChildren(...values.map(entries => {
            const row = element("tr");
            row.append(...entries.map(entry => element("td", entry)));
            return row;
        }));
    }
    function render(data) {
        const strategies = [data.current, data.traditional, data.robust];
        const period = p => p.start + " to " + p.end + " (" + p.observations + " returns)";
        $("robust-summary").textContent = "Training: " + period(data.training_period) +
            " | Validation: " + period(data.holdout_period) + " | Asset cap: " + percent(data.max_weight) +
            " | Turnover cap: " + percent(data.max_turnover) + " | Risk aversion: " + data.risk_aversion +
            " | Mean shrinkage: " + percent(data.mean_shrinkage) + " | Covariance shrinkage: " + percent(data.covariance_shrinkage) +
            " | Risk-free rate: " + percent(data.annual_risk_free_rate);
        $("robust-warning").textContent = data.current_respects_max_weight ? "" :
            "The original allocation exceeds the selected asset cap; only optimized allocations are constrained.";
        rows("robust-weights", [
            ...data.tickers.map(ticker => [ticker, ...strategies.map(strategy => percent(strategy.weights[ticker]))]),
            ["One-way turnover", ...strategies.map(strategy => percent(strategy.turnover))]
        ]);
        for (const [id, key] of [["robust-training", "training"], ["robust-validation", "holdout"]]) {
            rows(id, [
                ["Total return", ...strategies.map(s => percent(s[key].total_return))],
                ["Annualized arithmetic return", ...strategies.map(s => percent(s[key].annualized_return))],
                ["Annualized volatility", ...strategies.map(s => percent(s[key].annualized_volatility))],
                ["Sharpe ratio", ...strategies.map(s => nullable(s[key].sharpe_ratio))]
            ]);
        }
        $("robust-results").hidden = false;
    }
    button.addEventListener("click", async () => {
        button.disabled = true;
        status.className = "muted";
        try {
            const payload = buildRobustPayload(getAllocation("allocation"), $("start").value, $("end").value, {
                cap: $("frontier-cap").value, rate: $("frontier-rate").value, turnover: $("robust-turnover").value,
                aversion: $("robust-aversion").value, mean: $("robust-mean").value,
                covariance: $("robust-covariance").value, holdout: $("robust-holdout").value
            });
            status.textContent = "Fitting and validating allocations...";
            render(await requestRobust(payload));
            status.textContent = "Comparison complete. Results reflect submitted settings.";
        } catch (error) {
            status.className = "muted error";
            status.textContent = error.message + " Previous results are unchanged.";
        } finally {
            button.disabled = false;
        }
    });
}

if (typeof module !== "undefined" && module.exports) {
    module.exports = { buildRobustPayload, requestRobust };
} else {
    initRobustDashboard();
}
