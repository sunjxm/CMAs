"""Offline exponential projection of official Treasury par nodes, not pricing."""

from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd

from .analysis import load_settings, markdown_table, sha256


def project_par_curve(starting, anchors, candidate, horizons, half_life):
    horizons = np.asarray(horizons, dtype=float)
    if horizons.ndim != 1 or not len(horizons) or not np.isfinite(horizons).all():
        raise ValueError("Horizons must be a nonempty finite one-dimensional sequence.")
    if horizons[0] != 0 or np.any(np.diff(horizons) <= 0):
        raise ValueError("Horizons must start at zero and increase strictly.")
    if not np.isfinite(half_life) or half_life <= 0:
        raise ValueError("Half-life must be positive and finite.")
    selected = anchors[anchors.candidate == candidate].copy()
    if selected.empty or selected.key.duplicated().any() or starting.key.duplicated().any():
        raise ValueError("Candidate and starting nodes must be nonempty and unique.")
    if set(selected.key) != set(starting.key):
        raise ValueError("Starting curve and selected anchor must have exactly matching nodes.")
    if not starting.curve_type.eq("par").all() or not selected.curve_type.eq("par").all():
        raise ValueError("Projection accepts par curves only.")
    if not starting.verified.eq(True).all() or starting.date.nunique() != 1:
        raise ValueError("Starting curve must be verified and observed on one common date.")
    nodes = starting[["key", "maturity_years", "rate_decimal"]].merge(
        selected[["key", "maturity_years", "anchor_decimal"]], on="key", validate="one_to_one",
        suffixes=("", "_anchor"))
    if not np.allclose(nodes.maturity_years, nodes.maturity_years_anchor, rtol=0, atol=1e-10):
        raise ValueError("Starting and anchor maturities differ.")
    if not np.isfinite(nodes[["maturity_years", "rate_decimal", "anchor_decimal"]]).all().all():
        raise ValueError("Nonfinite curve data.")
    if (nodes.maturity_years <= 0).any() or nodes.maturity_years.duplicated().any():
        raise ValueError("Maturities must be unique and positive.")
    rows = []
    for node in nodes.itertuples(index=False):
        yields = node.anchor_decimal + (node.rate_decimal - node.anchor_decimal) * np.exp2(-horizons / half_life)
        rows.append(pd.DataFrame({"candidate": candidate, "key": node.key,
                                 "maturity_years": node.maturity_years, "horizon_years": horizons,
                                 "half_life_years": half_life, "curve_type": "par",
                                 "rate_decimal": yields, "yield_percent": yields * 100,
                                 "anchor_decimal": node.anchor_decimal}))
    return pd.concat(rows, ignore_index=True).sort_values(["horizon_years", "maturity_years"]).reset_index(drop=True)


def latest_review(root):
    reviews = []
    for path in Path(root).glob("*/manifest.json"):
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if manifest.get("kind") == "anchor-review":
            reviews.append((pd.Timestamp(manifest["created_at_utc"]), path.parent))
    if not reviews:
        raise ValueError("Run --task anchor-review before projecting the curve.")
    return max(reviews, key=lambda item: item[0])[1]


def run_projection(output, anchor_settings, projection_settings, review_bundle=None, progress=print):
    output = Path(output)
    review = Path(review_bundle) if review_bundle else latest_review(output)
    manifest = json.loads((review / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("kind") != "anchor-review":
        raise ValueError("Supply an anchor-review bundle.")
    for filename in ("candidate_anchors.csv", "starting_par_curve.csv"):
        if manifest.get("output_sha256", {}).get(filename) != sha256(review / filename):
            raise ValueError(f"Review output checksum mismatch: {filename}")
    settings = load_settings(anchor_settings)
    if manifest["settings"] != settings:
        raise ValueError("Anchor settings changed. Rerun --task anchor-review before projection.")
    config = json.loads(Path(projection_settings).read_text(encoding="utf-8"))
    if config.get("status") != "research_draft_not_approved":
        raise ValueError("Projection settings must remain research draft.")
    for key in ("horizon_years", "steps_per_year"):
        if type(config[key]) is not int or config[key] <= 0:
            raise ValueError(f"{key} must be a positive integer.")
    scenarios = config["half_life_scenarios_years"]
    if not scenarios or any(not isinstance(h, (int, float)) or not np.isfinite(h) or h <= 0 for h in scenarios):
        raise ValueError("Half-life scenarios must be positive and finite.")
    if len(set(scenarios)) != len(scenarios) or config["base_half_life_years"] not in scenarios:
        raise ValueError("Unique scenarios must include the base half-life.")
    starting = pd.read_csv(review / "starting_par_curve.csv", parse_dates=["date"])
    anchors = pd.read_csv(review / "candidate_anchors.csv")
    horizons = np.arange(config["horizon_years"] * config["steps_per_year"] + 1) / config["steps_per_year"]
    paths = pd.concat([project_par_curve(starting, anchors, settings["primary_candidate"], horizons, h)
                       for h in scenarios], ignore_index=True)
    paths["scenario"] = paths.half_life_years.map(lambda h: "base" if h == config["base_half_life_years"] else f"half_life_{h:g}")
    stamp = datetime.now(timezone.utc)
    folder = output / (stamp.strftime("%Y%m%dT%H%M%S") + "_curve-projection_" + uuid4().hex[:8])
    folder.mkdir(parents=True, exist_ok=False)
    paths.to_csv(folder / "projected_par_curves.csv", index=False)
    focus = paths[(paths.scenario == "base") & paths.key.isin(["BC_1MONTH", "BC_2YEAR", "BC_5YEAR", "BC_10YEAR", "BC_30YEAR"])
                  & paths.horizon_years.isin([0, 1, 5, 10, 20, 30, 40])]
    report = ["# Treasury Par Curve Projection", "", "Status: research draft, not asset-return forecasts.", "",
              f"Selected candidate: {settings['primary_candidate']}. Starting curve date: {starting.date.iloc[0].date()}.", "",
              f"Base half-life: {config['base_half_life_years']} years; sensitivity half-lives: {scenarios}.", "",
              "$$", r"y_m(h) = a_m + \left[y_m(0)-a_m\right] 2^{-h/H_m}", "$$", "",
              "Horizon and half-life are years; rates are decimal values. Maturity and forecast horizon are distinct.", "",
              "The base half-life is provisional, not fitted or committee-approved. No market overlay is applied. "
              "Nodes are not interpolated, bootstrapped, or used to price cash flows in this step. "
              "This is a current-vintage research projection, not a point-in-time backtest.", "",
              "## Selected Base Nodes", "", "Yields below are percentages.", "",
              markdown_table(focus[["key", "horizon_years", "yield_percent"]]), "",
              "## Reproduction", "", f"Anchor-review bundle: `{review.resolve()}`", ""]
    (folder / "run_summary.md").write_text("\n".join(report), encoding="utf-8")
    metadata = {"kind": "curve-projection", "created_at_utc": stamp.isoformat(),
                "status": "research_draft_not_approved", "point_in_time_eligible": False,
                "review_bundle": str(review.resolve()), "review_manifest_sha256": sha256(review / "manifest.json"),
                "anchor_settings": settings, "projection_settings": config,
                "anchor_settings_sha256": sha256(anchor_settings), "projection_settings_sha256": sha256(projection_settings),
                "code_sha256": sha256(__file__), "outputs_are": "par_node_paths_not_asset_returns",
                "output_sha256": {p.name: sha256(p) for p in folder.iterdir()}}
    (folder / "manifest.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    if progress:
        progress(f"Saved projected par curves and summary: {folder}")
    return folder
