#!/usr/bin/env python3
"""Download Kalshi Companies market candlesticks to Research/CompaniesMarkets."""

from download_kalshi_climate_markets import main


if __name__ == "__main__":
    raise SystemExit(
        main(
            default_category="Companies",
            default_output_dir="Research/CompaniesMarkets",
        )
    )
