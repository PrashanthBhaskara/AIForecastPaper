#!/usr/bin/env python3
"""Audit overlap, coverage, and concentration for curated Polymarket CSVs."""

from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

from build_diverse_polymarket_datasets import CATEGORY_CONFIGS, family_key_for_market


PHASE_FILES = {
    "historical": "markets.csv",
    "future": "newmarkets.csv",
}


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def event_key(row: dict[str, str]) -> str:
    return row.get("event_slug") or row.get("market_slug") or row.get("condition_id") or ""


def family_key(row: dict[str, str]) -> str:
    market = {
        "slug": row.get("market_slug") or "",
        "market_slug": row.get("market_slug") or "",
        "question": row.get("title") or "",
        "title": row.get("title") or "",
    }
    return family_key_for_market(market)


def pairwise_overlap(rows_by_category: dict[str, list[dict[str, str]]]) -> list[tuple[str, str, int]]:
    overlaps: list[tuple[str, str, int]] = []
    categories = list(rows_by_category)
    for index, left in enumerate(categories):
        left_ids = {row["condition_id"] for row in rows_by_category[left] if row.get("condition_id")}
        for right in categories[index + 1 :]:
            right_ids = {row["condition_id"] for row in rows_by_category[right] if row.get("condition_id")}
            shared = len(left_ids & right_ids)
            if shared:
                overlaps.append((left, right, shared))
    return sorted(overlaps, key=lambda item: (-item[2], item[0], item[1]))


def global_duplicate_count(rows_by_category: dict[str, list[dict[str, str]]]) -> int:
    seen: dict[str, str] = {}
    duplicates = 0
    for category, rows in rows_by_category.items():
        for row in rows:
            key = row.get("condition_id")
            if not key:
                continue
            prior = seen.get(key)
            if prior is not None and prior != category:
                duplicates += 1
            seen[key] = category
    return duplicates


def date_span(rows: Iterable[dict[str, str]]) -> tuple[str, str]:
    values = sorted(row["close_time"] for row in rows if row.get("close_time"))
    if not values:
        return ("", "")
    return values[0], values[-1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit curated Polymarket datasets.")
    parser.add_argument("--phase", action="append", default=[], help="Optional phase filter: historical,future")
    parser.add_argument("--target-count", type=int, default=300)
    return parser


def normalize_phases(values: list[str]) -> list[str]:
    if not values:
        return list(PHASE_FILES)
    phases: list[str] = []
    for value in values:
        for item in value.split(","):
            phase = item.strip().lower()
            if phase not in PHASE_FILES:
                valid = ", ".join(sorted(PHASE_FILES))
                raise SystemExit(f"unknown phase {item!r}; valid values: {valid}")
            if phase not in phases:
                phases.append(phase)
    return phases


def main() -> int:
    args = build_parser().parse_args()
    phases = normalize_phases(args.phase)
    root = repo_root()

    for phase in phases:
        filename = PHASE_FILES[phase]
        print(f"\n## {phase}")
        rows_by_category: dict[str, list[dict[str, str]]] = {}
        for config in CATEGORY_CONFIGS:
            path = root / config.output_dir / filename
            rows = read_rows(path)
            rows_by_category[config.category] = rows

            events = Counter(event_key(row) for row in rows if event_key(row))
            families = Counter(family_key(row) for row in rows if row.get("condition_id"))
            start, end = date_span(rows)
            top_family, top_family_count = ("", 0)
            if families:
                top_family, top_family_count = families.most_common(1)[0]
            family_share = (top_family_count / len(rows)) if rows else 0.0
            status_bits: list[str] = []
            if len(rows) < args.target_count:
                status_bits.append(f"UNDER target ({len(rows)}/{args.target_count})")
            if family_share >= 0.12:
                status_bits.append(f"top family concentration {family_share:.0%}")
            status = "; ".join(status_bits) if status_bits else "ok"
            print(
                f"- {config.category}: rows={len(rows)} unique_events={len(events)} "
                f"date_span={start or 'n/a'}..{end or 'n/a'} "
                f"top_family={top_family or 'n/a'}:{top_family_count} status={status}"
            )

        duplicate_count = global_duplicate_count(rows_by_category)
        print(f"global duplicate ids: {duplicate_count}")
        overlaps = pairwise_overlap(rows_by_category)
        if overlaps:
            print("pairwise overlaps:")
            for left, right, count in overlaps[:15]:
                print(f"- {left} <-> {right}: {count}")
        else:
            print("pairwise overlaps: none")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
