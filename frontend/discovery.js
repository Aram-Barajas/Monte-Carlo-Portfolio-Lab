// Research hypothetical candidate additions; do not modify the current portfolio.

function buildDiscoveryPayload(allocation, start, end, settings) {
    if (!start || !end || start >= end) throw new Error("Select a valid historical date range.");
    if (allocation.tickers.length > 19) throw new Error("Screening supports up to 19 existing holdings.");
    const aliases = { "BRK.A": "BRK-A", "BRK.B": "BRK-B", "BF.B": "BF-B" };
    const candidates = String(settings.candidates ?? "").split(/[,\n]+/).map(value => value.trim().toUpperCase())
        .filter(Boolean).map(value => Object.hasOwn(aliases, value) ? aliases[value] : value);
    if (!candidates.length || candidates.length > 8 || new Set(candidates).size !== candidates.length ||
        candidates.some(ticker => !/^[A-Z0-9^][A-Z0-9.\-=^]{0,19}$/.test(ticker))) {
        throw new Error("Enter one to eight distinct valid candidate tickers.");
    }
    const objective = settings.objective;
    if (!["volatility_reduction", "sharpe_improvement", "return_improvement"].includes(objective)) {
        throw new Error("Select a screening objective.");
    }
    function numeric(key, low, high, label) {
        const raw = settings[key], value = Number(raw);
        if (raw == null || String(raw).trim() === "" || !Number.isFinite(value) || value < low || value > high) {
            throw new Error(label + " must be finite and within the allowed range.");
        }
        return value;
    }
    return {
        ...allocation, start, end, candidates, objective,
        candidate_weight: numeric("weight", 1, 50, "Candidate allocation") / 100,
        holdout_fraction: numeric("holdout", 10, 50, "Reserved validation history") / 100,
        annual_risk_free_rate: numeric("rate", -Infinity, Infinity, "Risk-free rate") / 100
    };
}

async function requestDiscovery(payload, fetcher = fetch) {
    const response = await fetcher("/api/discover", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload)
    });
    const data = await response.json();
    if (!response.ok) {
        const detail = Array.isArray(data.detail) ? data.detail.map(item => item.msg).join("; ") : data.detail;
        throw new Error(detail || "Candidate screening failed.");
    }
    return data;
}

function initDiscoveryDashboard() {
    const button = $("run-discovery"), status = $("discovery-status"), select = $("discovery-selected");
    let last = null;
    const decimal = value => value == null ? "N/A" : value.toFixed(2);
    const signed = value => value == null ? "N/A" : (value > 0 ? "+" : "") + value.toFixed(2);
    const pp = value => value == null ? "N/A" : signed(value * 100) + " pp";
    function rows(id, entries) {
        $(id).replaceChildren(...entries.map(values => {
            const row = element("tr");
            row.append(...values.map(value => element("td", value)));
            return row;
        }));
    }
    function inspect() {
        if (!last) return;
        const candidate = last.evaluated.find(item => item.ticker === select.value);
        if (!candidate) return;
        rows("discovery-weights", Object.entries(candidate.weights).map(([name, weight]) =>
            [name, percent(last.weights[name] ?? 0), percent(weight)]));
        for (const [id, period] of [["discovery-training", "training"], ["discovery-holdout-table", "holdout"]]) {
            const metrics = [last.baseline[period], candidate[period].portfolio, candidate[period].candidate];
            const specs = [["Total return", "total_return", percent],
                ["Annualized arithmetic return", "annualized_return", percent],
                ["Annualized volatility", "annualized_volatility", percent],
                ["Maximum drawdown", "max_drawdown", percent],
                ["Sharpe ratio", "sharpe_ratio", decimal]];
            rows(id, [
                ...specs.map(([label, key, format]) => [label, ...metrics.map(metric => format(metric[key]))]),
                ["Candidate correlation with original", "-", "-", decimal(candidate[period].candidate_correlation)]
            ]);
        }
    }
    function render(data) {
        const period = p => p.start + " to " + p.end + " (" + p.observations + " daily returns)";
        const objectiveNames = { volatility_reduction: "Volatility reduction", sharpe_improvement: "Sharpe ratio improvement",
            return_improvement: "Annualized return improvement" };
        const objectiveFormat = data.objective === "sharpe_improvement" ? signed : pp;
        $("discovery-summary").textContent = data.evaluated.length + " evaluated | " + data.excluded.length + " excluded | " +
            "Training: " + period(data.training_period) + " | Validation: " + period(data.holdout_period) +
            " | Shared price dates: " + data.first_price_date + " to " + data.last_price_date +
            " | Each hypothetical addition: " + percent(data.candidate_weight) +
            " | Risk-free rate: " + percent(data.annual_risk_free_rate) + " | " +
            Object.entries(data.weights).map(([ticker, weight]) => ticker + " " + percent(weight)).join(", ");
        $("discovery-ranking-note").textContent = "Ranked by " + objectiveNames[data.objective] +
            " on training dates only; validation results do not change the rankings." +
            (data.evaluated.length ? "" : " No candidates had sufficient eligible data.");
        rows("discovery-ranking", data.evaluated.map(item => [
            item.rank == null ? "N/A" : String(item.rank), item.ticker, decimal(item.training.candidate_correlation),
            pp(item.training.deltas.volatility_reduction), signed(item.training.deltas.sharpe_improvement),
            pp(item.training.deltas.return_improvement), objectiveFormat(item.holdout.deltas[data.objective])
        ]));
        select.replaceChildren(...data.evaluated.map(item => {
            const option = element("option", item.ticker);
            option.value = item.ticker;
            return option;
        }));
        $("discovery-inspector").hidden = !data.evaluated.length;
        $("discovery-exclusions").hidden = !data.excluded.length;
        rows("discovery-excluded", data.excluded.map(item => [item.ticker, item.reason]));
        last = data;
        $("discovery-results").hidden = false;
        if (data.evaluated.length) {
            select.value = data.evaluated[0].ticker;
            inspect();
        }
    }
    select.addEventListener("change", inspect);
    button.addEventListener("click", async () => {
        button.disabled = true;
        status.className = "muted";
        try {
            const settings = Object.fromEntries(["candidates", "weight", "objective", "holdout", "rate"].map(key => [key, $("discovery-" + key).value]));
            const payload = buildDiscoveryPayload(getAllocation("allocation"), $("start").value, $("end").value, settings);
            status.textContent = "Retrieving and comparing candidate histories...";
            render(await requestDiscovery(payload));
            status.textContent = "Screening complete. Results reflect submitted settings.";
        } catch (error) {
            status.className = "muted error";
            status.textContent = error.message + " Previous results are unchanged.";
        } finally {
            button.disabled = false;
        }
    });
}

if (typeof module !== "undefined" && module.exports) {
    module.exports = { buildDiscoveryPayload, requestDiscovery };
} else {
    initDiscoveryDashboard();
}
