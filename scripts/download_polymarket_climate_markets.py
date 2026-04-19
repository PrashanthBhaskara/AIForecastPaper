#!/usr/bin/env python3
"""Download Polymarket Climate and Weather market metadata to Research/ClimateMarkets."""

from polymarket_market_downloader import main


if __name__ == "__main__":
    raise SystemExit(
        main(
            default_category="Climate and Weather",
            default_tags=("Weather", "Climate"),
            default_output_dir="Research/ClimateMarkets",
            default_start_date="2023-01-01",
            default_end_date="2025-01-01",
        )
    )
