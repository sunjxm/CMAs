import unittest
import numpy as np
import pandas as pd

from cma_curve.estimate_anchors import build_candidate_anchors, macro_candidates, spread_statistics
from cma_curve.source_parsers import normalize_series


class AnchorEstimateTests(unittest.TestCase):
    def settings(self):
        return {"slope_statistic": "mean", "primary_slope_window_years": 1,
                "primary_candidate": "hlw_latest", "maximum_macro_age_months": 12,
                "rstar_smoothing_quarters": 20, "policy_to_3m_basis_bps": -10.,
                "core_to_headline_pce_adjustment_bps": 5.}

    def history(self):
        rows = []
        for date in pd.date_range("2025-10-31", "2026-09-30", freq="ME"):
            for key, maturity, value in [("BC_1MONTH", 1/12, .0295), ("BC_3MONTH", .25, .03), ("BC_10YEAR", 10., .04)]:
                rows.append({"date": date, "key": key, "maturity_years": maturity,
                             "rate_decimal": value, "curve_type": "par", "source": "US Treasury", "verified": True})
        return pd.DataFrame(rows)

    def sources(self):
        dates = pd.Series(pd.period_range("2021Q3", "2026Q2", freq="Q").start_time)
        parts = []
        for key, value in [("hlw_us_rstar", 1.), ("lw_us_rstar", 1.5)]:
            parts.append(normalize_series(dates, pd.Series([value] * len(dates)), key, "quarterly",
                                          "real_neutral_policy_rate", "core_PCE"))
        parts.append(normalize_series(pd.Series(["2026-07-01"]), pd.Series([2.2]), "spf_pce10_median",
                                      "quarterly", "median_10y_inflation_forecast", "headline_PCE"))
        data = pd.concat(parts, ignore_index=True)
        return data.assign(source_file="test.xlsx", source_sha256="test", retrieved_at_utc="2026-10-07T00:00:00Z")

    def test_anchor_components_and_no_extra_term_premium(self):
        history = self.history()
        slopes = spread_statistics(history, "2025-10-01", "2026-09-30", [1], 2)
        anchors, macro = build_candidate_anchors(history, self.sources(), slopes, "2026-09-30", self.settings())
        base = anchors[anchors.candidate == "hlw_latest"].set_index("key")
        self.assertAlmostEqual(base.loc["BC_3MONTH", "anchor_decimal"], .0315)
        self.assertAlmostEqual(base.loc["BC_1MONTH", "anchor_decimal"], .0310)
        self.assertAlmostEqual(base.loc["BC_10YEAR", "anchor_decimal"], .0415)
        self.assertFalse(anchors.point_in_time_eligible.any())
        self.assertTrue(anchors.status.eq("research_draft_not_approved").all())
        self.assertEqual(macro[macro.candidate == "hlw_median20"].quarters_used.iloc[0], 20)

    def test_spreads_pair_actual_dates_and_keep_gaps(self):
        history = self.history()
        history.loc[(history.key == "BC_10YEAR") & (history.date == pd.Timestamp("2025-10-31")), "date"] = pd.Timestamp("2025-10-30")
        result = spread_statistics(history, "2025-10-01", "2026-09-30", [1], 2).set_index("key")
        self.assertEqual(result.loc["BC_10YEAR", "paired_months"], 11)
        self.assertEqual(result.loc["BC_10YEAR", "expected_months"], 12)
        self.assertAlmostEqual(result.loc["BC_10YEAR", "mean_bps"], 100.)

    def test_benchmark_and_duplicate_months_rejected(self):
        history = self.history()
        with self.assertRaisesRegex(ValueError, "par observations"):
            spread_statistics(history.assign(curve_type="benchmark_yield"), "2025-10-01", "2026-09-30", [1])
        with self.assertRaisesRegex(ValueError, "one observation"):
            spread_statistics(pd.concat([history, history.iloc[:1]]), "2025-10-01", "2026-09-30", [1])

    def test_stale_macro_rejected(self):
        with self.assertRaisesRegex(ValueError, "Stale macro"):
            macro_candidates(self.sources(), "2028-09-30", self.settings())

    def test_cpi_cannot_be_used_as_pce(self):
        sources = self.sources()
        sources.loc[sources.key == "spf_pce10_median", "inflation_basis"] = "headline_CPI"
        with self.assertRaisesRegex(ValueError, "inflation definition"):
            macro_candidates(sources, "2026-09-30", self.settings())

    def test_insufficient_primary_history_rejected(self):
        history = self.history()
        slopes = spread_statistics(history, "2025-10-01", "2026-09-30", [1], 60)
        with self.assertRaisesRegex(ValueError, "insufficient"):
            build_candidate_anchors(history, self.sources(), slopes, "2026-09-30", self.settings())

    def test_missing_smoothing_quarter_rejected(self):
        sources = self.sources()
        sources = sources[~((sources.key == "hlw_us_rstar") & (sources.observation_period == "2022Q2"))]
        with self.assertRaisesRegex(ValueError, "consecutive quarters"):
            macro_candidates(sources, "2026-09-30", self.settings())

    def test_future_macro_period_excluded(self):
        sources = self.sources()
        future = sources[(sources.key == "hlw_us_rstar")].tail(1).copy()
        future["date"], future["observation_period"], future["rate_decimal"] = pd.Timestamp("2026-12-31"), "2026Q4", .10
        result = macro_candidates(pd.concat([sources, future]), "2026-09-30", self.settings())
        self.assertAlmostEqual(result[result.candidate == "hlw_latest"].rate_decimal.iloc[0], .01)
