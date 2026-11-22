const $ = id => document.getElementById(id);

const money = value => new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0
}).format(value);

const percent = value => `${(value * 100).toFixed(2)}%`;

const number = id => Number($(id).value);

let currentBands = null;
let comparisonBands = null;

$("compare-enabled").addEventListener("change", () => {
    const enabled = $("compare-enabled").checked;
    $("comparison-input").hidden = !enabled;
    $("allocation-b").required = enabled;
    $("run").textContent = enabled ? "Compare portfolios" : "Run simulation";
});

// Light and dark mode

const THEME_KEY = "portfolio-lab-theme";

function setTheme(theme) {
    document.documentElement.dataset.theme = theme;

    $("theme-toggle").textContent =
        theme === "dark"
            ? "Light mode"
            : "Dark mode";
}

let savedTheme;

try {
    savedTheme = localStorage.getItem(THEME_KEY);
} catch (error) {
    // Theme still works when storage is unavailable.
}

setTheme(
    savedTheme === "light" || savedTheme === "dark"
        ? savedTheme
        : window.matchMedia("(prefers-color-scheme: dark)").matches
            ? "dark"
            : "light"
);

$("theme-toggle").addEventListener("click", () => {
    const theme =
        document.documentElement.dataset.theme === "dark"
            ? "light"
            : "dark";

    setTheme(theme);

    try {
        localStorage.setItem(THEME_KEY, theme);
    } catch (error) {
        // Keep the selected theme for the current page.
    }
});

// Collect and validate form inputs.

const ALLOCATION_ROUNDING_TOLERANCE = 0.0005;

function allocationTotal(weights) {
    return Object.values(weights).reduce(
        (sum, weight) => sum + weight,
        0
    );
}

function getAllocation(id) {
    const entries = $(id).value.trim()
        .split(/\n+/)
        .map(line => {
            const parts = line.split(",")
                .map(part => part.trim());

            const ticker = parts[0].toUpperCase();
            const weight = Number(parts[1]);

            if (
                parts.length !== 2 ||
                !/^[A-Z0-9^][A-Z0-9.\-=^]{0,19}$/.test(ticker) ||
                !parts[1] ||
                !Number.isFinite(weight) ||
                weight < 0
            ) {
                throw new Error(
                    "Use one ticker and nonnegative percentage per line, e.g. VTI, 60."
                );
            }

            return [ticker, weight / 100];
        });

    const tickers = entries.map(entry => entry[0]);

    if (
        tickers.length > 20 ||
        new Set(tickers).size !== tickers.length
    ) {
        throw new Error(
            "Enter up to 20 distinct tickers."
        );
    }

    const total = entries.reduce(
        (sum, entry) => sum + entry[1],
        0
    );

    if (
        Math.abs(total - 1) >
        ALLOCATION_ROUNDING_TOLERANCE + 1e-12
    ) {
        const portfolio = id === "allocation-b"
            ? "B"
            : "A";

        throw new Error(
            `Portfolio ${portfolio} totals ${(total * 100).toFixed(2)}%. ` +
            "Enter a total between 99.95% and 100.05%."
        );
    }

    return { tickers, weights: Object.fromEntries(entries) };
}

function getPayload() {
    const allocation = getAllocation("allocation");
    if ($("start").value >= $("end").value) {
        throw new Error(
            "End date must be after start date."
        );
    }

    return {
        ...allocation,
        start: $("start").value,
        end: $("end").value,
        initial_value: number("initial"),
        monthly_contribution: number("monthly"),
        trading_days: number("years") * 252,
        num_simulations: number("paths"),
        confidence: number("confidence") / 100,
        seed: $("seed").value === ""
            ? null
            : number("seed")
    };
}


// Create HTML elements safely.

function element(tag, text, className) {
    const node = document.createElement(tag);

    if (text !== undefined) {
        node.textContent = text;
    }

    if (className) {
        node.className = className;
    }

    return node;
}


// Display financial metrics.

function metrics(target, rows, cards = false) {
    $(target).replaceChildren(
        ...rows.map(([label, value]) => {
            const row = element(
                "div",
                undefined,
                cards ? "panel metric" : ""
            );

            row.append(
                element(
                    cards ? "span" : "dt",
                    label
                ),
                element(
                    cards ? "strong" : "dd",
                    value
                )
            );

            return row;
        })
    );
}


// Draw the portfolio growth chart.

function drawChart(bands, otherBands = null) {
    const chart = $("chart");

    chart.replaceChildren();

    const width = Math.max(280, chart.clientWidth);

    chart.setAttribute(
        "viewBox",
        `0 0 ${width} 320`
    );

    const left = 76;
    const right = width - 28;
    const top = 18;
    const bottom = 280;

    const last = bands.at(-1).trading_day;

    const max = Math.max(
        1,
        ...bands.map(point => point.p95),
        ...(otherBands || []).map(point => point.median)
    );

    const x = day =>
        left + day / last * (right - left);

    const y = value =>
        bottom - value / max * (bottom - top);

    function svg(tag, attrs, text) {
        const node = document.createElementNS(
            "http://www.w3.org/2000/svg",
            tag
        );

        Object.entries(attrs).forEach(
            ([key, value]) => {
                node.setAttribute(key, value);
            }
        );

        if (text !== undefined) {
            node.textContent = text;
        }

        chart.append(node);
    }

    // Horizontal grid lines and dollar labels.

    for (let i = 0; i <= 4; i++) {
        const value = max * i / 4;

        svg("line", {
            x1: left,
            x2: right,
            y1: y(value),
            y2: y(value),
            stroke: "#d9ddd3"
        });

        const label = new Intl.NumberFormat("en-US", {
            notation: "compact",
            style: "currency",
            currency: "USD",
            maximumFractionDigits: 1
        }).format(value);

        svg("text", {
            x: left - 8,
            y: y(value) + 4,
            "text-anchor": "end",
            fill: "#65736a",
            "font-size": 13
        }, label);
    }

    const points = (rows, key) => rows.map(row =>
        `${x(row.trading_day)},${y(row[key])}`
    ).join(" ");

    // Outer percentile band.

    svg("polygon", {
        points:
            points(bands, "p95") + " " +
            points([...bands].reverse(), "p05"),
        fill: "#d9e8da"
    });

    // Inner percentile band.

    svg("polygon", {
        points:
            points(bands, "p75") + " " +
            points([...bands].reverse(), "p25"),
        fill: "#91b59c"
    });

    // Median portfolio trajectory.

    svg("polyline", {
        points: points(bands, "median"),
        fill: "none",
        stroke: "#245b45",
        "stroke-width": 2.5
    });

    if (otherBands) {
        svg("polyline", {
            points: points(otherBands, "median"),
            fill: "none",
            class: "comparison-line",
            "stroke-width": 2.5
        });
    }

    // Investment horizon labels.

    for (const fraction of [0, 0.5, 1]) {
        svg("text", {
            x: x(last * fraction),
            y: 302,
            "text-anchor": "middle",
            fill: "#65736a",
            "font-size": 13
        }, `${last * fraction / 252} yr`);
    }
}


// Render the API response.

function render(data, comparison = null, seed = null) {
    const {
        analysis,
        simulation_risk: risk,
        percentiles
    } = data;

    const history = analysis.historical_risk;
    const portfolio = analysis.portfolio_metrics;
    const last = percentiles.at(-1);

    $("summary").textContent =
        `${data.num_simulations.toLocaleString()} SIMULATIONS | ` +
        `${data.trading_days / 252} YEARS | ` +
        `${analysis.observations} HISTORICAL OBSERVATIONS`;

    metrics("metrics", [
        [
            "Median ending value",
            money(risk.median_ending_value)
        ],
        [
            "Total contributed capital",
            money(risk.total_invested)
        ],
        [
            "5th-95th percentile at end",
            `${money(last.p05)} - ${money(last.p95)}`
        ],
        [
            "Probability of loss vs. contributions",
            percent(risk.probability_of_loss)
        ]
    ], true);

    metrics("historical", [
        [
            "Annualized return (arithmetic)",
            percent(portfolio.annualized_return)
        ],
        [
            "Annualized volatility",
            percent(portfolio.annualized_volatility)
        ],
        [
            "Sharpe ratio",
            history.sharpe_ratio === null
                ? "N/A"
                : history.sharpe_ratio.toFixed(2)
        ],
        [
            "Maximum drawdown",
            percent(history.max_drawdown)
        ]
    ]);

    metrics("risk", [
        [
            "Confidence",
            percent(risk.confidence)
        ],
        [
            "Value at Risk (signed loss)",
            money(risk.terminal_var)
        ],
        [
            "Expected shortfall (signed loss)",
            money(risk.terminal_expected_shortfall)
        ],
        [
            "Mean ending value",
            money(risk.mean_ending_value)
        ]
    ]);

    // Asset breakdown table.

    $("assets").replaceChildren(
        ...analysis.asset_metrics.map(asset => {
            const row = element("tr");
            const ticker = element("th", asset.ticker);

            ticker.scope = "row";

            row.append(
                ticker,
                element(
                    "td",
                    percent(analysis.weights[asset.ticker])
                ),
                element(
                    "td",
                    percent(asset.annualized_return)
                ),
                element(
                    "td",
                    percent(asset.annualized_volatility)
                )
            );

            return row;
        })
    );

    $("empty").hidden = true;
    $("results").hidden = false;

    currentBands = percentiles;
    comparisonBands = comparison ? comparison.percentiles : null;
    $("comparison-results").hidden = !comparison;
    $("comparison-legend").hidden = !comparison;
    $("median-label").textContent = comparison ? "Portfolio A median" : "Median";
    $("chart").setAttribute("aria-label", comparison
        ? "Portfolio A percentile bands and both portfolio median trajectories"
        : "Projected portfolio percentile bands");
    if (comparison) renderComparison(data, comparison, seed);
    drawChart(currentBands, comparisonBands);
}

function renderComparison(a, b, seed) {
    const ar = a.simulation_risk, br = b.simulation_risk;
    const ap = a.analysis.portfolio_metrics, bp = b.analysis.portfolio_metrics;
    const ah = a.analysis.historical_risk, bh = b.analysis.historical_risk;
    const range = item => `${money(item.percentiles.at(-1).p05)} - ${money(item.percentiles.at(-1).p95)}`;
    const rows = [
        ["Median ending value", money(ar.median_ending_value), money(br.median_ending_value)],
        ["5th-95th percentile at end", range(a), range(b)],
        ["Probability of loss", percent(ar.probability_of_loss), percent(br.probability_of_loss)],
        ["Annualized return (arithmetic)", percent(ap.annualized_return), percent(bp.annualized_return)],
        ["Annualized volatility", percent(ap.annualized_volatility), percent(bp.annualized_volatility)],
        ["Maximum drawdown", percent(ah.max_drawdown), percent(bh.max_drawdown)]
    ];
    $("comparison-summary").textContent = `Shared random seed: ${seed}. Other result panels show Portfolio A.`;
    $("comparison-table").replaceChildren(...rows.map(([label, first, second]) => {
        const row = element("tr");
        const heading = element("th", label);
        heading.scope = "row";
        row.append(heading, element("td", first), element("td", second));
        return row;
    }));
}


// Redraw the chart when the screen size changes.

window.addEventListener("resize", () => {
    if (currentBands) {
        drawChart(currentBands, comparisonBands);
    }
});


// Submit the simulation request.

$("simulation-form").addEventListener(
    "submit",
    async event => {
        event.preventDefault();

        $("status").className = "";

        try {
            const payload = getPayload();
            const comparing = $("compare-enabled").checked;
            if (comparing) {
                payload.comparison_weights = getAllocation("allocation-b").weights;
            }

            const normalized = [];

            if (Math.abs(allocationTotal(payload.weights) - 1) > 1e-8) {
                normalized.push("Portfolio A");
            }

            if (
                comparing &&
                Math.abs(allocationTotal(payload.comparison_weights) - 1) > 1e-8
            ) {
                normalized.push("Portfolio B");
            }

            $("run").disabled = true;

            $("status").textContent =
                "Downloading market data and simulating outcomes...";

            const response = await fetch(comparing ? "/api/compare" : "/api/simulate", {
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
                    detail || "Simulation request failed."
                );
            }

            if (comparing) {
                render(data.portfolio_a, data.portfolio_b, data.seed);
            } else {
                render(data);
            }

            $("status").textContent =
                "Simulation complete. Results reflect your last submitted settings." +
                (
                    normalized.length
                        ? ` ${normalized.join(" and ")} normalized to 100%.`
                        : ""
                );

        } catch (error) {
            $("status").className = "error";

            $("status").textContent =
                error.message +
                " Previous results, if shown, are unchanged.";

        } finally {
            $("run").disabled = false;
        }
    }
);
