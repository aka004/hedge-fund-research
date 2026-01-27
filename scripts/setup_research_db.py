#!/usr/bin/env python3
"""
Initialize research database and populate with test data.

Usage:
    python scripts/setup_research_db.py --ticker AAPL --years 7
    python scripts/setup_research_db.py --initialize-only  # Just create schema
    python scripts/setup_research_db.py --status AAPL  # Check data status
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse
import logging
from datetime import date, timedelta

from config import RESEARCH_DB_PATH, STORAGE_PATH
from data.providers.yahoo import YahooFinanceProvider
from data.storage.parquet import ParquetStorage
import duckdb

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def initialize_schema(db_path: Path):
    """Create research database schema."""
    logger.info(f"Initializing schema at {db_path}")
    
    # Ensure directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    con = duckdb.connect(str(db_path))
    
    schema = """
    -- Price data
    CREATE TABLE IF NOT EXISTS prices (
        ticker VARCHAR,
        date DATE,
        open DECIMAL,
        high DECIMAL,
        low DECIMAL,
        close DECIMAL,
        adj_close DECIMAL,
        volume BIGINT,
        PRIMARY KEY (ticker, date)
    );

    -- Fundamental data
    CREATE TABLE IF NOT EXISTS fundamentals (
        ticker VARCHAR,
        period_end DATE,
        period_type VARCHAR,  -- 'Q' or 'A'
        revenue DECIMAL,
        gross_profit DECIMAL,
        operating_income DECIMAL,
        net_income DECIMAL,
        eps DECIMAL,
        pe_ratio DECIMAL,
        market_cap DECIMAL,
        -- Extended fields (add these over time as gaps are identified)
        segment_revenue_product DECIMAL,
        segment_revenue_services DECIMAL,
        nrr DECIMAL,  -- Net revenue retention
        cac DECIMAL,  -- Customer acquisition cost
        ltv DECIMAL,  -- Lifetime value
        gross_margin DECIMAL,
        operating_margin DECIMAL,
        debt_total DECIMAL,
        debt_current DECIMAL,
        cash_equivalents DECIMAL,
        PRIMARY KEY (ticker, period_end, period_type)
    );

    -- Social metrics (StockTwits/Reddit)
    CREATE TABLE IF NOT EXISTS social_metrics (
        ticker VARCHAR,
        date DATE,
        source VARCHAR,
        mention_count INT,
        sentiment_score DECIMAL,
        bullish_count INT,
        bearish_count INT,
        PRIMARY KEY (ticker, date, source)
    );

    -- SEC filings metadata
    CREATE TABLE IF NOT EXISTS filings (
        ticker VARCHAR,
        filing_type VARCHAR,
        filing_date DATE,
        url VARCHAR,
        extracted_text TEXT,
        PRIMARY KEY (ticker, filing_type, filing_date)
    );

    -- Improvement backlog (tracks data gaps)
    CREATE TABLE IF NOT EXISTS improvement_backlog (
        gap_id VARCHAR PRIMARY KEY,
        description VARCHAR,
        first_reported DATE,
        sessions_impacted INT DEFAULT 1,
        total_time_lost_minutes INT,
        priority VARCHAR,
        status VARCHAR DEFAULT 'OPEN',
        resolution_date DATE
    );
    
    -- Session history
    CREATE TABLE IF NOT EXISTS session_history (
        session_id VARCHAR PRIMARY KEY,
        ticker VARCHAR,
        company_name VARCHAR,
        start_time TIMESTAMP,
        end_time TIMESTAMP,
        duration_minutes DECIMAL,
        database_hit_rate DECIMAL,
        workaround_time_minutes INT,
        data_quality_score INT,
        status VARCHAR
    );
    """
    
    for statement in schema.split(';'):
        if statement.strip():
            try:
                con.execute(statement)
            except Exception as e:
                logger.warning(f"Schema statement failed: {e}")
    
    con.close()
    logger.info("✅ Schema initialized successfully")


def load_prices_from_parquet(db_path: Path, ticker: str):
    """Load prices from Parquet files into DuckDB."""
    logger.info(f"Loading prices for {ticker} from Parquet")
    
    parquet_file = STORAGE_PATH / "prices" / f"{ticker}.parquet"
    
    if not parquet_file.exists():
        logger.warning(f"No Parquet file found for {ticker} at {parquet_file}")
        logger.info("Run: python scripts/fetch_data.py --symbols {ticker} --years 7")
        return False
    
    con = duckdb.connect(str(db_path))
    
    # Read from Parquet and insert into prices table
    query = f"""
    INSERT OR REPLACE INTO prices
    SELECT 
        '{ticker}' as ticker,
        date,
        open,
        high,
        low,
        close,
        adj_close,
        volume
    FROM read_parquet('{parquet_file}')
    """
    
    try:
        con.execute(query)
        row_count = con.execute(
            f"SELECT COUNT(*) FROM prices WHERE ticker = '{ticker}'"
        ).fetchone()[0]
        logger.info(f"✅ Loaded {row_count} price records for {ticker}")
        con.close()
        return True
    except Exception as e:
        logger.error(f"❌ Failed to load prices: {e}")
        con.close()
        return False


def fetch_and_load_data(ticker: str, years: int = 7):
    """Fetch data from Yahoo Finance and load into research DB."""
    logger.info(f"Fetching {years} years of data for {ticker}")
    
    # Fetch using existing providers
    provider = YahooFinanceProvider()
    storage = ParquetStorage(STORAGE_PATH)
    
    end_date = date.today()
    start_date = end_date - timedelta(days=years * 365)
    
    # Fetch and save to Parquet
    logger.info(f"Fetching data from {start_date} to {end_date}")
    df = provider.get_historical_prices(ticker, start_date, end_date)
    
    if df is not None and len(df) > 0:
        storage.save_prices(ticker, df)
        logger.info(f"✅ Saved {len(df)} rows to Parquet")
        
        # Load into research DB
        load_prices_from_parquet(RESEARCH_DB_PATH, ticker)
        return True
    else:
        logger.error("❌ No data fetched")
        return False


def check_status(ticker: str):
    """Check data status for a ticker in the research database."""
    logger.info(f"Checking data status for {ticker}")
    
    if not RESEARCH_DB_PATH.exists():
        logger.error(f"❌ Research database not found at {RESEARCH_DB_PATH}")
        logger.info("Run: python scripts/setup_research_db.py --initialize-only")
        return
    
    con = duckdb.connect(str(RESEARCH_DB_PATH))
    
    # Check tables
    tables_result = con.execute("SHOW TABLES").fetchdf()
    logger.info(f"\nAvailable tables: {', '.join(tables_result['name'].tolist())}")
    
    # Check data for ticker
    print("\n" + "=" * 60)
    print(f"DATA STATUS FOR {ticker}")
    print("=" * 60)
    
    for table in ['prices', 'fundamentals', 'social_metrics', 'filings']:
        query = f"""
            SELECT 
                COUNT(*) as record_count,
                MIN(date) as earliest_date,
                MAX(date) as latest_date
            FROM {table}
            WHERE ticker = '{ticker}'
        """
        
        try:
            result = con.execute(query).fetchdf()
            if len(result) > 0 and result['record_count'][0] > 0:
                row = result.iloc[0]
                days_stale = (date.today() - row['latest_date'].date()).days if row['latest_date'] else None
                print(f"\n{table.upper()}:")
                print(f"  Records: {row['record_count']}")
                print(f"  Date range: {row['earliest_date']} to {row['latest_date']}")
                print(f"  Days stale: {days_stale}")
            else:
                print(f"\n{table.upper()}: NO DATA")
        except Exception as e:
            print(f"\n{table.upper()}: Table not found or error - {e}")
    
    print("=" * 60 + "\n")
    con.close()


def main():
    parser = argparse.ArgumentParser(description="Setup research database")
    parser.add_argument(
        "--initialize-only", 
        action="store_true", 
        help="Only create schema, don't load data"
    )
    parser.add_argument(
        "--ticker", 
        default="AAPL", 
        help="Ticker to load data for (default: AAPL)"
    )
    parser.add_argument(
        "--years", 
        type=int, 
        default=7, 
        help="Years of history to fetch (default: 7)"
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Check data status for ticker"
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("RESEARCH DATABASE SETUP")
    print("=" * 60)
    print(f"Research DB path: {RESEARCH_DB_PATH}")
    print(f"Storage path: {STORAGE_PATH}")
    print("=" * 60 + "\n")
    
    # Check status mode
    if args.status:
        check_status(args.ticker)
        return
    
    # Always initialize schema
    initialize_schema(RESEARCH_DB_PATH)
    
    if not args.initialize_only:
        # Fetch and load data
        success = fetch_and_load_data(args.ticker, args.years)
        
        if success:
            logger.info("\n✅ Setup complete!")
            logger.info(f"Next step: python scripts/test_research.py {args.ticker} \"Company Name\"")
        else:
            logger.error("\n❌ Setup failed")
            sys.exit(1)
    else:
        logger.info("\n✅ Schema initialization complete")
        logger.info(f"Next: python scripts/setup_research_db.py --ticker {args.ticker} --years 7")


if __name__ == "__main__":
    main()
