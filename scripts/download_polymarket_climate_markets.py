#!/usr/bin/env python3
"""Download Polymarket Climate and Weather market metadata to Research/ClimateMarkets."""

from polymarket_market_downloader import main


if __name__ == "__main__":
    raise SystemExit(
        main(
            default_category="Climate and Weather",
            default_tags=("Weather",),
            default_output_dir="Research/ClimateMarkets",
        )
    )
