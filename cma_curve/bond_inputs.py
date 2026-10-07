"""Explicit benchmark registration and auditable Bloomberg index input downloads."""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .analysis import markdown_table, sha256
from .catalog import SeriesSpec
from .data import completed_month_end, fetch_history, save_bundle


REQUIRED_ANALYTICS = {
    "us_nominal_credit": ("yield", "rate_duration", "spread_duration", "oas"),
    "us_aggregate_sectors": ("yield", "rate_duration", "spread_duration", "oas", "convexity"),
    "us_real_plus_cpi": ("real_yield", "real_duration"),
    "us_high_yield_credit": ("yield_to_worst", "rate_duration", "spread_duration", "oas"),
    "foreign_curves_usd_hedged": ("yield", "rate_duration", "spread_duration", "oas"),
    "usd_em_sovereign_credit": ("yield", "rate_duration", "spread_duration", "spread"),
    "usd_em_aggregate_credit": ("yield", "rate_duration", "spread_duration", "spread"),
}
METRIC_UNITS = {"yield": "percent", "yield_to_worst": "percent", "real_yield": "percent",
                "rate_duration": "years", "real_duration": "years", "spread_duration": "years",
                "oas": "basis_points", "spread": "basis_points", "convexity": "years_squared"}


def load_assets(path):
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    if config.get("return_basis") != "nominal" or config.get("reporting_currency") != "USD":
        raise ValueError("This implementation registers nominal USD return benchmarks only.")
    if config.get("status") != "research_draft_not_approved" or config.get("portfolio_convention") != "rebalanced_index":
        raise ValueError("Asset configuration must specify draft rebalanced-index assumptions.")
    assets = config["assets"]
    if not assets or len({a["key"] for a in assets}) != len(assets):
        raise ValueError("Asset keys must be nonempty and unique.")
    tickers = [a["ticker"] for a in assets if a["ticker"]]
    if len(set(tickers)) != len(tickers):
        raise ValueError("Duplicate benchmark tickers: review possible accidental substitutions.")
    for asset in assets:
        if not asset["key"] or not asset["name"] or asset["model"] not in REQUIRED_ANALYTICS:
            raise ValueError("Asset requires a key, name and recognized model.")
        if type(asset["verified"]) is not bool or not asset["total_return_field"]:
            raise ValueError("Asset verification flag and total-return field are required.")
        if asset["currency_exposure"] not in {"USD", "USD_hedged"}:
            raise ValueError("Currency exposure must be USD or explicitly USD hedged.")
        if asset["model"] == "foreign_curves_usd_hedged" and asset["currency_exposure"] != "USD_hedged":
            raise ValueError("Global ex-US benchmark must be explicitly USD hedged.")
        if asset["verified"] and not asset["ticker"]:
            raise ValueError("A verified asset needs its exact ticker.")
        if asset["verified"] and asset.get("verification_status") == "benchmark_mismatch_pending_decision":
            raise ValueError(f"Resolve benchmark mismatch for {asset['key']} before verification.")
        if asset["ticker"] is not None and (not isinstance(asset["ticker"], str) or not asset["ticker"].endswith(" Index")):
            raise ValueError("Supply an exact Bloomberg index security, including the Index suffix.")
        for metric, mapping in asset["analytics"].items():
            if metric not in METRIC_UNITS or mapping.get("units") != METRIC_UNITS[metric] or not mapping.get("field"):
                raise ValueError(f"Invalid analytics mapping for {asset['key']}/{metric}.")
            if type(mapping.get("verified")) is not bool:
                raise ValueError("Each analytics field needs its own verification flag.")
    return config


def asset_readiness(config):
    rows = []
    for asset in config["assets"]:
        missing = [key for key in REQUIRED_ANALYTICS[asset["model"]]
                   if key not in asset["analytics"] or not asset["analytics"][key]["verified"]]
        rows.append({"key": asset["key"], "benchmark": asset["name"], "ticker": asset["ticker"],
                     "verified": asset["verified"], "currency_exposure": asset["currency_exposure"],
                     "verification_status": asset.get("verification_status", "unreviewed"),
                     "reported_benchmark": asset.get("reported_benchmark"),
                     "definition_note": asset.get("definition_note", ""),
                     "history_ready": bool(asset["ticker"] and asset["verified"]),
                     "missing_analytics": ", ".join(missing),
                     "return_model_status": "planned_not_implemented"})
    return pd.DataFrame(rows)


def monthly_total_returns(history):
    """Calculate observed index returns only between adjacent calendar months."""
    if history.empty:
        raise ValueError("No total-return index history.")
    rows = history.sort_values(["key", "date"]).copy()
    rows["month"] = rows.date.dt.to_period("M")
    if rows.duplicated(["key", "month"]).any():
        raise ValueError("Duplicate monthly index observations.")
    if not np.isfinite(rows.value).all() or (rows.value <= 0).any():
        raise ValueError("Total-return index levels must be finite and positive.")
    previous = rows.groupby("key").value.shift()
    serial = rows["month"].astype("int64")
    consecutive = serial - serial.groupby(rows.key).shift() == 1
    rows["monthly_total_return_decimal"] = (rows.value / previous - 1).where(consecutive)
    rows["return_available"] = rows.monthly_total_return_decimal.notna()
    return rows[["date", "key", "monthly_total_return_decimal", "return_available"]]


def run_asset_inputs(task, catalog_path, output, start, end, client=None, selected=None, progress=print):
    config = load_assets(catalog_path)
    assets = config["assets"]
    if selected:
        unknown = set(selected) - {a["key"] for a in assets}
        if unknown:
            raise ValueError(f"Unknown assets: {sorted(unknown)}")
        assets = [a for a in assets if a["key"] in selected]
    readiness = asset_readiness({**config, "assets": assets})
    metadata = {"kind": task, "asset_config": config, "asset_config_sha256": sha256(catalog_path),
                "selected_assets": [a["key"] for a in assets], "status": "research_draft_not_approved",
                "point_in_time_eligible": False, "code_sha256": sha256(__file__)}
    history = pd.DataFrame()
    reference = None
    analytics = []
    coverage = pd.DataFrame()
    if task == "asset-metadata":
        tickers = [a["ticker"] for a in assets if a["ticker"]]
        if not tickers:
            raise ValueError("No exact benchmark tickers configured. Update bond_assets.json first.")
        if client is None:
            raise ValueError("A Bloomberg client is required.")
        reference = client.reference(tickers, fields=("NAME", "CRNCY", "PX_LAST"))
        if reference is None or reference.empty:
            raise ValueError("No benchmark metadata returned. Check tickers and entitlements.")
        metadata["reference_is"] = "current_snapshot_not_requested_historical_end_date"
        metadata["requested_tickers"] = tickers
    elif task == "asset-history":
        blocked = readiness.loc[~readiness.history_ready, "key"].tolist()
        if blocked:
            raise ValueError(f"Exact total-return benchmark definitions must be verified first: {blocked}. "
                             "Use --assets to select verified sleeves only.")
        if client is None:
            raise ValueError("A Bloomberg client is required.")
        effective_end = completed_month_end(end)
        if pd.Timestamp(start) > effective_end:
            raise ValueError("No complete months in requested range.")
        specs = [SeriesSpec(a["key"], a["ticker"], a["total_return_field"], "bond_indices", "index",
                            "total_return_index", verified=True) for a in assets]
        history, coverage = fetch_history(client, specs, start, effective_end, frequency="monthly")
        for asset in assets:
            for metric, mapping in asset["analytics"].items():
                if not mapping["verified"]:
                    continue
                data = client.history([asset["ticker"]], [mapping["field"]], start, effective_end, frequency="monthly")
                data = data.copy()
                if not data.empty:
                    data["value"] = pd.to_numeric(data.value, errors="coerce")
                    if data.duplicated(["date", "ticker", "field"]).any() or not np.isfinite(data.value).all():
                        raise ValueError(f"Invalid analytics history for {asset['key']}/{metric}.")
                    if not data.date.between(pd.Timestamp(start), effective_end).all():
                        raise ValueError("Analytics returned observations outside the requested window.")
                    data["key"], data["metric"], data["units"] = asset["key"], metric, mapping["units"]
                    data["normalized_value"] = data.value * {"percent": .01, "basis_points": .0001,
                                                              "years": 1, "years_squared": 1}[mapping["units"]]
                    analytics.append(data)
        metadata.update(start=start, end=end, effective_end=str(effective_end.date()), frequency="monthly")
    elif task != "asset-review":
        raise ValueError("Unknown asset input task.")
    returns = monthly_total_returns(history) if not history.empty else None
    folder = save_bundle(history, coverage, output, metadata)
    readiness.to_csv(folder / "asset_readiness.csv", index=False)
    if reference is not None:
        reference.to_csv(folder / "bloomberg_reference.csv", index=True)
    if returns is not None:
        returns.to_csv(folder / "historical_total_returns.csv", index=False)
    if analytics:
        pd.concat(analytics, ignore_index=True).to_csv(folder / "index_analytics.csv", index=False)
    report = ["# Fixed Income Benchmark Input Review", "", "Convention: nominal USD returns for rebalanced indices.", "",
              "Requested conventions: global ex-USD is USD hedged; EM debt is USD hard-currency debt. "
              "EM aggregate credit and sovereign-only models have different benchmark universes. "
              "Unresolved benchmark mismatches remain blocked pending a decision. "
              "Registration and historical downloads are not expected-return forecasts.", "",
              markdown_table(readiness[["key", "ticker", "verified", "verification_status",
                                        "reported_benchmark", "missing_analytics"]]), "",
              "## Definition Notes", "",
              *[f"- {row.key}: {row.definition_note}" for row in readiness.itertuples() if row.definition_note], "",
              "## Controls", "",
              "Benchmark metadata does not automatically verify maturity/rating filters, hedging, "
              "or total-return methodology. Confirm these in the Terminal before setting verified=true. "
              "Analytics fields also require individual definition and unit verification. "
              "Missing inputs are never replaced with zero or a broader index.", "",
              "Metadata is a current snapshot, not historical data as of the calibration endpoint. "
              "Monthly observed total returns require adjacent calendar months; no gaps are filled. "
              "Shorter index histories are retained and reported rather than fabricated.", "",
              "Return modeling additionally needs credit-loss assumptions, curve exposures, "
              "CPI and real-rate assumptions for TIPS, and foreign curves/currency weights/hedge carry "
              "for global bonds. See docs/FIXED_INCOME_RETURNS.md.", ""]
    (folder / "run_summary.md").write_text("\n".join(report), encoding="utf-8")
    manifest_path = folder / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["output_sha256"] = {p.name: sha256(p) for p in folder.iterdir() if p.name != "manifest.json"}
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    if progress:
        progress(f"Saved benchmark input review: {folder}")
        progress(readiness.to_string(index=False))
    return folder
