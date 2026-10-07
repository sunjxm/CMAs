import json
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from cma_curve.asset_analytics import discover_analytics, flatten_fields, normalize_probe, probe_analytics


class AnalyticsTests(unittest.TestCase):
    def test_field_definition_and_error_preserved(self):
        response = [{"fieldData": [{"id": "ABC", "fieldInfo": {"mnemonic": "FIELD", "description": "Description", "documentation": "Units are percent"}},
                                    {"id": "BAD", "fieldError": {"message": "Unknown"}}]}]
        rows = flatten_fields(response, "index yield")
        self.assertEqual(rows[0]["documentation"], "Units are percent")
        self.assertIn("Unknown", rows[1]["error"])

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.catalog = self.root / "assets.json"
        self.config = {"status": "research_draft_not_approved", "return_basis": "nominal", "reporting_currency": "USD",
                       "portfolio_convention": "rebalanced_index", "assets": [{"key": "test", "name": "Test", "ticker": "TEST Index",
                       "verified": True, "currency_exposure": "USD", "model": "us_nominal_credit", "total_return_field": "PX_LAST", "analytics": {}}]}
        self.catalog.write_text(json.dumps(self.config))

    def test_discovery_archives_definitions_without_approving_config(self):
        class Service:
            def search(self, query):
                return [{"fieldData": [{"id": "ID", "fieldInfo": {"mnemonic": "FIELD", "description": "Index field"}}]}]
        original = self.catalog.read_bytes()
        folder = discover_analytics(self.catalog, self.root, service=Service(), progress=None)
        self.assertEqual(self.catalog.read_bytes(), original)
        self.assertEqual(len(pd.read_csv(folder / "field_candidates.csv")), 6)
        self.assertIn("run_summary.md", json.loads((folder / "manifest.json").read_text())["output_sha256"])

    def test_failed_search_preserves_successes_and_error(self):
        class Service:
            def search(self, query):
                if query == "index yield":
                    raise TimeoutError("test timeout")
                return [{"fieldData": []}]
        with self.assertRaisesRegex(RuntimeError, "retained"):
            discover_analytics(self.catalog, self.root, service=Service(), progress=None)
        manifest = json.loads(next(self.root.glob("*/manifest.json")).read_text())
        self.assertEqual(manifest["errors"][0]["query"], "index yield")

    def test_probe_keeps_raw_units_and_reports_missing_fields(self):
        class Client:
            def reference(self, tickers, fields):
                return pd.DataFrame({"ticker": tickers, "field": fields * len(tickers), "value": [5.] * len(tickers)})
            def history(self, tickers, fields, start, end, frequency):
                if fields[0] == "INDEX_OAC_TSY":
                    return pd.DataFrame(columns=["date", "ticker", "field", "value"])
                return pd.DataFrame({"date": pd.to_datetime(["2025-01-31"]), "ticker": tickers,
                                     "field": fields, "value": [5.]})
        folder = probe_analytics(self.catalog, self.root, "2025-01-01", "2025-01-31", Client(), progress=None)
        raw = pd.read_csv(folder / "observations.csv")
        coverage = pd.read_csv(folder / "coverage.csv")
        self.assertTrue(raw.value.eq(5.).all())
        self.assertFalse(raw.definition_verified.any())
        self.assertEqual(coverage.loc[coverage.field == "INDEX_OAC_TSY", "observations"].iloc[0], 0)
        self.assertFalse(coverage.definition_verified.any())

    def test_normalization_respects_units_gaps_and_checksum(self):
        class Client:
            def reference(self, tickers, fields):
                return pd.DataFrame()
            def history(self, tickers, fields, start, end, frequency):
                return pd.DataFrame({"date": pd.to_datetime(["2025-01-31"]), "ticker": tickers,
                                     "field": fields, "value": [5.]})
        probe = probe_analytics(self.catalog, self.root, "2025-01-01", "2025-01-31", Client(), progress=None)
        self.config["assets"][0]["analytics"] = {
            "yield": {"field": "INDEX_YIELD_TO_WORST", "units": "percent", "verified": True},
            "oas": {"field": "INDEX_OAS_TSY_BP", "units": "basis_points", "verified": True},
            "rate_duration": {"field": "INDEX_OAD_TSY", "units": "years", "verified": True}}
        self.catalog.write_text(json.dumps(self.config))
        folder = normalize_probe(self.catalog, self.root, probe, progress=None)
        data = pd.read_csv(folder / "observations.csv").set_index("metric")
        self.assertAlmostEqual(data.loc["yield", "normalized_value"], .05)
        self.assertAlmostEqual(data.loc["oas", "normalized_value"], .0005)
        self.assertEqual(data.loc["rate_duration", "normalized_value"], 5.)
        coverage = pd.read_csv(folder / "coverage.csv").set_index("metric")
        self.assertEqual(coverage.loc["spread_duration", "status"], "definition_not_verified")
        (probe / "observations.csv").write_text("tampered")
        with self.assertRaisesRegex(ValueError, "checksum"):
            normalize_probe(self.catalog, self.root, probe, progress=None)
