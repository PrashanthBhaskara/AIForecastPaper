#!/usr/bin/env python3
"""
Fetch the 150 highest-volume closed Polymarket markets per domain (2023-2024).
Phase 1: primary tags (no keyword filter).
Phase 2: supplement from broader tags using keyword filter if < 150.
Saves as markets_2023_2024.csv; keywords column identifies each domain.
"""

import requests
import csv
import os
import time
import json

BASE_DIR = "/Users/shubhaankargupta/Downloads/AIForecastPaper/research"
GAMMA_API = "https://gamma-api.polymarket.com"
TARGET_COUNT = 150

# (dir_name, display_name, primary_tags, supplement_tags, supplement_kws, display_kws)
#  primary_tags     → fetch all, no keyword filter
#  supplement_tags  → keyword-filtered supplement if still < 150
#  supplement_kws   → keywords used ONLY to filter supplement markets
#  display_kws      → 10 identification keywords written to the 'keywords' CSV column
CATEGORY_CONFIGS = [
    (
        "CommoditiesMarkets", "Commodities",
        ["crypto", "commodities"],                          # primary tags
        [],                                                  # no supplement needed
        [],
        ["bitcoin", "ethereum", "cryptocurrency", "crypto", "btc",
         "eth", "solana", "token", "blockchain", "commodity"],
    ),
    (
        "ElectionsMarkets", "Elections",
        ["elections"],
        [],
        [],
        ["election", "vote", "candidate", "president", "primary",
         "ballot", "senate", "congress", "polling", "democrat"],
    ),
    (
        "CompaniesMarkets", "Companies",
        ["business", "companies"],
        [],
        [],
        ["company", "ceo", "earnings", "acquisition", "ipo",
         "merger", "revenue", "quarterly", "corporate", "stock"],
    ),
    (
        "ClimateMarkets", "Climate and Weather",
        ["climate", "weather"],
        ["science"],                                         # supplement from science tag
        ["temperature", "heat", "hottest", "hurricane", "storm",
         "earthquake", "flood", "wildfire", "climate", "weather",
         "cyclone", "rainfall", "tornado", "drought", "celsius",
         "record", "degree", "warming", "arctic", "typhoon"],
        ["climate", "weather", "hurricane", "temperature", "storm",
         "earthquake", "flood", "wildfire", "cyclone", "rainfall"],
    ),
    (
        "EntertainmentMarkets", "Entertainment",
        ["pop-culture", "entertainment"],
        [],
        [],
        ["oscar", "movie", "film", "award", "celebrity",
         "music", "album", "box office", "streaming", "actor"],
    ),
    (
        "EconomicsMarkets", "Economics",
        ["economics"],
        ["business", "finance", "news", "current-events"],  # supplement
        ["fed", "rate", "inflation", "cpi", "gdp", "unemployment",
         "recession", "fomc", "treasury", "powell", "economic",
         "fiscal", "monetary", "interest", "hike", "cut",
         "bps", "basis point", "central bank", "deficit", "debt"],
        ["inflation", "gdp", "unemployment", "recession", "cpi",
         "fomc", "interest rate", "federal reserve", "treasury", "economic"],
    ),
    (
        "ScienceTechnologyMarkets", "Science and Technology",
        ["science", "technology"],
        [],
        [],
        ["ai", "artificial intelligence", "nasa", "space", "launch",
         "research", "discovery", "gaming", "technology", "science"],
    ),
    (
        "PoliticsMarkets", "Politics",
        ["politics", "us-politics"],
        [],
        [],
        ["trump", "biden", "congress", "senate", "policy",
         "legislation", "debate", "rally", "administration", "political"],
    ),
    (
        "FinancialsMarkets", "Financials",
        ["finance", "financials"],
        [],
        [],
        ["stock", "market", "nasdaq", "s&p", "dow",
         "etf", "fed", "interest rate", "financial", "index"],
    ),
]

CSV_COLUMNS = [
    "category", "market_slug", "event_slug", "condition_id",
    "title", "resolution", "status",
    "open_time", "close_time", "settlement_ts", "volume", "keywords",
]


def parse_datetime(dt_str):
    if not dt_str:
        return ""
    s = str(dt_str).strip()
    if "T" not in s and "+00" in s:
        s = s.split("+00")[0].split(".")[0].replace(" ", "T") + "Z"
    elif "+00:00" in s:
        s = s.split("+00:00")[0] + "Z"
    elif "+00" in s and "T" in s:
        s = s.split("+00")[0] + "Z"
    return s


def get_resolution(market):
    try:
        raw_o = market.get("outcomes", "[]")
        raw_p = market.get("outcomePrices", "[]")
        outcomes = json.loads(raw_o) if isinstance(raw_o, str) else raw_o
        prices   = json.loads(raw_p) if isinstance(raw_p, str) else raw_p
        if not outcomes or not prices or len(outcomes) != len(prices):
            return "N/A"
        fp = [float(p) for p in prices]
        mx = max(fp)
        if mx == 0:
            return "N/A"
        return str(outcomes[fp.index(mx)])
    except Exception:
        return "N/A"


def market_to_row(market, event_slug, category_name, keywords_str):
    close_time    = parse_datetime(market.get("endDate", ""))
    settlement_ts = parse_datetime(market.get("closedTime", close_time))
    open_time     = parse_datetime(market.get("startDate", ""))
    try:
        volume = float(market.get("volume", market.get("volumeNum", 0)) or 0)
    except Exception:
        volume = 0.0
    return {
        "category":      category_name,
        "market_slug":   market.get("slug", ""),
        "event_slug":    event_slug,
        "condition_id":  market.get("conditionId", ""),
        "title":         market.get("question", ""),
        "resolution":    get_resolution(market),
        "status":        "closed",
        "open_time":     open_time,
        "close_time":    close_time,
        "settlement_ts": settlement_ts,
        "volume":        volume,
        "keywords":      keywords_str,
    }


def fetch_events(tag_slug, offset=0, limit=100):
    params = {
        "closed":       "true",
        "tag_slug":     tag_slug,
        "limit":        limit,
        "offset":       offset,
        "end_date_min": "2023-01-01T00:00:00Z",
        "end_date_max": "2024-12-31T23:59:59Z",
    }
    try:
        r = requests.get(f"{GAMMA_API}/events", params=params, timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"    [warn] tag={tag_slug} offset={offset}: {e}")
        return []


def harvest(tag_slug, seen, keyword_filter=None):
    """Yield (market, event_slug) pairs from a tag. Optional keyword filter."""
    offset = 0
    added = 0
    while True:
        events = fetch_events(tag_slug, offset=offset)
        if not events:
            break
        for event in events:
            event_slug = event.get("slug", "")
            for market in event.get("markets", []):
                cid = market.get("conditionId", "")
                if not cid or cid in seen:
                    continue
                if not market.get("closed", False):
                    continue
                end_date = market.get("endDate", "")
                if not end_date or int(end_date[:4]) not in (2023, 2024):
                    continue
                if keyword_filter:
                    title = market.get("question", "").lower()
                    if not any(kw.lower() in title for kw in keyword_filter):
                        continue
                seen.add(cid)
                added += 1
                yield market, event_slug
        if len(events) < 100:
            break
        offset += 100
        time.sleep(0.2)
    print(f" {added}", end="", flush=True)


def collect(primary_tags, supplement_tags, supplement_kws, category_name, keywords_str):
    seen = set()
    all_entries = []

    # Phase 1: primary tags, no keyword filter
    for tag in primary_tags:
        print(f"  primary tag={tag} ...", end="", flush=True)
        for m, es in harvest(tag, seen):
            all_entries.append((m, es))
        print()

    # Phase 2: supplement if still < TARGET_COUNT
    if supplement_tags and len(all_entries) < TARGET_COUNT:
        print(f"  [{len(all_entries)} so far, supplementing]")
        for tag in supplement_tags:
            if len(all_entries) >= TARGET_COUNT * 3:   # stop fetching once we have plenty
                break
            print(f"  suppl  tag={tag} (kw-filtered) ...", end="", flush=True)
            for m, es in harvest(tag, seen, keyword_filter=supplement_kws):
                all_entries.append((m, es))
            print()

    # Sort by volume descending, take top 150
    all_entries.sort(
        key=lambda x: float(x[0].get("volume", x[0].get("volumeNum", 0)) or 0),
        reverse=True,
    )
    rows = [market_to_row(m, es, category_name, keywords_str) for m, es in all_entries[:TARGET_COUNT]]
    return rows


def save_csv(rows, filepath):
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def main():
    for dir_name, category_name, primary_tags, supplement_tags, supplement_kws, display_kws in CATEGORY_CONFIGS:
        keywords_str = "; ".join(display_kws)
        out_file = os.path.join(BASE_DIR, dir_name, "markets_2023_2024.csv")

        print(f"\n{'='*62}")
        print(f"{category_name}  [{dir_name}]")
        print(f"  Keywords: {keywords_str}")

        rows = collect(primary_tags, supplement_tags, supplement_kws, category_name, keywords_str)
        save_csv(rows, out_file)
        print(f"  → Saved {len(rows)} markets (top by volume)  →  {out_file}")

    print("\nDone.")


if __name__ == "__main__":
    main()
