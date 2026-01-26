#!/usr/bin/env python3
"""CLI script to fetch and update politician trade data from SEC EDGAR."""

import argparse
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

import yaml

from agents.data_pipeline import DataPipelineAgent
from agents.events import EventBus
from config import POLITICIAN_WATCHLIST_PATH, STORAGE_PATH

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def load_politicians() -> list[dict]:
    """Load politician watchlist from YAML."""
    if not POLITICIAN_WATCHLIST_PATH.exists():
        logger.error(f"Politician watchlist not found: {POLITICIAN_WATCHLIST_PATH}")
        sys.exit(1)
    
    with open(POLITICIAN_WATCHLIST_PATH) as f:
        watchlist = yaml.safe_load(f)
    
    return watchlist.get("politicians", [])


def list_politicians() -> None:
    """List all politicians in watchlist."""
    politicians = load_politicians()
    
    print(f"\nPolitician Watchlist ({len(politicians)} politicians):")
    print("=" * 80)
    
    for pol in politicians:
        print(f"  {pol.get('name', 'Unknown')}")
        print(f"    CIK: {pol.get('cik', 'N/A')}")
        print(f"    Role: {pol.get('role', 'N/A')}")
        print(f"    Party: {pol.get('party', 'N/A')}")
        if pol.get("notes"):
            print(f"    Notes: {pol.get('notes')}")
        print()


def fetch_trades(
    politician_name: str | None = None,
    all_politicians: bool = False,
    days_back: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> None:
    """Fetch politician trades from free House Stock Watcher data."""
    # Initialize data pipeline
    event_bus = EventBus()
    pipeline = DataPipelineAgent(event_bus, cache_path=STORAGE_PATH)
    
    # Determine date range
    if days_back:
        end_date = date.today()
        start_date = end_date - timedelta(days=days_back)
    elif not start_date:
        # Default: last 90 days
        end_date = date.today()
        start_date = end_date - timedelta(days=90)
    
    logger.info(f"Fetching trades from {start_date} to {end_date}")
    
    # Fetch trades
    result = pipeline.fetch_politician_trades(
        politician_name=politician_name if not all_politicians else None,
        start_date=start_date,
        end_date=end_date,
    )
    
    # Print results
    print("\n" + "=" * 80)
    print("Fetch Results:")
    print("=" * 80)
    
    if result["success"]:
        print(f"✅ Successfully fetched {result['rows']} trades")
        if result.get("failed"):
            print(f"⚠️  Failed politicians: {', '.join(result['failed'])}")
    else:
        print(f"❌ Error: {result.get('error', 'Unknown error')}")
        if result.get("failed"):
            print(f"   Failed politicians: {', '.join(result['failed'])}")
        sys.exit(1)


def main() -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Fetch politician stock trades from free House Stock Watcher data"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # List command
    list_parser = subparsers.add_parser("list", help="List politicians in watchlist")
    
    # Fetch command
    fetch_parser = subparsers.add_parser("fetch", help="Fetch politician trades from Quiver")
    
    fetch_group = fetch_parser.add_mutually_exclusive_group(required=True)
    fetch_group.add_argument(
        "--politician",
        type=str,
        help="Name of specific politician to fetch",
    )
    fetch_group.add_argument(
        "--all",
        action="store_true",
        help="Fetch trades for all politicians in watchlist",
    )
    
    fetch_parser.add_argument(
        "--days-back",
        type=int,
        help="Number of days to look back (default: 90)",
    )
    fetch_parser.add_argument(
        "--start-date",
        type=str,
        help="Start date (YYYY-MM-DD)",
    )
    fetch_parser.add_argument(
        "--end-date",
        type=str,
        help="End date (YYYY-MM-DD)",
    )
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    if args.command == "list":
        list_politicians()
        return 0
    
    elif args.command == "fetch":
        start_date = None
        end_date = None
        
        if args.start_date:
            start_date = date.fromisoformat(args.start_date)
        if args.end_date:
            end_date = date.fromisoformat(args.end_date)
        
        fetch_trades(
            politician_name=args.politician,
            all_politicians=args.all,
            days_back=args.days_back,
            start_date=start_date,
            end_date=end_date,
        )
        return 0
    
    return 1


if __name__ == "__main__":
    sys.exit(main())
