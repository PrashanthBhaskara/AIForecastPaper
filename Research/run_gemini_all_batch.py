#!/usr/bin/env python3
"""Run Gemini recall first, then Gemini forecasts, across market categories.

Historical recall uses ``markets.csv`` and writes ``recall/<model>_recall.json``.
By default it runs 100 ClimateMarkets rows and 150 rows for every other
category. Future forecasting uses ``newmarkets.csv`` and writes
``forecast/<model>_fc.json`` with a default 150-row cap for every category.

If a child script exits with code 2, that means Gemini returned a 429
RESOURCE_EXHAUSTED error. This runner stops immediately and does not continue to
another category or phase.

Typical usage:
    python3 Research/run_gemini_all_batch.py --dry-run
    python3 Research/run_gemini_all_batch.py --historical-limit 2 --forecast-limit 2 --only PoliticsMarkets
    python3 Research/run_gemini_all_batch.py
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
RECALL_CONFIG_PATH = BASE_DIR / "recall_config.txt"
FC_CONFIG_PATH = BASE_DIR / "fc_config.txt"
GEMINI_RECALL_SCRIPT = BASE_DIR / "gemini_recall.py"
GEMINI_FC_SCRIPT = BASE_DIR / "gemini_fc.py"
RESOURCE_EXHAUSTED_EXIT_CODE = 2
DEFAULT_HISTORICAL_LIMIT_DEFAULT = 150
DEFAULT_HISTORICAL_LIMIT_CLIMATE = 100
DEFAULT_FORECAST_LIMIT = 150

_recall_cfg = configparser.ConfigParser(interpolation=None)
_recall_cfg.read(RECALL_CONFIG_PATH, encoding="utf-8")

_fc_cfg = configparser.ConfigParser(interpolation=None)
_fc_cfg.read(FC_CONFIG_PATH, encoding="utf-8")

DEFAULT_MODEL = _fc_cfg.get(
    "models",
    "gemini_model",
    fallback=_recall_cfg.get(
        "models",
        "gemini_model",
        fallback=os.environ.get("GEMINI_MODEL", "gemini-3-flash-preview"),
    ),
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


def apply_category_filters(categories: list[Path], only: set[str], exclude: set[str]) -> list[Path]:
    if only:
        categories = [path for path in categories if path.name in only]
    if exclude:
        categories = [path for path in categories if path.name not in exclude]
    return categories


def historical_limit_for_category(category_name: str, args: argparse.Namespace) -> int:
    if args.historical_limit is not None:
        return args.historical_limit
    if category_name == "ClimateMarkets":
        return args.historical_limit_climate
    return args.historical_limit_default


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run Gemini historical recall first, then Gemini future forecasts."
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Gemini model to pass through. Default: {DEFAULT_MODEL}",
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help=f"Python interpreter used to launch child scripts. Default: {sys.executable}",
    )
    parser.add_argument(
        "--historical-limit",
        type=int,
        default=None,
        help="Override both historical per-category limits.",
    )
    parser.add_argument(
        "--historical-limit-default",
        type=int,
        default=DEFAULT_HISTORICAL_LIMIT_DEFAULT,
        help=f"Historical recall limit for non-climate categories. Default: {DEFAULT_HISTORICAL_LIMIT_DEFAULT}.",
    )
    parser.add_argument(
        "--historical-limit-climate",
        type=int,
        default=DEFAULT_HISTORICAL_LIMIT_CLIMATE,
        help=f"Historical recall limit for ClimateMarkets. Default: {DEFAULT_HISTORICAL_LIMIT_CLIMATE}.",
    )
    parser.add_argument(
        "--forecast-limit",
        type=int,
        default=DEFAULT_FORECAST_LIMIT,
        help=f"Per-category limit for newmarkets.csv forecasts. Default: {DEFAULT_FORECAST_LIMIT}.",
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
        help="Print the commands that would run without launching child scripts.",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Keep going after non-429 category failures. 429 RESOURCE_EXHAUSTED always stops.",
    )
    parser.add_argument(
        "--sleep-between-calls",
        type=float,
        default=None,
        help="Override child script --sleep-between-calls.",
    )
    parser.add_argument(
        "--max-output-tokens",
        type=int,
        default=None,
        help="Override child script --max-output-tokens.",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=None,
        help="Override child script --temperature.",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=None,
        help="Override child script --max-retries; -1 retries until valid JSON.",
    )
    return parser


def validate_args(args: argparse.Namespace) -> None:
    if args.historical_limit is not None and args.historical_limit < 0:
        raise SystemExit("--historical-limit must be zero or positive")
    if args.historical_limit_default < 0:
        raise SystemExit("--historical-limit-default must be zero or positive")
    if args.historical_limit_climate < 0:
        raise SystemExit("--historical-limit-climate must be zero or positive")
    if args.forecast_limit is not None and args.forecast_limit < 0:
        raise SystemExit("--forecast-limit must be zero or positive")
    if args.max_output_tokens is not None and args.max_output_tokens <= 0:
        raise SystemExit("--max-output-tokens must be positive")
    if args.max_retries is not None and args.max_retries < -1:
        raise SystemExit("--max-retries must be -1, zero, or positive")
    if args.sleep_between_calls is not None and args.sleep_between_calls < 0:
        raise SystemExit("--sleep-between-calls must be zero or positive")


def add_common_child_args(cmd: list[str], args: argparse.Namespace) -> None:
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


def build_phase_command(
    *,
    args: argparse.Namespace,
    script: Path,
    input_path: Path,
    output_path: Path,
    limit: int | None,
) -> list[str]:
    cmd = [
        args.python,
        str(script),
        "--input",
        str(input_path),
        "--output",
        str(output_path),
        "--model",
        args.model,
    ]
    if limit is not None:
        cmd.extend(["--limit", str(limit)])
    add_common_child_args(cmd, args)
    return cmd


def run_phase(
    *,
    args: argparse.Namespace,
    label: str,
    script: Path,
    categories: list[Path],
    input_filename: str,
    output_subdir: str,
    output_suffix: str,
    limit_label: str,
    category_limit_kind: str,
    model_slug: str,
) -> list[tuple[str, int]]:
    failures: list[tuple[str, int]] = []

    print(f"\n== {label} ==")
    print(f"Script:     {script}")
    print(f"Categories: {len(categories)}")
    print(f"Limit:      {limit_label}\n")

    for category_dir in categories:
        if category_limit_kind == "historical":
            limit = historical_limit_for_category(category_dir.name, args)
        elif category_limit_kind == "forecast":
            limit = args.forecast_limit
        else:
            raise RuntimeError(f"unknown category_limit_kind: {category_limit_kind}")

        input_path = category_dir / input_filename
        output_path = category_dir / output_subdir / f"{model_slug}{output_suffix}"
        cmd = build_phase_command(
            args=args,
            script=script,
            input_path=input_path,
            output_path=output_path,
            limit=limit,
        )

        print(f"[{category_dir.name}] limit={limit}")
        print("  " + " ".join(cmd))

        if args.dry_run:
            continue

        result = subprocess.run(cmd, cwd=REPO_ROOT)
        if result.returncode == RESOURCE_EXHAUSTED_EXIT_CODE:
            print("  STOPPED: 429 RESOURCE_EXHAUSTED. No row was saved for the failed call.")
            raise SystemExit(RESOURCE_EXHAUSTED_EXIT_CODE)
        if result.returncode != 0:
            failures.append((category_dir.name, result.returncode))
            print(f"  FAILED: exit code {result.returncode}\n")
            if not args.continue_on_error:
                break
        else:
            print("  OK\n")

    return failures


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    validate_args(args)

    only = parse_category_list(args.only)
    exclude = parse_category_list(args.exclude)
    model_slug = sanitize_model_for_filename(args.model)

    historical_categories = apply_category_filters(discover_categories("markets.csv"), only, exclude)
    forecast_categories = apply_category_filters(discover_categories("newmarkets.csv"), only, exclude)

    if not historical_categories:
        raise SystemExit("No historical category folders matched the requested filters.")
    if not forecast_categories:
        raise SystemExit("No forecast category folders matched the requested filters.")

    print(f"Model: {args.model}")
    print(f"Mode:  {'dry-run' if args.dry_run else 'live'}")

    failures: list[tuple[str, str, int]] = []

    historical_failures = run_phase(
        args=args,
        label="Historical recall",
        script=GEMINI_RECALL_SCRIPT,
        categories=historical_categories,
        input_filename="markets.csv",
        output_subdir="recall",
        output_suffix="_recall.json",
        limit_label=(
            str(args.historical_limit)
            if args.historical_limit is not None
            else f"ClimateMarkets={args.historical_limit_climate}, others={args.historical_limit_default}"
        ),
        category_limit_kind="historical",
        model_slug=model_slug,
    )
    failures.extend(("historical", category, code) for category, code in historical_failures)
    if historical_failures and not args.continue_on_error:
        print("Historical phase failed; forecast phase was not started.")
    else:
        forecast_failures = run_phase(
            args=args,
            label="Future forecasts",
            script=GEMINI_FC_SCRIPT,
            categories=forecast_categories,
            input_filename="newmarkets.csv",
            output_subdir="forecast",
            output_suffix="_fc.json",
            limit_label=str(args.forecast_limit),
            category_limit_kind="forecast",
            model_slug=model_slug,
        )
        failures.extend(("forecast", category, code) for category, code in forecast_failures)

    if args.dry_run:
        return

    if failures:
        print("\nFailures:")
        for phase, category_name, returncode in failures:
            print(f"  {phase} {category_name}: exit code {returncode}")
        raise SystemExit(1)

    print("\nHistorical recall and future forecast phases completed successfully.")


if __name__ == "__main__":
    main()
