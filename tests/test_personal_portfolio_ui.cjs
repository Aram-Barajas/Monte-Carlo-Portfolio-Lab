const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { parseHoldingsCsv, portfolioConcentration } = require("../frontend/personal-portfolio.js");

test("CSV weight import handles header, quotes, alias normalization and rounded percentages", () => {
    const rows = parseHoldingsCsv('ticker,weight\r\n"BRK.B",25\r\nVTI,75\r\n');
    assert.equal(rows.length, 2);
    assert.deepEqual(rows[0], ["BRK-B", 25]);
    assert.deepEqual(rows[1], ["VTI", 75]);
});

test("CSV shares/price import normalizes notional holdings without uploading transactions", () => {
    const rows = parseHoldingsCsv("ticker,shares,price\nVTI,2,250\nNVDA,5,100\n");
    assert.deepEqual(rows, [["VTI", 50], ["NVDA", 50]]);
});

test("CSV parser rejects duplicate aliases, missing values, malformed quotes and formula payloads", () => {
    for (const content of [
        "ticker,weight\nBRK.B,50\nBRK-B,50",
        "ticker,weight\nVTI,90\nNVDA,0",
        "ticker,weight\nVTI,90\nNVDA,10,EXTRA",
        "ticker,weight\n=SUM(A1),100",
        'ticker,weight\n"VTI,100',
        "ticker,shares,price\nVTI,1,-100",
        "ticker,weight\nVTI,10\nNVDA,10"
    ]) assert.throws(() => parseHoldingsCsv(content));
});

test("portfolio concentration is a warning, not an ETF look-through assertion", () => {
    assert.match(portfolioConcentration({ VTI: .7, NVDA: .3 }), /VTI 70.0%.*NVDA 30.0%/);
    assert.match(portfolioConcentration({ A: .2, B: .2, C: .2, D: .2, E: .2 }), /ETF/);
});

test("dashboard serves approved private tools, correct default model and rate assumption", () => {
    const html = fs.readFileSync(path.join(__dirname, "../frontend/index.html"), "utf8");
    assert.match(html, /simulation-model[\\s\\S]*value="gaussian_uncertain" selected/);
    for (const id of ["personal-csv", "personal-save", "personal-load", "personal-delete", "analysis-rate"]) {
        assert.ok(html.includes('id="' + id + '"'), id);
    }
    assert.match(html, /\/static\/personal-portfolio\.js/);
});
