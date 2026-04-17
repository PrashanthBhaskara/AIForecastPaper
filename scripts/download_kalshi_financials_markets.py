#!/usr/bin/env python3
"""Download Kalshi Financials market candlesticks to Research/FinancialsMarkets."""

from download_kalshi_climate_markets import main


if __name__ == "__main__":
    raise SystemExit(
        main(
            default_category="Financials",
            default_output_dir="Research/FinancialsMarkets",
        )
    )
