"""Data inputs for capital market assumption yield curves."""

from .catalog import SeriesSpec, load_catalog
from .bloomberg import BloombergClient
from .data import fetch_history, curve_asof, save_bundle

__all__ = ["SeriesSpec", "load_catalog", "BloombergClient", "fetch_history", "curve_asof", "save_bundle"]
