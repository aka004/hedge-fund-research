#!/usr/bin/env python3
"""Fetch S&P 500 data and store in Parquet.

This script:
1. Checks current data status (what's already cached)
2. Fetches missing or outdated data
3. Stores to Parquet for the Momentum Researcher

Usage:
    # Check data status only (no fetch)
    python scripts/fetch_data.py --status

    # Fetch all missing data for S&P 500
    python scripts/fetch_data.py --universe sp500 --years 7

    # Fetch specific symbols
    python scripts/fetch_data.py --symbols AAPL MSFT GOOGL --years 7

    # Force re-fetch (ignore cache)
    python scripts/fetch_data.py --universe sp500 --years 7 --force
"""

import argparse
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from data.providers.yahoo import YahooFinanceProvider
from data.storage.parquet import ParquetStorage
from data.storage.universe import SP500_SYMBOLS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Default storage path
DEFAULT_STORAGE_PATH = Path(__file__).parent.parent / "data" / "cache"


class DataStatus:
    """Track data status for a symbol."""

    def __init__(
        self,
        symbol: str,
        has_data: bool = False,
        first_date: date | None = None,
        last_date: date | None = None,
        row_count: int = 0,
    ):
        self.symbol = symbol
        self.has_data = has_data
        self.first_date = first_date
        self.last_date = last_date
        self.row_count = row_count

    @property
    def years_of_data(self) -> float:
        if self.first_date and self.last_date:
            return (self.last_date - self.first_date).days / 365
        return 0.0

    @property
    def days_stale(self) -> int:
        """Days since last data point."""
        if self.last_date:
            return (date.today() - self.last_date).days
        return 999

    def needs_update(self, required_years: int, max_stale_days: int = 3) -> bool:
        """Check if this symbol needs data update."""
        if not self.has_data:
            return True
        if self.years_of_data < required_years - 0.1:  # Allow 10% slack
            return True
        if self.days_stale > max_stale_days:
            return True
        return False


def get_data_status(
    storage: ParquetStorage, symbols: list[str]
) -> dict[str, DataStatus]:
    """Get current data status for all symbols."""
    status = {}

    for symbol in symbols:
        df = storage.load_prices(symbol)
        if df is not None and len(df) > 0:
            status[symbol] = DataStatus(
                symbol=symbol,
                has_data=True,
                first_date=df["date"].min(),
                last_date=df["date"].max(),
                row_count=len(df),
            )
        else:
            status[symbol] = DataStatus(symbol=symbol, has_data=False)

    return status


def print_status_report(status: dict[str, DataStatus], required_years: int) -> None:
    """Print a status report of all symbols."""
    print("\n" + "=" * 70)
    print("DATA STATUS REPORT")
    print("=" * 70)
    print(
        f"{'Symbol':<8} {'Status':<12} {'Rows':>7} {'Years':>6} {'Stale':>6} {'Action'}"
    )
    print("-" * 70)

    complete = 0
    needs_update = 0
    missing = 0

    for symbol, s in sorted(status.items()):
        if not s.has_data:
            action = "FETCH"
            status_str = "MISSING"
            missing += 1
        elif s.needs_update(required_years):
            action = "UPDATE"
            status_str = "STALE" if s.days_stale > 3 else "INCOMPLETE"
            needs_update += 1
        else:
            action = "-"
            status_str = "OK"
            complete += 1

        print(
            f"{symbol:<8} {status_str:<12} {s.row_count:>7} "
            f"{s.years_of_data:>5.1f}y {s.days_stale:>5}d {action}"
        )

    print("-" * 70)
    print(f"Complete: {complete} | Needs update: {needs_update} | Missing: {missing}")
    print("=" * 70 + "\n")


def fetch_symbol(
    provider: YahooFinanceProvider,
    storage: ParquetStorage,
    symbol: str,
    start_date: date,
    end_date: date,
    current_status: DataStatus | None = None,
) -> bool:
    """Fetch data for a single symbol."""
    try:
        # If we have data, only fetch from the last date
        if current_status and current_status.has_data and current_status.last_date:
            fetch_start = current_status.last_date + timedelta(days=1)
            if fetch_start >= end_date:
                logger.debug(f"{symbol}: Already up to date")
                return True
        else:
            fetch_start = start_date

        logger.info(f"{symbol}: Fetching {fetch_start} to {end_date}")
        df = provider.get_historical_prices(symbol, fetch_start, end_date)

        if df is not None and len(df) > 0:
            storage.save_prices(symbol, df)
            logger.info(f"{symbol}: Saved {len(df)} rows")
            return True
        else:
            logger.warning(f"{symbol}: No data returned")
            return False

    except Exception as e:
        logger.error(f"{symbol}: Failed - {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Fetch and cache S&P 500 data")
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show data status only, don't fetch",
    )
    parser.add_argument(
        "--universe",
        choices=["sp500"],
        help="Universe to fetch (sp500)",
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        help="Specific symbols to fetch",
    )
    parser.add_argument(
        "--years",
        type=int,
        default=7,
        help="Years of history to fetch (default: 7)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-fetch, ignore cache",
    )
    parser.add_argument(
        "--storage-path",
        type=Path,
        default=DEFAULT_STORAGE_PATH,
        help="Path to Parquet storage",
    )

    args = parser.parse_args()

    # Initialize storage
    storage = ParquetStorage(args.storage_path)
    provider = YahooFinanceProvider()

    # Determine symbols to process
    if args.symbols:
        symbols = args.symbols
    elif args.universe == "sp500":
        symbols = SP500_SYMBOLS
    else:
        symbols = SP500_SYMBOLS  # Default

    logger.info(f"Processing {len(symbols)} symbols")

    # Get current status
    status = get_data_status(storage, symbols)

    # Print status report
    print_status_report(status, args.years)

    # Exit if status-only mode
    if args.status:
        return

    # Calculate date range
    end_date = date.today()
    start_date = end_date - timedelta(days=args.years * 365 + 30)  # Extra buffer

    # Fetch data
    success_count = 0
    fail_count = 0

    for symbol in symbols:
        current = status.get(symbol)

        # Skip if up to date (unless force)
        if not args.force and current and not current.needs_update(args.years):
            logger.debug(f"{symbol}: Skipping (up to date)")
            success_count += 1
            continue

        if fetch_symbol(provider, storage, symbol, start_date, end_date, current):
            success_count += 1
        else:
            fail_count += 1

    # Print summary
    print("\n" + "=" * 40)
    print(f"FETCH COMPLETE: {success_count} success, {fail_count} failed")
    print("=" * 40)

    # Show updated status
    if not args.status:
        updated_status = get_data_status(storage, symbols)
        print_status_report(updated_status, args.years)


if __name__ == "__main__":
    main()
