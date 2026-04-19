#!/usr/bin/env python3
"""Download Polymarket Politics market metadata to Research/PoliticsMarkets."""

from polymarket_market_downloader import main


if __name__ == "__main__":
    raise SystemExit(
        main(
            default_category="Politics",
            default_tags=("Politics",),
            default_output_dir="Research/PoliticsMarkets",
        )
    )
