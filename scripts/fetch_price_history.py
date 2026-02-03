#!/usr/bin/env python3
"""
Fetch historical price data for stocks.

Usage:
    python scripts/fetch_price_history.py --ticker AAPL --years 2
    python scripts/fetch_price_history.py --all-stocks  # Fetch for all stocks in database
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse
import logging
from datetime import datetime, timedelta
import yfinance as yf
import pandas as pd
from config import RESEARCH_DB_PATH
import duckdb

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def fetch_prices(ticker: str, years: int = 2, conn=None):
    """Fetch historical price data from Yahoo Finance."""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=years * 365)
    
    logger.info(f"Fetching {ticker} prices from {start_date.date()} to {end_date.date()}...")
    
    try:
        # Download data
        df = yf.download(ticker, start=start_date, end=end_date, progress=False)
        
        if df.empty:
            logger.warning(f"No data returned for {ticker}")
            return 0
        
        # Reset index to get date as column
        df = df.reset_index()
        
        # Flatten multi-index columns if present
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [col[0] for col in df.columns]
        
        # Prepare data for insertion
        df['ticker'] = ticker
        
        # Rename columns to match database schema
        df = df.rename(columns={
            'Date': 'date',
            'Open': 'open',
            'High': 'high',
            'Low': 'low',
            'Close': 'close',
            'Volume': 'volume'
        })
        
        # Use Close as adj_close if Adj Close is not available
        if 'Adj Close' in df.columns:
            df = df.rename(columns={'Adj Close': 'adj_close'})
        else:
            df['adj_close'] = df['close']
        
        # Select only needed columns
        df = df[['ticker', 'date', 'open', 'high', 'low', 'close', 'adj_close', 'volume']]
        
        # Delete existing data for this ticker
        if conn:
            conn.execute("DELETE FROM prices WHERE ticker = $ticker", {"ticker": ticker})
        
        # Insert new data
        rows_inserted = 0
        for _, row in df.iterrows():
            if conn:
                conn.execute("""
                    INSERT INTO prices (ticker, date, open, high, low, close, adj_close, volume)
                    VALUES ($ticker, $date, $open, $high, $low, $close, $adj_close, $volume)
                """, {
                    'ticker': row['ticker'],
                    'date': row['date'].date(),
                    'open': float(row['open']),
                    'high': float(row['high']),
                    'low': float(row['low']),
                    'close': float(row['close']),
                    'adj_close': float(row['adj_close']),
                    'volume': int(row['volume'])
                })
                rows_inserted += 1
        
        if conn:
            conn.commit()
        
        logger.info(f"  ✓ Inserted {rows_inserted} rows for {ticker}")
        return rows_inserted
        
    except Exception as e:
        logger.error(f"Failed to fetch {ticker}: {e}")
        return 0


def main():
    parser = argparse.ArgumentParser(description="Fetch historical price data")
    parser.add_argument("--ticker", help="Single ticker to fetch")
    parser.add_argument("--tickers", help="Comma-separated list of tickers")
    parser.add_argument("--all-stocks", action="store_true", help="Fetch for all stocks in database")
    parser.add_argument("--years", type=int, default=2, help="Number of years of history (default: 2)")
    
    args = parser.parse_args()
    
    # Connect to database
    conn = duckdb.connect(str(RESEARCH_DB_PATH))
    
    # Determine which tickers to fetch
    if args.ticker:
        tickers = [args.ticker.upper()]
    elif args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(',')]
    elif args.all_stocks:
        # Get all tickers from stocks table
        result = conn.execute("SELECT ticker FROM stocks ORDER BY ticker").fetchall()
        tickers = [row[0] for row in result]
        logger.info(f"Found {len(tickers)} stocks in database")
    else:
        logger.error("Must specify --ticker, --tickers, or --all-stocks")
        sys.exit(1)
    
    logger.info(f"Fetching {args.years} years of price data for {len(tickers)} stocks...")
    
    total_rows = 0
    success_count = 0
    
    for ticker in tickers:
        rows = fetch_prices(ticker, args.years, conn)
        if rows > 0:
            success_count += 1
            total_rows += rows
    
    conn.close()
    
    logger.info(f"\n✅ Complete: {success_count}/{len(tickers)} stocks, {total_rows} total price rows")


if __name__ == "__main__":
    main()
