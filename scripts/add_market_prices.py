#!/usr/bin/env python3
"""
For every forecast JSON in Research/*/forecast/*.json, fetch the current
Polymarket price via the gamma API using market_slug, and add a
`market_price` field if not already present. Skips records that already
have `market_price` or where the API returns no price data.
"""

import json
import os
import time
import requests

RESEARCH_DIR = os.path.join(os.path.dirname(__file__), "..", "Research")
GAMMA_API = "https://gamma-api.polymarket.com"
RATE_DELAY = 0.2  # seconds between API calls


def fetch_market_price(market_slug: str) -> dict | None:
    """Return {outcome: price, ...} for the given slug, or None on failure."""
    try:
        r = requests.get(
            f"{GAMMA_API}/markets",
            params={"slug": market_slug},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"    [warn] API error for {market_slug}: {e}")
        return None

    markets = data if isinstance(data, list) else [data]
    for market in markets:
        raw_outcomes = market.get("outcomes", "[]")
        raw_prices = market.get("outcomePrices", "[]")
        try:
            outcomes = json.loads(raw_outcomes) if isinstance(raw_outcomes, str) else raw_outcomes
            prices = json.loads(raw_prices) if isinstance(raw_prices, str) else raw_prices
        except Exception:
            continue

        if outcomes and prices and len(outcomes) == len(prices):
            return {outcome: float(price) for outcome, price in zip(outcomes, prices)}

    return None


def process_file(path: str) -> None:
    with open(path, "r", encoding="utf-8") as f:
        records = json.load(f)

    changed = False
    for record in records:
        if "market_price" in record:
            continue

        slug = record.get("market_slug", "")
        if not slug:
            continue

        price = fetch_market_price(slug)
        time.sleep(RATE_DELAY)

        if price is None:
            print(f"    [skip] no price returned for: {slug}")
            continue

        record["market_price"] = price
        changed = True
        print(f"    [ok] {slug}: {price}")

    if changed:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2, ensure_ascii=False)
        print(f"  -> saved {path}")
    else:
        print(f"  -> no changes ({path})")


def main() -> None:
    research_dir = os.path.abspath(RESEARCH_DIR)
    forecast_files = []
    for entry in os.scandir(research_dir):
        if not entry.is_dir():
            continue
        forecast_dir = os.path.join(entry.path, "forecast")
        if not os.path.isdir(forecast_dir):
            continue
        for fname in os.listdir(forecast_dir):
            if fname.endswith(".json"):
                forecast_files.append(os.path.join(forecast_dir, fname))

    forecast_files.sort()
    print(f"Found {len(forecast_files)} forecast file(s).\n")

    for path in forecast_files:
        print(f"Processing: {path}")
        process_file(path)
        print()

    print("Done.")


if __name__ == "__main__":
    main()
