#!/usr/bin/env python3
"""Download Polymarket Economics market metadata to Research/EconomicsMarkets."""

from polymarket_market_downloader import main


if __name__ == "__main__":
    raise SystemExit(
        main(
            default_category="Economics",
            default_tags=("Economics",),
            default_output_dir="Research/EconomicsMarkets",
        )
    )
