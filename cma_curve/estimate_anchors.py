"""Candidate par anchors from macro inputs and same-date monthly par spreads."""

import numpy as np
import pandas as pd

from .data import completed_month_end


def spread_statistics(history, start, end, windows, minimum_months=60):
    start, end = pd.Timestamp(start), completed_month_end(end)
    if start > end:
        raise ValueError("No complete months in calibration window.")
    data = history[history.date.between(start, end)].copy()
    if data.empty or not data.curve_type.eq("par").all() or not data.source.eq("US Treasury").all():
        raise ValueError("Slope estimation requires official Treasury par observations only.")
    if not data.verified.eq(True).all() or not np.isfinite(data.rate_decimal).all():
        raise ValueError("Slope estimation requires verified finite yields.")
    data["month"] = data.date.dt.to_period("M")
    if data.duplicated(["month", "key"]).any():
        raise ValueError("Supply at most one observation per node per month.")
    wide = data.pivot(index="date", columns="key", values="rate_decimal")
    if "BC_3MONTH" not in wide:
        raise ValueError("Missing 3-month Treasury reference series.")
    rows = []
    for years in windows:
        window_start = max(start, (end.to_period("M") - (int(years) * 12 - 1)).start_time)
        subset = wide[wide.index >= window_start]
        for key in sorted(wide.columns):
            pair = subset[["BC_3MONTH", key]].dropna() if key != "BC_3MONTH" else subset[[key]].dropna()
            spread = pair[key] - pair["BC_3MONTH"]
            months = len(spread)
            rows.append({"key": key, "reference_key": "BC_3MONTH", "window_years": int(years),
                         "requested_start": str(window_start.date()), "requested_end": str(end.date()),
                         "paired_months": months,
                         "expected_months": len(pd.period_range(window_start, end, freq="M")),
                         "first_date": str(pair.index.min().date()) if months else None,
                         "last_date": str(pair.index.max().date()) if months else None,
                         "mean_bps": float(spread.mean() * 10000) if months else None,
                         "median_bps": float(spread.median() * 10000) if months else None,
                         "p10_bps": float(spread.quantile(.1) * 10000) if months else None,
                         "p90_bps": float(spread.quantile(.9) * 10000) if months else None,
                         "eligible": months >= minimum_months})
    return pd.DataFrame(rows)


def macro_candidates(sources, end, settings):
    end = completed_month_end(end)
    rows = []
    for key in ("hlw_us_rstar", "lw_us_rstar", "spf_pce10_median"):
        data = sources[(sources.key == key) & (sources.vintage_label == "current") & (sources.date <= end)].sort_values("date")
        if data.empty:
            raise ValueError(f"Missing required macro input {key} at observation cutoff {end.date()}.")
        latest = data.iloc[-1]
        if latest.date < end - pd.DateOffset(months=settings["maximum_macro_age_months"]):
            raise ValueError(f"Stale macro input {key}: {latest.date.date()}.")
        expected_basis = "headline_PCE" if key == "spf_pce10_median" else "core_PCE"
        if not data.inflation_basis.eq(expected_basis).all():
            raise ValueError(f"Incorrect inflation definition for {key}.")
        rows.append({"candidate": {"hlw_us_rstar": "hlw_latest", "lw_us_rstar": "lw_latest",
                                   "spf_pce10_median": "inflation_latest"}[key],
                     "key": key, "rate_decimal": float(latest.rate_decimal),
                     "observation_period": latest.observation_period, "quarters_used": 1,
                     "source_file": latest.source_file, "source_sha256": latest.source_sha256,
                     "retrieved_at_utc": latest.retrieved_at_utc})
        if key == "hlw_us_rstar":
            count = int(settings["rstar_smoothing_quarters"])
            tail = data.tail(count)
            if len(tail) != count or len(pd.period_range(tail.date.min(), tail.date.max(), freq="Q")) != count:
                raise ValueError("HLW smoothing requires the configured number of consecutive quarters.")
            rows.append({"candidate": "hlw_median20" if count == 20 else f"hlw_median{count}",
                         "key": key, "rate_decimal": float(tail.rate_decimal.median()),
                         "observation_period": f"{tail.observation_period.iloc[0]} to {tail.observation_period.iloc[-1]}",
                         "quarters_used": count, "source_file": latest.source_file,
                         "source_sha256": latest.source_sha256, "retrieved_at_utc": latest.retrieved_at_utc})
    return pd.DataFrame(rows)


def build_candidate_anchors(history, sources, diagnostics, end, settings):
    if settings["slope_statistic"] not in {"mean", "median"}:
        raise ValueError("Slope statistic must be mean or median.")
    macro = macro_candidates(sources, end, settings)
    inflation = macro[macro.candidate == "inflation_latest"].iloc[0]
    window = settings["primary_slope_window_years"]
    slopes = diagnostics[diagnostics.window_years == window]
    nodes = history[["key", "maturity_years"]].drop_duplicates()
    if nodes.key.duplicated().any():
        raise ValueError("Inconsistent maturities for Treasury nodes.")
    slopes = slopes.merge(nodes, on="key", validate="one_to_one")
    if slopes.empty or not slopes.eligible.all():
        raise ValueError("Primary slope window has missing or insufficient paired history.")
    column = settings["slope_statistic"] + "_bps"
    rows = []
    for _, neutral in macro[macro.candidate != "inflation_latest"].iterrows():
        core_headline = settings["core_to_headline_pce_adjustment_bps"] / 10000
        policy_bill = settings["policy_to_3m_basis_bps"] / 10000
        neutral_nominal = neutral.rate_decimal + inflation.rate_decimal + core_headline
        reference = neutral_nominal + policy_bill
        for _, slope in slopes.iterrows():
            spread = slope[column] / 10000
            anchor = reference + spread
            if not np.isfinite(anchor):
                raise ValueError("Nonfinite candidate anchor.")
            rows.append({"candidate": neutral.candidate, "key": slope.key,
                         "maturity_years": slope.maturity_years, "curve_type": "par",
                         "anchor_decimal": anchor, "anchor_percent": anchor * 100,
                         "real_neutral_percent": neutral.rate_decimal * 100,
                         "inflation_percent": inflation.rate_decimal * 100,
                         "core_to_headline_adjustment_bps": settings["core_to_headline_pce_adjustment_bps"],
                         "policy_to_3m_basis_bps": settings["policy_to_3m_basis_bps"],
                         "neutral_nominal_policy_percent": neutral_nominal * 100,
                         "reference_3m_percent": reference * 100,
                         "slope_bps": slope[column], "slope_statistic": settings["slope_statistic"],
                         "slope_window_years": window, "paired_months": slope.paired_months,
                         "expected_months": slope.expected_months,
                         "observation_cutoff": str(completed_month_end(end).date()),
                         "rstar_period": neutral.observation_period,
                         "inflation_survey_period": inflation.observation_period,
                         "primary_candidate": neutral.candidate == settings["primary_candidate"],
                         "status": "research_draft_not_approved", "point_in_time_eligible": False})
    anchors = pd.DataFrame(rows).sort_values(["candidate", "maturity_years"])
    if not anchors.primary_candidate.any():
        raise ValueError("Primary candidate does not match an available macro method.")
    return anchors, macro
