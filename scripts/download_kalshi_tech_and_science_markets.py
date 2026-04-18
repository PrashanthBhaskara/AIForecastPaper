#!/usr/bin/env python3
"""Download Kalshi Science and Technology market metadata to Research/ScienceTechnologyMarkets."""

from download_kalshi_climate_markets import main


if __name__ == "__main__":
    raise SystemExit(
        main(
            default_category="Science and Technology",
            default_output_dir="Research/ScienceTechnologyMarkets",
        )
    )
