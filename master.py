#!/usr/bin/env python3
"""Run all Kalshi category downloaders with the same market limit."""

from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from pathlib import Path


DEFAULT_MAX_MARKETS = 150

CATEGORY_DOWNLOADERS = [
    ("Climate and Weather", "scripts/download_kalshi_climate_markets.py", "Research/ClimateMarkets"),
    ("Elections", "scripts/download_kalshi_elections_markets.py", "Research/ElectionsMarkets"),
    ("Politics", "scripts/download_kalshi_politics_markets.py", "Research/PoliticsMarkets"),
    ("Entertainment", "scripts/download_kalshi_entertainment_markets.py", "Research/EntertainmentMarkets"),
    ("Commodities", "scripts/download_kalshi_commodities_markets.py", "Research/CommoditiesMarkets"),
    ("Economics", "scripts/download_kalshi_economics_markets.py", "Research/EconomicsMarkets"),
    ("Companies", "scripts/download_kalshi_companies_markets.py", "Research/CompaniesMarkets"),
    ("Financials", "scripts/download_kalshi_financials_markets.py", "Research/FinancialsMarkets"),
    (
        "Science and Technology",
        "scripts/download_kalshi_tech_and_science_markets.py",
        "Research/ScienceTechnologyMarkets",
    ),
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download Kalshi market CSVs for every configured category.",
    )
    parser.add_argument(
        "x",
        nargs="?",
        type=int,
        default=DEFAULT_MAX_MARKETS,
        help="Maximum number of market CSVs to generate per category. Default: 150.",
    )
    parser.add_argument(
        "--max-markets",
        type=int,
        default=None,
        help="Named alias for the positional x argument.",
    )
    parser.add_argument("--start-date", default=None, help="Optional override passed to each downloader.")
    parser.add_argument("--end-date", default=None, help="Optional override passed to each downloader.")
    parser.add_argument(
        "--request-sleep",
        type=float,
        default=None,
        help="Optional per-request sleep override passed to each downloader.",
    )
    parser.add_argument(
        "--period-interval",
        type=int,
        default=None,
        help="Optional candlestick period interval override passed to each downloader.",
    )
    parser.add_argument(
        "--chunk-minutes",
        type=int,
        default=None,
        help="Optional candlestick request chunk size override passed to each downloader.",
    )
    parser.add_argument(
        "--series-limit",
        type=int,
        default=None,
        help="Optional series discovery limit passed to each downloader.",
    )
    parser.add_argument(
        "--full-history-scan",
        action="store_true",
        help="Pass through to each downloader to scan all historical pages.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Discover target markets without downloading candlestick CSVs.",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Pass through to each downloader so a market-level download error stops that category.",
    )
    parser.add_argument(
        "--stop-on-category-error",
        action="store_true",
        help="Stop master.py after the first category script returns a non-zero exit code.",
    )
    parser.add_argument(
        "--clean-output",
        action="store_true",
        help="Delete existing CSV files in each category output folder before downloading.",
    )
    return parser


def market_limit(args: argparse.Namespace) -> int:
    return args.max_markets if args.max_markets is not None else args.x


def pass_through_args(args: argparse.Namespace, limit: int) -> list[str]:
    passthrough = ["--max-markets", str(limit)]
    optional_pairs = [
        ("--start-date", args.start_date),
        ("--end-date", args.end_date),
        ("--request-sleep", args.request_sleep),
        ("--period-interval", args.period_interval),
        ("--chunk-minutes", args.chunk_minutes),
        ("--series-limit", args.series_limit),
    ]
    for flag, value in optional_pairs:
        if value is not None:
            passthrough.extend([flag, str(value)])
    for flag in ("--full-history-scan", "--dry-run", "--fail-fast"):
        if getattr(args, flag.removeprefix("--").replace("-", "_")):
            passthrough.append(flag)
    return passthrough


def count_successful_manifest_rows(output_dir: Path) -> int | None:
    manifest_path = output_dir / "markets_index.csv"
    if not manifest_path.exists():
        return None
    with manifest_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return sum(1 for row in reader if row.get("csv_path") and not row.get("error"))


def clean_output_csvs(output_dir: Path) -> None:
    if not output_dir.exists():
        return
    for csv_path in output_dir.glob("*.csv"):
        csv_path.unlink()


def main() -> int:
    args = build_parser().parse_args()
    limit = market_limit(args)
    if limit < 0:
        raise SystemExit("market limit must be zero or positive")

    repo_root = Path(__file__).resolve().parent
    failures: list[tuple[str, int]] = []
    shared_args = pass_through_args(args, limit)

    for category, script, output_dir in CATEGORY_DOWNLOADERS:
        output_path = repo_root / output_dir
        if args.clean_output and not args.dry_run:
            clean_output_csvs(output_path)

        command = [sys.executable, script, *shared_args]
        print(f"\n=== {category}: {' '.join(command)} ===", file=sys.stderr, flush=True)
        result = subprocess.run(command, cwd=repo_root, check=False)
        count = None if args.dry_run else count_successful_manifest_rows(output_path)
        if count is not None:
            print(f"{category}: {count} successful market CSVs recorded in {output_dir}", file=sys.stderr)

        if result.returncode != 0:
            failures.append((category, result.returncode))
            if args.stop_on_category_error:
                break

    if failures:
        print("\nCompleted with category errors:", file=sys.stderr)
        for category, return_code in failures:
            print(f"- {category}: exit code {return_code}", file=sys.stderr)
        return 1

    print("\nAll configured category downloaders completed.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
