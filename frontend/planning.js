// Goal-based financial planning.

function buildPlanningPayload(allocation, start, end, initial, settings) {
    if (!start || !end || start >= end) throw new Error("Select a valid historical date range.");
    function numeric(raw, low, high, label, integer = false) {
        const value = Number(raw);
        if (raw == null || String(raw).trim() === "" || !Number.isFinite(value) ||
            value < low || value > high || (integer && !Number.isInteger(value))) {
            throw new Error(label + " must be between " + low + " and " + high + (integer ? " (whole number)." : "."));
        }
        return value;
    }
    const years = numeric(settings.years, 1, 40, "Years to goal", true);
    const paths = numeric(settings.paths, 1, 2000, "Simulated paths", true);
    if (years * paths * 252 * allocation.tickers.length > 20000000) {
        throw new Error("Planning simulation is too large. Reduce years, paths, or assets.");
    }
    if (!["gaussian", "gaussian_uncertain", "block_bootstrap"].includes(settings.model)) {
        throw new Error("Select a return model.");
    }
    return {
        ...allocation, start, end, years, num_simulations: paths,
        initial_value: numeric(initial, 0, 1e9, "Initial investment"),
        monthly_contribution: numeric(settings.monthly, 0, 1e9, "Monthly contribution"),
        goal: numeric(settings.goal, .01, 1e9, "Goal"),
        contribution_growth: numeric(settings.growth, -10, 25, "Annual contribution increase") / 100,
        annual_inflation: numeric(settings.inflation, -5, 25, "Annual inflation") / 100,
        target_probability: numeric(settings.probability, 50, 99, "Desired success") / 100,
        model: settings.model, drift_weight: numeric(settings.drift, 0, 100, "Drift retained") / 100,
        block_length: settings.model === "block_bootstrap" ? numeric(settings.block, 1, 252, "Block length", true) : 21,
        seed: String(settings.seed ?? "").trim() === "" ? null : numeric(settings.seed, 0, 4294967295, "Seed", true)
    };
}

async function requestPlanning(payload, fetcher = fetch) {
    const response = await fetcher("/api/plan", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload)
    });
    const data = await response.json();
    if (!response.ok) {
        const detail = Array.isArray(data.detail) ? data.detail.map(item => item.msg).join("; ") : data.detail;
        throw new Error(detail || "Planning request failed.");
    }
    return data;
}

function planningChartLayout(annual, goal, width) {
    const left = 68, right = width - 22, top = 15, bottom = 215;
    const max = Math.max(1, goal, ...annual.map(row => row.p95));
    const years = annual.at(-1).year;
    const x = year => left + year / years * (right - left);
    const y = value => bottom - value / max * (bottom - top);
    return { left, right, top, bottom, max, x, y, years,
        points: (rows, key) => rows.map(row => x(row.year) + "," + y(row[key])).join(" ") };
}

function drawPlanningChart(chart, annual, goal) {
    const width = Math.max(280, chart.clientWidth);
    const layout = planningChartLayout(annual, goal, width);
    const { left, right, bottom, max, x, y, years, points } = layout;
    chart.setAttribute("viewBox", `0 0 ${width} 245`);
    chart.replaceChildren();
    function svg(tag, attrs, text) {
        const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
        for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
        if (text !== undefined) node.textContent = text;
        chart.append(node);
    }
    const compact = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", notation: "compact", maximumFractionDigits: 1 });
    for (let i = 0; i <= 4; i++) {
        const value = max * i / 4;
        svg("line", { x1: left, x2: right, y1: y(value), y2: y(value) });
        svg("text", { x: left - 7, y: y(value) + 4, "text-anchor": "end" }, compact.format(value));
    }
    svg("polygon", { points: points(annual, "p95") + " " + points([...annual].reverse(), "p05"), class: "plan-band" });
    svg("polyline", { points: points(annual, "median"), class: "plan-median" });
    svg("polyline", { points: left + "," + y(goal) + " " + right + "," + y(goal), class: "plan-goal" });
    for (const year of [...new Set([0, Math.round(years / 2), years])]) {
        svg("text", { x: x(year), y: bottom + 23, "text-anchor": "middle" }, year + " yr");
    }
}

function initPlanningDashboard() {
    const button = $("run-plan"), status = $("plan-status");
    let last = null;
    const model = $("plan-model");
    function updateModel() {
        $("plan-block-control").hidden = $("plan-block").hidden = model.value !== "block_bootstrap";
    }
    model.addEventListener("change", updateModel);
    updateModel();
    function rows(id, entries) {
        $(id).replaceChildren(...entries.map(values => {
            const row = element("tr");
            row.append(...values.map(value => element("td", value)));
            return row;
        }));
    }
    function draw() {
        if (last && !$("planning-results").hidden) drawPlanningChart($("plan-chart"), last.annual, last.goal);
    }
    function render(data) {
        const end = data.annual.at(-1);
        const names = { gaussian: "Gaussian", gaussian_uncertain: "Gaussian with uncertain mean", block_bootstrap: "Historical block bootstrap" };
        $("plan-summary").textContent = data.years + " years | " + data.num_simulations + " paths | " +
            data.start + " to " + data.end + " (exclusive) | " + data.observations + " historical returns | " +
            names[data.model] + " | drift " + percent(data.drift_weight) +
            (data.block_length == null ? "" : " | block " + data.block_length + " days") +
            " | initial " + money(data.initial_value) + " | starting monthly " + money(data.monthly_contribution) +
            " | inflation " + percent(data.annual_inflation) + " | yearly contribution change " + percent(data.contribution_growth) +
            " | seed " + data.seed + " | " + Object.entries(data.weights).map(([ticker, weight]) => ticker + " " + percent(weight)).join(", ");
        metrics("plan-metrics", [
            ["Goal (today's dollars)", money(data.goal)],
            ["Modeled success at horizon", percent(data.goal_probability)],
            ["Median ending value (today's dollars)", money(end.median)],
            ["Estimated starting monthly amount for " + percent(data.target_probability), money(data.required_monthly_contribution)],
            ["Modeled success at estimated amount", percent(data.required_contribution_probability)],
            ["Median shortfall among missed paths", data.median_shortfall_when_missed == null ? "N/A" : money(data.median_shortfall_when_missed)],
            ["Nominal goal at horizon", money(data.nominal_goal)],
            ["Total nominal capital contributed", money(end.nominal_contributed)]
        ], true);
        rows("plan-sensitivity", data.sensitivity.map(row => [
            money(row.monthly_contribution), percent(row.goal_probability), money(row.median_ending_real)
        ]));
        rows("plan-annual", data.annual.map(row => [
            String(row.year), money(row.p05), money(row.median), money(row.p95), percent(row.goal_probability), money(row.nominal_contributed)
        ]));
        $("planning-results").hidden = false;
        last = data;
        draw();
    }
    button.addEventListener("click", async () => {
        button.disabled = true;
        status.className = "muted";
        try {
            const settings = Object.fromEntries(["years", "paths", "monthly", "goal", "growth", "inflation", "probability", "model", "drift", "block", "seed"].map(key => [key, $("plan-" + key).value]));
            const payload = buildPlanningPayload(getAllocation("allocation"), $("start").value, $("end").value, $("initial").value, settings);
            status.textContent = "Evaluating goal under simulated market paths...";
            render(await requestPlanning(payload));
            status.textContent = "Planning complete. Results reflect submitted settings.";
        } catch (error) {
            status.className = "muted error";
            status.textContent = error.message + " Previous results are unchanged.";
        } finally {
            button.disabled = false;
        }
    });
    window.addEventListener("resize", draw);
}

if (typeof module !== "undefined" && module.exports) {
    module.exports = { buildPlanningPayload, requestPlanning, planningChartLayout };
} else {
    initPlanningDashboard();
}
