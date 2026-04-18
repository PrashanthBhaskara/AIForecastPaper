#!/usr/bin/env python3
"""Download Kalshi Politics market metadata to Research/PoliticsMarkets."""

from download_kalshi_climate_markets import main


if __name__ == "__main__":
    raise SystemExit(
        main(
            default_category="Politics",
            default_output_dir="Research/PoliticsMarkets",
        )
    )
