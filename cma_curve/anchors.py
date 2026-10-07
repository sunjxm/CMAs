"""Import dated external anchors and compute historical slope diagnostics."""

import pandas as pd
import numpy as np


def load_anchor_inputs(path, asof):
    data = pd.read_csv(path)
    required = {"key", "value", "units", "observation_date", "publication_date", "vintage_date", "source", "definition"}
    if not required.issubset(data.columns):
        raise ValueError(f"Anchor CSV missing columns: {sorted(required - set(data.columns))}")
    for column in ["observation_date", "publication_date", "vintage_date"]:
        data[column] = pd.to_datetime(data[column], errors="raise")
        if data[column].isna().any():
            raise ValueError(f"Missing {column}.")
    for column in ["key", "source", "definition"]:
        if data[column].isna().any() or data[column].astype(str).str.strip().eq("").any():
            raise ValueError(f"Missing {column}.")
    date = pd.Timestamp(asof)
    # Observation periods may be future forecasts; availability dates must be historical.
    data = data[(data.publication_date <= date) & (data.vintage_date <= date)].copy()
    if data.empty:
        raise ValueError("No anchor inputs were available as of the requested date.")
    data["value"] = pd.to_numeric(data.value, errors="raise")
    if not np.isfinite(data.value).all():
        raise ValueError("Nonfinite anchor value.")
    if not data.units.isin(["percent", "basis_points", "decimal"]).all():
        raise ValueError("Anchor units must be percent, basis_points or decimal.")
    data["rate_decimal"] = data.value * data.units.map({"percent": .01, "basis_points": .0001, "decimal": 1.})
    return data.sort_values(["key", "vintage_date", "publication_date"]).reset_index(drop=True)


def slope_diagnostics(history, cash_key, bond_keys, start, end):
    selected = history[history.date.between(pd.Timestamp(start), pd.Timestamp(end))]
    selected = selected[selected.key.isin([cash_key, *bond_keys])]
    if selected.curve_type.nunique() != 1:
        raise ValueError("Use one curve definition for slope diagnostics.")
    if selected.duplicated(["date", "key"]).any():
        raise ValueError("Duplicate observations.")
    wide = selected.pivot(index="date", columns="key", values="rate_decimal")
    needed = [cash_key, *bond_keys]
    if any(key not in wide for key in needed):
        raise ValueError("Requested slope series missing.")
    rows = []
    for key in bond_keys:
        pair = wide[[cash_key, key]].dropna()
        # Equal weight to calendar months rather than varying trading-day counts.
        spread = (pair[key] - pair[cash_key]).resample("ME").mean().dropna()
        if spread.empty:
            raise ValueError(f"No paired observations for {key}.")
        rows.append({"key": key, "cash_key": cash_key, "months": len(spread),
                     "mean_bps": spread.mean() * 10000, "median_bps": spread.median() * 10000,
                     "p10_bps": spread.quantile(.1) * 10000, "p90_bps": spread.quantile(.9) * 10000})
    return pd.DataFrame(rows)
