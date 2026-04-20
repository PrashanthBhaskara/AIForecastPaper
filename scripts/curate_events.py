#!/usr/bin/env python3
"""Curate raw Polymarket market CSVs into a benchmark event table.

This script consolidates category-level market dumps under ``Research/`` into a
single CSV suitable for evaluation experiments. It filters by domain/date,
deduplicates cross-listed markets, labels each event relative to a training
cutoff, and selects a fixed number of events per domain/phase.
"""

from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable


DEFAULT_INPUT_GLOB = "Research/*/markets.csv"
DEFAULT_OUTPUT_PATH = "Research/curated_events.csv"
DEFAULT_DOMAINS = [
    "Economics",
    "Entertainment",
    "Politics",
]
DEFAULT_START_DATE = "2024-01-01"
DEFAULT_END_DATE = "2024-12-31"
DEFAULT_TRAINING_CUTOFF_DATE = "2024-07-01"
DEFAULT_PHASE_I_COUNT = 100
DEFAULT_PHASE_II_COUNT = 50

OUTPUT_COLUMNS = [
    "benchmark_id",
    "phase",
    "domain",
    "market_slug",
    "event_slug",
    "condition_id",
    "title",
    "resolution",
    "status",
    "open_time",
    "close_time",
    "close_date",
    "settlement_ts",
    "volume",
    "source_csv",
]


@dataclass(frozen=True)
class MarketRow:
    category: str
    market_slug: str
    event_slug: str
    condition_id: str
    title: str
    resolution: str
    status: str
    open_time: str
    close_time: str
    settlement_ts: str
    volume: str
    source_csv: str

    @property
    def domain(self) -> str:
        return self.category

    @property
    def close_date(self) -> date:
        return parse_timestamp(self.close_time).date()

    @property
    def numeric_volume(self) -> float:
        if not self.volume:
            return 0.0
        try:
            parsed = float(self.volume.replace(",", ""))
        except ValueError:
            return 0.0
        return parsed if math.isfinite(parsed) else 0.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Curate benchmark events from category-level Polymarket market CSVs.",
    )
    parser.add_argument(
        "--input-glob",
        default=DEFAULT_INPUT_GLOB,
        help=f"Glob of input CSVs. Default: {DEFAULT_INPUT_GLOB}",
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT_PATH,
        help=f"Destination curated CSV path. Default: {DEFAULT_OUTPUT_PATH}",
    )
    parser.add_argument(
        "--domain",
        action="append",
        default=[],
        help=(
            "Domain/category to include. Can be repeated or comma-separated. "
            f"Defaults to: {', '.join(DEFAULT_DOMAINS)}"
        ),
    )
    parser.add_argument(
        "--start-date",
        default=DEFAULT_START_DATE,
        help=f"Inclusive lower bound on close_date (YYYY-MM-DD). Default: {DEFAULT_START_DATE}",
    )
    parser.add_argument(
        "--end-date",
        default=DEFAULT_END_DATE,
        help=f"Inclusive upper bound on close_date (YYYY-MM-DD). Default: {DEFAULT_END_DATE}",
    )
    parser.add_argument(
        "--training-cutoff-date",
        default=DEFAULT_TRAINING_CUTOFF_DATE,
        help=(
            "Events before this date are labeled phase_i; events on or after it are "
            f"phase_ii. Default: {DEFAULT_TRAINING_CUTOFF_DATE}"
        ),
    )
    parser.add_argument(
        "--phase-i-count",
        type=int,
        default=DEFAULT_PHASE_I_COUNT,
        help=f"Target number of pre-cutoff events per domain. Default: {DEFAULT_PHASE_I_COUNT}",
    )
    parser.add_argument(
        "--phase-ii-count",
        type=int,
        default=DEFAULT_PHASE_II_COUNT,
        help=f"Target number of post-cutoff events per domain. Default: {DEFAULT_PHASE_II_COUNT}",
    )
    parser.add_argument(
        "--allow-incomplete-domains",
        action="store_true",
        help="Write partial domain splits instead of failing when a domain lacks enough events.",
    )
    return parser.parse_args()


def parse_date(value: str) -> date:
    return date.fromisoformat(value)


def parse_timestamp(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def requested_domains(values: list[str]) -> list[str]:
    if not values:
        return list(DEFAULT_DOMAINS)
    domains: list[str] = []
    for value in values:
        for item in value.split(","):
            item = item.strip()
            if item:
                domains.append(item)
    return domains


def load_market_rows(input_glob: str) -> list[MarketRow]:
    rows: list[MarketRow] = []
    for csv_path in sorted(Path().glob(input_glob)):
        with csv_path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for raw in reader:
                rows.append(
                    MarketRow(
                        category=raw.get("category", ""),
                        market_slug=raw.get("market_slug", ""),
                        event_slug=raw.get("event_slug", ""),
                        condition_id=raw.get("condition_id", ""),
                        title=raw.get("title", ""),
                        resolution=raw.get("resolution", ""),
                        status=raw.get("status", ""),
                        open_time=raw.get("open_time", ""),
                        close_time=raw.get("close_time", ""),
                        settlement_ts=raw.get("settlement_ts", ""),
                        volume=raw.get("volume", ""),
                        source_csv=str(csv_path),
                    )
                )
    if not rows:
        raise SystemExit(f"No input CSVs matched {input_glob!r}")
    return rows


def filter_rows(
    rows: Iterable[MarketRow],
    domains: set[str],
    start_date: date,
    end_date: date,
) -> list[MarketRow]:
    filtered: list[MarketRow] = []
    for row in rows:
        if row.domain not in domains:
            continue
        close_date = row.close_date
        if close_date < start_date or close_date > end_date:
            continue
        filtered.append(row)
    return filtered


def deduplicate_rows(rows: Iterable[MarketRow]) -> list[MarketRow]:
    best_by_slug: dict[str, MarketRow] = {}
    for row in rows:
        key = row.condition_id or row.market_slug
        if not key:
            continue
        current = best_by_slug.get(key)
        if current is None:
            best_by_slug[key] = row
            continue
        replacement_key = (
            row.numeric_volume,
            row.close_time,
            row.domain,
            row.source_csv,
        )
        current_key = (
            current.numeric_volume,
            current.close_time,
            current.domain,
            current.source_csv,
        )
        if replacement_key > current_key:
            best_by_slug[key] = row
    return list(best_by_slug.values())


def phase_for_row(row: MarketRow, cutoff_date: date) -> str:
    return "phase_i" if row.close_date < cutoff_date else "phase_ii"


def sort_rows(rows: Iterable[MarketRow]) -> list[MarketRow]:
    return sorted(
        rows,
        key=lambda row: (
            -row.numeric_volume,
            row.close_time,
            row.market_slug,
        ),
    )


def select_rows_for_domain(
    rows: Iterable[MarketRow],
    cutoff_date: date,
    phase_i_count: int,
    phase_ii_count: int,
    allow_incomplete_domains: bool,
) -> list[tuple[str, MarketRow]]:
    rows_by_phase: dict[str, list[MarketRow]] = defaultdict(list)
    for row in rows:
        rows_by_phase[phase_for_row(row, cutoff_date)].append(row)

    targets = {
        "phase_i": phase_i_count,
        "phase_ii": phase_ii_count,
    }

    selected: list[tuple[str, MarketRow]] = []
    shortages: list[str] = []
    for phase, target in targets.items():
        ordered = sort_rows(rows_by_phase.get(phase, []))
        chosen = ordered[:target]
        if len(chosen) < target:
            shortages.append(f"{phase}: needed {target}, found {len(chosen)}")
            if not allow_incomplete_domains:
                continue
        selected.extend((phase, row) for row in chosen)

    if shortages and not allow_incomplete_domains:
        raise ValueError("; ".join(shortages))
    return selected


def benchmark_id(domain: str, phase: str, index: int) -> str:
    domain_slug = "".join(ch.lower() if ch.isalnum() else "_" for ch in domain).strip("_")
    while "__" in domain_slug:
        domain_slug = domain_slug.replace("__", "_")
    return f"{domain_slug}_{phase}_{index:03d}"


def write_output(
    output_path: Path,
    domain_order: list[str],
    selected_by_domain: dict[str, list[tuple[str, MarketRow]]],
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        for domain in domain_order:
            phase_counts: dict[str, int] = defaultdict(int)
            ordered_rows = sorted(
                selected_by_domain.get(domain, []),
                key=lambda item: (
                    item[0],
                    -item[1].numeric_volume,
                    item[1].close_time,
                    item[1].market_slug,
                ),
            )
            for phase, row in ordered_rows:
                phase_counts[phase] += 1
                writer.writerow(
                    {
                        "benchmark_id": benchmark_id(domain, phase, phase_counts[phase]),
                        "phase": phase,
                        "domain": domain,
                        "market_slug": row.market_slug,
                        "event_slug": row.event_slug,
                        "condition_id": row.condition_id,
                        "title": row.title,
                        "resolution": row.resolution,
                        "status": row.status,
                        "open_time": row.open_time,
                        "close_time": row.close_time,
                        "close_date": row.close_date.isoformat(),
                        "settlement_ts": row.settlement_ts,
                        "volume": row.volume,
                        "source_csv": row.source_csv,
                    }
                )


def print_summary(domain_order: list[str], selected_by_domain: dict[str, list[tuple[str, MarketRow]]]) -> None:
    for domain in domain_order:
        phase_counts: dict[str, int] = defaultdict(int)
        for phase, _ in selected_by_domain.get(domain, []):
            phase_counts[phase] += 1
        print(
            f"{domain}: phase_i={phase_counts['phase_i']} phase_ii={phase_counts['phase_ii']}",
        )


def main() -> int:
    args = parse_args()
    if args.phase_i_count < 0 or args.phase_ii_count < 0:
        raise SystemExit("phase counts must be zero or positive")

    start_date = parse_date(args.start_date)
    end_date = parse_date(args.end_date)
    cutoff_date = parse_date(args.training_cutoff_date)
    if end_date < start_date:
        raise SystemExit("--end-date must be on or after --start-date")

    domain_order = requested_domains(args.domain)
    domain_set = set(domain_order)

    raw_rows = load_market_rows(args.input_glob)
    filtered_rows = filter_rows(raw_rows, domain_set, start_date, end_date)
    unique_rows = deduplicate_rows(filtered_rows)

    rows_by_domain: dict[str, list[MarketRow]] = defaultdict(list)
    for row in unique_rows:
        rows_by_domain[row.domain].append(row)

    selected_by_domain: dict[str, list[tuple[str, MarketRow]]] = {}
    errors: list[str] = []
    for domain in domain_order:
        try:
            selected_by_domain[domain] = select_rows_for_domain(
                rows=rows_by_domain.get(domain, []),
                cutoff_date=cutoff_date,
                phase_i_count=args.phase_i_count,
                phase_ii_count=args.phase_ii_count,
                allow_incomplete_domains=args.allow_incomplete_domains,
            )
        except ValueError as exc:
            errors.append(f"{domain}: {exc}")

    if errors:
        raise SystemExit(
            "Unable to satisfy requested per-domain counts.\n"
            + "\n".join(errors)
            + "\nUse --allow-incomplete-domains to write the available subset."
        )

    output_path = Path(args.output)
    write_output(output_path, domain_order, selected_by_domain)
    print_summary(domain_order, selected_by_domain)
    print(f"Wrote curated benchmark CSV to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
