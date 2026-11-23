import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from backend.advanced_risk import calculate_risk_contributions, calculate_rolling_risk, replay_crisis
from backend.api import app


class AdvancedRiskTests(unittest.TestCase):
    def setUp(self):
        self.returns = pd.DataFrame({
            "A": [.01, -.01, .01, -.01],
            "B": [.02, .02, -.02, -.02],
        }, index=pd.date_range("2025-01-02", periods=4))
        self.weights = {"A": .5, "B": .5}
        self.prices = pd.DataFrame({
            "A": [100., 80., 90.],
            "B": [100., 90., 80.],
            "SPY": [100., 85., 75.],
        }, index=pd.to_datetime(["2020-02-19", "2020-03-02", "2020-03-23"]))

    def test_euler_identity_and_diversification(self):
        result = calculate_risk_contributions(self.returns, self.weights)
        assets = result["assets"]
        self.assertAlmostEqual(assets[0]["risk_share"], .2)
        self.assertAlmostEqual(assets[1]["risk_share"], .8)
        self.assertAlmostEqual(sum(a["component_contribution"] for a in assets),
                               result["annualized_volatility"])
        self.assertAlmostEqual(result["diversification_ratio"], 3 / np.sqrt(5))
        reversed_result = calculate_risk_contributions(self.returns[["B", "A"]], self.weights)
        self.assertAlmostEqual(reversed_result["assets"][0]["risk_share"], .8)

    def test_negative_risk_share(self):
        returns = self.returns.assign(B=-self.returns.A)
        result = calculate_risk_contributions(returns, {"A": .8, "B": .2})
        self.assertAlmostEqual(result["assets"][0]["risk_share"], 4 / 3)
        self.assertAlmostEqual(result["assets"][1]["risk_share"], -1 / 3)

    def test_zero_volatility_and_zero_weight(self):
        result = calculate_risk_contributions(self.returns.assign(B=-self.returns.A), self.weights)
        self.assertIsNone(result["diversification_ratio"])
        self.assertTrue(all(a["risk_share"] is None for a in result["assets"]))
        weighted = calculate_risk_contributions(self.returns, {"A": 1, "B": 0})
        self.assertEqual(weighted["assets"][1]["risk_share"], 0)

    def test_rolling_compounding_and_volatility(self):
        result = calculate_rolling_risk(self.returns, self.weights, 3)
        expected = self.returns.mean(axis=1).iloc[:3]
        self.assertEqual(len(result), 2)
        self.assertEqual(result.index[0], self.returns.index[2])
        self.assertAlmostEqual(result.iloc[0].trailing_return, (1 + expected).prod() - 1)
        self.assertAlmostEqual(result.iloc[0].annualized_volatility, expected.std(ddof=1) * np.sqrt(252))
        self.assertTrue(calculate_rolling_risk(self.returns, self.weights, 63).empty)
        for window in (1, 253, 3.5, True):
            with self.subTest(window=window), self.assertRaises(ValueError):
                calculate_rolling_risk(self.returns, self.weights, window)

    def test_crisis_replay_math(self):
        result = replay_crisis(self.prices, self.weights, "covid")
        expected = (1 + self.prices[["A", "B"]].pct_change().iloc[1:].mean(axis=1)).prod()
        self.assertAlmostEqual(result["portfolio"]["ending_value"], 1000 * expected)
        self.assertAlmostEqual(result["benchmark"]["ending_value"], 750)
        self.assertAlmostEqual(result["benchmark"]["max_drawdown"], .25)
        self.assertEqual(result["portfolio"]["observations"], 2)

    def test_incomplete_crisis_rejected(self):
        for row in (0, 1, 2):
            prices = self.prices.copy()
            prices.iloc[row, 0] = np.nan
            with self.subTest(row=row), self.assertRaises(ValueError):
                replay_crisis(prices, self.weights, "covid")
        with self.assertRaises(ValueError):
            replay_crisis(self.prices, self.weights, "unknown")

    def test_risk_endpoint(self):
        request = {"tickers": ["A", "B"], "weights": self.weights,
                   "start": "2025-01-01", "end": "2025-02-01", "rolling_window": 3}
        with patch("backend.api.fetch_daily_returns", return_value=self.returns):
            response = TestClient(app).post("/api/risk-analysis", json=request)
            self.assertEqual(response.status_code, 200, response.text)
            data = response.json()
            self.assertEqual(data["rolling"][0]["date"], "2025-01-04")
            self.assertEqual(data["last_return_date"], "2025-01-05")
            self.assertEqual(len(data["rolling"]), 2)
            request["rolling_window"] = 63
            response = TestClient(app).post("/api/risk-analysis", json=request)
            self.assertEqual(response.json()["rolling"], [])
            request["rolling_window"] = 1
            self.assertEqual(TestClient(app).post("/api/risk-analysis", json=request).status_code, 422)

    def test_crisis_endpoint_uses_preset_dates(self):
        request = {"tickers": ["A", "B"], "weights": self.weights, "scenario": "covid", "initial_value": 1000}
        with patch("backend.api.fetch_historical_prices", return_value=self.prices) as fetch:
            response = TestClient(app).post("/api/crisis-replay", json=request)
            self.assertEqual(response.status_code, 200, response.text)
            fetch.assert_called_once_with(["A", "B", "SPY"], "2020-02-19", "2020-03-24")
            self.assertEqual(response.json()["portfolio"]["trajectory"][-1]["date"], "2020-03-23")
        request["scenario"] = "invalid"
        self.assertEqual(TestClient(app).post("/api/crisis-replay", json=request).status_code, 422)
