"""Offline source processing, candidate anchor review, and dated methodology reports."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd

from .data import completed_month_end, curve_asof
from .estimate_anchors import build_candidate_anchors, spread_statistics
from .source_parsers import PARSER_VERSION, parse_official_archive


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def latest_bundle(root, kind):
    candidates = []
    for path in Path(root).glob("*/manifest.json"):
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if manifest.get("kind") == kind:
            candidates.append((pd.Timestamp(manifest["retrieved_at_utc"]), path.parent))
    if not candidates:
        raise ValueError(f"No archived {kind} bundle under {root}. Download the inputs first.")
    return max(candidates, key=lambda item: item[0])[1]


def load_settings(path):
    settings = json.loads(Path(path).read_text(encoding="utf-8"))
    if settings.get("status") != "research_draft_not_approved":
        raise ValueError("This review pipeline produces draft candidates only; approval requires a separate workflow.")
    for key in ("policy_to_3m_basis_bps", "core_to_headline_pce_adjustment_bps"):
        if not isinstance(settings[key], (int, float)) or not np.isfinite(settings[key]):
            raise ValueError(f"{key} must be finite.")
    for key in ("minimum_paired_months", "rstar_smoothing_quarters", "maximum_macro_age_months"):
        if type(settings[key]) is not int or settings[key] <= 0:
            raise ValueError(f"{key} must be a positive integer.")
    windows = settings["slope_windows_years"]
    if not windows or any(type(y) is not int or y <= 0 for y in windows) or len(windows) != len(set(windows)):
        raise ValueError("Slope windows must be unique positive integer years.")
    if settings["primary_slope_window_years"] not in windows:
        raise ValueError("Primary slope window must be included in diagnostic windows.")
    return settings


def markdown_table(frame):
    def value(item):
        if pd.isna(item):
            return "Unavailable"
        if isinstance(item, (float, np.floating)):
            return f"{item:.4f}"
        return str(item).replace("|", "\\|").replace("\n", " ")
    lines = ["| " + " | ".join(frame.columns) + " |",
             "| " + " | ".join(["---"] * len(frame.columns)) + " |"]
    lines.extend("| " + " | ".join(value(v) for v in row) + " |" for row in frame.itertuples(index=False, name=None))
    return "\n".join(lines)


def acm_diagnostics(sources, start, end, windows):
    data = sources[(sources.key == "acmtp10") & sources.date.between(pd.Timestamp(start), completed_month_end(end))]
    rows = []
    for years in windows:
        window_start = max(pd.Timestamp(start), (completed_month_end(end).to_period("M") - (years * 12 - 1)).start_time)
        sample = data[data.date >= window_start].sort_values("date")
        rows.append({"window_years": years, "months": len(sample),
                     "first_date": str(sample.date.min().date()) if len(sample) else None,
                     "last_date": str(sample.date.max().date()) if len(sample) else None,
                     "mean_bps": sample.rate_decimal.mean() * 10000,
                     "median_bps": sample.rate_decimal.median() * 10000,
                     "latest_bps": sample.rate_decimal.iloc[-1] * 10000 if len(sample) else None,
                     "role": "zero_term_premium_diagnostic_not_added_to_par_spreads"})
    return pd.DataFrame(rows)


def run_analysis(task, start, end, output, settings_path, official_archive=None, treasury_bundle=None,
                 progress=print):
    end = completed_month_end(end)
    if pd.Timestamp(start) > end:
        raise ValueError("No complete months in requested analysis window.")
    output = Path(output)
    archive = Path(official_archive) if official_archive else latest_bundle(output, "official_anchor_sources")
    sources, inventory, source_manifest = parse_official_archive(archive, progress=progress)
    settings = load_settings(settings_path)
    treasury = None
    if task == "anchor-review":
        treasury = Path(treasury_bundle) if treasury_bundle else latest_bundle(output, "treasury_par_history")
        treasury_manifest = json.loads((treasury / "manifest.json").read_text(encoding="utf-8"))
        if treasury_manifest.get("kind") != "treasury_par_history" or treasury_manifest.get("frequency") != "monthly":
            raise ValueError("Anchor review requires a monthly official Treasury par bundle.")
        if pd.Timestamp(treasury_manifest["start"]) > pd.Timestamp(start) or pd.Timestamp(treasury_manifest["effective_end"]) < end:
            raise ValueError("Treasury bundle request window does not cover analysis dates. Select another bundle or refetch.")
        history = pd.read_csv(treasury / "observations.csv", parse_dates=["date"])
        slopes = spread_statistics(history, start, end, settings["slope_windows_years"], settings["minimum_paired_months"])
        anchors, macro = build_candidate_anchors(history, sources, slopes, end, settings)
        current = curve_asof(history, end, anchors.key.unique(), require_type="par")
        premiums = acm_diagnostics(sources, start, end, settings["slope_windows_years"])
    elif task != "process-inputs":
        raise ValueError("Unknown analysis task.")
    stamp = datetime.now(timezone.utc)
    folder = output / (stamp.strftime("%Y%m%dT%H%M%S") + "_" + task + "_" + uuid4().hex[:8])
    folder.mkdir(parents=True, exist_ok=False)
    sources.to_csv(folder / "official_observations.csv", index=False)
    inventory.to_csv(folder / "source_inventory.csv", index=False)
    manifest = {"kind": task, "created_at_utc": stamp.isoformat(), "parser_version": PARSER_VERSION,
                "observation_cutoff": str(end.date()), "calibration_start": start,
                "official_archive": str(archive.resolve()), "official_manifest_sha256": sha256(archive / "manifest.json"),
                "source_retrieved_at_utc": source_manifest["retrieved_at_utc"],
                "settings": settings, "settings_sha256": sha256(settings_path),
                "status": "research_draft_not_approved", "point_in_time_eligible": False,
                "availability_note": "Observation cutoff is not forecast as-of. Current-vintage sources have not been release-date mapped.",
                "code_sha256": {name: sha256(Path(__file__).with_name(name))
                                for name in ("source_parsers.py", "estimate_anchors.py", "analysis.py", "data.py")}}
    report = ["# CMA Input Processing And Anchor Review", "", f"Run created (UTC): {stamp.isoformat()}", "",
              "Status: research draft. No anchors have been approved.", "",
              f"Calibration window: {start} to {end.date()}. Macro observation cutoff: {end.date()}.", "",
              "This is a current-vintage research snapshot, not a point-in-time forecast or backtest.", "",
              "## Source Processing", "", markdown_table(inventory.drop(columns=["sha256"])), "",
              "Rates retain original percentage-point values and are converted to decimals by dividing by 100.", "",
              "ACM uses the publisher's monthly end-of-month worksheet, not averages of daily premiums. "
              "HLW/LW and SPF remain quarterly. Quarter-end dates label economic/survey periods, not publication dates.", "",
              "All raw files passed SHA-256 checks against their download manifest. Publication and vintage dates "
              "remain unmapped, including the HLW real-time sheets. No gaps are filled."]
    if treasury:
        slopes.to_csv(folder / "slope_diagnostics.csv", index=False)
        anchors.to_csv(folder / "candidate_anchors.csv", index=False)
        macro.to_csv(folder / "macro_components.csv", index=False)
        current.to_csv(folder / "starting_par_curve.csv", index=False)
        premiums.to_csv(folder / "acm_diagnostics.csv", index=False)
        manifest.update(treasury_bundle=str(treasury.resolve()),
                        treasury_manifest_sha256=sha256(treasury / "manifest.json"),
                        treasury_observations_sha256=sha256(treasury / "observations.csv"),
                        treasury_retrieved_at_utc=treasury_manifest["retrieved_at_utc"],
                        common_starting_curve_date=str(current.date.iloc[0].date()))
        focus = ["BC_1MONTH", "BC_2YEAR", "BC_5YEAR", "BC_10YEAR", "BC_30YEAR"]
        comparison = anchors[anchors.key.isin(focus)][["candidate", "key", "anchor_percent", "paired_months"]]
        report += ["", "## Candidate Construction", "",
                   "Neutral nominal policy = real neutral rate + SPF median 10-year headline PCE forecast "
                   "+ core-to-headline adjustment. Reference 3-month yield = neutral nominal policy + policy-to-bill basis. "
                   "Each par anchor = reference 3-month yield + its historical par spread to the 3-month node.", "",
                   "This additive nominal-rate approximation is a modeling convention, not an exact Fisher calculation.", "",
                   f"Primary research candidate: {settings['primary_candidate']}. "
                   f"Primary slope window: {settings['primary_slope_window_years']} years; "
                   f"statistic: {settings['slope_statistic']}.", "",
                   f"Policy-to-3m adjustment: {settings['policy_to_3m_basis_bps']} bps. "
                   f"Core-to-headline PCE adjustment: {settings['core_to_headline_pce_adjustment_bps']} bps. "
                   "Zero settings are assumptions requiring review, not empirically estimated adjustments.", "",
                   "### Macro Components", "", markdown_table(macro[["candidate", "key", "rate_decimal", "observation_period", "quarters_used"]]),
                   "", "### Selected Par Nodes", "", "Yields below are percentages, not decimal rates.", "", markdown_table(comparison),
                   "", "### Historical Spread Coverage", "",
                   markdown_table(slopes[(slopes.key.isin(focus)) & (slopes.window_years == settings["primary_slope_window_years"])][
                       ["key", "paired_months", "expected_months", "first_date", "last_date", "mean_bps", "median_bps"]]),
                   "", "Spreads use equal weights across paired months with matching actual observation dates. "
                   "No missing 1-month or 30-year rates are synthesized. The 30-year calibration window does not "
                   "guarantee 360 observations for every node. Different node histories can affect curve shape.",
                   "", "### ACM Cross-Check", "", markdown_table(premiums.drop(columns=["role"])), "",
                   "ACM zero-coupon term premiums are diagnostics only. They are not added to historical par spreads "
                   "and are not extrapolated from 10 years to 30 years.", "", "## Review Before Adoption", "",
                   "- Confirm the real-neutral source and smoothing choice; compare LW and HLW instead of treating their difference as a confidence interval.",
                   "- Review the headline/core PCE alignment and policy-to-3-month basis, including average-cycle effects.",
                   "- Inspect 10-, 20-, and 30-year spread windows, mean versus median, and unequal node coverage.",
                   "- Add dated FOMC/market-expectations and other long-run rate cross-checks before selecting approved anchors.",
                   "- Map release dates and source vintages before any historical forecast evaluation.",
                   "- Choose convergence speeds separately; this stage does not bootstrap discount curves or calculate returns."]
    report += ["", "## Reproduction", "", f"Official archive: `{archive.resolve()}`", "",
               f"Treasury bundle: `{treasury.resolve()}`" if treasury else "Treasury inputs were not used in this processing-only run.",
               "", "The run manifest captures source locations, input hashes, settings, and processing-code hashes. "
               "Preserve this entire folder alongside the raw archives. The version-controlled methodology and "
               "development log explain the decisions; this report records one numerical snapshot.", ""]
    (folder / "run_summary.md").write_text("\n".join(report), encoding="utf-8")
    manifest["output_sha256"] = {p.name: sha256(p) for p in folder.iterdir() if p.is_file()}
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    if progress:
        progress(f"Saved {task} results and methodology summary to {folder}")
    return folder
