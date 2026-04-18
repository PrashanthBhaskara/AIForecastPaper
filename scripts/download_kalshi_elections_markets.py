#!/usr/bin/env python3
"""Download Kalshi Elections market metadata to Research/ElectionsMarkets."""

from download_kalshi_climate_markets import main


if __name__ == "__main__":
    raise SystemExit(
        main(
            default_category="Elections",
            default_output_dir="Research/ElectionsMarkets",
            default_start_date="2023-01-01",
            default_end_date="2024-09-01",
        )
    )
