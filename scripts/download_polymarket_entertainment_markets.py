#!/usr/bin/env python3
"""Download Polymarket Entertainment market metadata to Research/EntertainmentMarkets."""

from polymarket_market_downloader import main


if __name__ == "__main__":
    raise SystemExit(
        main(
            default_category="Entertainment",
            default_tags=("Entertainment",),
            default_output_dir="Research/EntertainmentMarkets",
        )
    )
