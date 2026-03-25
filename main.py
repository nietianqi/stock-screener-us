from __future__ import annotations

import argparse
import sys

from app.config import AppSettings
from app.data_sources.longbridge_auth import LongbridgeAuthError
from app.pipelines.daily_scan import DailyScanPipeline, ScanOptions
from app.pipelines.weekly_rebalance import run_weekly_rebalance
from app.reports.candidate_report import build_console_summary
from app.utils.dates import parse_scan_date
from app.utils.logging import configure_logging


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="US Swing Scanner (Longbridge Edition)")
    subparsers = parser.add_subparsers(dest="command")

    for command_name in ("scan", "weekly"):
        subparser = subparsers.add_parser(command_name)
        subparser.add_argument("--symbols", help="Comma separated Longbridge symbols, e.g. AAPL.US,MSFT.US")
        subparser.add_argument("--universe-file", help="CSV file with symbol,industry_etf_proxy")
        subparser.add_argument("--scan-date", help="Scan date in YYYY-MM-DD format")
        subparser.add_argument("--top-n", type=int, default=20)
        subparser.add_argument("--no-html", action="store_true")
    return parser


def parse_symbols(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    return [symbol.strip() for symbol in raw.split(",") if symbol.strip()]


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    settings = AppSettings.load()
    configure_logging(settings.log_dir)

    options = ScanOptions(
        scan_date=parse_scan_date(getattr(args, "scan_date", None)),
        symbols=parse_symbols(getattr(args, "symbols", None)),
        universe_file=getattr(args, "universe_file", None),
        top_n=getattr(args, "top_n", 20),
        enable_html_report=not getattr(args, "no_html", False),
    )

    try:
        pipeline = DailyScanPipeline(settings)
        if args.command == "weekly":
            result = run_weekly_rebalance(pipeline, options)
        else:
            result = pipeline.run(options)
    except LongbridgeAuthError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(build_console_summary(result.candidates, options.top_n))
    for name, path in result.artifacts.items():
        print(f"{name}: {path}")
    if not result.failures.empty:
        print(f"failures: {len(result.failures)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
