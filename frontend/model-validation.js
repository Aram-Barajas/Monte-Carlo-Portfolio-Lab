// Walk-forward comparison of simulated forecast distributions.

const VALIDATION_MODELS = ["gaussian", "gaussian_uncertain", "block_bootstrap"];

function buildValidationPayload(allocation, start, end, settings) {
    if (!start || !end || start >= end) throw new Error("Select a valid historical date range.");
    function numeric(key, low, high, label, integer = true) {
        const raw = settings[key], value = Number(raw);
        if (raw == null || String(raw).trim() === "" || !Number.isFinite(value) ||
            value < low || value > high || (integer && !Number.isInteger(value))) {
            throw new Error(label + " must be between " + low + " and " + high + (integer ? " (whole number)." : "."));
        }
        return value;
    }
    const training_days = numeric("training", 63, 1260, "Training days");
    const forecast_days = numeric("horizon", 5, 252, "Forecast days");
    const max_folds = numeric("folds", 3, 24, "Maximum folds");
    const num_simulations = numeric("paths", 100, 1000, "Paths");
    const block_length = numeric("block", 1, 252, "Block length");
    if (block_length > training_days) throw new Error("Block length cannot exceed the training window.");
    if (max_folds * num_simulations * forecast_days * allocation.tickers.length * 3 > 20000000) {
        throw new Error("Validation is too large. Reduce folds, forecast days, paths, or assets.");
    }
    return { ...allocation, start, end, training_days, forecast_days, max_folds, num_simulations, block_length,
        drift_weight: numeric("drift", 0, 100, "Drift retained", false) / 100,
        seed: String(settings.seed ?? "").trim() === "" ? null : numeric("seed", 0, 4294967295, "Seed") };
}

async function requestValidation(payload, fetcher = fetch) {
    const response = await fetcher("/api/validate-models", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload)
    });
    const data = await response.json();
    if (!response.ok) {
        const detail = Array.isArray(data.detail) ? data.detail.map(item => item.msg).join("; ") : data.detail;
        throw new Error(detail || "Model validation failed.");
    }
    return data;
}

function validationChartLayout(folds, model, width) {
    const left = 62, right = width - 22, top = 15, bottom = 215;
    const minimum = Math.min(0, ...folds.map(row => Math.min(row.actual_return, row.models[model].p05)));
    const maximum = Math.max(.01, ...folds.map(row => Math.max(row.actual_return, row.models[model].p95)));
    const x = index => left + index / (folds.length - 1) * (right - left);
    const y = value => bottom - (value - minimum) / (maximum - minimum) * (bottom - top);
    return { left, right, top, bottom, minimum, maximum, x, y };
}

function drawValidationChart(chart, folds, model) {
    const width = Math.max(280, chart.clientWidth);
    const { left, right, bottom, minimum, maximum, x, y } = validationChartLayout(folds, model, width);
    chart.setAttribute("viewBox", `0 0 ${width} 245`);
    chart.replaceChildren();
    function svg(tag, attrs, text) {
        const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
        for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
        if (text !== undefined) node.textContent = text;
        chart.append(node);
    }
    for (let i = 0; i <= 4; i++) {
        const value = minimum + (maximum - minimum) * i / 4;
        svg("line", { x1: left, x2: right, y1: y(value), y2: y(value) });
        svg("text", { x: left - 7, y: y(value) + 4, "text-anchor": "end" }, (value * 100).toFixed(1) + "%");
    }
    // Each vertical segment is a separate predictive interval, not a continuous time band.
    folds.forEach((row, i) => {
        const half = Math.min(7, (right - left) / (folds.length - 1) / 4);
        const lower = y(row.models[model].p05), upper = y(row.models[model].p95);
        svg("rect", { x: x(i) - half, y: upper, width: 2 * half,
            height: Math.max(1, lower - upper), class: "validation-band" });
    });
    const points = getter => folds.map((row, i) => x(i) + "," + y(getter(row))).join(" ");
    svg("polyline", { points: points(row => row.models[model].median), class: "validation-median" });
    svg("polyline", { points: points(row => row.actual_return), class: "validation-actual" });
    folds.forEach((row, i) => svg("circle", { cx: x(i), cy: y(row.actual_return), r: 3, class: "validation-observed" }));
    for (const i of [...new Set([0, Math.floor((folds.length - 1) / 2), folds.length - 1])]) {
        svg("text", { x: x(i), y: bottom + 23, "text-anchor": "middle" }, "Fold " + folds[i].fold);
    }
}

function initValidationDashboard() {
    const button = $("run-validation"), status = $("validation-status"), select = $("validation-model");
    let last = null;
    function rows(id, entries) {
        $(id).replaceChildren(...entries.map(values => {
            const row = element("tr");
            row.append(...values.map(value => element("td", value)));
            return row;
        }));
    }
    function draw() {
        if (last && !$("validation-results").hidden) drawValidationChart($("validation-chart"), last.folds, select.value);
    }
    function inspect() {
        if (!last) return;
        const model = select.value;
        rows("validation-pit", last.models[model].pit_histogram.map((count, i) => [
            `${i * 10}% to ${(i + 1) * 10}%`, String(count)
        ]));
        rows("validation-fold-table", last.folds.map(row => {
            const score = row.models[model];
            return [String(row.fold), row.training_start + " to " + row.training_end,
                row.forecast_start + " to " + row.forecast_end, percent(row.actual_return), percent(score.median),
                percent(score.p05) + " to " + percent(score.p95), percent(score.probability_loss), percent(score.crps)];
        }));
        draw();
    }
    function render(data) {
        $("validation-summary").textContent = data.fold_count + " of " + data.max_folds +
            " requested folds | " + data.training_days + " training days | " + data.forecast_days +
            " forecast days | " + data.num_simulations + " paths per model | " + data.start + " to " + data.end +
            " (exclusive) | " + data.observations + " historical observations | drift " + percent(data.drift_weight) +
            " | bootstrap block " + data.block_length + " days | seed " + data.seed + " | " +
            Object.entries(data.weights).map(([ticker, weight]) => ticker + " " + percent(weight)).join(", ");
        $("validation-warning").textContent = "Only " + data.fold_count +
            " realized outcomes per model. Coverage and PIT are descriptive; the outcomes are not necessarily independent. " +
            "The Wilson range below is an independent-outcome reference only, not a guarantee of forecast coverage.";
        const specs = [
            ["50% interval coverage", "coverage_50", percent],
            ["90% interval coverage", "coverage_90", percent],
            ["90% coverage range (IID reference)", "coverage_90_wilson_reference", value => value ? percent(value[0]) + "–" + percent(value[1]) : "N/A"],
            ["Below 5th percentile (count)", "below_05", String],
            ["Above 95th percentile (count)", "above_95", String],
            ["Mean 90% interval width", "mean_width_90", percent],
            ["Mean absolute median error", "mean_absolute_error", percent],
            ["Mean signed median error", "median_bias", percent],
            ["Mean CRPS", "mean_crps", percent],
            ["Mean loss Brier score (0-1)", "mean_brier_loss", value => value.toFixed(4)]
        ];
        rows("validation-scores", specs.map(([label, key, format]) =>
            [label, ...VALIDATION_MODELS.map(model => format(data.models[model][key]))]));
        last = data;
        $("validation-results").hidden = false;
        inspect();
    }
    select.addEventListener("change", inspect);
    window.addEventListener("resize", draw);
    button.addEventListener("click", async () => {
        button.disabled = true;
        status.className = "muted";
        try {
            const settings = Object.fromEntries(["training", "horizon", "folds", "paths", "drift", "block", "seed"].map(key => [key, $("validation-" + key).value]));
            const payload = buildValidationPayload(getAllocation("allocation"), $("start").value, $("end").value, settings);
            status.textContent = "Running historical forecast folds...";
            render(await requestValidation(payload));
            status.textContent = "Validation complete. Results reflect submitted settings.";
        } catch (error) {
            status.className = "muted error";
            status.textContent = error.message + " Previous results are unchanged.";
        } finally {
            button.disabled = false;
        }
    });
}

if (typeof module !== "undefined" && module.exports) {
    module.exports = { buildValidationPayload, requestValidation, validationChartLayout };
} else {
    initValidationDashboard();
}
