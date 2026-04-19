#!/usr/bin/env python3
"""Download Polymarket Companies market metadata to Research/CompaniesMarkets.

Polymarket's canonical tag for corporate/business markets is ``Business`` (the
literal ``Companies`` tag causes 504s on Dome API as of 2026-04).
"""

from polymarket_market_downloader import main


if __name__ == "__main__":
    raise SystemExit(
        main(
            default_category="Companies",
            default_tags=("Business",),
            default_output_dir="Research/CompaniesMarkets",
            default_start_date="2023-01-01",
            default_end_date="2025-01-01",
        )
    )
