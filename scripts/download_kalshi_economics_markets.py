#!/usr/bin/env python3
"""Download Kalshi Economics market metadata to Research/EconomicsMarkets."""

from kalshi_market_downloader import main


if __name__ == "__main__":
    raise SystemExit(
        main(
            default_category="Economics",
            default_output_dir="Research/EconomicsMarkets",
        )
    )
