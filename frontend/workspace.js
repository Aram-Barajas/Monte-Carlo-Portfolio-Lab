// URL-based research navigation. Keep inputs and successful results mounted.

const WORKSPACE_VIEWS = {
    overview: ["Understand your portfolio.", "Analyze your allocation over the selected historical period.", ["overview-results"]],
    simulation: ["What might the future hold?", "Run a simulation to explore hypothetical future outcomes.", ["results"]],
    backtesting: ["Replay historical performance.", "Run a backtest or compare against a market benchmark.", ["backtest-results", "benchmark-results"]],
    optimization: ["Explore the risk-return tradeoff.", "Build an efficient frontier or compare robust allocations.", ["frontier-results", "robust-results"]],
    stress: ["How could your portfolio react?", "Run a hypothetical stress test or replay a historical crisis.", ["stress-results", "crisis-results"]],
    risk: ["Where does the risk come from?", "Explore each asset's risk contribution and changing historical risk.", ["advanced-risk-results"]]
};

function getWorkspaceView(hash) {
    const view = hash.replace(/^#/, "");
    return Object.hasOwn(WORKSPACE_VIEWS, view) ? view : "overview";
}

function applyWorkspaceView(view, doc) {
    for (const link of doc.querySelectorAll("[data-workspace-tab]")) {
        if (link.dataset.workspaceTab === view) link.setAttribute("aria-current", "page");
        else link.removeAttribute("aria-current");
    }
    for (const control of doc.querySelectorAll("[data-controls]")) {
        control.hidden = !control.dataset.controls.split(/\s+/).includes(view);
    }
    for (const panel of doc.querySelectorAll("[data-result-view]")) {
        panel.hidden = panel.dataset.resultView !== view;
    }
    updateWorkspaceEmpty(view, doc);
}

function updateWorkspaceEmpty(view, doc) {
    const [title, description, ids] = WORKSPACE_VIEWS[view];
    const empty = doc.getElementById("empty");
    const ready = ids.some(id => !doc.getElementById(id).hidden);
    if (empty.hidden !== ready) empty.hidden = ready;
    doc.getElementById("workspace-empty-title").textContent = title;
    doc.getElementById("workspace-empty-description").textContent = description;
}

function buildOverviewPayload(allocation, start, end) {
    if (!start || !end || start >= end) {
        throw new Error("Select a valid historical date range.");
    }
    return { ...allocation, start, end };
}

async function requestOverview(payload, fetcher = fetch) {
    const response = await fetcher("/api/portfolio", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
    });
    const data = await response.json();
    if (!response.ok) {
        const detail = Array.isArray(data.detail)
            ? data.detail.map(item => item.msg).join("; ") : data.detail;
        throw new Error(detail || "Historical analysis failed.");
    }
    return data;
}

function initWorkspace() {
    function navigate() {
        applyWorkspaceView(getWorkspaceView(window.location.hash), document);
        // Redraw SVG charts after their containing view has become visible.
        window.dispatchEvent(new Event("resize"));
    }

    const observer = new MutationObserver(() => {
        updateWorkspaceEmpty(getWorkspaceView(window.location.hash), document);
    });
    for (const [, , ids] of Object.values(WORKSPACE_VIEWS)) {
        for (const id of ids) observer.observe($(id), { attributes: true, attributeFilter: ["hidden"] });
    }
    // Legacy result handlers also hide this placeholder after success.
    observer.observe($("empty"), { attributes: true, attributeFilter: ["hidden"] });
    window.addEventListener("hashchange", () => {
        navigate();
        window.scrollTo(0, 0);
    });
    navigate();

    const button = $("run-overview"), status = $("overview-status");
    button.addEventListener("click", async () => {
        button.disabled = true;
        status.className = "muted";
        try {
            const payload = buildOverviewPayload(getAllocation("allocation"), $("start").value, $("end").value);
            status.textContent = "Analyzing historical returns...";
            const analysis = await requestOverview(payload);
            renderHistoricalOverview(analysis, null, payload, "Historical analysis");
            status.textContent = "Analysis complete. Results reflect submitted settings.";
        } catch (error) {
            status.className = "muted error";
            status.textContent = error.message + " Previous overview results are unchanged.";
        } finally {
            button.disabled = false;
        }
    });
}

if (typeof module !== "undefined" && module.exports) {
    module.exports = { getWorkspaceView, applyWorkspaceView, updateWorkspaceEmpty, buildOverviewPayload, requestOverview };
} else {
    initWorkspace();
}
