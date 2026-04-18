#!/usr/bin/env python3
"""Download Kalshi Science and Technology market metadata to Research/ScienceTechnologyMarkets."""

from kalshi_market_downloader import main


if __name__ == "__main__":
    raise SystemExit(
        main(
            default_category="Science and Technology",
            default_output_dir="Research/ScienceTechnologyMarkets",
            default_start_date="2020-01-01",
            default_end_date="2024-08-01",
        )
    )
