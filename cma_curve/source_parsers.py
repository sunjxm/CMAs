"""Explicit official-workbook mappings with conservative availability metadata."""

import hashlib
import json
from pathlib import Path
import re
import warnings

import numpy as np
import pandas as pd


REQUIRED_SOURCES = {"hlw_current", "hlw_realtime", "lw_current", "spf_inflation", "spf_pce10", "acm"}
PARSER_VERSION = "1.0"


def read_sheet(path, sheet, **kwargs):
    try:
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="Cannot parse header or footer.*", category=UserWarning)
            return pd.read_excel(path, sheet_name=sheet, **kwargs)
    except ImportError as exc:
        raise RuntimeError('Install official Excel readers: python -m pip install -e ".[official]"') from exc


def normalize_series(dates, values, key, frequency, measure, inflation_basis="not_applicable",
                     curve_type="not_applicable", maturity_years=None, vintage_label="current"):
    frame = pd.DataFrame({"source_date": pd.to_datetime(dates, errors="raise"),
                          "value": pd.to_numeric(values, errors="raise")}).reset_index(drop=True)
    frame = frame.dropna(subset=["value"])
    if frame.empty or frame.source_date.isna().any() or not np.isfinite(frame.value).all():
        raise ValueError(f"{key}: empty series, invalid dates, or nonfinite values.")
    period = frame.source_date.dt.to_period("Q" if frequency == "quarterly" else "M")
    if period.duplicated().any():
        raise ValueError(f"{key}: duplicate observation periods in vintage {vintage_label}.")
    frame["observation_period"] = period.astype(str)
    frame["date"] = period.dt.end_time.dt.normalize() if frequency == "quarterly" else frame.source_date.dt.normalize()
    frame["key"] = key
    frame["rate_decimal"] = frame.value / 100
    frame["units"] = "percent"
    frame["frequency"] = frequency
    frame["measure"] = measure
    frame["inflation_basis"] = inflation_basis
    frame["curve_type"] = curve_type
    frame["maturity_years"] = maturity_years
    frame["vintage_label"] = vintage_label
    # A quarter label, one-sided estimate, or retrieval date is not a release date.
    frame["publication_date"] = None
    frame["vintage_date"] = None
    frame["availability_status"] = "release_dates_not_mapped"
    frame["point_in_time_eligible"] = False
    return frame.sort_values("date").reset_index(drop=True)


def parse_hlw_sheet(raw, key="hlw_us_rstar", vintage_label="current"):
    if raw.shape[0] < 7 or raw.shape[1] < 3 or str(raw.iat[5, 0]).strip() != "Date":
        raise ValueError("Unrecognized HLW layout: expected Date on Excel row 6.")
    columns = [i for i in range(raw.shape[1])
               if str(raw.iat[4, i]).strip() == "Natural Rate (r*)"
               and str(raw.iat[5, i]).strip() == "US"]
    if len(columns) != 1:
        raise ValueError("Expected exactly one US Natural Rate (r*) column in HLW workbook.")
    dates = raw.iloc[6:, 0]
    selected = dates.notna()
    return normalize_series(dates[selected], raw.iloc[6:, columns[0]][selected], key,
                            "quarterly", "real_neutral_policy_rate", "core_PCE",
                            vintage_label=vintage_label)


def parse_lw_sheet(raw):
    if (raw.shape[0] < 7 or raw.shape[1] < 3 or str(raw.iat[5, 0]).strip() != "Date"
            or str(raw.iat[4, 2]).strip() != "One-Sided Estimates"
            or str(raw.iat[5, 2]).strip() != "rstar"):
        raise ValueError("Unrecognized LW layout: expected one-sided rstar in column C, row 6.")
    selected = raw.iloc[6:, 0].notna()
    return normalize_series(raw.iloc[6:, 0][selected], raw.iloc[6:, 2][selected], "lw_us_rstar",
                            "quarterly", "real_neutral_policy_rate", "core_PCE")


def parse_spf_sheet(raw, field, key, basis):
    if not {"YEAR", "QUARTER", field}.issubset(raw.columns):
        raise ValueError(f"SPF workbook missing YEAR, QUARTER or {field}.")
    years = pd.to_numeric(raw.YEAR, errors="raise")
    quarters = pd.to_numeric(raw.QUARTER, errors="raise")
    if (years.isna().any() or quarters.isna().any() or not quarters.isin([1, 2, 3, 4]).all()
            or not years.eq(years.astype(int)).all()):
        raise ValueError("Invalid SPF survey year/quarter.")
    dates = pd.Series([pd.Period(f"{int(y)}Q{int(q)}", freq="Q").start_time
                       for y, q in zip(years, quarters)], index=raw.index)
    return normalize_series(dates, raw[field], key, "quarterly", "median_10y_inflation_forecast", basis)


def parse_acm_sheet(raw):
    fields = [f"{prefix}{year:02d}" for prefix in ("ACMY", "ACMTP", "ACMRNY") for year in range(1, 11)]
    if not {"DATE", *fields}.issubset(raw.columns):
        raise ValueError("ACM Monthly workbook missing expected yield, premium or risk-neutral columns.")
    numeric = raw[fields].apply(pd.to_numeric, errors="raise")
    for year in range(1, 11):
        columns = [f"ACMY{year:02d}", f"ACMTP{year:02d}", f"ACMRNY{year:02d}"]
        complete = numeric[columns].dropna()
        if complete.empty or not np.isfinite(complete).all().all():
            raise ValueError(f"ACM {year}y decomposition lacks finite complete observations.")
        residual = complete[columns[0]] - complete[columns[1]] - complete[columns[2]]
        if residual.abs().max() > 1e-6:
            raise ValueError(f"ACM {year}y yield != risk-neutral yield + term premium.")
    dates = pd.to_datetime(raw.DATE, format="%d-%b-%Y", errors="raise")
    frames = []
    for field in fields:
        prefix, maturity = field[:-2], int(field[-2:])
        measure = {"ACMY": "model_fitted_zero_yield", "ACMTP": "zero_term_premium",
                   "ACMRNY": "risk_neutral_zero_yield"}[prefix]
        frames.append(normalize_series(dates, numeric[field], field.lower(), "monthly", measure,
                                       curve_type="zero_model", maturity_years=maturity))
    return pd.concat(frames, ignore_index=True)


def parse_official_archive(folder, progress=None):
    folder = Path(folder)
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    sources = manifest["sources"]
    if len({s["key"] for s in sources}) != len(sources):
        raise ValueError("Duplicate source keys in official manifest.")
    records = {s["key"]: s for s in sources}
    missing = REQUIRED_SOURCES - records.keys()
    if missing:
        raise ValueError(f"Archive lacks {sorted(missing)}; rerun main.py --task official-inputs.")
    frames, inventory = [], []
    for key in sorted(REQUIRED_SOURCES):
        source = records[key]
        if source.get("status") != "ok":
            raise ValueError(f"Official source {key} was not downloaded successfully.")
        filename = source["filename"]
        if Path(filename).name != filename:
            raise ValueError("Official manifest filename must be a plain filename.")
        path = folder / filename
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != source["sha256"]:
            raise ValueError(f"Checksum mismatch for {filename}; preserve the original archive.")
        if progress:
            progress(f"Parsing {filename}...")
        if key == "hlw_current":
            sheet = "HLW Estimates"
            data = parse_hlw_sheet(read_sheet(path, sheet, header=None))
        elif key == "hlw_realtime":
            with pd.ExcelFile(path) as workbook:
                sheets = [s for s in workbook.sheet_names if re.fullmatch(r"\d{4}Q[1-4]", s)]
            if not sheets:
                raise ValueError("No recognized quarterly vintages in HLW real-time workbook.")
            parts = []
            for sheet in sheets:
                part = parse_hlw_sheet(read_sheet(path, sheet, header=None), "hlw_us_rstar_realtime", sheet)
                part["source_sheet"] = sheet
                if part.observation_period.max() != sheet:
                    raise ValueError(f"HLW vintage {sheet} does not end in its labeled quarter.")
                parts.append(part)
            data = pd.concat(parts, ignore_index=True)
        elif key == "lw_current":
            sheet = "data"
            data = parse_lw_sheet(read_sheet(path, sheet, header=None))
        elif key == "spf_inflation":
            sheet = "INFLATION"
            data = parse_spf_sheet(read_sheet(path, sheet), "INFCPI10YR", "spf_cpi10_median", "headline_CPI")
        elif key == "spf_pce10":
            sheet = "Median_Level"
            data = parse_spf_sheet(read_sheet(path, sheet), "PCE10", "spf_pce10_median", "headline_PCE")
        else:
            sheet = "ACM Monthly"
            data = parse_acm_sheet(read_sheet(path, sheet))
        if "source_sheet" not in data:
            data["source_sheet"] = sheet
        data["source_key"] = key
        data["source_file"] = filename
        data["source_url"] = source["url"]
        data["source_sha256"] = digest
        data["retrieved_at_utc"] = manifest["retrieved_at_utc"]
        frames.append(data)
        inventory.append({"source_key": key, "source_file": filename, "sha256": digest,
                          "observations": len(data), "series": data.key.nunique(),
                          "vintages": data.vintage_label.nunique(),
                          "first_period": str(data.date.min().date()), "last_period": str(data.date.max().date())})
    data = pd.concat(frames, ignore_index=True)
    if data.duplicated(["source_key", "key", "vintage_label", "observation_period"]).any():
        raise ValueError("Duplicate normalized source/vintage/period observations.")
    return data.sort_values(["source_key", "key", "vintage_label", "date"]), pd.DataFrame(inventory), manifest
