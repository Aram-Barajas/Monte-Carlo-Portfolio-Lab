import unittest
from unittest.mock import patch

import pandas as pd
from fastapi.testclient import TestClient

from backend.api import app


class APITests(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)

        self.prices = pd.DataFrame(
            {
                "NVDA": [100, 102, 101, 104],
                "VTI": [200, 201, 202, 203]
            },
            index=pd.date_range(
                "2025-01-02",
                periods=4,
                freq="B"
            )
        )

        self.returns = self.prices.pct_change().dropna()

        self.market = {
            "tickers": ["NVDA", "VTI"],
            "start": "2025-01-01",
            "end": "2026-01-01"
        }

        self.portfolio = {
            **self.market,
            "weights": {
                "NVDA": 0.4,
                "VTI": 0.6
            }
        }

        self.simulation = {
            **self.portfolio,
            "trading_days": 42,
            "num_simulations": 20,
            "initial_value": 1000,
            "monthly_contribution": 100,
            "seed": 42
        }

    def test_health(self):
        response = self.client.get("/api/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    @patch("backend.api.fetch_daily_returns")
    def test_simulation_model_settings_and_generated_seed(self, fetch):
        fetch.return_value = self.returns
        for model in ("gaussian", "gaussian_uncertain", "block_bootstrap"):
            with self.subTest(model=model):
                payload = {**self.simulation, "model": model, "block_length": 2,
                           "drift_weight": .5, "seed": None}
                response = self.client.post("/api/simulate", json=payload)
                self.assertEqual(response.status_code, 200)
                body = response.json()
                self.assertEqual(body["model"], model)
                self.assertEqual(body["drift_weight"], .5)
                self.assertEqual(body["block_length"], 2 if model == "block_bootstrap" else None)
                self.assertIsInstance(body["seed"], int)
                repeated = self.client.post("/api/simulate", json={**payload, "seed": body["seed"]})
                self.assertEqual(body, repeated.json())

    @patch("backend.api.fetch_daily_returns")
    def test_invalid_simulation_model_settings(self, fetch):
        fetch.return_value = self.returns
        for settings in ({"model": "invalid"}, {"drift_weight": 1.2},
                         {"block_length": 0}, {"model": "block_bootstrap", "block_length": 4}):
            with self.subTest(settings=settings):
                response = self.client.post("/api/simulate", json={**self.simulation, **settings})
                self.assertEqual(response.status_code, 422)

    def test_all_historical_analytics_reject_price_gaps(self):
        prices = self.prices.copy().astype(float)
        prices.loc[prices.index[1], "NVDA"] = float("nan")
        requests = {
            "/api/portfolio": self.portfolio,
            "/api/simulate": self.simulation,
            "/api/compare": {**self.simulation, "comparison_weights": {"VTI": 1.0}},
            "/api/optimize": self.portfolio,
            "/api/frontier": self.portfolio,
            "/api/backtest": self.portfolio,
            "/api/benchmark": {**self.portfolio, "benchmark": "VTI"},
        }

        # Mock downloads, not return calculations: exercise the real alignment.
        with patch("backend.market_data.fetch_historical_prices", return_value=prices), \
             patch("backend.api.fetch_historical_prices", return_value=prices):
            for endpoint, payload in requests.items():
                with self.subTest(endpoint=endpoint):
                    response = self.client.post(endpoint, json=payload)
                    self.assertEqual(response.status_code, 422)
                    self.assertIn("missing prices", response.json()["detail"])
                    self.assertIn("NVDA", response.json()["detail"])

    def test_historical_analytics_use_complete_overlap(self):
        prices = self.prices.astype(float)
        prices.iloc[0, 0] = float("nan")

        with patch("backend.market_data.fetch_historical_prices", return_value=prices):
            response = self.client.post("/api/portfolio", json=self.portfolio)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["observations"], 2)
        expected = (((101 / 102 - 1) + (104 / 101 - 1)) / 2) * 252
        self.assertAlmostEqual(response.json()["asset_metrics"][0]["annualized_return"], expected)

    def test_comparison_rejects_gaps_in_assets_only_in_second_portfolio(self):
        prices = self.prices.assign(SPY=[100., float("nan"), 103., 105.])
        payload = {**self.simulation, "comparison_weights": {"SPY": 1.0}}
        with patch("backend.market_data.fetch_historical_prices", return_value=prices) as fetch:
            response = self.client.post("/api/compare", json=payload)
        self.assertEqual(response.status_code, 422)
        self.assertIn("missing prices", response.json()["detail"])
        self.assertIn("SPY", response.json()["detail"])
        self.assertEqual(fetch.call_args.args[0], ["NVDA", "VTI", "SPY"])

    def test_raw_market_data_retains_missing_price(self):
        prices = self.prices.astype(float)
        prices.iloc[1, 0] = float("nan")
        with patch("backend.api.fetch_historical_prices", return_value=prices):
            response = self.client.post("/api/market-data", json=self.market)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["prices"]), 4)
        self.assertIsNone(response.json()["prices"][1]["NVDA"])

    @patch("backend.api.fetch_historical_prices")
    def test_market_data(self, fetch):
        fetch.return_value = self.prices

        response = self.client.post(
            "/api/market-data",
            json=self.market
        )

        self.assertEqual(response.status_code, 200)

        self.assertEqual(
            response.json()["prices"][0],
            {
                "date": "2025-01-02",
                "NVDA": 100,
                "VTI": 200
            }
        )

    @patch("backend.api.fetch_daily_returns")
    def test_portfolio(self, fetch):
        fetch.return_value = self.returns

        response = self.client.post(
            "/api/portfolio",
            json=self.portfolio
        )

        self.assertEqual(response.status_code, 200)

        body = response.json()

        self.assertEqual(body["observations"], 3)

        self.assertIn(
            "annualized_return",
            body["portfolio_metrics"]
        )

        self.assertIn(
            "sharpe_ratio",
            body["historical_risk"]
        )

        self.assertAlmostEqual(
            body["correlation"][0]["NVDA"],
            1.0
        )

    @patch("backend.api.fetch_daily_returns")
    def test_simulation(self, fetch):
        fetch.return_value = self.returns

        response = self.client.post(
            "/api/simulate",
            json=self.simulation
        )

        self.assertEqual(response.status_code, 200)

        body = response.json()

        self.assertEqual(len(body["percentiles"]), 43)
        self.assertEqual(len(body["ending_values"]), 20)

        self.assertEqual(
            body["percentiles"][0]["median"],
            1000
        )

        self.assertEqual(
            body["simulation_risk"]["total_invested"],
            1200
        )

        second = self.client.post(
            "/api/simulate",
            json=self.simulation
        )

        self.assertEqual(body, second.json())

    @patch("backend.api.fetch_daily_returns")
    def test_invalid_weights(self, fetch):
        payload = {
            **self.portfolio,
            "weights": {
                "NVDA": 0.1,
                "VTI": 0.1
            }
        }

        response = self.client.post(
            "/api/portfolio",
            json=payload
        )

        self.assertEqual(response.status_code, 422)
        fetch.assert_not_called()

    @patch("backend.api.fetch_historical_prices")
    def test_invalid_dates(self, fetch):
        payload = {
            **self.market,
            "end": "2024-01-01"
        }

        response = self.client.post(
            "/api/market-data",
            json=payload
        )

        self.assertEqual(response.status_code, 422)
        fetch.assert_not_called()

    @patch("backend.api.fetch_daily_returns")
    def test_simulation_limit(self, fetch):
        payload = {
            **self.simulation,
            "trading_days": 2520,
            "num_simulations": 5000
        }

        response = self.client.post(
            "/api/simulate",
            json=payload
        )

        self.assertEqual(response.status_code, 422)
        fetch.assert_not_called()

    @patch(
        "backend.api.fetch_historical_prices",
        side_effect=RuntimeError("offline")
    )
    def test_market_data_failure(self, fetch):
        response = self.client.post(
            "/api/market-data",
            json=self.market
        )

        self.assertEqual(response.status_code, 502)

    @patch("backend.api.fetch_daily_returns")
    def test_undefined_correlation(self, fetch):
        fetch.return_value = pd.DataFrame({
            "NVDA": [0.01, 0.01],
            "VTI": [0.02, -0.01]
        })

        response = self.client.post(
            "/api/portfolio",
            json=self.portfolio
        )

        self.assertEqual(response.status_code, 200)

        self.assertIsNone(
            response.json()["correlation"][0]["NVDA"]
        )
