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

    def test_internal_gap_is_rejected_instead_of_losing_returns(self):
        self.prices.loc[self.dates[1], "NVDA"] = np.nan

        with self.assertRaisesRegex(ValueError, "missing prices.*NVDA.*2025-01-03"):
            calculate_daily_returns(self.prices)

    def test_mixed_calendars_cannot_silently_discard_growth(self):
        dates = pd.date_range("2025-01-03", periods=5, freq="D")
        prices = pd.DataFrame({
            "VTI": [100, np.nan, np.nan, 110, 121],
            "BTC-USD": [100, 105, 110, 115, 120]
        }, index=dates)

        # The old code silently retained only the last return.
        with self.assertRaisesRegex(ValueError, "missing prices.*VTI"):
            calculate_daily_returns(prices)

    def test_fully_missing_interior_row_is_rejected(self):
        self.prices.loc[self.dates[1], :] = np.nan
        with self.assertRaisesRegex(ValueError, "missing prices.*NVDA, VTI"):
            calculate_daily_returns(self.prices)

    def test_trim_edges_and_preserve_all_shared_growth(self):
        dates = pd.date_range("2025-01-01", periods=6, freq="B")
        prices = pd.DataFrame({
            "NVDA": [100, 110, 121, 133.1, 146.41, np.nan],
            "VTI": [np.nan, 200, 210, 220, 240, 250]
        }, index=dates)
        original = prices.copy(deep=True)
        returns = calculate_daily_returns(prices)

        self.assertEqual(returns.index.tolist(), dates[2:5].tolist())
        np.testing.assert_allclose(
            (1 + returns).prod(), [146.41 / 110, 240 / 200],
            rtol=1e-12
        )
        pd.testing.assert_frame_equal(prices, original)

    def test_no_common_history_or_single_common_date(self):
        for values in ([np.nan, np.nan, 200, 210], [np.nan, 200, 210, 220]):
            with self.subTest(values=values):
                prices = self.prices.copy()
                prices["NVDA"] = [100, 110, np.nan, np.nan]
                prices["VTI"] = values
                with self.assertRaisesRegex(ValueError, "Insufficient overlapping"):
                    calculate_daily_returns(prices)

    def test_weekend_is_not_a_gap_when_no_price_rows_exist(self):
        prices = pd.DataFrame({"VTI": [100, 102]}, index=pd.to_datetime([
            "2025-01-03", "2025-01-06"
        ]))
        returns = calculate_daily_returns(prices)
        self.assertEqual(len(returns), 1)
        self.assertAlmostEqual(returns.iloc[0, 0], .02)

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
