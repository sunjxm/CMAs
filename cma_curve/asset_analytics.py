"""Discover analytics fields without treating returned values as verified definitions."""
import json
import pandas as pd
import numpy as np

from .analysis import latest_bundle, markdown_table, sha256
from .bloomberg_fields import FieldService
from .bond_inputs import load_assets
from .data import save_bundle
from .data import completed_month_end, monthly_sample


SEARCH_QUERIES = ("index yield", "index option adjusted duration", "index option adjusted spread",
                  "index convexity", "index real yield", "index spread duration")
PROBE_FIELDS = ("INDEX_YIELD_TO_WORST", "INDEX_YIELD_TO_MATURITY", "INDEX_OAD_TSY",
                "INDEX_BLENDED_SPREAD_DUR", "INDEX_OAS_TSY_BP", "INDEX_OAS_TSY",
                "INDEX_OAC_TSY", "INDEX_SPREAD_BENCHMARK")


def probe_analytics(catalog, output, start, end, client, progress=print):
    config = load_assets(catalog)
    tickers = [asset["ticker"] for asset in config["assets"]]
    keys = {asset["ticker"]: asset["key"] for asset in config["assets"]}
    end = completed_month_end(end)
    if pd.Timestamp(start) > end:
        raise ValueError("No complete months in analytics probe window.")
    snapshots, histories, errors, coverage = [], [], [], []
    for field in PROBE_FIELDS:
        if progress:
            progress(f"Probing candidate field: {field}")
        try:
            reference = client.reference(tickers, fields=[field])
            if reference is not None and not reference.empty:
                reference = reference.copy()
                reference["probe_field"] = field
                snapshots.append(reference)
            history = client.history(tickers, [field], start, end, frequency="monthly").copy()
            if not history.empty:
                history["value"] = pd.to_numeric(history.value, errors="coerce")
                history = history[history.value.notna() & history.date.between(pd.Timestamp(start), end)]
                if not np.isfinite(history.value).all():
                    raise ValueError("Nonfinite candidate analytics values.")
                history["key"] = history.ticker.map(keys)
                if history.duplicated(["date", "key"]).any():
                    raise ValueError("Duplicate analytics observations.")
                history = monthly_sample(history, end)
                history["definition_verified"] = False
                histories.append(history)
            for ticker in tickers:
                sample = history[history.ticker == ticker] if not history.empty else history
                coverage.append({"key": keys[ticker], "field": field, "observations": len(sample),
                                 "first_date": str(sample.date.min().date()) if len(sample) else None,
                                 "last_date": str(sample.date.max().date()) if len(sample) else None,
                                 "definition_verified": False, "request_error": ""})
        except (RuntimeError, ValueError, OSError) as exc:
            errors.append({"field": field, "error": str(exc)})
            coverage.extend({"key": keys[ticker], "field": field, "observations": 0,
                             "first_date": None, "last_date": None, "definition_verified": False,
                             "request_error": str(exc)} for ticker in tickers)
    data = pd.concat(histories, ignore_index=True) if histories else pd.DataFrame()
    coverage = pd.DataFrame(coverage)
    folder = save_bundle(data, coverage, output,
                         {"kind": "asset-analytics-probe", "asset_config": config,
                          "asset_config_sha256": sha256(catalog), "fields": PROBE_FIELDS,
                          "start": start, "effective_end": str(end.date()), "frequency": "monthly",
                          "errors": errors, "status": "raw_candidates_not_model_inputs", "code_sha256": sha256(__file__),
                          "snapshot_is": "current_reference_not_historical_end", "point_in_time_eligible": False})
    if snapshots:
        pd.concat(snapshots, ignore_index=False).to_csv(folder / "current_reference_raw.csv", index=True)
    report = ["# Bloomberg Analytics History Availability", "",
              "Raw candidate observations only. Returned numbers do not establish units or model applicability. "
              "No analytics mapping was automatically approved. Current reference values are not the historical endpoint.", "",
              markdown_table(coverage), "", "## Request Errors", "", json.dumps(errors, indent=2), ""]
    (folder / "run_summary.md").write_text("\n".join(report), encoding="utf-8")
    path = folder / "manifest.json"
    metadata = json.loads(path.read_text())
    metadata["output_sha256"] = {p.name: sha256(p) for p in folder.iterdir() if p.name != "manifest.json"}
    path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    if progress:
        progress(f"Saved candidate analytics observations: {folder}")
    if errors:
        raise RuntimeError(f"Some probes failed; successful data and errors retained in {folder}")
    return folder


def normalize_probe(catalog, output, probe_bundle=None, progress=print):
    """Normalize reviewed mappings only; retain missing required metrics as gaps."""
    from pathlib import Path
    from .bond_inputs import REQUIRED_ANALYTICS
    config = load_assets(catalog)
    probe = Path(probe_bundle) if probe_bundle else latest_bundle(output, "asset-analytics-probe")
    if not all(asset["verified"] for asset in config["assets"]):
        raise ValueError("Approve benchmark definitions before normalizing analytics.")
    source = json.loads((probe / "manifest.json").read_text())
    if source.get("kind") != "asset-analytics-probe" or source.get("output_sha256", {}).get("observations.csv") != sha256(probe / "observations.csv"):
        raise ValueError("Analytics probe type or observation checksum mismatch.")
    tickers = {a["key"]: a["ticker"] for a in source["asset_config"]["assets"]}
    data = pd.read_csv(probe / "observations.csv", parse_dates=["date"])
    records, coverage = [], []
    for asset in config["assets"]:
        if tickers.get(asset["key"]) != asset["ticker"]:
            raise ValueError("Benchmark changed since analytics probe; rerun the probe.")
        for metric in REQUIRED_ANALYTICS[asset["model"]]:
            mapping = asset["analytics"].get(metric)
            if not mapping or not mapping["verified"]:
                coverage.append({"key": asset["key"], "metric": metric, "field": None, "observations": 0,
                                 "first_date": None, "last_date": None, "status": "definition_not_verified"})
                continue
            rows = data[(data.key == asset["key"]) & (data.field == mapping["field"])].copy()
            if not rows.empty:
                if rows.duplicated("date").any() or not np.isfinite(rows.value).all():
                    raise ValueError("Duplicate or nonfinite analytics observations.")
                rows["metric"], rows["units"] = metric, mapping["units"]
                rows["normalized_value"] = rows.value * {"percent": .01, "basis_points": .0001,
                                                          "years": 1, "years_squared": 1}[mapping["units"]]
                rows["definition_verified"] = True
                records.append(rows)
            coverage.append({"key": asset["key"], "metric": metric, "field": mapping["field"], "observations": len(rows),
                             "first_date": str(rows.date.min().date()) if len(rows) else None,
                             "last_date": str(rows.date.max().date()) if len(rows) else None,
                             "status": "available" if len(rows) else "history_unavailable"})
    normalized = pd.concat(records, ignore_index=True) if records else pd.DataFrame()
    coverage = pd.DataFrame(coverage)
    folder = save_bundle(normalized, coverage, output,
                         {"kind": "asset-analytics-normalized", "asset_config": config, "asset_config_sha256": sha256(catalog),
                          "probe_bundle": str(probe.resolve()), "probe_manifest_sha256": sha256(probe / "manifest.json"),
                          "status": "research_inputs_not_return_forecasts", "point_in_time_eligible": False,
                          "code_sha256": sha256(__file__)})
    report = ["# Reviewed Bond Index Analytics", "", "Yields are normalized to decimals, OAS to decimals, duration remains years.", "",
              "No carry, credit-loss, real-curve, foreign-curve or hedge assumptions are inferred. "
              "Missing metrics remain gaps. Convexity is excluded until its scaling is verified. "
              "Histories have different start dates; available observations are not forward-filled.", "",
              markdown_table(coverage), "", f"Raw probe archive: `{probe.resolve()}`", ""]
    (folder / "run_summary.md").write_text("\n".join(report), encoding="utf-8")
    path = folder / "manifest.json"
    metadata = json.loads(path.read_text())
    metadata["output_sha256"] = {p.name: sha256(p) for p in folder.iterdir() if p.name != "manifest.json"}
    path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    if progress:
        progress(f"Saved reviewed index analytics: {folder}")
    return folder


def flatten_fields(responses, query):
    rows = []
    for response in responses:
        for field in response.get("fieldData", []):
            info = field.get("fieldInfo", {})
            rows.append({"query": query, "id": field.get("id"), "mnemonic": info.get("mnemonic"),
                         "description": info.get("description"), "datatype": info.get("datatype"),
                         "documentation": info.get("documentation"),
                         "error": json.dumps(field.get("fieldError")) if field.get("fieldError") else ""})
    return rows


def discover_analytics(catalog, output, host="localhost", port=8194, service=None, progress=print):
    config = load_assets(catalog)
    service = service or FieldService(host, port)
    results, rows, errors = {}, [], []
    for query in SEARCH_QUERIES:
        if progress:
            progress(f"Searching Bloomberg field definitions: {query}")
        try:
            responses = service.search(query)
            results[query] = responses
            rows.extend(flatten_fields(responses, query))
        except (RuntimeError, TimeoutError, ValueError) as exc:
            errors.append({"query": query, "error": str(exc)})
    candidates = pd.DataFrame(rows, columns=["query", "id", "mnemonic", "description", "datatype", "documentation", "error"])
    folder = save_bundle(pd.DataFrame(), pd.DataFrame(), output,
                         {"kind": "asset-analytics", "asset_config": config, "asset_config_sha256": sha256(catalog),
                          "queries": SEARCH_QUERIES, "errors": errors, "code_sha256": sha256(__file__),
                          "field_service_code_sha256": sha256(__file__.replace("asset_analytics.py", "bloomberg_fields.py")),
                          "status": "field_discovery_not_verified", "point_in_time_eligible": False})
    candidates.to_csv(folder / "field_candidates.csv", index=False)
    (folder / "field_responses.json").write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    summary = candidates[["query", "id", "mnemonic", "description"]]
    report = ["# Bloomberg Index Analytics Field Discovery", "",
              "Status: discovered candidates only. Field discovery does not verify asset applicability, units or history.", "",
              "Full definitions are retained in field_candidates.csv and raw responses in field_responses.json. "
              "Check option-adjusted versus modified duration, real versus nominal yield, spread definition and "
              "convexity scaling before configuring a metric. No benchmark's analytics flags were changed.", "",
              markdown_table(summary) if len(summary) else "No candidate definitions returned.", "",
              "## Request Errors", "", json.dumps(errors, indent=2), ""]
    (folder / "run_summary.md").write_text("\n".join(report), encoding="utf-8")
    path = folder / "manifest.json"
    metadata = json.loads(path.read_text())
    metadata["output_sha256"] = {p.name: sha256(p) for p in folder.iterdir() if p.name != "manifest.json"}
    path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    if progress:
        progress(f"Saved analytics field discovery: {folder}")
    if errors:
        raise RuntimeError(f"Some field searches failed; successful responses and errors retained in {folder}")
    return folder
