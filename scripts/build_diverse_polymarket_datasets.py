#!/usr/bin/env python3
"""Build diverse, globally de-duplicated Polymarket datasets for all categories.

This script regenerates both historical resolved markets (``markets.csv``) and
future open markets (``newmarkets.csv``) while enforcing:

1. global cross-category uniqueness by market identifier,
2. topic-aware assignment of ambiguous markets to a single best-fit category,
3. within-category diversity caps across repeated events and market families.

The result is intended to be a cleaner base for Phase I / Phase II curation.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_BASE_URL = "https://gamma-api.polymarket.com"
DEFAULT_TARGET_PER_CATEGORY = 300
DEFAULT_REQUEST_SLEEP = 0.05
DEFAULT_PAGE_LIMIT = 100
DEFAULT_MAX_PAGES = 18

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


def csv_output_path(output_dir: str, filename: str) -> Path:
    return Path(__file__).resolve().parent.parent / output_dir / filename


@dataclass(frozen=True)
class PhaseWindow:
    start_date: str
    end_date: str


@dataclass(frozen=True)
class PhaseConfig:
    name: str
    output_filename: str
    is_closed: bool
    windows: tuple[PhaseWindow, ...]
    max_event_cap: int
    max_family_cap: int


@dataclass(frozen=True)
class CategoryConfig:
    key: str
    category: str
    output_dir: str
    priority: int
    historical_tags: tuple[str, ...]
    future_tags: tuple[str, ...]
    topic_keywords: dict[str, tuple[str, ...]]
    hard_exclude_keywords: tuple[str, ...]
    allow_tag_fallback: bool = True
    historical_related_tag_slugs: tuple[str, ...] = ()
    future_related_tag_slugs: tuple[str, ...] = ()


@dataclass
class Candidate:
    key: str
    phase: str
    category_key: str
    category_name: str
    priority: int
    source_tag: str
    score: int
    topic_scores: dict[str, int]
    primary_topic: str
    event_key: str
    family_key: str
    text: str
    market: dict[str, Any]

    @property
    def volume(self) -> float:
        return market_volume(self.market) or 0.0

    @property
    def close_time(self) -> str:
        return str(self.market.get("endDate") or self.market.get("close_time") or "")


PHASE_CONFIGS = {
    "historical": PhaseConfig(
        name="historical",
        output_filename="markets.csv",
        is_closed=True,
        windows=(
            PhaseWindow("2023-01-01", "2025-01-01"),
            PhaseWindow("2022-01-01", "2025-01-01"),
            PhaseWindow("2021-01-01", "2025-01-01"),
            PhaseWindow("2020-01-01", "2025-01-01"),
        ),
        max_event_cap=6,
        max_family_cap=36,
    ),
    "future": PhaseConfig(
        name="future",
        output_filename="newmarkets.csv",
        is_closed=False,
        windows=(
            PhaseWindow("2026-09-01", "2030-01-01"),
        ),
        max_event_cap=6,
        max_family_cap=32,
    ),
}

ALL_PHASE_NAMES = tuple(PHASE_CONFIGS)

GLOBAL_EXCLUDE_KEYWORDS = (
    "luigi mangione",
    "manifesto",
    "brian thompson",
    "brian-thompson",
)


CATEGORY_CONFIGS = (
    CategoryConfig(
        key="climate",
        category="Climate and Weather",
        output_dir="Research/ClimateMarkets",
        priority=0,
        historical_tags=(
            "weather",
            "climate",
            "global-temp",
            "global-warming",
            "hurricane",
            "hurricanes",
            "earthquake",
            "wildfire",
            "volcano",
            "temperature",
            "snow",
            "science",
            "climate-science",
            "climate-weather",
            "disaster",
            "news",
            "current-events",
        ),
        future_tags=(
            "weather",
            "climate",
            "global-temp",
            "global-warming",
            "hurricane",
            "hurricanes",
            "earthquake",
            "wildfire",
            "volcano",
            "temperature",
            "science",
            "climate-science",
            "climate-weather",
            "disaster",
            "disease",
        ),
        topic_keywords={
            "temperature": ("temperature", "hottest", "heat", "warming", "celsius", "fahrenheit", "hot"),
            "storms": ("hurricane", "cyclone", "typhoon", "storm", "rainfall", "snow", "flood", "drought"),
            "geology": ("earthquake", "volcano", "eruption", "wildfire", "seismic", "meteor"),
            "oceans": ("arctic", "sea ice", "ice extent", "ocean", "minimum extent"),
        },
        hard_exclude_keywords=(
            "election",
            "primary",
            "senate",
            "house seat",
            "fed ",
            "interest rate",
            "inflation",
            "ipo",
            "acquisition",
            "merger",
            "box office",
            "grammy",
            "oscar",
            "billboard",
            "spacex ipo",
            "nba",
            "wnba",
            "nfl",
            "mlb",
            "nhl",
            "basketball",
            "soccer",
            "football",
            "playoff",
            "miami heat",
        ),
        historical_related_tag_slugs=("weather", "climate", "science", "climate-science"),
        future_related_tag_slugs=("weather", "climate", "science", "climate-science"),
    ),
    CategoryConfig(
        key="commodities",
        category="Commodities",
        output_dir="Research/CommoditiesMarkets",
        priority=1,
        historical_tags=(
            "commodities",
            "gold",
            "oil",
            "gas",
            "crude-oil",
            "commodity-market",
            "energy-market",
            "energy-industry",
            "oil-production",
            "silver",
            "copper",
            "uranium",
            "crypto",
            "cryptocurrency",
            "bitcoin",
            "ethereum",
            "solana",
            "altcoins",
            "finance",
            "business",
            "news",
            "current-events",
        ),
        future_tags=(
            "commodities",
            "gold",
            "oil",
            "gas",
            "crude-oil",
            "commodity-market",
            "energy-market",
            "energy-industry",
            "oil-production",
            "silver",
            "copper",
            "uranium",
            "crypto",
            "bitcoin",
            "ethereum",
            "solana",
            "cryptocurrency",
        ),
        topic_keywords={
            "energy": ("oil", "crude", "gas", "lng", "opec", "barrel", "reserves", "diesel", "gasoline", "refinery"),
            "metals": ("gold", "silver", "copper", "metal", "lithium", "uranium", "steel"),
            "agriculture": ("wheat", "corn", "soy", "coffee", "cocoa", "sugar"),
            "shipping": ("strait of hormuz", "tanker", "transit", "ships"),
            "crypto": (
                "bitcoin",
                "ethereum",
                "solana",
                "crypto",
                "cryptocurrency",
                "token",
                "stablecoin",
                "altcoin",
                "airdrop",
                "dogecoin",
                "btc",
                "eth",
            ),
        },
        hard_exclude_keywords=(
            "election",
            "primary",
            "ipo",
            "acquisition",
            "merger",
            "company",
            "ceo",
            "earnings",
            "revenue",
            "grammy",
            "oscar",
            "hurricane",
            "earthquake",
            "tweet",
            "sentenced",
            "airdrop",
            "farcaster",
            "robinhood",
        ),
    ),
    CategoryConfig(
        key="economics",
        category="Economics",
        output_dir="Research/EconomicsMarkets",
        priority=2,
        historical_tags=(
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
            "cpi",
            "gdp",
            "business",
            "finance",
            "news",
            "current-events",
        ),
        future_tags=(
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
            "cpi",
            "gdp",
        ),
        topic_keywords={
            "inflation": ("inflation", "cpi", "pce", "prices", "deflation"),
            "rates": ("fed", "ecb", "fomc", "interest rate", "rate cut", "rate hike", "powell", "central bank"),
            "labor": ("jobs", "payroll", "unemployment", "labor", "wages"),
            "growth": ("gdp", "recession", "economic growth", "deficit", "debt", "tariff", "trade deal"),
            "currency": ("usd", "dollar", "euro", "yen", "peso", "ruble", "exchange rate"),
        },
        hard_exclude_keywords=(
            "presidential election",
            "governor election",
            "senate election",
            "primary election",
            "ballot",
            "oscar",
            "grammy",
            "billboard",
            "movie",
            "hurricane",
            "earthquake",
        ),
    ),
    CategoryConfig(
        key="elections",
        category="Elections",
        output_dir="Research/ElectionsMarkets",
        priority=3,
        historical_tags=(
            "elections",
            "us-election",
            "global-elections",
            "world-elections",
            "presidential-election",
            "german-election",
        ),
        future_tags=(
            "elections",
            "us-election",
            "global-elections",
            "world-elections",
            "presidential-election",
            "german-election",
        ),
        topic_keywords={
            "presidential": ("election", "candidate", "popular vote", "electoral", "president", "runoff", "primary", "caucus"),
            "legislative": ("senate", "house", "district", "seat", "parliament", "assembly", "governor", "mayor"),
            "party": ("democrat", "republican", "labour", "conservative", "coalition", "party"),
        },
        hard_exclude_keywords=(
            "fed ",
            "interest rate",
            "inflation",
            "cpi",
            "oscar",
            "grammy",
            "hurricane",
            "earthquake",
            "ipo",
            "acquisition",
        ),
        allow_tag_fallback=False,
    ),
    CategoryConfig(
        key="entertainment",
        category="Entertainment",
        output_dir="Research/EntertainmentMarkets",
        priority=4,
        historical_tags=(
            "awards",
            "movies",
            "music",
            "entertainment",
            "oscars",
            "grammys",
            "golden-globes",
            "emmys",
            "tv",
            "box-office",
            "pop-culture",
        ),
        future_tags=(
            "awards",
            "movies",
            "music",
            "entertainment",
            "oscars",
            "grammys",
            "golden-globes",
            "emmys",
            "tv",
            "box-office",
            "pop-culture",
        ),
        topic_keywords={
            "film_tv": ("movie", "film", "actor", "actress", "director", "series", "tv", "streaming", "box office", "avengers"),
            "music": ("music", "album", "song", "billboard", "grammy", "artist", "concert", "band"),
            "awards": ("oscar", "emmy", "golden globe", "bafta", "tony", "award", "nobel prize"),
            "celebrity": ("celebrity", "cast", "cameo", "divorce", "engagement", "baby", "tour"),
        },
        hard_exclude_keywords=(
            "presidential election",
            "governor election",
            "senate election",
            "prime minister",
            "fed ",
            "interest rate",
            "inflation",
            "hurricane",
            "earthquake",
            "ipo",
            "acquisition",
            "trump",
            "kamala",
            "obama",
            "biden",
            "debate",
            "rally",
            "speech",
            "tweet",
            "mlb ",
            "mls ",
            "nba ",
            "nfl ",
            "uefa",
            "fifa",
        ),
        allow_tag_fallback=False,
    ),
    CategoryConfig(
        key="companies",
        category="Companies",
        output_dir="Research/CompaniesMarkets",
        priority=5,
        historical_tags=(
            "business",
            "companies",
            "ceo",
            "ipo",
            "earnings",
            "stocks",
            "finance",
            "news",
            "current-events",
        ),
        future_tags=(
            "business",
            "companies",
            "ceo",
            "ipo",
            "earnings",
            "stocks",
        ),
        topic_keywords={
            "corporate": ("company", "ceo", "earnings", "revenue", "acquisition", "merger", "antitrust", "bankruptcy", "lawsuit"),
            "public_market": ("ipo", "public offering", "ticker", "valuation", "market cap", "richest person"),
            "products": ("launch", "product", "release", "partnership", "acquired"),
        },
        hard_exclude_keywords=(
            "presidential election",
            "senate election",
            "fed ",
            "interest rate",
            "inflation",
            "treasury yield",
            "oscar",
            "grammy",
            "hurricane",
            "earthquake",
        ),
    ),
    CategoryConfig(
        key="financials",
        category="Financials",
        output_dir="Research/FinancialsMarkets",
        priority=6,
        historical_tags=(
            "finance",
            "financials",
            "crypto-prices",
            "bitcoin",
            "ethereum",
            "solana",
            "etf",
            "stocks",
        ),
        future_tags=(
            "finance",
            "financials",
            "crypto-prices",
            "bitcoin",
            "ethereum",
            "solana",
            "etf",
            "stocks",
        ),
        topic_keywords={
            "indices": ("nasdaq", "s&p", "dow", "index", "etf", "stock"),
            "rates_fx": ("treasury", "yield", "bond", "fed", "interest rate", "dollar", "euro", "yen", "peso"),
            "crypto": ("bitcoin", "ethereum", "solana", "crypto", "token", "airdrop", "stablecoin"),
            "banks": ("bank", "financial", "credit", "liquidity"),
        },
        hard_exclude_keywords=(
            "presidential election",
            "senate election",
            "governor election",
            "movie",
            "grammy",
            "oscar",
            "hurricane",
            "earthquake",
            "acquisition",
            "merger",
            "richest person",
        ),
        allow_tag_fallback=False,
    ),
    CategoryConfig(
        key="politics",
        category="Politics",
        output_dir="Research/PoliticsMarkets",
        priority=7,
        historical_tags=(
            "politics",
            "geopolitics",
            "us-government",
            "u-s-politics",
            "cabinet",
            "congress",
            "middle-east",
            "campaign-promises",
        ),
        future_tags=(
            "politics",
            "geopolitics",
            "us-government",
            "u-s-politics",
            "cabinet",
            "congress",
            "middle-east",
            "campaign-promises",
        ),
        topic_keywords={
            "leaders": ("cabinet", "minister", "secretary", "leader", "prime minister", "president", "dictator", "ambassador"),
            "policy": ("shutdown", "congress", "legislation", "bill", "sanctions", "treaty", "border", "pardon", "nominee", "confirmed"),
            "geopolitics": ("greenland", "taiwan", "nato", "iran", "israel", "ukraine", "china", "venezuela", "ceasefire", "war"),
        },
        hard_exclude_keywords=(
            "presidential election",
            "governor election",
            "senate election",
            "house seat",
            "primary election",
            "runoff",
            "ballot",
            "fed ",
            "interest rate",
            "inflation",
            "treasury yield",
            "movie",
            "grammy",
            "oscar",
            "box office",
            "hurricane",
            "earthquake",
            "nobel peace prize",
        ),
        allow_tag_fallback=False,
    ),
    CategoryConfig(
        key="science_technology",
        category="Science and Technology",
        output_dir="Research/ScienceTechnologyMarkets",
        priority=8,
        historical_tags=(
            "science",
            "tech",
            "ai",
            "deepseek",
            "grok",
            "spacex",
            "nasa",
            "space",
            "gaming",
            "news",
            "current-events",
        ),
        future_tags=(
            "science",
            "tech",
            "ai",
            "deepseek",
            "grok",
            "spacex",
            "nasa",
            "space",
            "gaming",
            "big-tech",
            "anthropic",
            "claude",
            "disease",
            "google",
        ),
        topic_keywords={
            "ai": ("ai", "artificial intelligence", "openai", "anthropic", "gpt", "model", "benchmark", "llm"),
            "space": ("nasa", "spacex", "starship", "launch", "rocket", "satellite", "orbit", "moon", "mars"),
            "gaming": ("game", "gaming", "steam", "playstation", "xbox", "nintendo", "switch"),
            "science": ("science", "scientific", "research", "discovery", "fusion", "quantum", "robot", "biotech"),
        },
        hard_exclude_keywords=(
            "temperature",
            "hurricane",
            "weather",
            "climate",
            "earthquake",
            "wildfire",
            "snow",
            "presidential election",
            "senate election",
            "interest rate",
            "inflation",
            "treasury yield",
            "ipo",
            "acquisition",
            "merger",
            "richest person",
            "oscar",
            "grammy",
        ),
        future_related_tag_slugs=("tech", "science", "ai", "big-tech"),
    ),
)

CATEGORY_CONFIG_BY_KEY = {config.key: config for config in CATEGORY_CONFIGS}
CATEGORY_NAME_LOOKUP = {config.category.lower(): config.key for config in CATEGORY_CONFIGS}
for config in CATEGORY_CONFIGS:
    CATEGORY_NAME_LOOKUP[config.key] = config.key

SUPPLEMENT_ONLY_TAGS: dict[str, set[str]] = {
    "climate": {"science", "news", "current-events"},
    "commodities": {"finance", "business", "news", "current-events"},
    "economics": {"business", "finance", "news", "current-events"},
    "companies": {"finance", "news", "current-events"},
    "science_technology": {"news", "current-events"},
}


@dataclass
class GammaClient:
    base_url: str = DEFAULT_BASE_URL
    request_sleep: float = DEFAULT_REQUEST_SLEEP
    timeout: int = 60
    max_retries: int = 5
    tag_cache: dict[str, dict[str, Any] | None] = field(default_factory=dict)
    market_cache: dict[tuple[Any, ...], list[dict[str, Any]]] = field(default_factory=dict)
    _last_request_at: float = field(default=0.0, init=False, repr=False)

    def get_json(self, path: str, params: list[tuple[str, Any]] | None = None) -> Any:
        pairs = [(k, v) for k, v in (params or []) if v not in (None, "")]
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
                    "User-Agent": "Mozilla/5.0 AIForecastPaper-DiverseDatasetBuilder/1.0",
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

        raise last_error or RuntimeError(f"GET {url} failed")

    def _pace(self) -> None:
        if self.request_sleep <= 0:
            return
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.request_sleep:
            time.sleep(self.request_sleep - elapsed)
        self._last_request_at = time.monotonic()

    def fetch_tag(self, slug: str) -> dict[str, Any] | None:
        if slug not in self.tag_cache:
            payload = self.get_json(f"/tags/slug/{urllib.parse.quote(slug, safe='')}")
            self.tag_cache[slug] = payload if isinstance(payload, dict) else None
        return self.tag_cache[slug]

    def fetch_markets_for_tag(
        self,
        *,
        phase_name: str,
        tag_slug: str,
        window: PhaseWindow,
        page_limit: int,
        max_pages: int,
        related_tags: bool = False,
    ) -> list[dict[str, Any]]:
        cache_key = (
            phase_name,
            tag_slug,
            window.start_date,
            window.end_date,
            page_limit,
            max_pages,
            related_tags,
        )
        if cache_key in self.market_cache:
            return self.market_cache[cache_key]

        phase = PHASE_CONFIGS[phase_name]
        tag = self.fetch_tag(tag_slug)
        if tag is None:
            self.market_cache[cache_key] = []
            return []

        start = isoformat_z(parse_utc_datetime(window.start_date))
        end = isoformat_z(parse_utc_datetime(window.end_date))
        markets: list[dict[str, Any]] = []
        for page_index in range(max_pages):
            params: list[tuple[str, Any]] = [
                ("limit", page_limit),
                ("offset", page_index * page_limit),
                ("tag_id", tag.get("id")),
                ("end_date_min", start),
                ("end_date_max", end),
                ("order", "volume"),
                ("ascending", "false"),
            ]
            if related_tags:
                params.append(("related_tags", "true"))
            if phase.is_closed:
                params.append(("closed", "true"))
            else:
                params.extend([("active", "true"), ("closed", "false")])
            payload = self.get_json("/markets", params)
            if not isinstance(payload, list) or not payload:
                break
            markets.extend(item for item in payload if isinstance(item, dict))
            if len(payload) < page_limit:
                break

        self.market_cache[cache_key] = markets
        return markets


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


def parse_optional_utc_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        return parse_utc_datetime(str(value))
    except ValueError:
        return None


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


def market_key(market: dict[str, Any]) -> str:
    return str(market.get("conditionId") or market.get("condition_id") or market.get("slug") or market.get("market_slug") or market.get("id") or "")


def event_slug(market: dict[str, Any]) -> str:
    events = market.get("events") or []
    if events and isinstance(events[0], dict):
        slug = events[0].get("slug")
        if slug:
            return str(slug)
    value = market.get("eventSlug") or market.get("event_slug")
    return "" if value in (None, "") else str(value)


def market_title(market: dict[str, Any]) -> str:
    return str(market.get("question") or market.get("title") or "")


def event_key_for_market(market: dict[str, Any]) -> str:
    return event_slug(market) or str(market.get("slug") or market.get("market_slug") or market_key(market))


def family_key_for_market(market: dict[str, Any]) -> str:
    slug = str(market.get("slug") or market.get("market_slug") or "")
    if slug:
        tokens = [token for token in slug.split("-") if token]
    else:
        normalized = re.sub(r"[^a-z0-9]+", "-", market_title(market).lower()).strip("-")
        tokens = [token for token in normalized.split("-") if token]
    if not tokens:
        return market_key(market)
    return "-".join(tokens[:3])


def market_status(market: dict[str, Any]) -> str:
    if market.get("closed") or str(market.get("status") or "").lower() == "closed":
        return "closed"
    if market.get("active"):
        return "open"
    return str(market.get("status") or "inactive")


def market_resolution(market: dict[str, Any]) -> str:
    direct = market.get("resolution")
    if direct not in (None, ""):
        return str(direct)

    winning_side = market.get("winning_side") or market.get("winningSide")
    if winning_side not in (None, ""):
        return str(winning_side)

    raw_outcomes = market.get("outcomes")
    raw_prices = market.get("outcomePrices")
    try:
        outcomes = json.loads(raw_outcomes) if isinstance(raw_outcomes, str) else (raw_outcomes or [])
        prices = json.loads(raw_prices) if isinstance(raw_prices, str) else (raw_prices or [])
        parsed_prices = [float(value) for value in prices]
    except (TypeError, ValueError, json.JSONDecodeError):
        return ""

    if not outcomes or len(outcomes) != len(parsed_prices):
        return ""
    best_index = max(range(len(parsed_prices)), key=parsed_prices.__getitem__)
    if parsed_prices[best_index] <= 0:
        return ""
    return str(outcomes[best_index])


def settlement_ts(market: dict[str, Any]) -> str:
    for key in ("closedTime", "resolvedAt", "settlement_ts", "settlementTs"):
        value = market.get(key)
        if value:
            return str(value)
    return ""


def market_close_time(market: dict[str, Any]) -> str:
    for key in ("endDate", "close_time", "closeTime"):
        value = market.get(key)
        if value:
            return str(value)
    return ""


def market_open_time(market: dict[str, Any]) -> str:
    for key in ("startDate", "open_time", "createdAt"):
        value = market.get(key)
        if value:
            return str(value)
    return ""


def build_text_blob(market: dict[str, Any], source_tag: str) -> str:
    parts = [
        market_title(market),
        event_slug(market),
        source_tag,
    ]
    events = market.get("events") or []
    if events and isinstance(events[0], dict):
        parts.append(str(events[0].get("title") or ""))
        parts.append(str(events[0].get("description") or ""))
    return " ".join(part for part in parts if part).lower()


def market_matches_window(market: dict[str, Any], window: PhaseWindow) -> bool:
    window_start = parse_utc_datetime(window.start_date)
    window_end = parse_utc_datetime(window.end_date)
    close_time = parse_optional_utc_datetime(market_close_time(market))
    if close_time is None or not (window_start <= close_time < window_end):
        return False
    return True


def count_keyword_hits(text: str, keywords: tuple[str, ...]) -> int:
    total = 0
    for keyword in keywords:
        if keyword in text:
            total += 1
    return total


def build_candidate(
    *,
    phase_name: str,
    config: CategoryConfig,
    source_tag: str,
    market: dict[str, Any],
) -> Candidate | None:
    key = market_key(market)
    if not key:
        return None

    text = build_text_blob(market, source_tag)
    if count_keyword_hits(text, GLOBAL_EXCLUDE_KEYWORDS):
        return None
    if count_keyword_hits(text, config.hard_exclude_keywords):
        return None

    topic_scores = {
        topic: count_keyword_hits(text, keywords)
        for topic, keywords in config.topic_keywords.items()
    }
    matched_topics = {topic: score for topic, score in topic_scores.items() if score > 0}
    title = market_title(market).lower()
    base_score = 30
    if matched_topics:
        base_score += sum(matched_topics.values()) * 12 + len(matched_topics) * 8
    elif source_tag in SUPPLEMENT_ONLY_TAGS.get(config.key, set()):
        return None
    elif config.allow_tag_fallback and any(tag_token in text for tag_token in source_tag.replace("-", " ").split()):
        base_score += 12
    else:
        return None

    if "?" in title:
        base_score += 2
    if event_slug(market):
        base_score += 2

    primary_topic = "misc"
    if matched_topics:
        primary_topic = sorted(
            matched_topics.items(),
            key=lambda item: (-item[1], item[0]),
        )[0][0]

    return Candidate(
        key=key,
        phase=phase_name,
        category_key=config.key,
        category_name=config.category,
        priority=config.priority,
        source_tag=source_tag,
        score=base_score,
        topic_scores=matched_topics,
        primary_topic=primary_topic,
        event_key=event_key_for_market(market),
        family_key=family_key_for_market(market),
        text=text,
        market=market,
    )


def normalize_categories(values: list[str]) -> list[CategoryConfig]:
    if not values:
        return list(CATEGORY_CONFIGS)
    keys: list[str] = []
    for value in values:
        for item in value.split(","):
            key = CATEGORY_NAME_LOOKUP.get(item.strip().lower())
            if key is None:
                valid = ", ".join(sorted(CATEGORY_NAME_LOOKUP))
                raise SystemExit(f"unknown category {item!r}; valid values include: {valid}")
            if key not in keys:
                keys.append(key)
    return [CATEGORY_CONFIG_BY_KEY[key] for key in keys]


def normalize_phases(values: list[str]) -> list[str]:
    if not values:
        return list(ALL_PHASE_NAMES)
    phases: list[str] = []
    for value in values:
        for item in value.split(","):
            phase = item.strip().lower()
            if phase not in PHASE_CONFIGS:
                valid = ", ".join(sorted(PHASE_CONFIGS))
                raise SystemExit(f"unknown phase {item!r}; valid values: {valid}")
            if phase not in phases:
                phases.append(phase)
    return phases


def collect_phase_candidates(
    *,
    client: GammaClient,
    phase_name: str,
    categories: list[CategoryConfig],
    page_limit: int,
    max_pages: int,
) -> dict[str, list[Candidate]]:
    phase = PHASE_CONFIGS[phase_name]
    by_category: dict[str, dict[str, Candidate]] = {config.key: {} for config in categories}

    for config in categories:
        windows = phase.windows
        direct_tags = config.historical_tags if phase.is_closed else config.future_tags
        related_tags = (
            config.historical_related_tag_slugs if phase.is_closed else config.future_related_tag_slugs
        )
        for window_index, window in enumerate(windows, start=1):
            for tag_slug in dict.fromkeys(direct_tags):
                markets = client.fetch_markets_for_tag(
                    phase_name=phase_name,
                    tag_slug=tag_slug,
                    window=window,
                    page_limit=page_limit,
                    max_pages=max_pages,
                    related_tags=False,
                )
                if not markets:
                    continue
                for market in markets:
                    if not market_matches_window(
                        market,
                        window,
                    ):
                        continue
                    candidate = build_candidate(
                        phase_name=phase_name,
                        config=config,
                        source_tag=tag_slug,
                        market=market,
                    )
                    if candidate is None:
                        continue
                    existing = by_category[config.key].get(candidate.key)
                    if existing is None or candidate.score > existing.score or (
                        candidate.score == existing.score and candidate.volume > existing.volume
                    ):
                        by_category[config.key][candidate.key] = candidate
            for tag_slug in dict.fromkeys(related_tags):
                markets = client.fetch_markets_for_tag(
                    phase_name=phase_name,
                    tag_slug=tag_slug,
                    window=window,
                    page_limit=page_limit,
                    max_pages=max_pages,
                    related_tags=True,
                )
                if not markets:
                    continue
                for market in markets:
                    if not market_matches_window(market, window):
                        continue
                    candidate = build_candidate(
                        phase_name=phase_name,
                        config=config,
                        source_tag=tag_slug,
                        market=market,
                    )
                    if candidate is None:
                        continue
                    existing = by_category[config.key].get(candidate.key)
                    if existing is None or candidate.score > existing.score or (
                        candidate.score == existing.score and candidate.volume > existing.volume
                    ):
                        by_category[config.key][candidate.key] = candidate
            if len(by_category[config.key]) >= DEFAULT_TARGET_PER_CATEGORY * 3:
                break
            print(
                f"{config.category} {phase_name}: window {window_index}/{len(windows)} "
                f"yielded {len(by_category[config.key])} unique scored candidates",
                file=sys.stderr,
                flush=True,
            )

    return {key: list(bucket.values()) for key, bucket in by_category.items()}


def assign_global_ownership(
    phase_name: str,
    candidates_by_category: dict[str, list[Candidate]],
) -> dict[str, list[Candidate]]:
    owned, _, _ = assign_global_ownership_details(phase_name, candidates_by_category)
    return owned


def assign_global_ownership_details(
    phase_name: str,
    candidates_by_category: dict[str, list[Candidate]],
) -> tuple[dict[str, list[Candidate]], dict[str, list[Candidate]], dict[str, str]]:
    by_market_key: dict[str, list[Candidate]] = defaultdict(list)
    for candidates in candidates_by_category.values():
        for candidate in candidates:
            by_market_key[candidate.key].append(candidate)

    owned: dict[str, list[Candidate]] = {key: [] for key in candidates_by_category}
    owner_by_market: dict[str, str] = {}
    multi_category_count = 0
    for market_key, options in by_market_key.items():
        if len(options) > 1:
            multi_category_count += 1
        winner = sorted(
            options,
            key=lambda candidate: (
                -candidate.score,
                -len(candidate.topic_scores),
                candidate.priority,
                -candidate.volume,
                candidate.category_name,
            ),
        )[0]
        owned[winner.category_key].append(winner)
        owner_by_market[market_key] = winner.category_key

    print(
        f"{phase_name}: assigned {len(by_market_key)} unique markets; "
        f"{multi_category_count} appeared in multiple categories before ownership resolution",
        file=sys.stderr,
        flush=True,
    )
    return owned, by_market_key, owner_by_market


def rebalance_minimum_counts(
    *,
    owned_by_category: dict[str, list[Candidate]],
    by_market_key: dict[str, list[Candidate]],
    owner_by_market: dict[str, str],
    minimum_count: int,
) -> None:
    if minimum_count <= 0:
        return

    progress = True
    while progress:
        progress = False
        counts = {category_key: len(candidates) for category_key, candidates in owned_by_category.items()}
        for category_key, count in sorted(counts.items(), key=lambda item: (item[1], item[0])):
            if count >= minimum_count:
                continue

            best_transfer: tuple[tuple[Any, ...], str, str, Candidate] | None = None
            for market_key, options in by_market_key.items():
                current_owner = owner_by_market.get(market_key)
                if current_owner in (None, category_key):
                    continue
                if counts.get(current_owner, 0) <= minimum_count:
                    continue

                target_option: Candidate | None = None
                current_option: Candidate | None = None
                for option in options:
                    if option.category_key == category_key and (
                        target_option is None
                        or option.score > target_option.score
                        or (option.score == target_option.score and option.volume > target_option.volume)
                    ):
                        target_option = option
                    if option.category_key == current_owner and (
                        current_option is None
                        or option.score > current_option.score
                        or (option.score == current_option.score and option.volume > current_option.volume)
                    ):
                        current_option = option

                if target_option is None or current_option is None:
                    continue

                rank = (
                    target_option.score - current_option.score,
                    len(target_option.topic_scores),
                    target_option.score,
                    counts[current_owner],
                    target_option.volume,
                    market_key,
                )
                if best_transfer is None or rank > best_transfer[0]:
                    best_transfer = (rank, market_key, current_owner, target_option)

            if best_transfer is None:
                continue

            _, market_key, donor_key, target_option = best_transfer
            owned_by_category[donor_key] = [
                candidate for candidate in owned_by_category[donor_key] if candidate.key != market_key
            ]
            owned_by_category[category_key].append(target_option)
            owner_by_market[market_key] = category_key
            progress = True


def select_diverse_candidates(
    candidates: list[Candidate],
    *,
    target_count: int,
    max_event_cap: int,
    max_family_cap: int,
) -> list[Candidate]:
    if not candidates:
        return []

    ordered = sorted(
        candidates,
        key=lambda candidate: (
            -candidate.score,
            -candidate.volume,
            candidate.close_time,
            candidate.key,
        ),
    )
    by_topic: dict[str, list[Candidate]] = defaultdict(list)
    for candidate in ordered:
        by_topic[candidate.primary_topic].append(candidate)

    selected: list[Candidate] = []
    selected_keys: set[str] = set()
    event_counts: Counter[str] = Counter()
    family_counts: Counter[str] = Counter()
    topic_counts: Counter[str] = Counter()

    cap_steps = [1, 2, 3, 4, 5, max_event_cap]
    family_steps = [6, 10, 14, 18, 24, max_family_cap]

    for event_cap in cap_steps:
        for family_cap in family_steps:
            progress = True
            while progress and len(selected) < target_count:
                progress = False
                topics = sorted(
                    by_topic,
                    key=lambda topic: (
                        topic_counts[topic],
                        topic,
                    ),
                )
                for topic in topics:
                    for candidate in by_topic[topic]:
                        if candidate.key in selected_keys:
                            continue
                        if event_counts[candidate.event_key] >= event_cap:
                            continue
                        if family_counts[candidate.family_key] >= family_cap:
                            continue
                        selected.append(candidate)
                        selected_keys.add(candidate.key)
                        event_counts[candidate.event_key] += 1
                        family_counts[candidate.family_key] += 1
                        topic_counts[candidate.primary_topic] += 1
                        progress = True
                        break
                    if len(selected) >= target_count:
                        break

    if len(selected) < target_count:
        for candidate in ordered:
            if candidate.key in selected_keys:
                continue
            if family_counts[candidate.family_key] >= max_family_cap * 2:
                continue
            selected.append(candidate)
            selected_keys.add(candidate.key)
            event_counts[candidate.event_key] += 1
            family_counts[candidate.family_key] += 1
            topic_counts[candidate.primary_topic] += 1
            if len(selected) >= target_count:
                break

    return selected[:target_count]


def market_row(category: str, market: dict[str, Any], *, is_closed_phase: bool) -> dict[str, Any]:
    volume = market_volume(market)
    resolution = market_resolution(market) if is_closed_phase else ""
    return {
        "category": category,
        "market_slug": str(market.get("slug") or market.get("market_slug") or ""),
        "event_slug": event_slug(market),
        "condition_id": market_key(market),
        "title": market_title(market),
        "resolution": resolution,
        "status": market_status(market),
        "open_time": market_open_time(market),
        "close_time": market_close_time(market),
        "settlement_ts": settlement_ts(market),
        "volume": "" if volume is None else format_number(volume),
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=MARKET_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def report_selection(
    *,
    phase_name: str,
    config: CategoryConfig,
    selected: list[Candidate],
) -> None:
    event_counts = Counter(candidate.event_key for candidate in selected)
    family_counts = Counter(candidate.family_key for candidate in selected)
    topic_counts = Counter(candidate.primary_topic for candidate in selected)
    print(
        f"{config.category} {phase_name}: selected={len(selected)} "
        f"unique_events={len(event_counts)} "
        f"top_events={event_counts.most_common(5)} "
        f"top_families={family_counts.most_common(5)} "
        f"topics={topic_counts.most_common()}",
        file=sys.stderr,
        flush=True,
    )


def pairwise_overlap(selected_by_category: dict[str, list[Candidate]]) -> int:
    seen: dict[str, str] = {}
    duplicates = 0
    for category_key, candidates in selected_by_category.items():
        for candidate in candidates:
            prior = seen.get(candidate.key)
            if prior is not None and prior != category_key:
                duplicates += 1
            seen[candidate.key] = category_key
    return duplicates


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build diverse, overlap-reduced Polymarket datasets for all categories.",
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--category", action="append", default=[], help="Optional category filter.")
    parser.add_argument("--phase", action="append", default=[], help="Optional phase filter: historical,future")
    parser.add_argument("--target-count", type=int, default=DEFAULT_TARGET_PER_CATEGORY)
    parser.add_argument(
        "--minimum-count",
        type=int,
        default=150,
        help="Try to rebalance overlapping markets so every category reaches at least this many rows when possible.",
    )
    parser.add_argument("--page-limit", type=int, default=DEFAULT_PAGE_LIMIT)
    parser.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES)
    parser.add_argument("--request-sleep", type=float, default=DEFAULT_REQUEST_SLEEP)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.target_count <= 0:
        raise SystemExit("--target-count must be positive")
    if args.minimum_count < 0:
        raise SystemExit("--minimum-count must be non-negative")
    if not 1 <= args.page_limit <= 100:
        raise SystemExit("--page-limit must be between 1 and 100")
    if args.max_pages <= 0:
        raise SystemExit("--max-pages must be positive")

    categories = normalize_categories(args.category)
    phases = normalize_phases(args.phase)
    client = GammaClient(base_url=args.base_url, request_sleep=args.request_sleep)

    for phase_name in phases:
        phase = PHASE_CONFIGS[phase_name]
        print(f"\n=== Building {phase_name} datasets ===", file=sys.stderr, flush=True)
        candidates_by_category = collect_phase_candidates(
            client=client,
            phase_name=phase_name,
            categories=categories,
            page_limit=args.page_limit,
            max_pages=args.max_pages,
        )
        owned, by_market_key, owner_by_market = assign_global_ownership_details(phase_name, candidates_by_category)
        rebalance_minimum_counts(
            owned_by_category=owned,
            by_market_key=by_market_key,
            owner_by_market=owner_by_market,
            minimum_count=args.minimum_count,
        )
        selected_by_category: dict[str, list[Candidate]] = {}

        for config in categories:
            selected = select_diverse_candidates(
                owned.get(config.key, []),
                target_count=args.target_count,
                max_event_cap=phase.max_event_cap,
                max_family_cap=phase.max_family_cap,
            )
            selected_by_category[config.key] = selected
            report_selection(phase_name=phase_name, config=config, selected=selected)

            if args.dry_run:
                continue

            output_path = csv_output_path(config.output_dir, phase.output_filename)
            rows = [
                market_row(config.category, candidate.market, is_closed_phase=phase.is_closed)
                for candidate in selected
            ]
            write_csv(output_path, rows)
            print(f"wrote {len(rows)} rows to {output_path}", file=sys.stderr, flush=True)

        duplicates = pairwise_overlap(selected_by_category)
        print(
            f"{phase_name}: remaining cross-category duplicates after selection = {duplicates}",
            file=sys.stderr,
            flush=True,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
