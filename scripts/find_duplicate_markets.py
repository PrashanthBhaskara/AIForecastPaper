"""Scan all Research/*/markets.csv files and report markets that appear in more than one CSV.

Markets are keyed on condition_id (Polymarket's unique identifier). Titles are also checked
as a soft signal for near-duplicates that don't share a condition_id.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

RESEARCH_DIR = Path(__file__).resolve().parent.parent / "Research"


def collect(key_field: str) -> dict[str, list[tuple[Path, str, str]]]:
    buckets: dict[str, list[tuple[Path, str, str]]] = defaultdict(list)
    for csv_path in sorted(RESEARCH_DIR.glob("*/markets.csv")):
        with csv_path.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            if key_field not in (reader.fieldnames or ()):
                continue
            for row in reader:
                key = (row.get(key_field) or "").strip()
                if not key:
                    continue
                buckets[key].append((csv_path, row.get("title", ""), row.get("category", "")))
    return buckets


def report(label: str, buckets: dict[str, list[tuple[Path, str, str]]]) -> int:
    cross_file_dupes = {
        k: v for k, v in buckets.items()
        if len({p for p, _, _ in v}) > 1
    }
    same_file_dupes = {
        k: v for k, v in buckets.items()
        if k not in cross_file_dupes and len(v) > 1
    }

    print(f"\n=== {label} ===")
    print(f"unique keys: {len(buckets)}")
    print(f"cross-file duplicates: {len(cross_file_dupes)}")
    print(f"within-file duplicates: {len(same_file_dupes)}")

    for key, rows in sorted(cross_file_dupes.items()):
        print(f"\n  [cross-file] {key}")
        for path, title, category in rows:
            rel = path.relative_to(RESEARCH_DIR.parent)
            print(f"    - {rel}  category={category}  title={title!r}")

    for key, rows in sorted(same_file_dupes.items()):
        path = rows[0][0].relative_to(RESEARCH_DIR.parent)
        print(f"\n  [within-file x{len(rows)}] {key}  ({path})")
        for _, title, category in rows:
            print(f"    - category={category}  title={title!r}")

    return len(cross_file_dupes) + len(same_file_dupes)


def report_titles(label: str) -> None:
    titles: dict[str, list[tuple[Path, str]]] = defaultdict(list)
    for csv_path in sorted(RESEARCH_DIR.glob("*/markets.csv")):
        with csv_path.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                t = (row.get("title") or "").strip().lower()
                if t:
                    titles[t].append((csv_path, row.get("category", "")))
    dupes = {t: rows for t, rows in titles.items() if len({p for p, _ in rows}) > 1}
    print(f"\n=== {label} — cross-file duplicate titles: {len(dupes)} ===")
    for title, rows in sorted(dupes.items()):
        print(f"\n  {title!r}")
        for path, category in rows:
            rel = path.relative_to(RESEARCH_DIR.parent)
            print(f"    - {rel}  category={category}")


def main() -> None:
    buckets = collect("condition_id")
    total = report("Polymarket (by condition_id)", buckets)
    report_titles("Polymarket")
    print(f"\nTotal duplicate keys: {total}")


if __name__ == "__main__":
    main()
