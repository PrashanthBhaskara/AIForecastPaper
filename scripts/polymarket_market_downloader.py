#!/usr/bin/env python3
"""Download resolved Polymarket market metadata to CSV via the Dome API.

This module is the Polymarket/Dome port of the Kalshi downloader. The
category-specific wrappers in this directory call into :func:`main` with the
tag filter(s) and output directory that correspond to each research category.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


DEFAULT_BASE_URL = "https://api.domeapi.io/v1"
DEFAULT_CATEGORY = "Climate and Weather"
DEFAULT_TAGS = ("Weather",)
DEFAULT_START_DATE = "2024-02-01"
DEFAULT_END_DATE = "2024-09-01"
DEFAULT_OUTPUT_DIR = "Research/ClimateMarkets"
DEFAULT_PAGE_LIMIT = 100
DEFAULT_MAX_PAGES = 200

MARKET_COLUMNS = [
    "category",
    "market_slug",
    "event_slug",
    "condition_id",
    "title",
    "resolution",
    "status",
    "open_time",
    "close_time",
    "settlement_ts",
    "volume",
]


def load_env_api_key() -> str | None:
    """Read DOME_API_KEY from the environment or from a .env file at the repo root."""

    key = os.environ.get("DOME_API_KEY")
    if key:
        return key.strip()

    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return None
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        if name.strip() == "DOME_API_KEY":
            return value.strip().strip('"').strip("'")
    return None


@dataclass
class DomeClient:
    api_key: str
    base_url: str = DEFAULT_BASE_URL
    request_sleep: float = 0.1
    timeout: int = 60
    max_retries: int = 5
    _last_request_at: float = field(default=0.0, init=False, repr=False)

    def get(self, path: str, params: list[tuple[str, Any]] | None = None) -> dict[str, Any]:
        pairs = [(k, v) for k, v in (params or []) if v not in (None, "")]
        query = urllib.parse.urlencode(pairs, doseq=True)
        url = f"{self.base_url.rstrip('/')}{path}"
        if query:
            url = f"{url}?{query}"

        for attempt in range(self.max_retries + 1):
            self._pace()
            request = urllib.request.Request(
                url,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "AIForecastPaper-PolymarketMarketMetadataDownloader/1.0",
                    "x-api-key": self.api_key,
                },
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    payload = response.read().decode("utf-8")
                return json.loads(payload)
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                if exc.code in {429, 500, 502, 503, 504} and attempt < self.max_retries:
                    retry_after = exc.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after else min(2**attempt, 30)
                    time.sleep(delay)
                    continue
                raise RuntimeError(f"GET {url} failed with HTTP {exc.code}: {body}") from exc
            except (urllib.error.URLError, TimeoutError) as exc:
                if attempt < self.max_retries:
                    time.sleep(min(2**attempt, 30))
                    continue
                raise RuntimeError(f"GET {url} failed: {exc}") from exc

        raise RuntimeError(f"GET {url} failed after retries")

    def _pace(self) -> None:
        if self.request_sleep <= 0:
            return
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.request_sleep:
            time.sleep(self.request_sleep - elapsed)
        self._last_request_at = time.monotonic()


def parse_utc_datetime(value: str) -> datetime:
    if not value:
        raise ValueError("empty datetime value")
    normalized = value.strip()
    if len(normalized) == 10 and normalized[4] == "-" and normalized[7] == "-":
        normalized = f"{normalized}T00:00:00+00:00"
    elif normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"

    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def unix_seconds(dt: datetime) -> int:
    return int(dt.astimezone(timezone.utc).timestamp())


def unix_to_iso(value: Any) -> str:
    if value in (None, ""):
        return ""
    try:
        ts = int(value)
    except (TypeError, ValueError):
        return ""
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def parse_numeric(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        parsed = float(str(value).replace(",", ""))
    except ValueError:
        return None
    return parsed if math.isfinite(parsed) else None


def format_number(value: float | int) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return f"{value:g}"


def market_volume(market: dict[str, Any]) -> float | None:
    for key in ("volume_total", "volume_1_year", "volume_1_month", "volume_1_week"):
        parsed = parse_numeric(market.get(key))
        if parsed is not None:
            return parsed
    return None


def market_passes_volume_filter(market: dict[str, Any], min_volume: float | None) -> bool:
    if min_volume is None:
        return True
    volume = market_volume(market)
    return volume is not None and volume >= min_volume


def winning_side_label(market: dict[str, Any]) -> str:
    winning_side = market.get("winning_side")
    if winning_side in (None, ""):
        return ""
    if isinstance(winning_side, dict):
        label = winning_side.get("label")
        if label:
            return str(label)
        identifier = str(winning_side.get("id") or "")
        for side_key in ("side_a", "side_b"):
            side = market.get(side_key) or {}
            if str(side.get("id") or "") == identifier and side.get("label"):
                return str(side["label"])
        return identifier
    winning_str = str(winning_side).lower()
    for side_key, alias in (("side_a", "a"), ("side_b", "b")):
        side = market.get(side_key) or {}
        if winning_str in {alias, str(side.get("id") or "").lower(), str(side.get("label") or "").lower()}:
            label = side.get("label")
            if label:
                return str(label)
    return str(winning_side)


def is_resolved(market: dict[str, Any]) -> bool:
    status = str(market.get("status") or "").lower()
    if status != "closed":
        return False
    return bool(winning_side_label(market))


def market_close_unix(market: dict[str, Any]) -> int | None:
    for key in ("close_time", "completed_time", "end_time"):
        value = market.get(key)
        if value in (None, ""):
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def market_closes_in_window(market: dict[str, Any], start: datetime, end: datetime) -> bool:
    close_unix = market_close_unix(market)
    if close_unix is None:
        return False
    return unix_seconds(start) <= close_unix < unix_seconds(end)


def iter_paginated_markets(
    client: DomeClient,
    params: list[tuple[str, Any]],
    max_pages: int,
) -> Iterable[list[dict[str, Any]]]:
    pagination_key = ""
    for page_index in range(max_pages):
        page_params = list(params)
        if pagination_key:
            page_params.append(("pagination_key", pagination_key))
        data = client.get("/polymarket/markets", page_params)
        yield data.get("markets") or []
        pagination = data.get("pagination") or {}
        if not pagination.get("has_more"):
            return
        pagination_key = pagination.get("pagination_key") or ""
        if not pagination_key:
            return
    print(
        f"Stopped pagination after {max_pages} pages (increase --max-pages to scan deeper)",
        file=sys.stderr,
    )


def annotate_market(market: dict[str, Any], category: str, tags: tuple[str, ...]) -> dict[str, Any]:
    annotated = dict(market)
    annotated["_category"] = category
    annotated["_source_tags"] = ",".join(tags)
    return annotated


def title_is_excluded(market: dict[str, Any], exclude_keywords: tuple[str, ...]) -> bool:
    if not exclude_keywords:
        return False
    title = str(market.get("title") or "").lower()
    return any(keyword in title for keyword in exclude_keywords)


def load_sibling_market_keys(research_root: Path, skip: Path) -> set[str]:
    """Collect condition_id and market_slug values from every Research/*/markets.csv
    except the file at ``skip`` (typically the current run's output). Used so one
    market is never counted in more than one category."""

    keys: set[str] = set()
    if not research_root.exists():
        return keys
    skip_resolved = skip.resolve() if skip.exists() else skip
    for csv_path in sorted(research_root.glob("*/markets.csv")):
        if csv_path.resolve() == skip_resolved:
            continue
        try:
            with csv_path.open(newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    for field in ("condition_id", "market_slug"):
                        value = (row.get(field) or "").strip()
                        if value:
                            keys.add(value)
        except OSError:
            continue
    return keys


def market_matches_keys(market: dict[str, Any], keys: set[str]) -> bool:
    if not keys:
        return False
    for field in ("condition_id", "market_slug"):
        value = str(market.get(field) or "").strip()
        if value and value in keys:
            return True
    return False


def discover_markets(
    client: DomeClient,
    category: str,
    tags: tuple[str, ...],
    start: datetime,
    end: datetime,
    max_markets: int | None,
    min_volume: float | None,
    page_limit: int,
    max_pages: int,
    search: str | None,
    exclude_keywords: tuple[str, ...] = (),
    exclude_identifiers: set[str] | None = None,
) -> list[dict[str, Any]]:
    params: list[tuple[str, Any]] = [
        ("limit", page_limit),
        ("status", "closed"),
        ("start_time", unix_seconds(start)),
        ("end_time", unix_seconds(end)),
    ]
    for tag in tags:
        params.append(("tags", tag))
    if min_volume is not None:
        params.append(("min_volume", min_volume))
    if search:
        params.append(("search", search))

    markets: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    scanned = 0
    in_window_page = False

    for page in iter_paginated_markets(client, params, max_pages):
        if not page:
            break
        in_window_page = False
        for market in page:
            scanned += 1
            if not is_resolved(market):
                continue
            if not market_closes_in_window(market, start, end):
                continue
            if not market_passes_volume_filter(market, min_volume):
                continue
            if title_is_excluded(market, exclude_keywords):
                continue
            if exclude_identifiers and market_matches_keys(market, exclude_identifiers):
                continue
            identifier = market.get("condition_id") or market.get("market_slug")
            if not identifier or identifier in seen_ids:
                continue
            seen_ids.add(identifier)
            markets.append(annotate_market(market, category, tags))
            in_window_page = True
            if max_markets is not None and len(markets) >= max_markets:
                return markets
        print(
            f"  scanned={scanned} matched={len(markets)} (window hits this page: "
            f"{'yes' if in_window_page else 'no'})",
            file=sys.stderr,
            flush=True,
        )

    return markets


def market_row(category: str, market: dict[str, Any]) -> dict[str, Any]:
    volume = market_volume(market)
    return {
        "category": category,
        "market_slug": market.get("market_slug", ""),
        "event_slug": market.get("event_slug") or "",
        "condition_id": market.get("condition_id", ""),
        "title": market.get("title", ""),
        "resolution": winning_side_label(market),
        "status": market.get("status", ""),
        "open_time": unix_to_iso(market.get("start_time")),
        "close_time": unix_to_iso(market.get("end_time")),
        "settlement_ts": unix_to_iso(market.get("completed_time") or market.get("close_time")),
        "volume": "" if volume is None else format_number(volume),
    }


def write_markets_csv(output_dir: Path, category: str, markets: list[dict[str, Any]]) -> Path:
    csv_path = output_dir / "markets.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=MARKET_COLUMNS)
        writer.writeheader()
        for market in markets:
            writer.writerow(market_row(category, market))
    return csv_path


def parse_tag_arguments(values: list[str], defaults: tuple[str, ...]) -> tuple[str, ...]:
    if not values:
        return defaults
    tags: list[str] = []
    for value in values:
        for item in value.split(","):
            item = item.strip()
            if item:
                tags.append(item)
    return tuple(tags)


def build_parser(
    default_category: str = DEFAULT_CATEGORY,
    default_tags: tuple[str, ...] = DEFAULT_TAGS,
    default_output_dir: str = DEFAULT_OUTPUT_DIR,
    default_start_date: str = DEFAULT_START_DATE,
    default_end_date: str = DEFAULT_END_DATE,
    default_exclude_keywords: tuple[str, ...] = (),
) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=f"Download Polymarket {default_category} market metadata via the Dome API.",
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--category", default=default_category)
    parser.add_argument(
        "--tag",
        action="append",
        default=[],
        help=(
            "Polymarket tag(s) to filter on. Can be repeated or comma-separated. "
            f"Defaults to: {', '.join(default_tags)}"
        ),
    )
    parser.add_argument("--start-date", default=default_start_date)
    parser.add_argument("--end-date", default=default_end_date)
    parser.add_argument("--output-dir", default=default_output_dir)
    parser.add_argument(
        "--max-markets",
        type=int,
        default=None,
        help="Maximum market rows to write.",
    )
    parser.add_argument(
        "--min-volume",
        type=float,
        default=None,
        help="Only include markets whose total USD volume is at least this value.",
    )
    parser.add_argument(
        "--search",
        default=None,
        help="Optional fuzzy search across market titles/descriptions (overrides tag filter).",
    )
    parser.add_argument(
        "--exclude-keyword",
        action="append",
        default=[],
        help=(
            "Case-insensitive substring to exclude from market titles. Can be repeated "
            "or comma-separated. "
            + (
                f"Defaults to: {', '.join(default_exclude_keywords)}"
                if default_exclude_keywords
                else "No defaults."
            )
        ),
    )
    parser.add_argument("--request-sleep", type=float, default=0.1)
    parser.add_argument("--page-limit", type=int, default=DEFAULT_PAGE_LIMIT)
    parser.add_argument(
        "--max-pages",
        type=int,
        default=DEFAULT_MAX_PAGES,
        help="Maximum pages to scan per run. Default: 200.",
    )
    parser.add_argument("--dry-run", action="store_true")
    # Accepted-but-ignored flags kept for master.py compatibility with the
    # previous Kalshi-era interface.
    parser.add_argument("--series-limit", type=int, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--max-markets-per-series", type=int, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--full-history-scan", action="store_true", help=argparse.SUPPRESS)
    return parser


def main(
    default_category: str = DEFAULT_CATEGORY,
    default_tags: tuple[str, ...] = DEFAULT_TAGS,
    default_output_dir: str = DEFAULT_OUTPUT_DIR,
    default_start_date: str = DEFAULT_START_DATE,
    default_end_date: str = DEFAULT_END_DATE,
    default_exclude_keywords: tuple[str, ...] = (),
) -> int:
    args = build_parser(
        default_category=default_category,
        default_tags=default_tags,
        default_output_dir=default_output_dir,
        default_start_date=default_start_date,
        default_end_date=default_end_date,
        default_exclude_keywords=default_exclude_keywords,
    ).parse_args()
    start = parse_utc_datetime(args.start_date)
    end = parse_utc_datetime(args.end_date)
    if end <= start:
        raise SystemExit("--end-date must be after --start-date")
    if args.max_markets is not None and args.max_markets < 0:
        raise SystemExit("--max-markets must be zero or positive")
    if args.min_volume is not None and (not math.isfinite(args.min_volume) or args.min_volume < 0):
        raise SystemExit("--min-volume must be a finite number greater than or equal to zero")
    if not 1 <= args.page_limit <= 100:
        raise SystemExit("--page-limit must be between 1 and 100")
    if args.max_pages < 1:
        raise SystemExit("--max-pages must be at least 1")

    api_key = load_env_api_key()
    if not api_key:
        raise SystemExit("DOME_API_KEY not found in environment or .env file")

    tags = parse_tag_arguments(args.tag, default_tags)
    exclude_keywords = tuple(
        kw.lower()
        for kw in parse_tag_arguments(args.exclude_keyword, default_exclude_keywords)
    )
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    target_csv = output_dir / "markets.csv"
    sibling_keys = load_sibling_market_keys(output_dir.parent, skip=target_csv)
    if sibling_keys:
        print(
            f"Excluding {len(sibling_keys)} identifiers already recorded in sibling "
            f"{output_dir.parent}/*/markets.csv files",
            file=sys.stderr,
        )

    client = DomeClient(
        api_key=api_key,
        base_url=args.base_url,
        request_sleep=args.request_sleep,
    )
    print(
        f"Fetching resolved Polymarket markets with tags={list(tags)} "
        f"from {start.isoformat()} to {end.isoformat()}",
        file=sys.stderr,
    )

    markets = discover_markets(
        client=client,
        category=args.category,
        tags=tags,
        start=start,
        end=end,
        max_markets=args.max_markets,
        min_volume=args.min_volume,
        page_limit=args.page_limit,
        max_pages=args.max_pages,
        search=args.search,
        exclude_keywords=exclude_keywords,
        exclude_identifiers=sibling_keys,
    )

    print(
        f"Selected {len(markets)} resolved markets in {args.category!r} "
        f"from {start.isoformat()} to {end.isoformat()}",
        file=sys.stderr,
    )

    if args.dry_run:
        for market in markets:
            row = market_row(args.category, market)
            print(
                f"{row['market_slug']} {row['event_slug']} {row['close_time']} {row['resolution']}",
                file=sys.stdout,
            )
        return 0

    csv_path = write_markets_csv(output_dir, args.category, markets)
    print(f"Wrote {len(markets)} market rows to {csv_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
