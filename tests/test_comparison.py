import unittest
from unittest.mock import patch

import pandas as pd
from fastapi.testclient import TestClient
from backend.api import app


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.returns = pd.DataFrame({
            "NVDA": [.02, -.01, .03, -.02],
            "VTI": [.01, -.005, .015, -.01],
            "AMZN": [-.01, .02, -.02, .01]
        })
        self.payload = {
            "tickers": ["NVDA", "VTI"],
            "weights": {"NVDA": .4, "VTI": .6},
            "comparison_weights": {"VTI": .5, "AMZN": .5},
            "start": "2025-01-01", "end": "2026-01-01",
            "trading_days": 42, "num_simulations": 20,
            "initial_value": 1000, "monthly_contribution": 100, "seed": 42
        }

    @patch("backend.api.fetch_daily_returns")
    def test_shared_history_and_results(self, fetch):
        fetch.return_value = self.returns
        response = self.client.post("/api/compare", json=self.payload)
        self.assertEqual(response.status_code, 200)
        fetch.assert_called_once_with(["NVDA", "VTI", "AMZN"], "2025-01-01", "2026-01-01")
        body = response.json()
        self.assertEqual(body["seed"], 42)
        for key in ("portfolio_a", "portfolio_b"):
            item = body[key]
            self.assertEqual(item["analysis"]["observations"], 4)
            self.assertEqual(item["simulation_risk"]["total_invested"], 1200)
            self.assertEqual(len(item["percentiles"]), 43)
            self.assertEqual(len(item["ending_values"]), 20)
        self.assertEqual(body["portfolio_b"]["analysis"]["tickers"], ["VTI", "AMZN"])
        self.assertNotEqual(body["portfolio_a"]["ending_values"], body["portfolio_b"]["ending_values"])

    @patch("backend.api.fetch_daily_returns")
    def test_identical_portfolios_share_shocks(self, fetch):
        fetch.return_value = self.returns[["NVDA", "VTI"]]
        payload = {**self.payload, "comparison_weights": {"VTI": .6, "NVDA": .4}, "seed": None}
        response = self.client.post("/api/compare", json=payload)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["portfolio_a"]["ending_values"], body["portfolio_b"]["ending_values"])
        self.assertIsInstance(body["seed"], int)

    @patch("backend.api.fetch_daily_returns")
    def test_invalid_comparison_weights(self, fetch):
        response = self.client.post("/api/compare", json={**self.payload, "comparison_weights": {"VTI": .5}})
        self.assertEqual(response.status_code, 422)
        fetch.assert_not_called()

    @patch("backend.api.fetch_daily_returns")
    def test_combined_size_limit(self, fetch):
        payload = {**self.payload, "comparison_weights": {f"T{i}": 1/20 for i in range(20)}}
        response = self.client.post("/api/compare", json=payload)
        self.assertEqual(response.status_code, 422)
        fetch.assert_not_called()

    @patch("backend.api.fetch_daily_returns", side_effect=RuntimeError("offline"))
    def test_market_failure(self, fetch):
        response = self.client.post("/api/compare", json=self.payload)
        self.assertEqual(response.status_code, 502)

    @patch("backend.api.fetch_daily_returns")
    def test_reproducible(self, fetch):
        fetch.return_value = self.returns
        a = self.client.post("/api/compare", json=self.payload)
        b = self.client.post("/api/compare", json=self.payload)
        self.assertEqual(a.status_code, 200)
        self.assertEqual(a.json(), b.json())
