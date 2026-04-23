#!/usr/bin/env python3
"""Download future-dated Polymarket market metadata into Research/*/newmarkets.csv.

The existing downloader in this repo uses the Dome API with ``status=closed`` and
historical date bounds, which makes it appropriate for resolved pre-2025 pulls.
This script uses Polymarket's public Gamma API to fetch active markets whose
resolution dates fall in the requested future window.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_BASE_URL = "https://gamma-api.polymarket.com"
DEFAULT_START_DATE = "2026-09-01"
DEFAULT_END_DATE = "2030-01-01"
DEFAULT_MARKET_LIMIT = 300
DEFAULT_OUTPUT_FILENAME = "newmarkets.csv"
DEFAULT_PAGE_LIMIT = 100
DEFAULT_MAX_PAGES_PER_TAG = 10

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


@dataclass(frozen=True)
class CategoryConfig:
    key: str
    category: str
    tag_slugs: tuple[str, ...]
    output_dir: str
    start_date: str = DEFAULT_START_DATE
    end_date: str = DEFAULT_END_DATE


CATEGORY_CONFIGS = {
    "climate": CategoryConfig(
        key="climate",
        category="Climate and Weather",
        tag_slugs=("weather", "climate", "global-temp", "global-warming", "hurricane", "hurricanes"),
        output_dir="Research/ClimateMarkets",
    ),
    "elections": CategoryConfig(
        key="elections",
        category="Elections",
        tag_slugs=("elections",),
        output_dir="Research/ElectionsMarkets",
    ),
    "politics": CategoryConfig(
        key="politics",
        category="Politics",
        tag_slugs=("politics",),
        output_dir="Research/PoliticsMarkets",
    ),
    "entertainment": CategoryConfig(
        key="entertainment",
        category="Entertainment",
        tag_slugs=("awards", "movies", "music"),
        output_dir="Research/EntertainmentMarkets",
    ),
    "commodities": CategoryConfig(
        key="commodities",
        category="Commodities",
        tag_slugs=(
            "commodities",
            "gold",
            "oil",
            "gas",
            "crude-oil",
            "commodity-market",
            "energy-market",
            "energy-industry",
            "oil-production",
            "crypto",
        ),
        output_dir="Research/CommoditiesMarkets",
    ),
    "economics": CategoryConfig(
        key="economics",
        category="Economics",
        tag_slugs=(
            "economy",
            "economics",
            "inflation",
            "fed",
            "fed-rates",
            "economic-policy",
            "jerome-powell",
            "jobs",
            "interest-rates",
            "unemployment",
        ),
        output_dir="Research/EconomicsMarkets",
    ),
    "companies": CategoryConfig(
        key="companies",
        category="Companies",
        tag_slugs=("business",),
        output_dir="Research/CompaniesMarkets",
    ),
    "financials": CategoryConfig(
        key="financials",
        category="Financials",
        tag_slugs=("finance",),
        output_dir="Research/FinancialsMarkets",
    ),
    "science_technology": CategoryConfig(
        key="science_technology",
        category="Science and Technology",
        tag_slugs=("science", "tech"),
        output_dir="Research/ScienceTechnologyMarkets",
    ),
}

CATEGORY_NAME_LOOKUP = {
    config.key: config.key for config in CATEGORY_CONFIGS.values()
}
for config in CATEGORY_CONFIGS.values():
    CATEGORY_NAME_LOOKUP[config.category.lower()] = config.key


@dataclass
class GammaClient:
    base_url: str = DEFAULT_BASE_URL
    request_sleep: float = 0.05
    timeout: int = 60
    max_retries: int = 5
    _last_request_at: float = field(default=0.0, init=False, repr=False)

    def get(self, path: str, params: list[tuple[str, Any]] | None = None) -> Any:
        pairs = [(key, value) for key, value in (params or []) if value not in (None, "")]
        query = urllib.parse.urlencode(pairs, doseq=True)
        url = f"{self.base_url.rstrip('/')}{path}"
        if query:
            url = f"{url}?{query}"

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            self._pace()
            request = urllib.request.Request(
                url,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "Mozilla/5.0 AIForecastPaper-FutureMarketDownloader/1.0",
                },
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    payload = response.read().decode("utf-8")
                return json.loads(payload)
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                if exc.code == 404:
                    return None
                if exc.code in {429, 500, 502, 503, 504} and attempt < self.max_retries:
                    retry_after = exc.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after else min(2**attempt, 20)
                    time.sleep(delay)
                    continue
                last_error = RuntimeError(f"GET {url} failed with HTTP {exc.code}: {body}")
                break
            except (urllib.error.URLError, TimeoutError) as exc:
                last_error = RuntimeError(f"GET {url} failed: {exc}")
                if attempt < self.max_retries:
                    time.sleep(min(2**attempt, 20))
                    continue
                break

        if last_error is None:
            last_error = RuntimeError(f"GET {url} failed after retries")
        raise last_error

    def _pace(self) -> None:
        if self.request_sleep <= 0:
            return
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.request_sleep:
            time.sleep(self.request_sleep - elapsed)
        self._last_request_at = time.monotonic()


def parse_utc_datetime(value: str) -> datetime:
    normalized = value.strip()
    if len(normalized) == 10 and normalized[4] == "-" and normalized[7] == "-":
        normalized = f"{normalized}T00:00:00+00:00"
    elif normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def isoformat_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


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
    for key in ("volumeNum", "volumeClob", "volume", "volume1yr", "volume1mo", "volume1wk", "volume24hr"):
        parsed = parse_numeric(market.get(key))
        if parsed is not None:
            return parsed
    return None


def market_end_datetime(market: dict[str, Any]) -> datetime | None:
    value = market.get("endDate")
    if not value:
        return None
    try:
        return parse_utc_datetime(str(value))
    except ValueError:
        return None


def market_in_window(market: dict[str, Any], start: datetime, end: datetime) -> bool:
    market_end = market_end_datetime(market)
    if market_end is None:
        return False
    return start <= market_end < end


def market_key(market: dict[str, Any]) -> str:
    return str(market.get("conditionId") or market.get("slug") or market.get("id") or "")


def market_sort_key(market: dict[str, Any]) -> tuple[float, str, str]:
    volume = market_volume(market) or 0.0
    close_time = market.get("endDate") or ""
    slug = market.get("slug") or ""
    return (-volume, close_time, slug)


def normalize_status(market: dict[str, Any]) -> str:
    if market.get("closed"):
        return "closed"
    if market.get("active"):
        return "open"
    return "inactive"


def settlement_timestamp(market: dict[str, Any]) -> str:
    for key in ("closedTime", "resolvedAt"):
        value = market.get(key)
        if value:
            return str(value)
    return ""


def event_slug(market: dict[str, Any]) -> str:
    events = market.get("events") or []
    if events and isinstance(events[0], dict):
        slug = events[0].get("slug")
        if slug:
            return str(slug)
    value = market.get("eventSlug")
    return "" if value in (None, "") else str(value)


def annotate_market(market: dict[str, Any], category: str, source_tag_slug: str) -> dict[str, Any]:
    annotated = dict(market)
    annotated["_category"] = category
    annotated["_source_tag_slug"] = source_tag_slug
    return annotated


def fetch_tag(client: GammaClient, slug: str) -> dict[str, Any] | None:
    payload = client.get(f"/tags/slug/{urllib.parse.quote(slug, safe='')}")
    if not isinstance(payload, dict):
        return None
    return payload


def discover_markets(
    client: GammaClient,
    config: CategoryConfig,
    start: datetime,
    end: datetime,
    max_markets: int,
    page_limit: int,
    max_pages_per_tag: int,
    related_tags: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    seen_by_key: dict[str, dict[str, Any]] = {}
    resolved_tags: list[dict[str, Any]] = []

    for tag_slug in config.tag_slugs:
        tag = fetch_tag(client, tag_slug)
        if tag is None:
            print(f"  tag slug {tag_slug!r} not found; skipping", file=sys.stderr)
            continue
        resolved_tags.append(tag)
        tag_id = tag.get("id")
        print(
            f"  scanning tag={tag.get('label')!r} slug={tag_slug!r} id={tag_id}",
            file=sys.stderr,
            flush=True,
        )

        for page_index in range(max_pages_per_tag):
            params: list[tuple[str, Any]] = [
                ("limit", page_limit),
                ("offset", page_index * page_limit),
                ("order", "volume"),
                ("ascending", "false"),
                ("active", "true"),
                ("closed", "false"),
                ("tag_id", tag_id),
                ("related_tags", "true" if related_tags else "false"),
                ("end_date_min", isoformat_z(start)),
                ("end_date_max", isoformat_z(end)),
            ]
            payload = client.get("/markets", params)
            if not isinstance(payload, list) or not payload:
                break

            page_new = 0
            for market in payload:
                if not isinstance(market, dict):
                    continue
                if not market_in_window(market, start, end):
                    continue
                key = market_key(market)
                if not key or key in seen_by_key:
                    continue
                seen_by_key[key] = annotate_market(market, config.category, tag_slug)
                page_new += 1

            print(
                f"    page={page_index + 1} rows={len(payload)} new_unique={page_new} total_unique={len(seen_by_key)}",
                file=sys.stderr,
                flush=True,
            )
            if len(payload) < page_limit:
                break

    ordered = sorted(seen_by_key.values(), key=market_sort_key)
    return ordered[:max_markets], resolved_tags


def market_row(category: str, market: dict[str, Any]) -> dict[str, Any]:
    volume = market_volume(market)
    return {
        "category": category,
        "market_slug": str(market.get("slug") or ""),
        "event_slug": event_slug(market),
        "condition_id": str(market.get("conditionId") or ""),
        "title": str(market.get("question") or market.get("title") or ""),
        "resolution": "",
        "status": normalize_status(market),
        "open_time": str(market.get("startDate") or market.get("createdAt") or ""),
        "close_time": str(market.get("endDate") or ""),
        "settlement_ts": settlement_timestamp(market),
        "volume": "" if volume is None else format_number(volume),
    }


def write_markets_csv(
    repo_root: Path,
    config: CategoryConfig,
    output_filename: str,
    markets: list[dict[str, Any]],
) -> Path:
    output_dir = repo_root / config.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / output_filename
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=MARKET_COLUMNS)
        writer.writeheader()
        for market in markets:
            writer.writerow(market_row(config.category, market))
    return csv_path


def normalize_category_selection(values: list[str] | None) -> list[CategoryConfig]:
    if not values:
        return list(CATEGORY_CONFIGS.values())

    selected_keys: list[str] = []
    for value in values:
        for item in value.split(","):
            key = CATEGORY_NAME_LOOKUP.get(item.strip().lower())
            if key is None:
                valid = ", ".join(sorted(CATEGORY_NAME_LOOKUP))
                raise SystemExit(f"unknown category {item!r}; valid values include: {valid}")
            if key not in selected_keys:
                selected_keys.append(key)
    return [CATEGORY_CONFIGS[key] for key in selected_keys]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download future-dated Polymarket market metadata into Research/*/newmarkets.csv.",
    )
    parser.add_argument(
        "--category",
        action="append",
        default=[],
        help=(
            "Category key or exact category label. Can be repeated or comma-separated. "
            f"Defaults to all categories: {', '.join(CATEGORY_CONFIGS)}"
        ),
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--start-date", default=None, help="Optional global start-date override.")
    parser.add_argument("--end-date", default=None, help="Optional global end-date override.")
    parser.add_argument("--max-markets", type=int, default=DEFAULT_MARKET_LIMIT)
    parser.add_argument("--output-filename", default=DEFAULT_OUTPUT_FILENAME)
    parser.add_argument("--request-sleep", type=float, default=0.05)
    parser.add_argument("--page-limit", type=int, default=DEFAULT_PAGE_LIMIT)
    parser.add_argument("--max-pages-per-tag", type=int, default=DEFAULT_MAX_PAGES_PER_TAG)
    parser.add_argument(
        "--no-related-tags",
        action="store_true",
        help="Disable Gamma's related tag expansion.",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.max_markets <= 0:
        raise SystemExit("--max-markets must be positive")
    if not 1 <= args.page_limit <= 100:
        raise SystemExit("--page-limit must be between 1 and 100")
    if args.max_pages_per_tag <= 0:
        raise SystemExit("--max-pages-per-tag must be positive")

    repo_root = Path(__file__).resolve().parent.parent
    client = GammaClient(base_url=args.base_url, request_sleep=args.request_sleep)
    configs = normalize_category_selection(args.category)

    for config in configs:
        start = parse_utc_datetime(args.start_date or config.start_date)
        end = parse_utc_datetime(args.end_date or config.end_date)
        if end <= start:
            raise SystemExit(
                f"invalid date window for {config.category}: end-date must be after start-date"
            )

        print(
            f"\n=== {config.category} ===\n"
            f"window={isoformat_z(start)} -> {isoformat_z(end)}\n"
            f"tags={list(config.tag_slugs)}",
            file=sys.stderr,
            flush=True,
        )

        markets, resolved_tags = discover_markets(
            client=client,
            config=config,
            start=start,
            end=end,
            max_markets=args.max_markets,
            page_limit=args.page_limit,
            max_pages_per_tag=args.max_pages_per_tag,
            related_tags=not args.no_related_tags,
        )
        print(
            f"  selected={len(markets)} resolved_tags="
            f"{[tag.get('label') for tag in resolved_tags]}",
            file=sys.stderr,
            flush=True,
        )

        if args.dry_run:
            for market in markets:
                row = market_row(config.category, market)
                print(
                    f"{row['market_slug']} {row['event_slug']} {row['close_time']} {row['volume']}",
                    file=sys.stdout,
                )
            continue

        csv_path = write_markets_csv(repo_root, config, args.output_filename, markets)
        print(f"  wrote={csv_path}", file=sys.stderr, flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
