#!/usr/bin/env python3
"""Download Kalshi Entertainment market metadata to Research/EntertainmentMarkets."""

from kalshi_market_downloader import main


if __name__ == "__main__":
    raise SystemExit(
        main(
            default_category="Entertainment",
            default_output_dir="Research/EntertainmentMarkets",
        )
    )
