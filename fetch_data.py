"""Run from this folder in your Bloomberg-enabled environment."""

import argparse
import importlib.metadata
from pathlib import Path
import sys
import pandas as pd
from cma_curve import BloombergClient, load_catalog, fetch_history, save_bundle
from cma_curve.treasury import fetch_treasury_par
from cma_curve.official import fetch_official_inputs
from cma_curve.data import completed_month_end, monthly_sample


def main(argv=None, client=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["check", "metadata", "history", "treasury-par", "official-inputs"])
    parser.add_argument("--catalog", type=Path, default=Path(__file__).with_name("catalog.json"))
    parser.add_argument("--groups", nargs="+", default=["treasury", "cash"])
    parser.add_argument("--sources", type=Path, default=Path(__file__).with_name("official_sources.json"))
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--frequency", choices=["daily", "monthly"], default="monthly")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=8194)
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("data"))
    args = parser.parse_args(argv)
    if args.command == "official-inputs":
        folder, results = fetch_official_inputs(args.sources, args.output)
        print(f"Official-source archive: {folder}")
        for result in results:
            print(f"{result['key']}: {result['status']} {result.get('error', '')}")
        if any(result["status"] == "error" for result in results):
            raise ValueError("Some official downloads failed; successful files and the error report were retained.")
        return
    if client is None:
        client = BloombergClient(args.host, args.port)
    if args.command == "check":
        client.check_connection()
        print(f"API port reachable at {args.host}:{args.port}; a metadata request must still verify authorization.")
        return
    if args.command == "metadata":
        specs = load_catalog(args.catalog, args.groups)
        data = client.reference(list(dict.fromkeys(s.ticker for s in specs)))
        if data is None or data.empty:
            raise ValueError("Bloomberg returned no reference data.")
        folder = save_bundle(pd.DataFrame(), pd.DataFrame(), args.output,
                             {"kind": "reference_data", "catalog": [s.record() for s in specs]})
        data.to_csv(folder / "bloomberg_reference.csv", index=True)
        print(f"Reference data saved: {folder}")
        print(data.to_string())
        if {"ticker", "field", "value"}.issubset(data.columns):
            available = set(data.loc[data.value.notna(), "ticker"])
        else:
            available = set(data.index.astype(str))
        missing = [s.ticker for s in specs if s.required and s.ticker not in available]
        if missing:
            raise ValueError(f"Required securities missing from reference response: {missing}")
        return
    if not args.start or not args.end:
        raise ValueError("Supply explicit --start and --end dates for reproducible historical inputs.")
    effective_end = (completed_month_end(args.end).strftime("%Y-%m-%d")
                     if args.frequency == "monthly" else args.end)
    if pd.Timestamp(args.start) > pd.Timestamp(effective_end):
        raise ValueError("No complete months in the requested date range." if args.frequency == "monthly"
                         else "Start date must not exceed end date.")
    if args.command == "history":
        specs = load_catalog(args.catalog, args.groups)
        history, coverage = fetch_history(client, specs, args.start, effective_end, frequency=args.frequency)
        metadata = {"kind": "bloomberg_history", "start": args.start, "end": args.end,
                    "python": sys.version, "xbbg": importlib.metadata.version("xbbg"),
                    "catalog": [s.record() for s in specs]}
    else:
        history, urls = fetch_treasury_par(args.start, effective_end,
                                          progress=lambda message: print(message, flush=True))
        if args.frequency == "monthly":
            history = monthly_sample(history, effective_end)
        coverage = history.groupby("key").agg(observations=("value", "count"),
                                               first_date=("date", "min"), last_date=("date", "max")).reset_index()
        metadata = {"kind": "treasury_par_history", "start": args.start, "end": args.end, "urls": urls}
    metadata.update(frequency=args.frequency, effective_end=effective_end,
                    sampling="last_available_in_completed_month" if args.frequency == "monthly" else "daily",
                    requested_start=args.start, actual_start=str(history.date.min().date()))
    folder = save_bundle(history, coverage, args.output, metadata)
    print(f"Saved {len(history):,} observations to {folder}")
    print(coverage.to_string(index=False))


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, OSError) as exc:
        print(f"Data fetch failed: {exc}", file=sys.stderr)
        sys.exit(1)
