import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from cma_curve.analysis import latest_bundle, load_settings, run_analysis
from cma_curve.source_parsers import normalize_series


class AnalysisTests(unittest.TestCase):
    def test_offline_review_writes_report_hashes_and_draft_outputs(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as directory:
            root = Path(directory)
            archive, treasury = root / "official", root / "treasury"
            archive.mkdir()
            treasury.mkdir()
            official_manifest = {"kind": "official_anchor_sources", "retrieved_at_utc": "2026-10-07T00:00:00Z"}
            (archive / "manifest.json").write_text(json.dumps(official_manifest), encoding="utf-8")
            (treasury / "manifest.json").write_text(json.dumps({"kind": "treasury_par_history", "frequency": "monthly",
                "start": "2025-10-01", "effective_end": "2026-09-30", "retrieved_at_utc": "2026-10-07T00:00:00Z"}), encoding="utf-8")
            rows = [{"key": key, "date": "2026-09-30", "rate_decimal": value, "maturity_years": maturity,
                     "curve_type": "par", "source": "US Treasury", "verified": True}
                    for key, maturity, value in [("BC_1MONTH", 1/12, .029), ("BC_3MONTH", .25, .03), ("BC_10YEAR", 10, .04)]]
            pd.DataFrame(rows).to_csv(treasury / "observations.csv", index=False)
            parts = []
            for key, basis, value in [("hlw_us_rstar", "core_PCE", 1.), ("lw_us_rstar", "core_PCE", 1.5),
                                      ("spf_pce10_median", "headline_PCE", 2.2)]:
                parts.append(normalize_series(pd.Series(["2026-01-01", "2026-04-01"]), pd.Series([value, value]),
                                              key, "quarterly", "test", basis))
            parts.append(normalize_series(pd.Series(["2026-09-30"]), pd.Series([.5]), "acmtp10", "monthly", "test"))
            sources = pd.concat(parts, ignore_index=True).assign(source_file="test.xlsx", source_sha256="test",
                                                                 retrieved_at_utc=official_manifest["retrieved_at_utc"])
            settings = {"status": "research_draft_not_approved", "primary_candidate": "hlw_latest",
                        "policy_to_3m_basis_bps": 0., "core_to_headline_pce_adjustment_bps": 0.,
                        "slope_statistic": "mean", "slope_windows_years": [1], "primary_slope_window_years": 1,
                        "minimum_paired_months": 1, "rstar_smoothing_quarters": 2, "maximum_macro_age_months": 12}
            config = root / "settings.json"
            config.write_text(json.dumps(settings), encoding="utf-8")
            inventory = pd.DataFrame([{ "source_key": "test", "sha256": "test", "observations": len(sources)}])
            with patch("cma_curve.analysis.parse_official_archive", return_value=(sources, inventory, official_manifest)):
                folder = run_analysis("anchor-review", "2025-10-01", "2026-09-30", root, config, archive, treasury, progress=None)
            manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
            self.assertFalse(manifest["point_in_time_eligible"])
            self.assertIn("Current-vintage", manifest["availability_note"])
            for name, digest in manifest["output_sha256"].items():
                self.assertEqual(hashlib.sha256((folder / name).read_bytes()).hexdigest(), digest)
            anchors = pd.read_csv(folder / "candidate_anchors.csv")
            self.assertEqual(len(anchors), 9)
            self.assertTrue((folder / "run_summary.md").exists())
            self.assertEqual(latest_bundle(root, "treasury_par_history"), treasury)
            settings["status"] = "approved"
            config.write_text(json.dumps(settings), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "draft candidates only"):
                load_settings(config)
