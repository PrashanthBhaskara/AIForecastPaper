#!/usr/bin/env python3
"""Download Kalshi Companies market metadata to Research/CompaniesMarkets."""

from kalshi_market_downloader import main


if __name__ == "__main__":
    raise SystemExit(
        main(
            default_category="Companies",
            default_output_dir="Research/CompaniesMarkets",
        )
    )
