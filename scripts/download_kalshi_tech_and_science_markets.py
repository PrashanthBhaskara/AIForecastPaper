#!/usr/bin/env python3
"""Download Kalshi Science and Technology market metadata to Research/ScienceTechnologyMarkets."""

from kalshi_market_downloader import main


if __name__ == "__main__":
    raise SystemExit(
        main(
            default_category="Science and Technology",
            default_output_dir="Research/ScienceTechnologyMarkets",
        )
    )
