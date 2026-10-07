"""Official Treasury par rates from the public annual XML feed."""

from urllib.request import urlopen
from xml.etree import ElementTree
from time import monotonic
import warnings
import pandas as pd
import numpy as np

TENORS = {"BC_1MONTH": 1/12, "BC_3MONTH": .25, "BC_6MONTH": .5,
          "BC_1YEAR": 1., "BC_2YEAR": 2., "BC_3YEAR": 3., "BC_5YEAR": 5.,
          "BC_7YEAR": 7., "BC_10YEAR": 10., "BC_20YEAR": 20., "BC_30YEAR": 30.}


def parse_treasury_xml(payload):
    root = ElementTree.fromstring(payload)
    records = []
    for properties in root.iter():
        if properties.tag.split("}")[-1] != "properties":
            continue
        values = {child.tag.split("}")[-1]: child.text for child in properties}
        if not values.get("NEW_DATE"):
            continue
        for field, maturity in TENORS.items():
            value = values.get(field)
            if value is None:
                continue
            numeric = float(value)
            if not np.isfinite(numeric):
                continue
            records.append({"date": pd.Timestamp(values["NEW_DATE"]).normalize(),
                            "key": field, "ticker": field, "field": "par_yield",
                            "value": numeric, "rate_decimal": numeric / 100,
                            "units": "percent", "maturity_years": maturity,
                            "curve_type": "par", "source": "US Treasury", "verified": True})
    if not records:
        raise ValueError("Treasury response contains no recognized par yield observations.")
    result = pd.DataFrame(records).sort_values(["date", "maturity_years"])
    if result.duplicated(["date", "key"]).any():
        raise ValueError("Treasury feed contains duplicate date/node observations.")
    return result.reset_index(drop=True)


def fetch_treasury_par(start, end, opener=urlopen, progress=None, timeout_seconds=30):
    start, end = pd.Timestamp(start).normalize(), pd.Timestamp(end).normalize()
    if start > end:
        raise ValueError("Start date must not exceed end date.")
    if start.year < 1990:
        warnings.warn("Treasury public par history starts in 1990; earlier requested dates are unavailable.",
                      stacklevel=2)
        start = pd.Timestamp("1990-01-01")
    if start > end:
        raise ValueError("No Treasury feed coverage before 1990.")
    frames, urls = [], []
    years = range(start.year, end.year + 1)
    for position, year in enumerate(years, 1):
        url = ("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml"
               f"?data=daily_treasury_yield_curve&field_tdr_date_value={year}")
        if progress is not None:
            progress(f"Downloading Treasury year {year} ({position}/{len(years)})..."
                     f" Network timeout: {timeout_seconds}s.")
        started = monotonic()
        try:
            with opener(url, timeout=timeout_seconds) as response:
                frame = parse_treasury_xml(response.read())
        except (OSError, ValueError, ElementTree.ParseError) as exc:
            raise RuntimeError(f"Treasury download failed for {year}: {exc}. URL: {url}") from exc
        frames.append(frame)
        if progress is not None:
            progress(f"Treasury {year}: {len(frame):,} daily node observations"
                     f" received in {monotonic() - started:.1f}s.")
        urls.append(url)
    history = pd.concat(frames, ignore_index=True)
    history = history[history.date.between(start, end)].reset_index(drop=True)
    if history.empty:
        raise ValueError("No Treasury observations in requested date range.")
    return history, urls
