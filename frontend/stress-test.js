// Hypothetical portfolio stress testing.

function buildStressPayload(
    allocation,
    initial,
    customText = null
) {
    const initialValue = Number(initial);

    if (
        !String(initial).trim() ||
        !Number.isFinite(initialValue) ||
        initialValue <= 0 ||
        initialValue > 1000000000
    ) {
        throw new Error(
            "Initial investment must be positive and at most $1 billion."
        );
    }

    const payload = {
        weights: allocation.weights,
        initial_value: initialValue
    };

    if (customText !== null) {

        const entries = customText.trim()
            .split(/\n+/)
            .map(line => {

                const parts = line.split(",")
                    .map(part => part.trim());

                const ticker = parts[0].toUpperCase();
                const shock = Number(parts[1]);

                if (
                    parts.length !== 2 ||
                    !/^[A-Z0-9^][A-Z0-9.\-=^]{0,19}$/.test(ticker) ||
                    !parts[1] ||
                    !Number.isFinite(shock) ||
                    shock < -100 ||
                    shock > 100
                ) {
                    throw new Error(
                        "Enter each ticker and shock from -100 to 100, e.g. VTI, -20."
                    );
                }

                return [ticker, shock / 100];
            });

        if (
            entries.length > 20 ||
            new Set(
                entries.map(([ticker]) => ticker)
            ).size !== entries.length
        ) {
            throw new Error(
                "Enter one shock per ticker, with no duplicates."
            );
        }

        payload.scenarios = {
            "Custom asset shock":
                Object.fromEntries(entries)
        };
    }

    return payload;
}


async function requestStressTest(
    payload,
    fetcher = fetch
) {
    const response = await fetcher(
        "/api/stress-test",
        {
            method: "POST",

            headers: {
                "Content-Type": "application/json"
            },

            body: JSON.stringify(payload)
        }
    );

    const data = await response.json();

    if (!response.ok) {
        const detail = Array.isArray(data.detail)
            ? data.detail.map(item => item.msg).join("; ")
            : data.detail;

        throw new Error(
            detail || "Stress test request failed."
        );
    }

    return data;
}


function stressTableRow(label, values) {

    const row = element("tr");
    const heading = element("th", label);

    heading.scope = "row";

    row.append(
        heading,
        ...values.map(value =>
            element("td", value)
        )
    );

    return row;
}


function initStressDashboard() {

    const button = $("run-stress-test");
    const custom = $("stress-custom-enabled");
    const status = $("stress-status");
    const selector = $("stress-scenario-select");

    let lastStress = null;


    function showCustomInput() {

        $("stress-custom-input").hidden =
            !custom.checked;
    }


    function showAssetBreakdown() {

        if (!lastStress) {
            return;
        }

        const scenario =
            lastStress.scenarios[Number(selector.value)];

        $("stress-assets").replaceChildren(
            ...scenario.assets.map(asset =>
                stressTableRow(
                    asset.ticker,
                    [
                        percent(asset.weight),
                        percent(asset.shock),
                        money(asset.value_change)
                    ]
                )
            )
        );
    }


    custom.addEventListener(
        "change",
        showCustomInput
    );

    showCustomInput();

    selector.addEventListener(
        "change",
        showAssetBreakdown
    );


    button.addEventListener("click", async () => {

        button.disabled = true;
        status.className = "muted";

        try {

            const payload = buildStressPayload(
                getAllocation("allocation"),

                $("initial").value,

                custom.checked
                    ? $("stress-shocks").value
                    : null
            );

            status.textContent =
                "Evaluating hypothetical scenarios...";

            const data = await requestStressTest(payload);


            $("stress-summary").textContent =
                `Initial value: ${money(data.initial_value)} | ` +
                Object.entries(data.weights)
                    .map(([ticker, weight]) =>
                        `${ticker}: ${percent(weight)}`
                    ).join(" | ");


            $("stress-scenarios").replaceChildren(
                ...data.scenarios.map(scenario =>
                    stressTableRow(
                        scenario.name,
                        [
                            percent(scenario.portfolio_return),
                            money(scenario.value_change),
                            money(scenario.ending_value)
                        ]
                    )
                )
            );


            selector.replaceChildren(
                ...data.scenarios.map((scenario, index) => {

                    const option = element(
                        "option",
                        scenario.name
                    );

                    option.value = String(index);

                    return option;
                })
            );


            lastStress = data;

            selector.value = "0";

            showAssetBreakdown();

            $("stress-results").hidden = false;
            $("empty").hidden = true;

            status.textContent =
                "Stress test complete. Results reflect the submitted settings.";

            $("stress-results").scrollIntoView({
                block: "start"
            });

        } catch (error) {

            status.className = "muted error";
            status.textContent = error.message;

        } finally {

            button.disabled = false;
        }
    });
}


if (typeof module !== "undefined" && module.exports) {

    module.exports = {
        buildStressPayload,
        requestStressTest,
        initStressDashboard
    };

} else {

    initStressDashboard();
}