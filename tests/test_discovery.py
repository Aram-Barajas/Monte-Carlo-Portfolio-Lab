import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from backend.api import app
from backend.discovery import screen_candidates


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.dates = pd.bdate_range("2024-01-01", periods=113)
        daily = np.tile([.01, -.01, .01, -.01], 28)
        other = np.tile([.02, .02, -.02, -.02], 28)
        self.prices = pd.DataFrame({
            "A": 100 * np.r_[1, np.cumprod(1 + daily)],
            "B": 100 * np.r_[1, np.cumprod(1 + other)],
        }, index=self.dates)
        self.weights = {"A": .6, "B": .4}
        self.base_returns = daily * .6 + other * .4
        self.candidate_prices = {
            "HEDGE": self.prices_for("HEDGE", -self.base_returns),
            "RISK": self.prices_for("RISK", self.base_returns * 3),
            "CASH": self.prices_for("CASH", np.zeros(112)),
            "GROWTH": self.prices_for("GROWTH", self.base_returns + .001),
        }

    def prices_for(self, ticker, returns):
        return pd.DataFrame({ticker: 100 * np.r_[1, np.cumprod(1 + returns)]}, index=self.dates)

    def screen(self, candidates, **options):
        return screen_candidates(self.prices, self.weights, candidates,
                                 lambda ticker: self.candidate_prices[ticker], **options)

    def test_ranking_and_exact_hypothetical_weights(self):
        result = self.screen(["RISK", "HEDGE", "CASH"], candidate_weight=.1)
        self.assertEqual([row["ticker"] for row in result["evaluated"]], ["HEDGE", "CASH", "RISK"])
        self.assertEqual(result["training_period"]["observations"], 84)
        self.assertEqual(result["holdout_period"]["observations"], 28)
        hedge, cash, risk = result["evaluated"]
        self.assertEqual(hedge["rank"], 1)
        self.assertEqual(hedge["weights"], {"A": .54, "B": .36000000000000004, "HEDGE": .1})
        self.assertAlmostEqual(sum(hedge["weights"].values()), 1)
        self.assertAlmostEqual(hedge["training"]["candidate_correlation"], -1)
        self.assertIsNone(cash["training"]["candidate_correlation"])
        self.assertGreater(hedge["score"], 0)
        self.assertLess(risk["score"], 0)
        base_vol = np.std(self.base_returns[:84], ddof=1) * np.sqrt(252)
        self.assertAlmostEqual(hedge["training"]["portfolio"]["annualized_volatility"], .8 * base_vol)
        self.assertAlmostEqual(hedge["score"], .2 * base_vol)
        self.assertAlmostEqual(hedge["holdout"]["portfolio"]["total_return"],
                               np.prod(1 + .8 * self.base_returns[84:]) - 1)

    def test_candidate_objectives(self):
        for objective in ("return_improvement", "sharpe_improvement"):
            with self.subTest(objective=objective):
                result = self.screen(["HEDGE", "GROWTH"], objective=objective)
                self.assertEqual(result["evaluated"][0]["ticker"], "GROWTH")
                self.assertGreater(result["evaluated"][0]["score"], 0)

    def test_undefined_sharpe_is_not_ranked(self):
        result = self.screen(["HEDGE", "RISK"], candidate_weight=.5, objective="sharpe_improvement")
        hedge = next(row for row in result["evaluated"] if row["ticker"] == "HEDGE")
        self.assertIsNone(hedge["score"])
        self.assertIsNone(hedge["rank"])

    def test_holdout_changes_do_not_change_ranking(self):
        original = self.screen(["HEDGE", "RISK"])
        altered_returns = -self.base_returns.copy()
        altered_returns[84:] = .03
        self.candidate_prices["HEDGE"] = self.prices_for("HEDGE", altered_returns)
        changed = self.screen(["HEDGE", "RISK"])
        for a, b in zip(original["evaluated"], changed["evaluated"]):
            self.assertEqual(a["ticker"], b["ticker"])
            self.assertEqual(a["training"], b["training"])
            self.assertEqual(a["score"], b["score"])
        self.assertNotEqual(original["evaluated"][0]["holdout"], changed["evaluated"][0]["holdout"])

    def test_partial_failures_do_not_shorten_baseline(self):
        self.candidate_prices["LATE"] = self.candidate_prices["CASH"].rename(columns={"CASH": "LATE"}).iloc[1:]
        self.candidate_prices["GAP"] = self.candidate_prices["CASH"].rename(columns={"CASH": "GAP"}).drop(self.dates[55])
        extra = self.candidate_prices["CASH"].rename(columns={"CASH": "EXTRA"}).copy()
        extra.loc[pd.Timestamp("2024-01-06"), "EXTRA"] = 100.
        self.candidate_prices["EXTRA"] = extra
        def fetch(ticker):
            if ticker == "BAD":
                raise ValueError("No historical data for BAD")
            if ticker == "DOWN":
                raise RuntimeError("provider error")
            if ticker == "A":
                self.fail("Already-held ticker should not be downloaded")
            return self.candidate_prices[ticker]
        result = screen_candidates(self.prices, self.weights, ["A", "LATE", "GAP", "EXTRA", "BAD", "DOWN", "HEDGE"], fetch)
        self.assertEqual([row["ticker"] for row in result["evaluated"]], ["HEDGE"])
        self.assertEqual({item["ticker"] for item in result["excluded"]}, {"A", "LATE", "GAP", "EXTRA", "BAD", "DOWN"})
        self.assertEqual(result["first_price_date"], self.dates[0].strftime("%Y-%m-%d"))
        self.assertEqual(result["last_price_date"], self.dates[-1].strftime("%Y-%m-%d"))
        self.assertEqual(result["training_period"]["observations"], 84)

    def test_reject_short_history_and_bad_parameters(self):
        for options in ({"candidate_weight": 0}, {"holdout_fraction": .51}, {"objective": "buy"},
                        {"annual_risk_free_rate": float("nan")}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.screen(["HEDGE"], **options)
        with self.assertRaises(ValueError):
            self.screen(["HEDGE", "hedge"])
        with self.assertRaises(ValueError):
            screen_candidates(self.prices.iloc[:70], self.weights, ["HEDGE"], lambda _: self.candidate_prices["HEDGE"])
        with self.assertRaises(ValueError):
            self.screen(["HEDGE"], holdout_fraction=.1)

    def test_api_normalizes_aliases_and_fetches_one_candidate_at_a_time(self):
        request = {"tickers": ["A", "B"], "weights": self.weights, "start": "2024-01-01",
                   "end": "2025-01-01", "candidates": ["BRK.B", "A", "HEDGE"]}
        self.candidate_prices["BRK-B"] = self.candidate_prices["CASH"].rename(columns={"CASH": "BRK-B"})
        def fetch(tickers, start, end):
            self.assertEqual((start, end), ("2024-01-01", "2025-01-01"))
            return self.prices if len(tickers) == 2 else self.candidate_prices[tickers[0]]
        with patch("backend.api.fetch_historical_prices", side_effect=fetch) as downloader:
            client = TestClient(app)
            response = client.post("/api/discover", json=request)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual([row["ticker"] for row in response.json()["evaluated"]], ["HEDGE", "BRK-B"])
            self.assertEqual(response.json()["excluded"][0]["ticker"], "A")
            self.assertEqual(downloader.call_count, 3)
            request["candidates"] = ["BRK.B", "BRK-B"]
            self.assertEqual(client.post("/api/discover", json=request).status_code, 422)
            self.assertEqual(downloader.call_count, 3)
