#!/usr/bin/env python3
"""Download Kalshi Commodities market metadata to Research/CommoditiesMarkets."""

from download_kalshi_climate_markets import main


if __name__ == "__main__":
    raise SystemExit(
        main(
            default_category="Commodities",
            default_output_dir="Research/CommoditiesMarkets",
        )
    )
