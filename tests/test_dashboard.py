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
