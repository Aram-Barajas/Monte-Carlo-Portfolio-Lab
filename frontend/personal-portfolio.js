// Local-only portfolio import and saved allocations. No brokerage API access.
const PERSONAL_STORAGE_KEY = "portfolio-lab-personal-v1";
const PERSONAL_MAX_FILE_BYTES = 100_000;

function parseHoldingsCsv(source) {
    if (typeof source !== "string" || source.length > PERSONAL_MAX_FILE_BYTES) {
        throw new Error("Holdings CSV is too large (100 KB maximum).");
    }
    const rows = [];
    let row = [], field = "", quoted = false;
    const normalized = source.replace(/^\uFEFF/, "");
    for (let i = 0; i < normalized.length; i++) {
        const char = normalized[i];
        if (char === '"') {
            if (quoted && normalized[i + 1] === '"') { field += '"'; i++; }
            else if (quoted) quoted = false;
            else if (!field) quoted = true;
            else throw new Error("Malformed quoted CSV field.");
        } else if (char === "," && !quoted) {
            row.push(field.trim()); field = "";
        } else if ((char === "\n" || char === "\r") && !quoted) {
            if (char === "\r" && normalized[i + 1] === "\n") i++;
            row.push(field.trim()); field = "";
            if (row.some(value => value !== "")) rows.push(row);
            row = [];
        } else {
            field += char;
        }
    }
    if (quoted) throw new Error("Unclosed quoted field in CSV.");
    row.push(field.trim());
    if (row.some(value => value !== "")) rows.push(row);
    if (rows.length < 2 || rows.length > 22) {
        throw new Error("CSV must have headers and 1–20 holdings.");
    }
    const columns = rows.shift().map(value => value.toLowerCase());
    if (new Set(columns).size !== columns.length) throw new Error("Duplicate CSV headers.");
    const tickerCol = columns.indexOf("ticker");
    const weightCol = columns.indexOf("weight");
    const sharesCol = columns.indexOf("shares");
    const priceCol = columns.indexOf("price");
    if (tickerCol < 0 || (weightCol < 0 && (sharesCol < 0 || priceCol < 0))) {
        throw new Error("Use headers ticker,weight (%) or ticker,shares,price.");
    }
    const aliases = { "BRK.A": "BRK-A", "BRK.B": "BRK-B", "BF.B": "BF-B" };
    const weights = {};
    for (const values of rows) {
        if (values.length !== columns.length) throw new Error("CSV row has the wrong number of fields.");
        let ticker = (values[tickerCol] || "").toUpperCase();
        if (Object.hasOwn(aliases, ticker)) ticker = aliases[ticker];
        if (!/^[A-Z0-9^][A-Z0-9.\-=^]{0,19}$/.test(ticker) || Object.hasOwn(weights, ticker)) {
            throw new Error("CSV contains an invalid or duplicate ticker.");
        }
        const amounts = weightCol >= 0 ? [values[weightCol]] : [values[sharesCol], values[priceCol]];
        const numeric = amounts.map(value => Number(value));
        if (amounts.some(value => !value || !/^(?:\d+\.?\d*|\.\d+)$/.test(value)) ||
            numeric.some(value => !Number.isFinite(value) || value <= 0)) {
            throw new Error("Holdings need finite, positive weights or share quantities and prices.");
        }
        weights[ticker] = weightCol >= 0 ? numeric[0] : numeric[0] * numeric[1];
    }
    const total = Object.values(weights).reduce((sum, n) => sum + n, 0);
    if (!Number.isFinite(total) || total <= 0) throw new Error("Invalid total allocation.");
    // Input weight percentages may be rounded; accept close to 100% and normalize.
    if (weightCol >= 0 && Math.abs(total - 100) > .05) {
        throw new Error("CSV weight percentages must total approximately 100.");
    }
    const rounded = Object.entries(weights).map(([ticker, amount]) =>
        [ticker, 100 * amount / total]);
    return rounded;
}

function portfolioConcentration(weights) {
    const entries = Object.entries(weights);
    const alerts = entries.filter(([, weight]) => weight >= .25)
        .map(([ticker, weight]) => ticker + " " + (weight * 100).toFixed(1) + "%");
    return alerts.length
        ? "Concentration flag (25%+): " + alerts.join(", ") + ". ETF overlap is NOT analyzed."
        : "No holding is 25% or larger. ETF underlying holdings and sector overlap are NOT analyzed.";
}

function initPersonalPortfolio() {
    const saved = $("personal-saved"), status = $("personal-status");
    function readSaved() {
        try {
            const value = JSON.parse(localStorage.getItem(PERSONAL_STORAGE_KEY) || "{}");
            return value && typeof value === "object" && !Array.isArray(value) ? value : {};
        } catch { return {}; }
    }
    function writeSaved(value) {
        localStorage.setItem(PERSONAL_STORAGE_KEY, JSON.stringify(value));
    }
    function refresh() {
        const records = readSaved();
        saved.replaceChildren(...Object.keys(records).sort().map(name => {
            const option = document.createElement("option");
            option.value = name; option.textContent = name;
            return option;
        }));
        try { $("personal-concentration").textContent = portfolioConcentration(getAllocation("allocation").weights); }
        catch { $("personal-concentration").textContent = "Enter a valid allocation to see concentration flags."; }
    }
    $("allocation").addEventListener("input", refresh);
    $("personal-save").addEventListener("click", () => {
        try {
            const name = $("personal-name").value.trim();
            if (!name || name.length > 60) throw new Error("Use a portfolio name of 1–60 characters.");
            const allocation = getAllocation("allocation");
            const records = readSaved();
            if (!Object.hasOwn(records, name) && Object.keys(records).length >= 20)
                throw new Error("Maximum 20 saved portfolios.");
            records[name] = allocation.weights;
            writeSaved(records); refresh(); saved.value = name;
            status.textContent = "Saved locally in this browser. No upload was made.";
        } catch (error) { status.textContent = error.message; }
    });
    $("personal-load").addEventListener("click", () => {
        try {
            const weights = readSaved()[saved.value];
            if (!weights || typeof weights !== "object") throw new Error("Select a saved portfolio.");
            const text = Object.entries(weights).map(([ticker, value]) =>
                ticker + ", " + (value * 100).toFixed(6)).join("\n");
            const prior = $("allocation").value;
            $("allocation").value = text;
            try { getAllocation("allocation"); }
            catch (error) { $("allocation").value = prior; throw error; }
            refresh(); status.textContent = "Loaded locally saved allocation.";
        } catch (error) { status.textContent = error.message; }
    });
    $("personal-delete").addEventListener("click", () => {
        const records = readSaved();
        if (!Object.hasOwn(records, saved.value)) { status.textContent = "Select a saved portfolio."; return; }
        delete records[saved.value];
        try { writeSaved(records); refresh(); status.textContent = "Saved portfolio deleted from this browser."; }
        catch (error) { status.textContent = error.message; }
    });
    $("personal-import").addEventListener("click", async () => {
        try {
            const file = $("personal-csv").files[0];
            if (!file || file.size > PERSONAL_MAX_FILE_BYTES) throw new Error("Choose a CSV up to 100 KB.");
            const weights = parseHoldingsCsv(await file.text());
            const prior = $("allocation").value;
            $("allocation").value = weights.map(([ticker, value]) => ticker + ", " + value.toFixed(8)).join("\n");
            try { getAllocation("allocation"); }
            catch (error) { $("allocation").value = prior; throw error; }
            refresh(); status.textContent = "Imported " + weights.length + " holdings locally. Review the allocation before saving or analyzing.";
        } catch (error) { status.textContent = error.message; }
    });
    refresh();
}

if (typeof module !== "undefined" && module.exports) {
    module.exports = { parseHoldingsCsv, portfolioConcentration };
} else {
    initPersonalPortfolio();
}
