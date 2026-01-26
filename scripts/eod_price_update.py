#!/usr/bin/env python3
"""End-of-day price update script.

Fetches latest prices for all symbols in storage after market close.
Designed to run via cron at 1:30 PM PST (4:30 PM EST).

Usage:
    python scripts/eod_price_update.py              # Update all symbols in storage
    python scripts/eod_price_update.py --symbols INTC AAPL  # Update specific symbols
    python scripts/eod_price_update.py --dry-run    # Show what would be updated
"""

import argparse
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

PARQUET_DIR = Path(__file__).parent.parent / "data" / "storage" / "parquet" / "prices"


def get_stored_symbols() -> list[str]:
    """Get list of symbols with existing parquet files."""
    if not PARQUET_DIR.exists():
        return []
    return [f.stem for f in PARQUET_DIR.glob("*.parquet")]


def update_symbol(symbol: str, dry_run: bool = False) -> tuple[bool, str]:
    """Update price data for a single symbol.
    
    Returns (success, message).
    """
    parquet_path = PARQUET_DIR / f"{symbol}.parquet"
    
    if not parquet_path.exists():
        return False, f"No existing data file"
    
    try:
        # Load existing
        existing = pd.read_parquet(parquet_path)
        last_date = pd.to_datetime(existing['date'].max()).date()
        
        # Skip if already up to date
        today = date.today()
        if last_date >= today:
            return True, f"Already current ({last_date})"
        
        if dry_run:
            return True, f"Would update from {last_date} to {today}"
        
        # Fetch new data
        start = last_date + timedelta(days=1)
        end = today + timedelta(days=1)
        
        ticker = yf.Ticker(symbol)
        new_df = ticker.history(start=start.isoformat(), end=end.isoformat(), auto_adjust=False)
        
        if len(new_df) == 0:
            return True, f"No new data since {last_date}"
        
        # Normalize
        new_df = new_df.reset_index()
        new_df.columns = new_df.columns.str.lower().str.replace(' ', '_')
        new_df['date'] = pd.to_datetime(new_df['date']).dt.tz_localize(None)
        
        # Select columns that exist
        required_cols = ['date', 'open', 'high', 'low', 'close', 'volume', 'adj_close']
        available_cols = [c for c in required_cols if c in new_df.columns]
        new_df = new_df[available_cols]
        
        # Combine and dedupe
        combined = pd.concat([existing, new_df], ignore_index=True)
        combined = combined.drop_duplicates(subset=['date'], keep='last')
        combined = combined.sort_values('date').reset_index(drop=True)
        
        # Save
        combined.to_parquet(parquet_path, index=False)
        new_last = pd.to_datetime(combined['date'].max()).date()
        
        return True, f"Updated: {last_date} -> {new_last} (+{len(new_df)} rows)"
        
    except Exception as e:
        return False, f"Error: {e}"


def main():
    parser = argparse.ArgumentParser(description="End-of-day price update")
    parser.add_argument("--symbols", nargs="+", help="Specific symbols to update")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be updated")
    args = parser.parse_args()
    
    # Get symbols
    if args.symbols:
        symbols = [s.upper() for s in args.symbols]
    else:
        symbols = get_stored_symbols()
    
    if not symbols:
        logger.warning("No symbols to update")
        return 1
    
    logger.info(f"Updating {len(symbols)} symbols" + (" (dry run)" if args.dry_run else ""))
    
    success = 0
    failed = 0
    
    for symbol in sorted(symbols):
        ok, msg = update_symbol(symbol, args.dry_run)
        status = "OK" if ok else "FAIL"
        logger.info(f"{symbol}: {status} - {msg}")
        if ok:
            success += 1
        else:
            failed += 1
    
    logger.info(f"Complete: {success} success, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
