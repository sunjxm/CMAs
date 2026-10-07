"""Instrument definitions are configuration, not forecasting assumptions."""

from dataclasses import dataclass, asdict
import json
from pathlib import Path


@dataclass(frozen=True)
class SeriesSpec:
    key: str
    ticker: str
    field: str
    group: str
    units: str
    curve_type: str
    maturity_years: float | None = None
    required: bool = True
    verified: bool = False

    def __post_init__(self):
        if not self.key or not self.ticker or not self.field:
            raise ValueError("Series key, ticker and field must be nonempty.")
        if self.units not in {"percent", "basis_points", "decimal", "index"}:
            raise ValueError(f"Unsupported units: {self.units}")
        if self.maturity_years is not None and self.maturity_years <= 0:
            raise ValueError("Maturity must be positive.")

    def record(self):
        return asdict(self)


def load_catalog(path, groups=None):
    with Path(path).open(encoding="utf-8") as handle:
        specs = [SeriesSpec(**item) for item in json.load(handle)["series"]]
    if len({s.key for s in specs}) != len(specs):
        raise ValueError("Catalog keys must be unique.")
    if groups:
        specs = [s for s in specs if s.group in set(groups)]
    if not specs:
        raise ValueError("No series selected.")
    return specs
