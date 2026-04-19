#!/usr/bin/env python3
"""Download Polymarket Commodities market metadata to Research/CommoditiesMarkets."""

from polymarket_market_downloader import main


if __name__ == "__main__":
    raise SystemExit(
        main(
            default_category="Commodities",
            default_tags=(
                "Oil",
                "Gas",
                "crude oil",
                "commodity market",
                "energy market",
                "energy industry",
                "oil production",
                "Crypto",
            ),
            default_output_dir="Research/CommoditiesMarkets",
            default_start_date="2023-01-01",
            default_end_date="2025-01-01",
        )
    )
