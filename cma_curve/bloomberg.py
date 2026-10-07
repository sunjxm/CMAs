"""xbbg adapter supporting legacy wide and newer long dataframe outputs."""

import inspect
import socket
import pandas as pd


class BloombergError(RuntimeError):
    pass


def normalize_history(frame, tickers, fields):
    if frame is None or frame.empty:
        return pd.DataFrame(columns=["date", "ticker", "field", "value"])
    frame = frame.copy()
    names = {str(c).lower(): c for c in frame.columns}
    if {"date", "ticker", "field", "value"}.issubset(names):
        result = frame[[names[k] for k in ["date", "ticker", "field", "value"]]].copy()
        result.columns = ["date", "ticker", "field", "value"]
    elif "date" in names and "ticker" in names:
        result = frame.melt(id_vars=[names["date"], names["ticker"]], var_name="field", value_name="value")
        result = result.rename(columns={names["date"]: "date", names["ticker"]: "ticker"})
    elif isinstance(frame.columns, pd.MultiIndex) and frame.columns.nlevels == 2:
        pieces = []
        for ticker, field in frame.columns:
            pieces.append(pd.DataFrame({"date": frame.index, "ticker": ticker, "field": field,
                                        "value": frame[(ticker, field)].to_numpy()}))
        result = pd.concat(pieces, ignore_index=True)
    elif len(tickers) == 1:
        result = frame.rename_axis("date").reset_index().melt(id_vars="date", var_name="field", value_name="value")
        result["ticker"] = tickers[0]
    else:
        raise BloombergError(f"Unrecognized xbbg history layout: {frame.columns}")
    result["date"] = pd.to_datetime(result["date"]).dt.normalize()
    result["field"] = result["field"].astype(str).str.upper()
    result["ticker"] = result["ticker"].astype(str)
    return result[result["ticker"].isin(tickers) & result["field"].isin([f.upper() for f in fields])].reset_index(drop=True)


class BloombergClient:
    def __init__(self, host="localhost", port=8194, timeout_seconds=20, backend=None):
        self.host, self.port, self.timeout_seconds = host, port, timeout_seconds
        self._backend = backend

    def check_connection(self):
        try:
            with socket.create_connection((self.host, self.port), timeout=3):
                pass
        except OSError as exc:
            raise BloombergError(f"Bloomberg API is unreachable at {self.host}:{self.port}. "
                                 "Check the logged-in Terminal/API service or supply your API host and port.") from exc

    def _blp(self):
        if self._backend is None:
            self.check_connection()
            try:
                from xbbg import blp
            except ImportError as exc:
                raise BloombergError("Run this code in your Bloomberg-enabled Python environment.") from exc
            if hasattr(blp, "configure"):
                blp.configure(host=self.host, port=self.port,
                              request_timeout_ms=int(self.timeout_seconds * 1000), retry_max_retries=0)
            self._backend = blp
        return self._backend

    def _options(self, method):
        if "backend" in inspect.signature(method).parameters:
            return {"backend": "pandas", "format": "long"}
        return {"timeout": int(self.timeout_seconds * 1000), "server_host": self.host, "server_port": self.port}

    def reference(self, tickers, fields=("NAME", "PX_LAST")):
        method = self._blp().bdp
        return method(tickers=list(tickers), flds=list(fields), **self._options(method))

    def history(self, tickers, fields, start, end, frequency="daily"):
        if pd.Timestamp(start) > pd.Timestamp(end):
            raise ValueError("Start date must not exceed end date.")
        if frequency not in {"daily", "monthly"}:
            raise ValueError("Frequency must be daily or monthly.")
        method = self._blp().bdh
        raw = method(tickers=list(tickers), flds=list(fields),
                     start_date=pd.Timestamp(start).strftime("%Y-%m-%d"),
                     end_date=pd.Timestamp(end).strftime("%Y-%m-%d"),
                     Per="M" if frequency == "monthly" else "D",
                     periodicityAdjustment="CALENDAR" if frequency == "monthly" else "ACTUAL",
                     **self._options(method))
        return normalize_history(raw, tickers, fields)
