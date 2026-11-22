import unittest
from unittest.mock import Mock, patch

import pandas as pd
from fastapi.testclient import TestClient

from backend.api import app
from backend.market_cache import MarketDataCache
from backend.market_data import (
    fetch_historical_prices,
    fetch_daily_returns
)


class MarketCacheTests(unittest.TestCase):

    def setUp(self):
        self.now = 0

        self.cache = MarketDataCache(
            max_entries=2,
            ttl_seconds=10,
            clock=lambda: self.now
        )

        self.prices = pd.DataFrame(
            {
                "NVDA": [100.0, 110.0],
                "VTI": [200.0, 210.0]
            },
            index=pd.date_range(
                "2025-01-02",
                periods=2
            )
        )

        self.start = "2025-01-01"
        self.end = "2025-02-01"

    def test_expiration(self):
        self.cache.put("prices", self.prices)

        self.now = 9
        self.assertIsNotNone(
            self.cache.get("prices")
        )

        self.now = 10
        self.assertIsNone(
            self.cache.get("prices")
        )

    def test_least_recently_used_eviction(self):
        self.cache.put("a", self.prices)
        self.cache.put("b", self.prices)

        self.cache.get("a")
        self.cache.put("c", self.prices)

        self.assertIsNone(self.cache.get("b"))
        self.assertIsNotNone(self.cache.get("a"))
        self.assertIsNotNone(self.cache.get("c"))

    def test_copies_protect_cached_prices(self):
        original = self.prices.copy()

        self.cache.put("prices", self.prices)

        self.prices.iloc[0, 0] = 999

        result = self.cache.get("prices")
        result.iloc[0, 0] = 888

        pd.testing.assert_frame_equal(
            self.cache.get("prices"),
            original
        )

    def test_download_reused_across_order_and_returns(self):
        with patch(
            "backend.market_data._price_cache",
            self.cache
        ), patch(
            "backend.market_data._download_historical_prices",
            return_value=self.prices
        ) as download:

            first = fetch_historical_prices(
                ["vti", "nvda"],
                self.start,
                self.end
            )

            self.assertEqual(
                list(first.columns),
                ["VTI", "NVDA"]
            )

            first.iloc[0, 0] = 999

            second = fetch_daily_returns(
                ["NVDA", "VTI"],
                self.start,
                self.end
            )

            self.assertAlmostEqual(
                second.iloc[0]["VTI"],
                0.05
            )

            download.assert_called_once_with(
                ["NVDA", "VTI"],
                self.start,
                self.end
            )

            self.now = 10

            fetch_historical_prices(
                ["VTI", "NVDA"],
                self.start,
                self.end
            )

            self.assertEqual(download.call_count, 2)

    def test_changed_dates_or_tickers_download_again(self):

        def load(symbols, start, end):
            return self.prices[symbols]

        with patch(
            "backend.market_data._price_cache",
            self.cache
        ), patch(
            "backend.market_data._download_historical_prices",
            side_effect=load
        ) as download:

            fetch_historical_prices(
                ["VTI", "NVDA"],
                self.start,
                self.end
            )

            fetch_historical_prices(
                ["VTI", "NVDA"],
                self.start,
                "2025-03-01"
            )

            fetch_historical_prices(
                ["VTI"],
                self.start,
                self.end
            )

            self.assertEqual(download.call_count, 3)

    def test_failed_download_is_not_cached(self):
        with patch(
            "backend.market_data._price_cache",
            self.cache
        ), patch(
            "backend.market_data._download_historical_prices",
            side_effect=[
                RuntimeError("Offline"),
                self.prices
            ]
        ) as download:

            with self.assertRaises(RuntimeError):
                fetch_historical_prices(
                    ["NVDA", "VTI"],
                    self.start,
                    self.end
                )

            result = fetch_historical_prices(
                ["NVDA", "VTI"],
                self.start,
                self.end
            )

            pd.testing.assert_frame_equal(
                result,
                self.prices
            )

            self.assertEqual(download.call_count, 2)

    def test_custom_downloader_bypasses_cache(self):
        downloader = Mock(
            return_value=pd.concat(
                {"Close": self.prices},
                axis=1
            )
        )

        with patch(
            "backend.market_data._price_cache",
            self.cache
        ):

            for _ in range(2):
                fetch_historical_prices(
                    ["NVDA", "VTI"],
                    self.start,
                    self.end,
                    downloader=downloader
                )

            self.assertEqual(downloader.call_count, 2)
            self.assertEqual(len(self.cache.entries), 0)

    def test_api_reuses_market_prices_between_requests(self):
        prices = pd.DataFrame(
            {
                "NVDA": [100.0, 102.0, 101.0, 104.0],
                "VTI": [200.0, 201.0, 202.0, 203.0]
            },
            index=pd.date_range(
                "2025-01-02",
                periods=4
            )
        )

        market = {
            "tickers": ["NVDA", "VTI"],
            "start": self.start,
            "end": self.end
        }

        simulation = {
            **market,
            "weights": {
                "NVDA": 0.4,
                "VTI": 0.6
            },
            "num_simulations": 10,
            "trading_days": 21,
            "seed": 42
        }

        with patch(
            "backend.market_data._price_cache",
            self.cache
        ), patch(
            "backend.market_data._download_historical_prices",
            return_value=prices
        ) as download:

            client = TestClient(app)

            market_response = client.post(
                "/api/market-data",
                json=market
            )

            first = client.post(
                "/api/simulate",
                json=simulation
            )

            second = client.post(
                "/api/simulate",
                json={
                    **simulation,
                    "initial_value": 2000
                }
            )

            for response in (market_response, first, second):
                self.assertEqual(response.status_code, 200)

            self.assertEqual(
                first.json()["percentiles"][0]["median"],
                1000
            )

            self.assertEqual(
                second.json()["percentiles"][0]["median"],
                2000
            )

            download.assert_called_once()


if __name__ == "__main__":
    unittest.main()