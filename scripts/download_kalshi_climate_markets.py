#!/usr/bin/env python3
"""Download Kalshi market candlesticks to CSV.

Defaults are intentionally set for the proof window requested:

    python scripts/download_kalshi_climate_markets.py

The Climate script keeps its original defaults, while small wrapper scripts can
reuse this module with different Kalshi categories and output folders.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
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
DEFAULT_START_DATE = "2026-01-01"
DEFAULT_END_DATE = "2026-02-01"
DEFAULT_OUTPUT_DIR = "Research/ClimateMarkets"
DEFAULT_PERIOD_INTERVAL_MINUTES = 1
DEFAULT_CHUNK_MINUTES = 4_999
DEFAULT_LIMIT = 1_000

CLOSED_OR_RESOLVED_STATUSES = {
    "closed",
    "settled",
    "determined",
    "finalized",
}

CANDLE_COLUMNS = [
    "market_ticker",
    "series_ticker",
    "event_ticker",
    "market_title",
    "market_status",
    "market_result",
    "market_close_time",
    "market_settlement_ts",
    "source_endpoint",
    "end_period_ts",
    "end_period_time_utc",
    "yes_bid_open",
    "yes_bid_low",
    "yes_bid_high",
    "yes_bid_close",
    "yes_ask_open",
    "yes_ask_low",
    "yes_ask_high",
    "yes_ask_close",
    "price_open",
    "price_low",
    "price_high",
    "price_close",
    "price_mean",
    "price_previous",
    "price_min",
    "price_max",
    "volume",
    "open_interest",
]

MANIFEST_COLUMNS = [
    "market_ticker",
    "series_ticker",
    "event_ticker",
    "market_title",
    "market_status",
    "market_result",
    "open_time",
    "close_time",
    "settlement_ts",
    "source_endpoint",
    "candlestick_count",
    "csv_path",
    "error",
]


@dataclass
class KalshiClient:
    base_url: str = DEFAULT_BASE_URL
    request_sleep: float = 0.06
    timeout: int = 30
    max_retries: int = 5
    _last_request_at: float = field(default=0.0, init=False, repr=False)

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """GET JSON from Kalshi with light pacing and retry handling."""
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
                    "User-Agent": "AIForecastPaper-KalshiMarketDownloader/1.0",
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


def timestamp_to_utc(ts: Any) -> str:
    if ts in (None, ""):
        return ""
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat().replace("+00:00", "Z")


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
    return sorted(series, key=lambda item: item.get("ticker", ""))


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
            if market_closes_in_window(market, start, end) and is_closed_or_resolved(market):
                matches.append(annotate_market(market, series_ticker, "historical"))

        # Historical markets appear newest-first by close_time. This keeps the
        # January proof run from walking years of old markets for every series.
        if not full_history_scan and page_close_times and max(page_close_times) < start:
            break

    return matches


def fetch_live_markets_for_series(
    client: KalshiClient,
    series_ticker: str,
    start: datetime,
    end: datetime,
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
    return [
        annotate_market(market, series_ticker, "live")
        for market in markets
        if market_closes_in_window(market, start, end) and is_closed_or_resolved(market)
    ]


def discover_markets(
    client: KalshiClient,
    category: str,
    start: datetime,
    end: datetime,
    series_limit: int | None,
    requested_series_tickers: list[str] | None,
    full_history_scan: bool,
) -> list[dict[str, Any]]:
    if requested_series_tickers:
        series = [{"ticker": ticker} for ticker in sorted(set(requested_series_tickers))]
    else:
        series = get_series_for_category(client, category)
    if series_limit is not None:
        series = series[:series_limit]
    if not series:
        raise RuntimeError(f"No Kalshi series found for category {category!r}")

    markets_by_ticker: dict[str, dict[str, Any]] = {}
    for index, series_item in enumerate(series, start=1):
        series_ticker = series_item["ticker"]
        print(
            f"[{index}/{len(series)}] Discovering markets for {series_ticker}",
            file=sys.stderr,
            flush=True,
        )
        for market in fetch_historical_markets_for_series(
            client,
            series_ticker,
            start,
            end,
            full_history_scan=full_history_scan,
        ):
            markets_by_ticker[market["ticker"]] = market
        for market in fetch_live_markets_for_series(client, series_ticker, start, end):
            # Prefer historical copies when both endpoints can see a market.
            markets_by_ticker.setdefault(market["ticker"], market)

    return sorted(
        markets_by_ticker.values(),
        key=lambda item: (
            item.get("close_time") or "",
            item.get("_series_ticker") or "",
            item.get("ticker") or "",
        ),
    )


def choose_candlestick_path(market: dict[str, Any]) -> tuple[str, str]:
    ticker = market["ticker"]
    if market.get("_source_endpoint") == "historical":
        return "historical", f"/historical/markets/{urllib.parse.quote(ticker)}/candlesticks"

    series_ticker = market["_series_ticker"]
    return (
        "live",
        f"/series/{urllib.parse.quote(series_ticker)}/markets/{urllib.parse.quote(ticker)}/candlesticks",
    )


def fetch_candlesticks(
    client: KalshiClient,
    market: dict[str, Any],
    start: datetime,
    end: datetime,
    period_interval_minutes: int,
    chunk_minutes: int,
) -> list[dict[str, Any]]:
    global_start_ts = unix_seconds(start)
    global_end_inclusive_ts = unix_seconds(end) - (period_interval_minutes * 60)

    open_time = maybe_parse_utc_datetime(market.get("open_time"))
    close_time = maybe_parse_utc_datetime(market.get("close_time"))
    market_start_ts = unix_seconds(open_time) if open_time else global_start_ts
    market_end_ts = unix_seconds(close_time) if close_time else global_end_inclusive_ts

    start_ts = max(global_start_ts, market_start_ts)
    end_ts = min(global_end_inclusive_ts, market_end_ts)
    if end_ts < start_ts:
        return []

    source_endpoint, path = choose_candlestick_path(market)
    chunk_seconds = chunk_minutes * 60
    step_seconds = period_interval_minutes * 60
    candles_by_ts: dict[int, dict[str, Any]] = {}
    chunk_start = start_ts

    while chunk_start <= end_ts:
        chunk_end = min(end_ts, chunk_start + chunk_seconds)
        data = client.get(
            path,
            {
                "start_ts": chunk_start,
                "end_ts": chunk_end,
                "period_interval": period_interval_minutes,
            },
        )
        for candle in data.get("candlesticks") or []:
            candle["_source_endpoint"] = source_endpoint
            candle_ts = candle.get("end_period_ts")
            if candle_ts is not None:
                candles_by_ts[int(candle_ts)] = candle
        chunk_start = chunk_end + step_seconds

    return [candles_by_ts[key] for key in sorted(candles_by_ts)]


def nested_value(container: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in container:
            return container[key]
    return ""


def flatten_candle(market: dict[str, Any], candle: dict[str, Any]) -> dict[str, Any]:
    yes_bid = candle.get("yes_bid") or {}
    yes_ask = candle.get("yes_ask") or {}
    price = candle.get("price") or {}
    end_period_ts = candle.get("end_period_ts")

    return {
        "market_ticker": market.get("ticker", ""),
        "series_ticker": market.get("_series_ticker", ""),
        "event_ticker": market.get("event_ticker", ""),
        "market_title": market.get("title", ""),
        "market_status": market.get("status", ""),
        "market_result": market.get("result", ""),
        "market_close_time": market.get("close_time", ""),
        "market_settlement_ts": market.get("settlement_ts", ""),
        "source_endpoint": candle.get("_source_endpoint", market.get("_source_endpoint", "")),
        "end_period_ts": end_period_ts,
        "end_period_time_utc": timestamp_to_utc(end_period_ts),
        "yes_bid_open": nested_value(yes_bid, "open", "open_dollars"),
        "yes_bid_low": nested_value(yes_bid, "low", "low_dollars"),
        "yes_bid_high": nested_value(yes_bid, "high", "high_dollars"),
        "yes_bid_close": nested_value(yes_bid, "close", "close_dollars"),
        "yes_ask_open": nested_value(yes_ask, "open", "open_dollars"),
        "yes_ask_low": nested_value(yes_ask, "low", "low_dollars"),
        "yes_ask_high": nested_value(yes_ask, "high", "high_dollars"),
        "yes_ask_close": nested_value(yes_ask, "close", "close_dollars"),
        "price_open": nested_value(price, "open", "open_dollars"),
        "price_low": nested_value(price, "low", "low_dollars"),
        "price_high": nested_value(price, "high", "high_dollars"),
        "price_close": nested_value(price, "close", "close_dollars"),
        "price_mean": nested_value(price, "mean", "mean_dollars"),
        "price_previous": nested_value(price, "previous", "previous_dollars"),
        "price_min": nested_value(price, "min", "min_dollars"),
        "price_max": nested_value(price, "max", "max_dollars"),
        "volume": nested_value(candle, "volume", "volume_fp"),
        "open_interest": nested_value(candle, "open_interest", "open_interest_fp"),
    }


def safe_csv_name(ticker: str) -> str:
    safe_ticker = re.sub(r"[^A-Za-z0-9_.-]+", "_", ticker)
    return f"{safe_ticker}.csv"


def write_market_csv(output_dir: Path, market: dict[str, Any], candles: list[dict[str, Any]]) -> Path:
    csv_path = output_dir / safe_csv_name(market["ticker"])
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CANDLE_COLUMNS)
        writer.writeheader()
        for candle in candles:
            writer.writerow(flatten_candle(market, candle))
    return csv_path


def manifest_row(
    market: dict[str, Any],
    csv_path: Path | None,
    candlestick_count: int,
    error: str = "",
) -> dict[str, Any]:
    return {
        "market_ticker": market.get("ticker", ""),
        "series_ticker": market.get("_series_ticker", ""),
        "event_ticker": market.get("event_ticker", ""),
        "market_title": market.get("title", ""),
        "market_status": market.get("status", ""),
        "market_result": market.get("result", ""),
        "open_time": market.get("open_time", ""),
        "close_time": market.get("close_time", ""),
        "settlement_ts": market.get("settlement_ts", ""),
        "source_endpoint": market.get("_source_endpoint", ""),
        "candlestick_count": candlestick_count,
        "csv_path": str(csv_path) if csv_path else "",
        "error": error,
    }


def write_manifest(output_dir: Path, rows: list[dict[str, Any]]) -> Path:
    manifest_path = output_dir / "markets_index.csv"
    with manifest_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return manifest_path


def build_parser(
    default_category: str = DEFAULT_CATEGORY,
    default_output_dir: str = DEFAULT_OUTPUT_DIR,
) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=f"Download 1-minute Kalshi {default_category} closed/resolved market candlesticks.",
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--category", default=default_category)
    parser.add_argument("--start-date", default=DEFAULT_START_DATE)
    parser.add_argument("--end-date", default=DEFAULT_END_DATE)
    parser.add_argument("--output-dir", default=default_output_dir)
    parser.add_argument("--period-interval", type=int, default=DEFAULT_PERIOD_INTERVAL_MINUTES)
    parser.add_argument("--chunk-minutes", type=int, default=DEFAULT_CHUNK_MINUTES)
    parser.add_argument("--max-markets", type=int, default=None)
    parser.add_argument("--series-limit", type=int, default=None)
    parser.add_argument(
        "--series-ticker",
        action="append",
        default=[],
        help="Optional series ticker to restrict discovery. Can be repeated or comma-separated.",
    )
    parser.add_argument("--request-sleep", type=float, default=0.06)
    parser.add_argument("--full-history-scan", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--fail-fast", action="store_true")
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
    if args.period_interval not in {1, 60, 1440}:
        raise SystemExit("--period-interval must be one of 1, 60, or 1440")
    if args.chunk_minutes <= 0:
        raise SystemExit("--chunk-minutes must be positive")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    client = KalshiClient(base_url=args.base_url, request_sleep=args.request_sleep)
    cutoff = client.get("/historical/cutoff")
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
        series_limit=args.series_limit,
        requested_series_tickers=requested_series_tickers,
        full_history_scan=args.full_history_scan,
    )
    if args.max_markets is not None:
        markets = markets[: args.max_markets]

    print(
        f"Discovered {len(markets)} closed/resolved markets in {args.category!r} "
        f"from {start.isoformat()} to {end.isoformat()}",
        file=sys.stderr,
    )

    if args.dry_run:
        for market in markets:
            print(
                f"{market.get('ticker')} {market.get('_series_ticker')} {market.get('close_time')}",
                file=sys.stdout,
            )
        return 0

    manifest_rows: list[dict[str, Any]] = []
    errors = 0
    for index, market in enumerate(markets, start=1):
        print(f"[{index}/{len(markets)}] Downloading {market['ticker']}", file=sys.stderr, flush=True)
        try:
            candles = fetch_candlesticks(
                client=client,
                market=market,
                start=start,
                end=end,
                period_interval_minutes=args.period_interval,
                chunk_minutes=args.chunk_minutes,
            )
            csv_path = write_market_csv(output_dir, market, candles)
            manifest_rows.append(manifest_row(market, csv_path, len(candles)))
        except Exception as exc:  # noqa: BLE001 - keep batch runs moving by default.
            errors += 1
            message = str(exc)
            manifest_rows.append(manifest_row(market, None, 0, error=message))
            print(f"ERROR for {market.get('ticker')}: {message}", file=sys.stderr)
            if args.fail_fast:
                break

    manifest_path = write_manifest(output_dir, manifest_rows)
    print(f"Wrote manifest: {manifest_path}", file=sys.stderr)
    print(f"Wrote {len(manifest_rows) - errors} market CSVs to {output_dir}", file=sys.stderr)

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
