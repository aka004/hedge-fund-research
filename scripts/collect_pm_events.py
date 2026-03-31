#!/usr/bin/env python3
"""Collect prediction market events from Metaculus API."""

import argparse
from datetime import date, timedelta

from data.providers.metaculus import MetaculusProvider
from data.storage.event_store import EventStore

FINANCE_KEYWORDS = [
    "Federal Reserve interest rate",
    "CPI inflation",
    "GDP growth",
    "S&P 500",
    "unemployment rate",
]


def main(source: str, dry_run: bool, symbols: list[str]) -> None:
    """Collect and optionally save prediction market events."""
    store = EventStore(storage_dir="data/storage")
    end_date = date.today()
    start_date = end_date - timedelta(days=365)

    if source == "metaculus":
        provider = MetaculusProvider()
        all_events = []

        for keyword in FINANCE_KEYWORDS:
            print(f"Searching: {keyword}")
            questions = provider.search_questions(keyword, start_date, end_date)
            events = provider.questions_to_events(
                questions, symbol="SPY", event_type="macro"
            )
            all_events.extend(events)
            print(f"  Found {len(events)} events")

        if dry_run:
            print(f"\nDRY RUN — would save {len(all_events)} events")
            for e in all_events[:5]:
                print(f"  {e.event_id}: {e.description[:60]}...")
        else:
            store.save_events(all_events)
            print(f"Saved {len(all_events)} events to EventStore")
    else:
        print(f"Unknown source: {source}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Collect prediction market events from Metaculus API."
    )
    parser.add_argument(
        "--source",
        default="metaculus",
        choices=["metaculus"],
        help="Prediction market source (default: metaculus)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print events without saving to EventStore",
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=["SPY"],
        help="Symbols to associate with events (default: SPY)",
    )
    args = parser.parse_args()
    main(args.source, args.dry_run, args.symbols)
