#!/usr/bin/env python3
"""Download Kalshi Financials market metadata to Research/FinancialsMarkets."""

from kalshi_market_downloader import main


if __name__ == "__main__":
    raise SystemExit(
        main(
            default_category="Financials",
            default_output_dir="Research/FinancialsMarkets",
        )
    )
