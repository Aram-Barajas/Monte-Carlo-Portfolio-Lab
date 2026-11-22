import unittest
from fastapi.testclient import TestClient
from backend.api import app


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_dashboard_loads(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn('id="simulation-form"', response.text)
        self.assertIn('id="compare-enabled"', response.text)

    def test_stylesheet_loads(self):
        response = self.client.get("/static/styles.css")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/css", response.headers["content-type"])

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