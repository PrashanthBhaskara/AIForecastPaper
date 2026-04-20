#!/usr/bin/env python3
"""Download Polymarket Science and Technology market metadata to Research/ScienceTechnologyMarkets."""

from polymarket_market_downloader import main


if __name__ == "__main__":
    raise SystemExit(
        main(
            default_category="Science and Technology",
            default_tags=("Science", "Tech"),
            default_output_dir="Research/ScienceTechnologyMarkets",
            default_start_date="2023-01-01",
            default_end_date="2025-01-01",
            default_exclude_keywords=(
                "tsunami",
                "megaquake",
                "earthquake",
                "volcanic eruption",
                "hurricane",
            ),
        )
    )
