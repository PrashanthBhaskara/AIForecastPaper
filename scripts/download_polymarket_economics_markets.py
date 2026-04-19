#!/usr/bin/env python3
"""Download Polymarket Economics market metadata to Research/EconomicsMarkets."""

from polymarket_market_downloader import main


if __name__ == "__main__":
    raise SystemExit(
        main(
            default_category="Economics",
            default_tags=(
                "Economics",
                "Economy",
                "Inflation",
                "Fed",
                "Fed Rates",
                "Economic Policy",
                "Jerome Powell",
                "Jobs",
                "Interest Rates",
                "Unemployment",
            ),
            default_output_dir="Research/EconomicsMarkets",
            default_start_date="2023-01-01",
            default_end_date="2025-01-01",
        )
    )
