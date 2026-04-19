#!/usr/bin/env python3
"""Download Polymarket Financials market metadata to Research/FinancialsMarkets."""

from polymarket_market_downloader import main


if __name__ == "__main__":
    raise SystemExit(
        main(
            default_category="Financials",
            default_tags=("Finance",),
            default_output_dir="Research/FinancialsMarkets",
        )
    )
