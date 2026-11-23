"""Tests for non-destructive market-history quality warnings."""

import unittest
import numpy as np
import pandas as pd
from backend.data_quality import describe_historical_data


class HistoricalDataQualityTests(unittest.TestCase):
    def test_short_sample_warns_and_preserves_dates(self):
        dates = pd.bdate_range("2024-01-01", periods=12)
        result = describe_historical_data(pd.DataFrame({"TEST": np.full(12, .002)}, index=dates))
        self.assertEqual(result["observations"], 12)
        self.assertEqual(result["first_return_date"], dates[0].strftime("%Y-%m-%d"))
        self.assertEqual(result["last_return_date"], dates[-1].strftime("%Y-%m-%d"))
        self.assertGreaterEqual(len(result["warnings"]), 1)

    def test_extreme_return_flag_is_not_silently_dropped(self):
        dates = pd.bdate_range("2024-01-01", periods=260)
        values = np.zeros(260)
        values[101] = .42
        result = describe_historical_data(pd.DataFrame({"TEST": values}, index=dates))
        self.assertEqual(result["observations"], 260)
        self.assertIn("TEST", " ".join(result["warnings"]))

    def test_missing_nonfinite_returns_remain_an_error(self):
        with self.assertRaises(ValueError):
            describe_historical_data(pd.DataFrame({"TEST": [.02, float("nan")]}))


if __name__ == "__main__":
    unittest.main()
