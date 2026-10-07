"""Starting point for fetching the inputs to the CMA yield curve model.

Run main.py to check Bloomberg, or main.py --task all to fetch every input group.
Change the defaults below when running directly from your editor.
"""

import argparse
from pathlib import Path
import sys

from fetch_data import main as fetch_data
from cma_curve import BloombergClient


DEFAULT_TASK = "check"
START_DATE = "1996-10-01"
END_DATE = "2026-09-30"
FREQUENCY = "monthly"
GROUPS = ("treasury", "cash", "real_rates")
PROJECT_DIR = Path(__file__).resolve().parent
DATA_DIR = PROJECT_DIR / "data"
DOWNLOAD_TASKS = ("check", "metadata", "history", "treasury-par", "official-inputs")
TASKS = (*DOWNLOAD_TASKS, "process-inputs", "anchor-review", "curve-projection",
         "asset-review", "asset-metadata", "asset-history", "asset-analytics", "asset-analytics-probe", "asset-analytics-normalize", "tips-inputs", "bond-returns", "composition-inputs", "credit-review", "holding-returns", "global-hedge-review", "workbook-inputs", "foreign-cash", "all")


def run(task=DEFAULT_TASK, start=START_DATE, end=END_DATE, groups=GROUPS,
        output=DATA_DIR, host="localhost", port=8194, frequency=FREQUENCY,
        official_archive=None, treasury_bundle=None, settings=None, review_bundle=None,
        projection_settings=None, asset_catalog=None, assets=None, return_settings=None,
        curve_bundle=None, analytics_bundle=None, history_bundle=None, constituent_bundle=None,
        global_hedge_inputs=None, loss_segments=None, spread_segments=None,
        workbook=None, workbook_asof=None, workbook_rating_method=None,
        foreign_cash_settings=None, foreign_cash_inputs=None, workbook_bundle=None):
    """Run a selected task or the full data pipeline, independent of working directory."""
    if task not in TASKS:
        raise ValueError(f"Unknown task: {task}. Choose one of {TASKS}.")
    if task == "foreign-cash":
        if frequency != "monthly":
            raise ValueError("Foreign cash projection uses monthly steps.")
        from cma_curve.foreign_cash import run_foreign_cash
        return run_foreign_cash(output, foreign_cash_settings or PROJECT_DIR / "foreign_cash_settings.json",
                                foreign_cash_inputs, workbook_bundle, curve_bundle)
    if task == "workbook-inputs":
        from cma_curve.workbook_inputs import run_workbook_inputs
        return run_workbook_inputs(output, workbook or PROJECT_DIR / "BBG_bond_data.xlsx",
                                   workbook_asof, workbook_rating_method)
    if task == "composition-inputs":
        from cma_curve.composition_inputs import fetch_composition_inputs
        return fetch_composition_inputs(asset_catalog or PROJECT_DIR / "bond_assets.json", output,
                                         BloombergClient(host, port))
    if task in {"credit-review", "holding-returns", "global-hedge-review"}:
        if frequency != "monthly":
            raise ValueError("Fixed-income research inputs use monthly frequency.")
        if task == "credit-review":
            from cma_curve.credit_assumptions import run_credit_review
            return run_credit_review(output, constituent_bundle, loss_segments_path=loss_segments,
                                      spread_segments_path=spread_segments)
        if task == "holding-returns":
            from cma_curve.holding_returns import run_holding_returns
            return run_holding_returns(output, curve_bundle)
        from cma_curve.global_hedge import run_global_hedge_review
        return run_global_hedge_review(output, global_hedge_inputs)
    if task == "bond-returns":
        if frequency != "monthly":
            raise ValueError("Bond return research uses monthly frequency.")
        from cma_curve.bond_returns import run_bond_returns
        return run_bond_returns(output, return_settings or PROJECT_DIR / "return_settings.json",
                                asset_catalog or PROJECT_DIR / "bond_assets.json",
                                settings or PROJECT_DIR / "anchor_settings.json",
                                projection_settings or PROJECT_DIR / "projection_settings.json",
                                curve_bundle, analytics_bundle, history_bundle)
    if task == "tips-inputs":
        if frequency != "monthly":
            raise ValueError("TIPS proxy inputs use monthly frequency.")
        from cma_curve.tips_inputs import run_tips_inputs
        return run_tips_inputs(output, start, end, BloombergClient(host, port))
    if task == "asset-analytics":
        from cma_curve.asset_analytics import discover_analytics
        return discover_analytics(asset_catalog or PROJECT_DIR / "bond_assets.json", output, host, port)
    if task == "asset-analytics-probe":
        from cma_curve.asset_analytics import probe_analytics
        return probe_analytics(asset_catalog or PROJECT_DIR / "bond_assets.json", output, start, end,
                               BloombergClient(host, port))
    if task == "asset-analytics-normalize":
        from cma_curve.asset_analytics import normalize_probe
        return normalize_probe(asset_catalog or PROJECT_DIR / "bond_assets.json", output)
    if task == "curve-projection":
        if frequency != "monthly":
            raise ValueError("Curve projection uses the monthly calibration pipeline.")
        from cma_curve.curve_projection import run_projection
        return run_projection(output, settings or PROJECT_DIR / "anchor_settings.json",
                              projection_settings or PROJECT_DIR / "projection_settings.json", review_bundle)
    if task in {"asset-review", "asset-metadata", "asset-history"}:
        if frequency != "monthly":
            raise ValueError("Bond index inputs use monthly frequency.")
        from cma_curve.bond_inputs import run_asset_inputs
        client = None if task == "asset-review" else BloombergClient(host, port)
        return run_asset_inputs(task, asset_catalog or PROJECT_DIR / "bond_assets.json",
                                output, start, end, client, assets)
    if task in {"process-inputs", "anchor-review"}:
        if frequency != "monthly":
            raise ValueError("Input processing and anchor review use monthly calibration only.")
        from cma_curve.analysis import run_analysis
        return run_analysis(task, start, end, output, settings or PROJECT_DIR / "anchor_settings.json",
                            official_archive, treasury_bundle,
                            progress=lambda message: print(message, flush=True))
    if not groups:
        raise ValueError("Select at least one Bloomberg data group.")
    steps = DOWNLOAD_TASKS if task == "all" else (task,)
    client = BloombergClient(host, port)
    for step in steps:
        print(f"\nCMA inputs: {step}", flush=True)
        fetch_data([
            step, "--start", start, "--end", end,
            "--frequency", frequency,
            "--groups", *groups,
            "--catalog", str(PROJECT_DIR / "catalog.json"),
            "--sources", str(PROJECT_DIR / "official_sources.json"),
            "--output", str(Path(output).resolve()),
            "--host", host, "--port", str(port),
        ], client=client)
    print("\nSelected tasks completed.", flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", choices=TASKS, default=DEFAULT_TASK)
    parser.add_argument("--start", default=START_DATE)
    parser.add_argument("--end", default=END_DATE)
    parser.add_argument("--frequency", choices=["daily", "monthly"], default=FREQUENCY)
    parser.add_argument("--groups", nargs="+", default=list(GROUPS))
    parser.add_argument("--output", type=Path, default=DATA_DIR)
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=8194)
    parser.add_argument("--official-archive", type=Path)
    parser.add_argument("--treasury-bundle", type=Path)
    parser.add_argument("--settings", type=Path)
    parser.add_argument("--review-bundle", type=Path)
    parser.add_argument("--projection-settings", type=Path)
    parser.add_argument("--asset-catalog", type=Path)
    parser.add_argument("--return-settings", type=Path)
    parser.add_argument("--curve-bundle", type=Path)
    parser.add_argument("--analytics-bundle", type=Path)
    parser.add_argument("--history-bundle", type=Path)
    parser.add_argument("--constituent-bundle", type=Path)
    parser.add_argument("--global-hedge-inputs", type=Path)
    parser.add_argument("--loss-segments", type=Path)
    parser.add_argument("--spread-segments", type=Path)
    parser.add_argument("--workbook", type=Path)
    parser.add_argument("--workbook-asof", help="Actual export observation date; never inferred from --end.")
    parser.add_argument("--workbook-rating-method", help="Confirmed rating agency or composite definition.")
    parser.add_argument("--foreign-cash-settings", type=Path)
    parser.add_argument("--foreign-cash-inputs", type=Path)
    parser.add_argument("--workbook-bundle", type=Path)
    parser.add_argument("--assets", nargs="+", help="Asset keys to review/download; defaults to all six.")
    args = parser.parse_args(argv)
    run(args.task, args.start, args.end, args.groups, args.output, args.host, args.port, args.frequency,
        args.official_archive, args.treasury_bundle, args.settings, args.review_bundle,
        args.projection_settings, args.asset_catalog, args.assets, args.return_settings,
        args.curve_bundle, args.analytics_bundle, args.history_bundle,
        args.constituent_bundle, args.global_hedge_inputs, args.loss_segments, args.spread_segments,
        args.workbook, args.workbook_asof, args.workbook_rating_method,
        args.foreign_cash_settings, args.foreign_cash_inputs, args.workbook_bundle)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, OSError) as exc:
        print(f"CMA inputs failed: {exc}", file=sys.stderr)
        sys.exit(1)
