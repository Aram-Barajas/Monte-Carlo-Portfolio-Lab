import unittest
from unittest.mock import Mock

import numpy as np
import pandas as pd

from backend.market_data import (
    calculate_daily_returns,
    fetch_daily_returns,
    fetch_historical_prices,
    normalize_tickers,
    validate_date_range,
)


class MarketDataTests(unittest.TestCase):

    def setUp(self):
        self.dates = pd.date_range(
            "2025-01-02",
            periods=4,
            freq="B"
        )

        self.prices = pd.DataFrame(
            {
                "NVDA": [100, 110, 99, 108.9],
                "VTI": [200, 210, 210, 231]
            },
            index=self.dates
        )

        self.data = pd.concat(
            {"Close": self.prices},
            axis=1
        )

    def test_normalizes_ticker_symbols(self):
        self.assertEqual(
            normalize_tickers(" nvda "),
            ["NVDA"]
        )

        self.assertEqual(
            normalize_tickers(["vti", "BRK-B"]),
            ["VTI", "BRK-B"]
        )

    def test_invalid_or_duplicate_tickers(self):
        for tickers in (
            [],
            [""],
            [123],
            ["NVDA", "nvda"],
            ["NV DA"]
        ):
            with self.subTest(tickers=tickers):
                with self.assertRaises(ValueError):
                    normalize_tickers(tickers)

    def test_date_range_validation(self):
        validate_date_range("2025-01-01", "2025-02-01")

        for start, end in (
            ("01/01/2025", "2025-02-01"),
            ("2025-02-30", "2025-03-01"),
            ("2025-01-01", "2025-01-01"),
            ("2025-02-01", "2025-01-01"),
        ):
            with self.subTest(start=start, end=end):
                with self.assertRaises(ValueError):
                    validate_date_range(start, end)

    def test_download_multiple_tickers_in_requested_order(self):
        downloader = Mock(return_value=self.data)

        result = fetch_historical_prices(
            ["VTI", "NVDA"],
            "2025-01-01",
            "2025-02-01",
            downloader=downloader
        )

        pd.testing.assert_frame_equal(
            result,
            self.prices[["VTI", "NVDA"]].astype(float)
        )

        self.assertTrue(
            downloader.call_args.kwargs["auto_adjust"]
        )

        self.assertEqual(
            downloader.call_args.kwargs["interval"],
            "1d"
        )

    def test_download_single_ticker_flat_columns(self):
        data = pd.DataFrame({
            "Close": self.prices["NVDA"]
        })

        result = fetch_historical_prices(
            "NVDA",
            "2025-01-01",
            "2025-02-01",
            downloader=Mock(return_value=data)
        )

        self.assertEqual(list(result.columns), ["NVDA"])
        self.assertEqual(len(result), 4)

    def test_exclusive_end_date(self):
        result = fetch_historical_prices(
            ["NVDA", "VTI"],
            "2025-01-03",
            "2025-01-07",
            downloader=Mock(return_value=self.data)
        )

        self.assertEqual(len(result), 2)

        self.assertEqual(
            result.index[-1],
            pd.Timestamp("2025-01-06")
        )

    def test_empty_download(self):
        with self.assertRaisesRegex(
            ValueError,
            "No historical price data"
        ):
            fetch_historical_prices(
                "NVDA",
                "2025-01-01",
                "2025-02-01",
                downloader=Mock(
                    return_value=pd.DataFrame()
                )
            )

    def test_missing_ticker(self):
        with self.assertRaisesRegex(ValueError, "MISSING"):
            fetch_historical_prices(
                ["NVDA", "MISSING"],
                "2025-01-01",
                "2025-02-01",
                downloader=Mock(return_value=self.data)
            )

    def test_ticker_with_all_missing_prices(self):
        self.prices["VTI"] = np.nan

        data = pd.concat(
            {"Close": self.prices},
            axis=1
        )

        with self.assertRaisesRegex(ValueError, "VTI"):
            fetch_historical_prices(
                ["NVDA", "VTI"],
                "2025-01-01",
                "2025-02-01",
                downloader=Mock(return_value=data)
            )

    def test_download_failure(self):
        with self.assertRaisesRegex(
            RuntimeError,
            "Unable to download"
        ):
            fetch_historical_prices(
                "NVDA",
                "2025-01-01",
                "2025-02-01",
                downloader=Mock(
                    side_effect=ConnectionError("Offline")
                )
            )

    def test_daily_return_calculations(self):
        returns = calculate_daily_returns(self.prices)

        np.testing.assert_allclose(
            returns["NVDA"],
            [0.10, -0.10, 0.10]
        )

        np.testing.assert_allclose(
            returns["VTI"],
            [0.05, 0.00, 0.10]
        )

        self.assertEqual(len(returns), 3)

    def test_missing_prices_are_not_filled_or_bridged(self):
        self.prices.loc[self.dates[1], "NVDA"] = np.nan

        returns = calculate_daily_returns(self.prices)

        self.assertEqual(
            returns.index.tolist(),
            [self.dates[3]]
        )

        self.assertAlmostEqual(
            returns.iloc[0]["NVDA"],
            0.10
        )

    def test_invalid_prices(self):
        for value in (0, -1, np.inf):

            with self.subTest(value=value):
                prices = self.prices.copy()

                prices.loc[
                    self.dates[0],
                    "NVDA"
                ] = value

                with self.assertRaises(ValueError):
                    calculate_daily_returns(prices)

    def test_insufficient_price_history(self):
        with self.assertRaisesRegex(
            ValueError,
            "Insufficient"
        ):
            calculate_daily_returns(
                self.prices.iloc[:1]
            )

    def test_unsorted_dates(self):
        expected = calculate_daily_returns(self.prices)

        actual = calculate_daily_returns(
            self.prices.iloc[::-1]
        )

        pd.testing.assert_frame_equal(
            actual,
            expected,
            check_freq=False
        )

    def test_duplicate_dates(self):
        duplicate = pd.concat([
            self.prices,
            self.prices.iloc[:1]
        ])

        with self.assertRaisesRegex(
            ValueError,
            "duplicate dates"
        ):
            calculate_daily_returns(duplicate)

    def test_fetch_daily_returns(self):
        result = fetch_daily_returns(
            ["NVDA", "VTI"],
            "2025-01-01",
            "2025-02-01",
            downloader=Mock(return_value=self.data)
        )

        pd.testing.assert_frame_equal(
            result,
            calculate_daily_returns(self.prices)
        )


if __name__ == "__main__":
    unittest.main()