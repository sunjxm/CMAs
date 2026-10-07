import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd

from cma_curve.source_parsers import (REQUIRED_SOURCES, normalize_series, parse_acm_sheet,
                                     parse_hlw_sheet, parse_lw_sheet, parse_official_archive, parse_spf_sheet)


class SourceParserTests(unittest.TestCase):
    def test_quarter_labels_are_not_publication_dates(self):
        result = normalize_series(pd.Series(["2026-04-01"]), pd.Series([1.2]), "rstar",
                                  "quarterly", "real_neutral_policy_rate")
        self.assertEqual(result.date.iloc[0], pd.Timestamp("2026-06-30"))
        self.assertEqual(result.source_date.iloc[0], pd.Timestamp("2026-04-01"))
        self.assertAlmostEqual(result.rate_decimal.iloc[0], .012)
        self.assertEqual(result.observation_period.iloc[0], "2026Q2")
        self.assertTrue(result.publication_date.isna().all())
        self.assertFalse(result.point_in_time_eligible.any())

    def test_hlw_selects_us_natural_rate_not_growth_or_canada(self):
        raw = pd.DataFrame(np.nan, index=range(8), columns=range(8), dtype=object)
        raw.iat[4, 2], raw.iat[5, 2] = "Trend Growth (g), Annualized", "US"
        raw.iat[4, 6], raw.iat[5, 6], raw.iat[5, 7] = "Natural Rate (r*)", "US", "Canada"
        raw.iat[5, 0] = "Date"
        raw.iloc[6:, 0] = pd.to_datetime(["2026-01-01", "2026-04-01"])
        raw.iloc[6:, 2], raw.iloc[6:, 6], raw.iloc[6:, 7] = [3., 4.], [1., 1.2], [9., 8.]
        result = parse_hlw_sheet(raw)
        self.assertEqual(result.value.tolist(), [1., 1.2])
        raw.iat[5, 6] = "Canada"
        with self.assertRaisesRegex(ValueError, "US Natural Rate"):
            parse_hlw_sheet(raw)

    def test_lw_rejects_two_sided_mapping(self):
        raw = pd.DataFrame(np.nan, index=range(7), columns=range(3), dtype=object)
        raw.iat[5, 0], raw.iat[4, 2], raw.iat[5, 2] = "Date", "Two-Sided Estimates", "rstar"
        with self.assertRaisesRegex(ValueError, "one-sided"):
            parse_lw_sheet(raw)

    def test_spf_preserves_missing_quarters_and_rejects_wrong_field(self):
        raw = pd.DataFrame({"YEAR": [2026] * 3, "QUARTER": [1, 2, 3], "PCE10": [2.2, np.nan, 2.3]})
        result = parse_spf_sheet(raw, "PCE10", "pce", "headline_PCE")
        self.assertEqual(result.observation_period.tolist(), ["2026Q1", "2026Q3"])
        self.assertEqual(len(result), 2)
        with self.assertRaisesRegex(ValueError, "missing"):
            parse_spf_sheet(raw, "INFCPI10YR", "cpi", "headline_CPI")

    def acm(self):
        data = {"DATE": ["31-Aug-2026", "30-Sep-2026"]}
        for year in range(1, 11):
            data[f"ACMY{year:02d}"] = [4., 4.2]
            data[f"ACMRNY{year:02d}"] = [3., 3.1]
            data[f"ACMTP{year:02d}"] = [1., 1.1]
        return pd.DataFrame(data)

    def test_acm_units_decomposition_and_monthly_rows(self):
        result = parse_acm_sheet(self.acm())
        self.assertEqual(len(result), 60)
        self.assertAlmostEqual(result[result.key == "acmtp10"].rate_decimal.iloc[-1], .011)
        self.assertTrue(result.curve_type.eq("zero_model").all())

    def test_acm_bad_decomposition_fails(self):
        raw = self.acm()
        raw.loc[0, "ACMTP10"] = 9.
        with self.assertRaisesRegex(ValueError, "yield !="):
            parse_acm_sheet(raw)

    def test_duplicate_periods_fail(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            normalize_series(pd.Series(["2026-01-01", "2026-02-01"]), pd.Series([1., 2.]),
                             "rstar", "quarterly", "real_neutral_policy_rate")

    def test_archive_checksum_failure_before_excel_reading(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as directory:
            folder = Path(directory)
            records = [{"key": key, "status": "ok", "filename": key + ".xls", "sha256": "bad"}
                       for key in REQUIRED_SOURCES]
            (folder / "acm.xls").write_bytes(b"changed")
            (folder / "manifest.json").write_text(json.dumps({"sources": records}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Checksum mismatch"):
                parse_official_archive(folder)
