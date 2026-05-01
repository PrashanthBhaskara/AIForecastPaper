#!/usr/bin/env python3
"""Run Gemini recall across multiple market categories.

This wrapper avoids hand-editing ``DEFAULT_INPUT`` / ``DEFAULT_OUTPUT`` inside
``Research/gemini_recall.py``. It computes per-category paths and invokes the
existing single-category script with explicit flags.

Typical usage:
    ./venv/bin/python Research/run_gemini_batch.py
    ./venv/bin/python Research/run_gemini_batch.py --dry-run
    ./venv/bin/python Research/run_gemini_batch.py --exclude PoliticsMarkets
    ./venv/bin/python Research/run_gemini_batch.py --only ClimateMarkets,CommoditiesMarkets
"""

from __future__ import annotations

import argparse
import configparser
import os
import re
import subprocess
import sys
from pathlib import Path


BASE_DIR = Path(__file__).parent
REPO_ROOT = BASE_DIR.parent
CONFIG_PATH = BASE_DIR / "recall_config.txt"
GEMINI_SCRIPT = BASE_DIR / "gemini_recall.py"

_cfg = configparser.ConfigParser(interpolation=None)
_cfg.read(CONFIG_PATH, encoding="utf-8")

DEFAULT_MODEL = _cfg.get(
    "models",
    "gemini_model",
    fallback=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
)


def parse_category_list(raw_value: str) -> set[str]:
    return {part.strip() for part in raw_value.split(",") if part.strip()}


def sanitize_model_for_filename(model: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", model).strip("-")


def discover_categories(input_filename: str) -> list[Path]:
    categories: list[Path] = []
    for path in sorted(BASE_DIR.glob("*Markets")):
        if path.is_dir() and (path / input_filename).exists():
            categories.append(path)
    return categories


def category_limit(category_name: str, climate_limit: int, default_limit: int) -> int:
    if category_name == "ClimateMarkets":
        return climate_limit
    return default_limit


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Gemini recall across market categories.")
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Gemini model to pass through. Default: {DEFAULT_MODEL}",
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help=f"Python interpreter used to launch gemini_recall.py. Default: {sys.executable}",
    )
    parser.add_argument(
        "--input-filename",
        default="markets.csv",
        help="Input CSV filename expected inside each category folder. Default: markets.csv",
    )
    parser.add_argument(
        "--limit-default",
        type=int,
        default=150,
        help="Per-category limit for non-climate folders. Default: 150",
    )
    parser.add_argument(
        "--limit-climate",
        type=int,
        default=100,
        help="Per-category limit for ClimateMarkets. Default: 100",
    )
    parser.add_argument(
        "--only",
        default="",
        help="Comma-separated category names to run exclusively.",
    )
    parser.add_argument(
        "--exclude",
        default="",
        help="Comma-separated category names to skip.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the commands that would run without launching gemini_recall.py.",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Keep going if one category exits non-zero.",
    )
    parser.add_argument(
        "--sleep-between-calls",
        type=float,
        default=None,
        help="Override gemini_recall.py --sleep-between-calls.",
    )
    parser.add_argument(
        "--max-output-tokens",
        type=int,
        default=None,
        help="Override gemini_recall.py --max-output-tokens.",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=None,
        help="Override gemini_recall.py --temperature.",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=None,
        help="Override gemini_recall.py --max-retries.",
    )
    return parser


def validate_args(args: argparse.Namespace) -> None:
    if args.limit_default <= 0:
        raise SystemExit("--limit-default must be positive")
    if args.limit_climate <= 0:
        raise SystemExit("--limit-climate must be positive")
    if args.max_output_tokens is not None and args.max_output_tokens <= 0:
        raise SystemExit("--max-output-tokens must be positive")
    if args.max_retries is not None and args.max_retries < 0:
        raise SystemExit("--max-retries must be zero or positive")
    if args.sleep_between_calls is not None and args.sleep_between_calls < 0:
        raise SystemExit("--sleep-between-calls must be zero or positive")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    validate_args(args)

    only = parse_category_list(args.only)
    exclude = parse_category_list(args.exclude)

    categories = discover_categories(args.input_filename)
    if only:
        categories = [path for path in categories if path.name in only]
    if exclude:
        categories = [path for path in categories if path.name not in exclude]

    if not categories:
        raise SystemExit("No category folders matched the requested filters.")

    model_slug = sanitize_model_for_filename(args.model)
    failures: list[tuple[str, int]] = []

    print(f"Gemini script: {GEMINI_SCRIPT}")
    print(f"Model:         {args.model}")
    print(f"Categories:    {len(categories)}")
    print(f"Mode:          {'dry-run' if args.dry_run else 'live'}\n")

    for category_dir in categories:
        limit = category_limit(category_dir.name, args.limit_climate, args.limit_default)
        input_path = category_dir / args.input_filename
        output_path = category_dir / "recall" / f"{model_slug}_recall.json"

        cmd = [
            args.python,
            str(GEMINI_SCRIPT),
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--limit",
            str(limit),
            "--model",
            args.model,
        ]

        if args.sleep_between_calls is not None:
            cmd.extend(["--sleep-between-calls", str(args.sleep_between_calls)])
        if args.max_output_tokens is not None:
            cmd.extend(["--max-output-tokens", str(args.max_output_tokens)])
        if args.temperature is not None:
            cmd.extend(["--temperature", str(args.temperature)])
        if args.max_retries is not None:
            cmd.extend(["--max-retries", str(args.max_retries)])
        if args.dry_run:
            cmd.append("--dry-run")

        print(f"[{category_dir.name}] limit={limit}")
        print("  " + " ".join(cmd))

        if args.dry_run:
            continue

        result = subprocess.run(cmd, cwd=REPO_ROOT)
        if result.returncode != 0:
            failures.append((category_dir.name, result.returncode))
            print(f"  FAILED: exit code {result.returncode}\n")
            if not args.continue_on_error:
                break
        else:
            print("  OK\n")

    if args.dry_run:
        return

    if failures:
        print("Failures:")
        for category_name, returncode in failures:
            print(f"  {category_name}: exit code {returncode}")
        raise SystemExit(1)

    print("All requested categories completed successfully.")


if __name__ == "__main__":
    main()
