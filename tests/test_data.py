import io
import json
import tempfile
from pathlib import Path
import unittest
import pandas as pd
from cma_curve.catalog import SeriesSpec
from cma_curve.bloomberg import normalize_history
from cma_curve.data import fetch_history, curve_asof
from cma_curve.anchors import load_anchor_inputs, slope_diagnostics
from cma_curve.treasury import parse_treasury_xml
from cma_curve.official import fetch_official_inputs


class FakeClient:
    def __init__(self, data):
        self.data = data

    def history(self, tickers, fields, start, end):
        return self.data.copy()


class DataTests(unittest.TestCase):
    def test_bloomberg_layouts_agree(self):
        dates = pd.to_datetime(["2026-10-01", "2026-10-02"])
        wide = pd.DataFrame([4., 4.1], index=dates, columns=pd.MultiIndex.from_tuples([("A Index", "px_last")]))
        long = pd.DataFrame({"date": dates, "ticker": "A Index", "field": "PX_LAST", "value": [4., 4.1]})
        pd.testing.assert_frame_equal(normalize_history(wide, ["A Index"], ["PX_LAST"]),
                                      normalize_history(long, ["A Index"], ["PX_LAST"]))

    def test_percent_bps_decimal_and_negative_rates(self):
        specs = [SeriesSpec(unit, unit, "PX_LAST", "test", unit, "par")
                 for unit in ["percent", "basis_points", "decimal"]]
        raw = pd.DataFrame({"date": pd.to_datetime(["2026-10-01"] * 3),
                            "ticker": [s.ticker for s in specs], "field": "PX_LAST", "value": [-.5, -50., -.005]})
        result, _ = fetch_history(FakeClient(raw), specs, "2026-10-01", "2026-10-02")
        self.assertTrue(result.rate_decimal.eq(-.005).all())

    def test_missing_required_fails_and_optional_is_reported(self):
        raw = pd.DataFrame(columns=["date", "ticker", "field", "value"])
        required = SeriesSpec("cash", "A", "PX_LAST", "cash", "percent", "par")
        with self.assertRaisesRegex(ValueError, "Required series"):
            fetch_history(FakeClient(raw), [required], "2026-10-01", "2026-10-02")

    def sample_curve(self):
        return pd.DataFrame({"date": pd.to_datetime(["2026-10-01", "2026-10-01", "2026-10-02", "2026-10-07"]),
                             "key": ["cash", "long", "cash", "long"], "rate_decimal": [.03, .04, .035, .05],
                             "curve_type": "par", "maturity_years": [.0833, 10., .0833, 10.], "verified": True})

    def test_common_date_without_future_data_or_independent_fill(self):
        result = curve_asof(self.sample_curve(), "2026-10-06", ["cash", "long"], require_type="par")
        self.assertTrue(result.date.eq(pd.Timestamp("2026-10-01")).all())
        self.assertEqual(result.rate_decimal.tolist(), [.03, .04])

    def test_stale_curve_rejected(self):
        with self.assertRaisesRegex(ValueError, "stale"):
            curve_asof(self.sample_curve(), "2026-10-20", ["cash", "long"])

    def test_wrong_curve_type_rejected(self):
        data = self.sample_curve()
        data["curve_type"] = "benchmark_yield"
        with self.assertRaisesRegex(ValueError, "Expected par"):
            curve_asof(data, "2026-10-06", ["cash", "long"], require_type="par")

    def test_unverified_catalog_rejected(self):
        data = self.sample_curve()
        data["verified"] = False
        with self.assertRaisesRegex(ValueError, "not verified"):
            curve_asof(data, "2026-10-06", ["cash", "long"])

    def test_anchor_release_and_revision_dates_prevent_lookahead(self):
        text = ("key,value,units,observation_date,publication_date,vintage_date,source,definition\n"
                "neutral,3,percent,2050-01-01,2026-09-01,2026-09-01,Fed,long run nominal\n"
                "neutral,4,percent,2050-01-01,2026-09-01,2026-10-07,Fed,revised estimate\n")
        result = load_anchor_inputs(io.StringIO(text), "2026-10-06")
        self.assertEqual(len(result), 1)
        self.assertEqual(result.rate_decimal.iloc[0], .03)

    def test_treasury_xml_units_and_missing_node(self):
        xml = b'<feed xmlns:m="urn:m" xmlns:d="urn:d"><m:properties><d:NEW_DATE>2026-10-01T00:00:00</d:NEW_DATE><d:BC_1MONTH>3.8</d:BC_1MONTH><d:BC_10YEAR>4.2</d:BC_10YEAR><d:BC_30YEAR m:null="true"/></m:properties></feed>'
        result = parse_treasury_xml(xml)
        self.assertEqual(len(result), 2)
        self.assertAlmostEqual(result.rate_decimal.iloc[0], .038)
        self.assertTrue(result.curve_type.eq("par").all())

    def test_slope_uses_paired_observations(self):
        result = slope_diagnostics(self.sample_curve(), "cash", ["long"], "2026-10-01", "2026-10-06")
        self.assertAlmostEqual(result.mean_bps.iloc[0], 100.)
        self.assertEqual(result.months.iloc[0], 1)

    def test_overnight_inputs_cannot_be_maturity_nodes(self):
        data = self.sample_curve()
        data.loc[data.key.eq("cash"), "maturity_years"] = float("nan")
        with self.assertRaisesRegex(ValueError, "positive maturities"):
            curve_asof(data, "2026-10-06", ["cash", "long"])

    def test_official_download_failure_retains_success_and_manifest(self):
        class Response(io.BytesIO):
            def geturl(self):
                return "https://example.org/data.csv"

        def opener(request, timeout):
            return Response(b"Date,rate\n2026-10-01,3\n" if "good" in request.full_url else b"<html>error</html>")

        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as directory:
            path = Path(directory) / "sources.json"
            path.write_text(json.dumps({"sources": [
                {"key": "good", "filename": "good.csv", "format": "csv", "url": "https://example.org/good"},
                {"key": "bad", "filename": "bad.csv", "format": "csv", "url": "https://example.org/bad"},
            ]}), encoding="utf-8")
            folder, results = fetch_official_inputs(path, directory, opener)
            self.assertEqual([r["status"] for r in results], ["ok", "error"])
            self.assertTrue((folder / "good.csv").exists())
            self.assertFalse((folder / "bad.csv").exists())
            self.assertEqual(len(results[0]["sha256"]), 64)
            self.assertTrue((folder / "manifest.json").exists())


if __name__ == "__main__":
    unittest.main()
