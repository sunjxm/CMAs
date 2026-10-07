"""Normalize units, audit coverage, and preserve dated input bundles."""

from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4
import numpy as np
import pandas as pd


def completed_month_end(end):
    date = pd.Timestamp(end).normalize()
    return date if date.is_month_end else date.replace(day=1) - pd.Timedelta(days=1)


def monthly_sample(history, end):
    """Keep each series' last available observation in each completed month."""
    if history.empty:
        return history.assign(month=pd.Series(dtype="str"))
    data = history[history.date <= completed_month_end(end)].copy()
    data["month"] = data.date.dt.to_period("M").astype(str)
    # Preserve actual returned dates; do not fill missing months or replace them with calendar dates.
    return (data.sort_values(["date", "key"]).groupby(["month", "key"], sort=False)
            .tail(1).sort_values(["date", "key"]).reset_index(drop=True))


def fetch_history(client, specs, start, end, frequency="daily"):
    if frequency not in {"daily", "monthly"}:
        raise ValueError("Frequency must be daily or monthly.")
    if frequency == "monthly":
        end = completed_month_end(end)
    if pd.Timestamp(start) > pd.Timestamp(end):
        raise ValueError("No complete months in the requested date range." if frequency == "monthly"
                         else "Start date must not exceed end date.")
    records, coverage = [], []
    # Group by field to avoid requesting irrelevant cross-products of fields and securities.
    for field in sorted({s.field for s in specs}):
        selected = [s for s in specs if s.field == field]
        tickers = list(dict.fromkeys(s.ticker for s in selected))
        raw = (client.history(tickers, [field], start, end, frequency="monthly")
               if frequency == "monthly" else client.history(tickers, [field], start, end))
        for spec in selected:
            rows = raw[(raw.ticker == spec.ticker) & (raw.field == field.upper())].copy()
            rows["value"] = pd.to_numeric(rows["value"], errors="coerce")
            rows = rows[np.isfinite(rows["value"])]
            rows = rows[rows.date.between(pd.Timestamp(start), pd.Timestamp(end))]
            if rows.duplicated(["date"]).any():
                raise ValueError(f"Duplicate dates returned for {spec.key}.")
            rows["key"] = spec.key
            if frequency == "monthly":
                rows = monthly_sample(rows, end)
            coverage.append({"key": spec.key, "required": spec.required, "verified": spec.verified,
                             "observations": len(rows),
                             "first_date": str(rows.date.min().date()) if len(rows) else None,
                             "last_date": str(rows.date.max().date()) if len(rows) else None})
            rows["source"] = "Bloomberg"
            rows["units"] = spec.units
            rows["curve_type"] = spec.curve_type
            rows["maturity_years"] = spec.maturity_years
            rows["verified"] = spec.verified
            if spec.units != "index":
                rows["rate_decimal"] = rows.value * {"percent": 0.01, "basis_points": 0.0001, "decimal": 1.0}[spec.units]
            else:
                rows["rate_decimal"] = np.nan
            records.append(rows)
    missing = [r["key"] for r in coverage if r["required"] and not r["observations"]]
    if missing:
        raise ValueError(f"Required series returned no numeric data: {missing}. Check identifiers, fields and entitlements.")
    return pd.concat(records, ignore_index=True).sort_values(["date", "key"]), pd.DataFrame(coverage)


def curve_asof(history, asof, keys, max_age_days=7, require_type=None, require_verified=True):
    """Select a complete curve on one common observed date; never fill nodes separately."""
    date = pd.Timestamp(asof).normalize()
    keys = list(keys)
    if not keys or len(keys) != len(set(keys)):
        raise ValueError("Specify nonempty, unique curve keys.")
    data = history[(history.date <= date) & history.key.isin(keys)].copy()
    if data.duplicated(["date", "key"]).any():
        raise ValueError("Duplicate curve date/key pairs.")
    data = data[np.isfinite(data.rate_decimal)]
    complete = data.groupby("date").key.nunique()
    complete = complete[complete == len(keys)]
    if complete.empty:
        raise ValueError("No common date contains every requested curve node.")
    observed = complete.index.max()
    if (date - observed).days > max_age_days:
        raise ValueError(f"Latest complete curve is stale: {observed.date()}.")
    result = data[data.date == observed].sort_values("maturity_years")
    if result.maturity_years.isna().any() or not (result.maturity_years > 0).all():
        raise ValueError("Curve nodes must have positive maturities; overnight policy series are separate inputs.")
    if result.curve_type.nunique() != 1:
        raise ValueError("Curve nodes mix different curve types.")
    if require_type and not result.curve_type.eq(require_type).all():
        raise ValueError(f"Expected {require_type}; do not substitute benchmark yields for par or zero rates.")
    if require_verified and not result.verified.all():
        raise ValueError("Bloomberg definitions are not verified. Review catalog and metadata before use.")
    return result.reset_index(drop=True)


def save_bundle(history, coverage, output, metadata):
    stamp = datetime.now(timezone.utc)
    folder = Path(output) / (stamp.strftime("%Y%m%dT%H%M%S") + "_" + uuid4().hex[:8])
    folder.mkdir(parents=True, exist_ok=False)
    history.to_csv(folder / "observations.csv", index=False)
    coverage.to_csv(folder / "coverage.csv", index=False)
    metadata = {**metadata, "retrieved_at_utc": stamp.isoformat(), "forward_filled": False}
    (folder / "manifest.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return folder
