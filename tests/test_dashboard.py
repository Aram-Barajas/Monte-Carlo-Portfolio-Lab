import unittest
from fastapi.testclient import TestClient
from backend.api import app
from html.parser import HTMLParser

class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_dashboard_loads(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn('id="simulation-form"', response.text)
        self.assertIn('id="compare-enabled"', response.text)

    def test_simulation_model_controls_and_caveats(self):
        page = self.client.get("/").text
        for identifier in ("simulation-model", "block-length", "drift-weight", "simulation-model-summary"):
            self.assertIn(f'id="{identifier}"', page)
        self.assertIn('value="gaussian_uncertain"', page)
        self.assertIn('value="block_bootstrap"', page)
        self.assertIn("not confidence intervals", page)

    def test_trading_and_inflation_controls(self):
        page = self.client.get("/").text
        for identifier in ("rebalancing", "trading-cost-bps", "rebalance-threshold",
                           "annual-inflation", "chart-dollar-mode", "simulation-policy-summary"):
            self.assertIn(f'id="{identifier}"', page)
        self.assertIn('value="real-projections"', page)

    def test_workspace_navigation(self):
        page = self.client.get("/").text
        script = self.client.get("/static/workspace.js")
        for view in ("overview", "simulation", "backtesting", "optimization", "stress", "risk", "planning", "validation", "discovery"):
            self.assertIn(f'data-workspace-tab="{view}"', page)
            self.assertIn(f'data-result-view="{view}"', page)
        self.assertIn('id="run-overview"', page)
        self.assertIn('id="overview-results"', page)
        self.assertIn('src="/static/workspace.js"', page)
        self.assertEqual(script.status_code, 200)
        self.assertIn("/api/portfolio", script.text)

    def test_advanced_risk_dashboard(self):
        page = self.client.get("/").text
        for identifier in ("run-risk-analysis", "risk-contributions", "rolling-return-chart",
                           "rolling-volatility-chart", "run-crisis", "crisis-results", "crisis-chart"):
            self.assertIn(f'id="{identifier}"', page)
        script = self.client.get("/static/advanced-risk.js")
        self.assertEqual(script.status_code, 200)
        self.assertIn("/api/risk-analysis", script.text)
        self.assertIn("/api/crisis-replay", script.text)

    def test_goal_planning_dashboard(self):
        page = self.client.get("/").text
        for identifier in ("run-plan", "plan-goal", "plan-probability", "planning-results",
                           "plan-chart", "plan-sensitivity", "plan-annual"):
            self.assertIn(f'id="{identifier}"', page)
        script = self.client.get("/static/planning.js")
        self.assertEqual(script.status_code, 200)
        self.assertIn("/api/plan", script.text)

    def test_model_validation_dashboard(self):
        page = self.client.get("/").text
        for identifier in ("run-validation", "validation-results", "validation-chart",
                           "validation-scores", "validation-pit", "validation-fold-table"):
            self.assertIn(f'id="{identifier}"', page)
        script = self.client.get("/static/model-validation.js")
        self.assertEqual(script.status_code, 200)
        self.assertIn("/api/validate-models", script.text)

    def test_candidate_discovery_dashboard(self):
        page = self.client.get("/").text
        for identifier in ("run-discovery", "discovery-results", "discovery-ranking", "discovery-weights",
                           "discovery-training", "discovery-holdout-table", "discovery-excluded"):
            self.assertIn(f'id="{identifier}"', page)
        script = self.client.get("/static/discovery.js")
        self.assertEqual(script.status_code, 200)
        self.assertIn("/api/discover", script.text)

    def test_stylesheet_loads(self):
        response = self.client.get("/static/styles.css")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/css", response.headers["content-type"])

    def test_robust_optimization_dashboard(self):
        page = self.client.get("/").text
        for identifier in ("run-robust", "robust-results", "robust-weights",
                           "robust-training", "robust-validation"):
            self.assertIn(f'id="{identifier}"', page)
        script = self.client.get("/static/robust-optimization.js")
        self.assertEqual(script.status_code, 200)
        self.assertIn("/api/robust-optimize", script.text)

    def test_script_loads(self):
        response = self.client.get("/static/app.js")
        self.assertEqual(response.status_code, 200)
        self.assertIn("javascript", response.headers["content-type"])
        self.assertIn("/api/compare", response.text)

    def test_backend_not_public(self):
        response = self.client.get("/static/backend/api.py")
        self.assertEqual(response.status_code, 404)

    def test_correlation_heatmap_markup(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)

        self.assertIn(
            'id="correlation-a"',
            response.text
        )

        self.assertIn(
            'id="correlation-b"',
            response.text
        )

        self.assertIn(
            'id="correlation-b-panel"',
            response.text
        )

    def test_correlation_heatmap_assets(self):
        script = self.client.get("/static/app.js").text

        css = self.client.get("/static/styles.css").text

        self.assertIn("function renderCorrelation", script)
        self.assertIn("corr-undefined", css)
        self.assertIn("corr-positive-strong", css)

    def test_csv_export_markup(self):

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)

        self.assertIn(
            'id="export-format"',
            response.text
        )

        self.assertIn(
            'id="export-download"',
            response.text
        )

        self.assertIn(
            "/static/export.js",
            response.text
        )

    def test_csv_export_script(self):

        response = self.client.get("/static/export.js")

        self.assertEqual(response.status_code, 200)

        self.assertIn(
            "function buildCsvRows",
            response.text
        )

        self.assertIn(
            "function downloadSimulationCsv",
            response.text
        )
    def test_chart_inspection_loads(self):
        page = self.client.get("/").text
        script = self.client.get("/static/chart-tools.js")

        self.assertIn('id="chart-day"', page)
        self.assertIn('id="chart-value-median"', page)
        self.assertIn('id="chart-value-b-row"', page)

        self.assertEqual(script.status_code, 200)

        self.assertIn(
            "function attachChartInspection",
            script.text
        )
        self.assertLess(
            page.index('id="chart"'),
            page.index('id="chart-day"')
        )

        self.assertLess(
            page.index('id="chart-day"'),
            page.index('id="comparison-results"')
        )
        self.assertLess(
            page.index('id="chart"'),
            page.index('id="chart-day"')
        )

        self.assertLess(
            page.index('id="chart-day"'),
            page.index('id="comparison-results"')
        )
    def test_backtest_dashboard_loads(self):
        page = self.client.get("/").text

        script = self.client.get("/static/backtest.js")

        for element in (
            "run-backtest",
            "backtest-results",
            "backtest-metrics",
            "backtest-value-chart",
            "backtest-drawdown-chart"
        ):
            self.assertIn(
                f'id="{element}"',
                page
            )

        self.assertIn(
            'src="/static/backtest.js"',
            page
        )

        self.assertEqual(script.status_code, 200)

        self.assertIn(
            "/api/backtest",
            script.text
        )
    def test_stress_dashboard_loads(self):

        page = self.client.get("/").text

        script = self.client.get("/static/stress-test.js")

        for id in (
            "run-stress-test",
            "stress-custom-enabled",
            "stress-shocks",
            "stress-results",
            "stress-scenarios",
            "stress-scenario-select",
            "stress-assets"
        ):
            self.assertIn(
                f'id="{id}"',
                page
            )

        self.assertIn(
            'src="/static/stress-test.js"',
            page
        )

        self.assertEqual(script.status_code, 200)

        self.assertIn(
            "/api/stress-test",
            script.text
        )

    def test_benchmark_dashboard_loads(self):

        page = self.client.get("/").text

        script = self.client.get("/static/benchmark.js")

        for id in (
            "benchmark-ticker",
            "run-benchmark",
            "benchmark-results",
            "benchmark-chart",
            "benchmark-table",
            "benchmark-excess"
        ):
            self.assertIn(
                f'id="{id}"',
                page
            )

        self.assertIn(
            'src="/static/benchmark.js"',
            page
        )

        self.assertEqual(
            script.status_code,
            200
        )

        self.assertIn(
            "/api/benchmark",
            script.text
        )

    def test_independent_result_sections(self):

        class Sections(HTMLParser):

            stack = []
            parents = {}

            def handle_starttag(self, tag, attrs):

                if tag == "section":

                    attrs = dict(attrs)

                    name = attrs.get(
                        "id",
                        attrs.get("class")
                    )

                    self.parents[name] = (
                        self.stack[-1]
                        if self.stack
                        else None
                    )

                    self.stack.append(name)

            def handle_endtag(self, tag):

                if tag == "section":
                    self.stack.pop()

        parser = Sections()

        parser.feed(
            self.client.get("/").text
        )

        for id in (
            "backtest-results",
            "stress-results",
            "benchmark-results",
            "frontier-results"
        ):
            self.assertEqual(
                parser.parents[id],
                "results"
            )

    def test_frontier_dashboard_loads(self):

        page = self.client.get("/").text

        script = self.client.get("/static/frontier.js")

        for id in (
            "frontier-cap",
            "frontier-rate",
            "run-frontier",
            "frontier-results",
            "frontier-chart",
            "frontier-select",
            "frontier-weights"
        ):

            self.assertIn(
                f'id="{id}"',
                page
            )

        self.assertIn(
            'src="/static/frontier.js"',
            page
        )

        self.assertEqual(
            script.status_code,
            200
        )

        self.assertIn(
            "/api/frontier",
            script.text
        )
