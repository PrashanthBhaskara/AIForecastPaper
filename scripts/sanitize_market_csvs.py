#!/usr/bin/env python3
"""Remove banned market rows from CSVs under Research/."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


DEFAULT_GLOB = "Research/*/*.csv"
BANNED_KEYWORDS = (
    "luigi mangione",
    "manifesto",
    "brian thompson",
    "brian-thompson",
)


def row_text(row: dict[str, str]) -> str:
    return " ".join(str(value) for value in row.values()).lower()


def sanitize_csv(path: Path) -> tuple[int, int]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fieldnames = reader.fieldnames
    if not fieldnames:
        return 0, 0

    kept: list[dict[str, str]] = []
    removed = 0
    for row in rows:
        if any(keyword in row_text(row) for keyword in BANNED_KEYWORDS):
            removed += 1
            continue
        kept.append(row)

    if removed:
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(kept)
    return len(rows), removed


def main() -> int:
    parser = argparse.ArgumentParser(description="Remove banned market rows from research CSVs.")
    parser.add_argument("--glob", default=DEFAULT_GLOB)
    args = parser.parse_args()

    matched = sorted(Path().glob(args.glob))
    if not matched:
        raise SystemExit(f"No CSVs matched {args.glob!r}")

    total_removed = 0
    for path in matched:
        total_rows, removed = sanitize_csv(path)
        total_removed += removed
        if removed:
            print(f"{path}: removed {removed} banned rows out of {total_rows}")

    print(f"total removed rows: {total_removed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
