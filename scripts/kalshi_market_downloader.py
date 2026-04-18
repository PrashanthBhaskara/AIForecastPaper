#!/usr/bin/env python3
"""Download Kalshi resolved/closed market metadata to CSV.

This module contains the shared downloader used by the category-specific
wrapper scripts in this directory.
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


DEFAULT_BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
DEFAULT_CATEGORY = "Climate and Weather"
DEFAULT_START_DATE = "2024-02-01"
DEFAULT_END_DATE = "2024-09-01"
DEFAULT_OUTPUT_DIR = "Research/ClimateMarkets"
DEFAULT_LIMIT = 1_000

CLOSED_OR_RESOLVED_STATUSES = {
    "closed",
    "settled",
    "determined",
    "finalized",
}

MARKET_COLUMNS = [
    "category",
    "market_ticker",
    "series_ticker",
    "event_ticker",
    "title",
    "resolution",
    "status",
    "open_time",
    "close_time",
    "settlement_ts",
    "volume",
]


@dataclass
class KalshiClient:
    base_url: str = DEFAULT_BASE_URL
    request_sleep: float = 0.02
    timeout: int = 30
    max_retries: int = 5
    _last_request_at: float = field(default=0.0, init=False, repr=False)

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        query = urllib.parse.urlencode(params)
        url = f"{self.base_url.rstrip('/')}{path}"
        if query:
            url = f"{url}?{query}"

        for attempt in range(self.max_retries + 1):
            self._pace()
            request = urllib.request.Request(
                url,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "AIForecastPaper-KalshiMarketMetadataDownloader/1.0",
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
            except urllib.error.URLError as exc:
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


def maybe_parse_utc_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return parse_utc_datetime(value)
    except ValueError:
        return None


def unix_seconds(dt: datetime) -> int:
    return int(dt.astimezone(timezone.utc).timestamp())


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
    for key in ("volume_fp", "volume", "volume_dollars"):
        parsed = parse_numeric(market.get(key))
        if parsed is not None:
            return parsed
    return None


def market_passes_volume_filter(market: dict[str, Any], min_volume: float | None) -> bool:
    if min_volume is None:
        return True
    volume = market_volume(market)
    return volume is not None and volume >= min_volume


def paginate(
    client: KalshiClient,
    path: str,
    collection_key: str,
    params: dict[str, Any],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    cursor = ""
    while True:
        page_params = dict(params)
        if cursor:
            page_params["cursor"] = cursor
        data = client.get(path, page_params)
        items.extend(data.get(collection_key) or [])
        cursor = data.get("cursor") or ""
        if not cursor:
            return items


def iter_paginated_pages(
    client: KalshiClient,
    path: str,
    collection_key: str,
    params: dict[str, Any],
):
    cursor = ""
    while True:
        page_params = dict(params)
        if cursor:
            page_params["cursor"] = cursor
        data = client.get(path, page_params)
        yield data.get(collection_key) or []
        cursor = data.get("cursor") or ""
        if not cursor:
            break


def get_series_for_category(client: KalshiClient, category: str) -> list[dict[str, Any]]:
    data = client.get(
        "/series",
        {
            "category": category,
            "include_volume": "true",
        },
    )
    series = data.get("series") or []
    return sorted(
        series,
        key=lambda item: (
            -(market_volume(item) or 0),
            item.get("ticker", ""),
        ),
    )


def is_closed_or_resolved(market: dict[str, Any]) -> bool:
    status = str(market.get("status") or "").lower()
    if status in CLOSED_OR_RESOLVED_STATUSES:
        return True
    return bool(market.get("settlement_ts") or market.get("result"))


def market_closes_in_window(market: dict[str, Any], start: datetime, end: datetime) -> bool:
    close_time = maybe_parse_utc_datetime(market.get("close_time"))
    return bool(close_time and start <= close_time < end)


def annotate_market(
    market: dict[str, Any],
    series_ticker: str,
    source_endpoint: str,
) -> dict[str, Any]:
    annotated = dict(market)
    annotated["_series_ticker"] = series_ticker
    annotated["_source_endpoint"] = source_endpoint
    return annotated


def fetch_historical_markets_for_series(
    client: KalshiClient,
    series_ticker: str,
    start: datetime,
    end: datetime,
    max_matches: int | None,
    min_volume: float | None,
    full_history_scan: bool,
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for page in iter_paginated_pages(
        client,
        "/historical/markets",
        "markets",
        {
            "series_ticker": series_ticker,
            "limit": DEFAULT_LIMIT,
        },
    ):
        page_close_times = [
            close_time
            for close_time in (maybe_parse_utc_datetime(market.get("close_time")) for market in page)
            if close_time is not None
        ]

        for market in page:
            if not market_closes_in_window(market, start, end):
                continue
            if not is_closed_or_resolved(market):
                continue
            if not market_passes_volume_filter(market, min_volume):
                continue
            matches.append(annotate_market(market, series_ticker, "historical"))
            if max_matches is not None and len(matches) >= max_matches:
                return matches

        # Historical markets appear newest-first by close_time. Once the newest
        # market on a page is older than the requested start, later pages cannot
        # contain in-window markets for this series.
        if not full_history_scan and page_close_times and max(page_close_times) < start:
            break

    return matches


def fetch_live_markets_for_series(
    client: KalshiClient,
    series_ticker: str,
    start: datetime,
    end: datetime,
    max_matches: int | None,
    min_volume: float | None,
) -> list[dict[str, Any]]:
    start_ts = unix_seconds(start)
    end_exclusive_ts = unix_seconds(end)
    if end_exclusive_ts <= start_ts:
        return []

    markets = paginate(
        client,
        "/markets",
        "markets",
        {
            "series_ticker": series_ticker,
            "min_close_ts": start_ts,
            "max_close_ts": end_exclusive_ts - 1,
            "limit": DEFAULT_LIMIT,
        },
    )

    matches: list[dict[str, Any]] = []
    for market in markets:
        if not market_closes_in_window(market, start, end):
            continue
        if not is_closed_or_resolved(market):
            continue
        if not market_passes_volume_filter(market, min_volume):
            continue
        matches.append(annotate_market(market, series_ticker, "live"))
        if max_matches is not None and len(matches) >= max_matches:
            break
    return matches


def discover_markets(
    client: KalshiClient,
    category: str,
    start: datetime,
    end: datetime,
    max_markets: int | None,
    min_volume: float | None,
    series_limit: int | None,
    requested_series_tickers: list[str] | None,
    full_history_scan: bool,
    historical_cutoff: datetime | None,
) -> list[dict[str, Any]]:
    if requested_series_tickers:
        series = [{"ticker": ticker} for ticker in sorted(set(requested_series_tickers))]
    else:
        series = get_series_for_category(client, category)
    if series_limit is not None:
        series = series[:series_limit]
    if not series:
        raise RuntimeError(f"No Kalshi series found for category {category!r}")

    markets: list[dict[str, Any]] = []
    seen_tickers: set[str] = set()

    def add_market(market: dict[str, Any]) -> None:
        ticker = market.get("ticker")
        if ticker and ticker not in seen_tickers:
            seen_tickers.add(ticker)
            markets.append(market)

    def remaining() -> int | None:
        if max_markets is None:
            return None
        return max(max_markets - len(markets), 0)

    use_historical = historical_cutoff is None or start < historical_cutoff
    use_live = historical_cutoff is None or end > historical_cutoff

    for index, series_item in enumerate(series, start=1):
        if max_markets is not None and len(markets) >= max_markets:
            break

        series_ticker = series_item["ticker"]
        print(
            f"[{index}/{len(series)}] Discovering markets for {series_ticker}",
            file=sys.stderr,
            flush=True,
        )

        if use_historical:
            historical_end = min(end, historical_cutoff) if historical_cutoff else end
            for market in fetch_historical_markets_for_series(
                client=client,
                series_ticker=series_ticker,
                start=start,
                end=historical_end,
                max_matches=remaining(),
                min_volume=min_volume,
                full_history_scan=full_history_scan,
            ):
                add_market(market)

        if use_live and (max_markets is None or len(markets) < max_markets):
            live_start = max(start, historical_cutoff) if historical_cutoff else start
            for market in fetch_live_markets_for_series(
                client=client,
                series_ticker=series_ticker,
                start=live_start,
                end=end,
                max_matches=remaining(),
                min_volume=min_volume,
            ):
                add_market(market)

    return markets


def market_resolution(market: dict[str, Any]) -> str:
    result = market.get("result")
    if result not in (None, ""):
        return str(result)

    settlement_value = market.get("settlement_value_dollars")
    if settlement_value not in (None, ""):
        if str(settlement_value) == "1.0000":
            return "yes"
        if str(settlement_value) == "0.0000":
            return "no"
        return str(settlement_value)

    expiration_value = market.get("expiration_value")
    return "" if expiration_value in (None, "") else str(expiration_value)


def market_row(category: str, market: dict[str, Any]) -> dict[str, Any]:
    volume = market_volume(market)
    return {
        "category": category,
        "market_ticker": market.get("ticker", ""),
        "series_ticker": market.get("_series_ticker", ""),
        "event_ticker": market.get("event_ticker", ""),
        "title": market.get("title", ""),
        "resolution": market_resolution(market),
        "status": market.get("status", ""),
        "open_time": market.get("open_time", ""),
        "close_time": market.get("close_time", ""),
        "settlement_ts": market.get("settlement_ts", ""),
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


def build_parser(
    default_category: str = DEFAULT_CATEGORY,
    default_output_dir: str = DEFAULT_OUTPUT_DIR,
) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=f"Download Kalshi {default_category} market metadata.",
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--category", default=default_category)
    parser.add_argument("--start-date", default=DEFAULT_START_DATE)
    parser.add_argument("--end-date", default=DEFAULT_END_DATE)
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
        help="Only include markets whose market volume_fp is at least this value.",
    )
    parser.add_argument("--series-limit", type=int, default=None)
    parser.add_argument(
        "--series-ticker",
        action="append",
        default=[],
        help="Optional series ticker to restrict discovery. Can be repeated or comma-separated.",
    )
    parser.add_argument("--request-sleep", type=float, default=0.02)
    parser.add_argument("--full-history-scan", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(
    default_category: str = DEFAULT_CATEGORY,
    default_output_dir: str = DEFAULT_OUTPUT_DIR,
) -> int:
    args = build_parser(
        default_category=default_category,
        default_output_dir=default_output_dir,
    ).parse_args()
    start = parse_utc_datetime(args.start_date)
    end = parse_utc_datetime(args.end_date)
    if end <= start:
        raise SystemExit("--end-date must be after --start-date")
    if args.max_markets is not None and args.max_markets < 0:
        raise SystemExit("--max-markets must be zero or positive")
    if args.min_volume is not None and (not math.isfinite(args.min_volume) or args.min_volume < 0):
        raise SystemExit("--min-volume must be a finite number greater than or equal to zero")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    client = KalshiClient(base_url=args.base_url, request_sleep=args.request_sleep)
    cutoff = client.get("/historical/cutoff")
    historical_cutoff = maybe_parse_utc_datetime(cutoff.get("market_settled_ts"))
    print(f"Kalshi historical cutoff: {cutoff}", file=sys.stderr)

    requested_series_tickers = [
        ticker.strip()
        for value in args.series_ticker
        for ticker in value.split(",")
        if ticker.strip()
    ]
    markets = discover_markets(
        client=client,
        category=args.category,
        start=start,
        end=end,
        max_markets=args.max_markets,
        min_volume=args.min_volume,
        series_limit=args.series_limit,
        requested_series_tickers=requested_series_tickers,
        full_history_scan=args.full_history_scan,
        historical_cutoff=historical_cutoff,
    )

    print(
        f"Selected {len(markets)} closed/resolved markets in {args.category!r} "
        f"from {start.isoformat()} to {end.isoformat()}",
        file=sys.stderr,
    )

    if args.dry_run:
        for market in markets:
            row = market_row(args.category, market)
            print(
                f"{row['market_ticker']} {row['series_ticker']} {row['close_time']} {row['resolution']}",
                file=sys.stdout,
            )
        return 0

    csv_path = write_markets_csv(output_dir, args.category, markets)
    print(f"Wrote {len(markets)} market rows to {csv_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
