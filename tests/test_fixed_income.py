import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd

from cma_curve.analysis import sha256
from cma_curve.bond_inputs import REQUIRED_ANALYTICS, asset_readiness, load_assets, monthly_total_returns, run_asset_inputs
from cma_curve.curve_projection import project_par_curve, run_projection


class CurveProjectionTests(unittest.TestCase):
    def setUp(self):
        self.start = pd.DataFrame({"date": pd.to_datetime(["2026-09-30"] * 2), "key": ["a", "b"],
                                   "maturity_years": [2., 10.], "rate_decimal": [.02, .06],
                                   "curve_type": ["par"] * 2, "verified": [True] * 2})
        self.anchor = pd.DataFrame({"candidate": ["hlw_median20"] * 2, "key": ["a", "b"],
                                    "maturity_years": [2., 10.], "anchor_decimal": [.04, .04],
                                    "curve_type": ["par"] * 2})

    def test_initial_curve_half_gap_and_terminal_convergence(self):
        result = project_par_curve(self.start, self.anchor, "hlw_median20", [0, 5, 100], 5)
        np.testing.assert_allclose(result[result.horizon_years == 0].rate_decimal, [.02, .06])
        np.testing.assert_allclose(result[result.horizon_years == 5].rate_decimal, [.03, .05])
        np.testing.assert_allclose(result[result.horizon_years == 100].rate_decimal, [.04, .04], atol=3e-8)

    def test_invalid_horizons_and_half_lives(self):
        for horizons, half in [([1, 2], 5), ([0, 0], 5), ([0, np.nan], 5), ([0, 1], 0), ([0, 1], np.inf)]:
            with self.assertRaises(ValueError):
                project_par_curve(self.start, self.anchor, "hlw_median20", horizons, half)

    def test_mixed_types_dates_and_unverified_inputs_rejected(self):
        for column, value in [("curve_type", "zero"), ("date", pd.Timestamp("2026-09-29")), ("verified", False)]:
            data = self.start.copy()
            data.loc[0, column] = value
            with self.assertRaises(ValueError):
                project_par_curve(data, self.anchor, "hlw_median20", [0, 1], 5)

    def test_missing_and_mismatched_maturities_rejected(self):
        with self.assertRaises(ValueError):
            project_par_curve(self.start, self.anchor.iloc[:1], "hlw_median20", [0, 1], 5)
        data = self.anchor.copy()
        data.loc[0, "maturity_years"] = 3
        with self.assertRaises(ValueError):
            project_par_curve(self.start, data, "hlw_median20", [0, 1], 5)

    def test_projection_archive_hashes_and_settings_guard(self):
        with tempfile.TemporaryDirectory() as output:
            root = Path(output)
            review = root / "review"
            review.mkdir()
            self.start.to_csv(review / "starting_par_curve.csv", index=False)
            self.anchor.to_csv(review / "candidate_anchors.csv", index=False)
            settings = {"status": "research_draft_not_approved", "primary_candidate": "hlw_median20",
                        "policy_to_3m_basis_bps": 0, "core_to_headline_pce_adjustment_bps": 0,
                        "minimum_paired_months": 60, "rstar_smoothing_quarters": 20, "maximum_macro_age_months": 12,
                        "slope_windows_years": [30], "primary_slope_window_years": 30}
            (root / "anchor.json").write_text(json.dumps(settings))
            manifest = {"kind": "anchor-review", "settings": settings,
                        "output_sha256": {p.name: sha256(p) for p in review.iterdir()}}
            (review / "manifest.json").write_text(json.dumps(manifest))
            (root / "projection.json").write_text(json.dumps({"status": "research_draft_not_approved",
                    "horizon_years": 1, "steps_per_year": 12, "base_half_life_years": 5,
                    "half_life_scenarios_years": [3, 5, 8]}))
            folder = run_projection(root, root / "anchor.json", root / "projection.json", review, progress=None)
            result = pd.read_csv(folder / "projected_par_curves.csv")
            self.assertEqual(len(result), 78)
            archive = json.loads((folder / "manifest.json").read_text())
            self.assertEqual(archive["output_sha256"]["run_summary.md"], sha256(folder / "run_summary.md"))
            settings["primary_candidate"] = "hlw_latest"
            (root / "anchor.json").write_text(json.dumps(settings))
            with self.assertRaisesRegex(ValueError, "settings changed"):
                run_projection(root, root / "anchor.json", root / "projection.json", review, progress=None)
            settings["primary_candidate"] = "hlw_median20"
            (root / "anchor.json").write_text(json.dumps(settings))
            (review / "candidate_anchors.csv").write_text("tampered")
            with self.assertRaisesRegex(ValueError, "checksum"):
                run_projection(root, root / "anchor.json", root / "projection.json", review, progress=None)


class BondInputTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.catalog = Path(directory.name) / "assets.json"
        keys = ["short_term_bond", "us_aggregate", "inflation_linked", "high_yield", "global_ex_us", "em_debt"]
        assets = [{"key": key, "name": key, "model": model, "ticker": None, "verified": False,
                   "currency_exposure": "USD_hedged" if key == "global_ex_us" else "USD",
                   "total_return_field": "PX_LAST", "analytics": {}}
                  for key, model in zip(keys, REQUIRED_ANALYTICS)]
        assets[1]["ticker"] = "LBUSTRUU Index"
        config = {"return_basis": "nominal", "reporting_currency": "USD",
                  "status": "research_draft_not_approved", "portfolio_convention": "rebalanced_index", "assets": assets}
        self.catalog.write_text(json.dumps(config), encoding="utf-8")

    def test_registration_has_six_nominal_usd_sleeves_without_guessed_tickers(self):
        config = load_assets(self.catalog)
        self.assertEqual(len(config["assets"]), 6)
        self.assertEqual(sum(bool(a["ticker"]) for a in config["assets"]), 1)
        self.assertEqual(config["reporting_currency"], "USD")
        self.assertFalse(asset_readiness(config).history_ready.any())

    def test_monthly_returns_do_not_bridge_gaps(self):
        history = pd.DataFrame({"key": ["a"] * 4, "date": pd.to_datetime(["2025-01-31", "2025-02-28", "2025-04-30", "2025-05-30"]),
                                "value": [100., 102., 110., 111.]})
        result = monthly_total_returns(history)
        self.assertTrue(pd.isna(result.monthly_total_return_decimal.iloc[0]))
        self.assertAlmostEqual(result.monthly_total_return_decimal.iloc[1], .02)
        self.assertTrue(pd.isna(result.monthly_total_return_decimal.iloc[2]))
        self.assertAlmostEqual(result.monthly_total_return_decimal.iloc[3], 111 / 110 - 1)

    def test_duplicate_month_and_nonpositive_index_rejected(self):
        for dates, values in [(["2025-01-30", "2025-01-31"], [100, 101]),
                              (["2025-01-31", "2025-02-28"], [0, 101])]:
            data = pd.DataFrame({"key": ["a", "a"], "date": pd.to_datetime(dates), "value": values})
            with self.assertRaises(ValueError):
                monthly_total_returns(data)

    def test_history_blocks_before_bloomberg_when_unverified(self):
        with tempfile.TemporaryDirectory() as output:
            with self.assertRaisesRegex(ValueError, "verified first"):
                run_asset_inputs("asset-history", self.catalog, output, "1996-10-01", "2026-09-30", client=object())

    def test_unresolved_benchmark_mismatch_cannot_be_marked_verified(self):
        config = load_assets(self.catalog)
        asset = config["assets"][1]
        asset["verified"] = True
        asset["verification_status"] = "benchmark_mismatch_pending_decision"
        self.catalog.write_text(json.dumps(config))
        with self.assertRaisesRegex(ValueError, "Resolve benchmark mismatch"):
            load_assets(self.catalog)

    def test_readiness_exposes_benchmark_mismatch(self):
        config = load_assets(self.catalog)
        config["assets"][3]["verification_status"] = "benchmark_mismatch_pending_decision"
        config["assets"][3]["reported_benchmark"] = "Different benchmark"
        result = asset_readiness(config).set_index("key")
        self.assertEqual(result.loc["high_yield", "verification_status"], "benchmark_mismatch_pending_decision")
        self.assertEqual(result.loc["high_yield", "reported_benchmark"], "Different benchmark")
        self.assertFalse(result.loc["high_yield", "history_ready"])

    def test_em_aggregate_model_is_separate_from_sovereign_only(self):
        config = load_assets(self.catalog)
        config["assets"][5]["model"] = "usd_em_aggregate_credit"
        config["assets"][5]["ticker"] = "EMUSTRUU Index"
        self.catalog.write_text(json.dumps(config))
        result = load_assets(self.catalog)
        self.assertEqual(result["assets"][5]["model"], "usd_em_aggregate_credit")
        self.assertIn("spread", asset_readiness(result).iloc[5].missing_analytics)

    def test_invalid_field_units_and_global_hedge_rejected(self):
        config = load_assets(self.catalog)
        with tempfile.TemporaryDirectory() as output:
            path = Path(output) / "assets.json"
            config["assets"][0]["analytics"] = {"oas": {"field": "EXAMPLE", "units": "percent", "verified": True}}
            path.write_text(json.dumps(config), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "mapping"):
                load_assets(path)
            config["assets"][0]["analytics"] = {}
            config["assets"][4]["currency_exposure"] = "USD"
            path.write_text(json.dumps(config), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "hedged"):
                load_assets(path)

    def test_offline_review_creates_hashed_summary(self):
        with tempfile.TemporaryDirectory() as output:
            folder = run_asset_inputs("asset-review", self.catalog, output, "1996-10-01", "2026-09-30", progress=None)
            manifest = json.loads((folder / "manifest.json").read_text())
            self.assertIn("run_summary.md", manifest["output_sha256"])
            self.assertEqual(len(pd.read_csv(folder / "asset_readiness.csv")), 6)

    def test_verified_history_download_and_observed_returns(self):
        config = load_assets(self.catalog)
        config["assets"][1]["verified"] = True
        self.catalog.write_text(json.dumps(config))
        class Client:
            def history(self, tickers, fields, start, end, frequency):
                return pd.DataFrame({"date": pd.to_datetime(["2025-01-31", "2025-02-28"]),
                                     "ticker": [tickers[0]] * 2, "field": [fields[0]] * 2, "value": [100., 102.]})
        with tempfile.TemporaryDirectory() as output:
            folder = run_asset_inputs("asset-history", self.catalog, output, "2025-01-01", "2025-02-28",
                                      client=Client(), selected=["us_aggregate"], progress=None)
            result = pd.read_csv(folder / "historical_total_returns.csv")
            self.assertAlmostEqual(result.monthly_total_return_decimal.iloc[1], .02)
            self.assertFalse(bool(result.return_available.iloc[0]))
