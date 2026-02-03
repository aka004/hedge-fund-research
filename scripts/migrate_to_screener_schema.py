#!/usr/bin/env python3
"""
Migrate database schema to support stock screener.

Extends existing tables and adds new ones:
- Add `stocks` table (company master)
- Extend `fundamentals` table with comprehensive metrics
- Add `technicals` table (RSI, SMA, MACD, etc.)
- Add `options_chain` table
- Add `signals` table

Usage:
    python scripts/migrate_to_screener_schema.py
    python scripts/migrate_to_screener_schema.py --dry-run
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse
import logging
from config import RESEARCH_DB_PATH
import duckdb

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def migrate_schema(db_path: Path, dry_run: bool = False):
    """Migrate database to screener schema."""
    
    logger.info(f"{'[DRY RUN] ' if dry_run else ''}Migrating schema at {db_path}")
    
    if not db_path.exists():
        logger.error(f"Database not found at {db_path}")
        logger.info("Run scripts/setup_research_db.py first to initialize")
        return False
    
    con = duckdb.connect(str(db_path))
    
    migrations = []
    
    # ============================================================
    # 1. Create stocks table (company master)
    # ============================================================
    migrations.append("""
    CREATE TABLE IF NOT EXISTS stocks (
        ticker VARCHAR PRIMARY KEY,
        name VARCHAR NOT NULL,
        sector VARCHAR,
        industry VARCHAR,
        exchange VARCHAR,
        market_cap DOUBLE,
        country VARCHAR DEFAULT 'US',
        ipo_date DATE,
        employees INTEGER,
        description TEXT,
        website VARCHAR,
        is_active BOOLEAN DEFAULT TRUE,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    
    # ============================================================
    # 2. Extend fundamentals table
    # ============================================================
    # Check existing columns first
    existing_cols = con.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'fundamentals'
    """).fetchdf()['column_name'].tolist()
    
    logger.info(f"Existing fundamentals columns: {len(existing_cols)}")
    
    # Add missing columns
    new_columns = [
        ("roe", "DOUBLE", "Return on Equity"),
        ("roa", "DOUBLE", "Return on Assets"),
        ("roic", "DOUBLE", "Return on Invested Capital"),
        ("gross_margin", "DOUBLE", "Gross Profit Margin"),
        ("operating_margin", "DOUBLE", "Operating Profit Margin"),
        ("net_margin", "DOUBLE", "Net Profit Margin"),
        ("revenue_growth_yoy", "DOUBLE", "Revenue Growth YoY"),
        ("revenue_growth_qoq", "DOUBLE", "Revenue Growth QoQ"),
        ("earnings_growth_yoy", "DOUBLE", "Earnings Growth YoY"),
        ("earnings_growth_qoq", "DOUBLE", "Earnings Growth QoQ"),
        ("revenue_growth_3y_cagr", "DOUBLE", "Revenue 3Y CAGR"),
        ("earnings_growth_3y_cagr", "DOUBLE", "Earnings 3Y CAGR"),
        ("debt_equity", "DOUBLE", "Debt-to-Equity Ratio"),
        ("debt_assets", "DOUBLE", "Debt-to-Assets Ratio"),
        ("current_ratio", "DOUBLE", "Current Ratio"),
        ("quick_ratio", "DOUBLE", "Quick Ratio"),
        ("interest_coverage", "DOUBLE", "Interest Coverage Ratio"),
        ("dividend_yield", "DOUBLE", "Dividend Yield"),
        ("payout_ratio", "DOUBLE", "Dividend Payout Ratio"),
        ("forward_pe", "DOUBLE", "Forward P/E Ratio"),
        ("peg_ratio", "DOUBLE", "PEG Ratio"),
        ("pb_ratio", "DOUBLE", "Price-to-Book Ratio"),
        ("ps_ratio", "DOUBLE", "Price-to-Sales Ratio"),
        ("pcf_ratio", "DOUBLE", "Price-to-Cash-Flow Ratio"),
        ("ev_ebitda", "DOUBLE", "EV/EBITDA"),
        ("ev_sales", "DOUBLE", "EV/Sales"),
        ("free_cash_flow", "DOUBLE", "Free Cash Flow"),
        ("operating_cash_flow", "DOUBLE", "Operating Cash Flow"),
        ("total_assets", "DOUBLE", "Total Assets"),
        ("total_liabilities", "DOUBLE", "Total Liabilities"),
        ("shareholders_equity", "DOUBLE", "Shareholders' Equity"),
        ("shares_outstanding", "BIGINT", "Shares Outstanding"),
    ]
    
    for col_name, col_type, description in new_columns:
        if col_name not in existing_cols:
            # Escape single quotes in description
            escaped_desc = description.replace("'", "''")
            migrations.append(f"""
            ALTER TABLE fundamentals ADD COLUMN {col_name} {col_type};
            COMMENT ON COLUMN fundamentals.{col_name} IS '{escaped_desc}';
            """)
            logger.info(f"  + Adding column: {col_name} ({col_type})")
    
    # ============================================================
    # 3. Create technicals table
    # ============================================================
    migrations.append("""
    CREATE TABLE IF NOT EXISTS technicals (
        ticker VARCHAR,
        date DATE,
        -- Moving Averages
        sma_20 DOUBLE,
        sma_50 DOUBLE,
        sma_200 DOUBLE,
        ema_12 DOUBLE,
        ema_26 DOUBLE,
        -- Momentum
        rsi_14 DOUBLE,
        macd DOUBLE,
        macd_signal DOUBLE,
        macd_histogram DOUBLE,
        -- Volatility
        atr_14 DOUBLE,
        bollinger_upper DOUBLE,
        bollinger_lower DOUBLE,
        bollinger_bandwidth DOUBLE,
        -- Beta & Correlation
        beta DOUBLE,
        beta_36m DOUBLE,
        -- Volume
        volume_sma_20 DOUBLE,
        relative_volume DOUBLE,
        -- Price Distance
        distance_52w_high DOUBLE,
        distance_52w_low DOUBLE,
        distance_sma_20 DOUBLE,
        distance_sma_50 DOUBLE,
        distance_sma_200 DOUBLE,
        PRIMARY KEY (ticker, date)
    );
    """)
    
    # ============================================================
    # 4. Create options_chain table
    # ============================================================
    migrations.append("""
    CREATE TABLE IF NOT EXISTS options_chain (
        ticker VARCHAR,
        fetch_date DATE,
        expiry DATE,
        strike DOUBLE,
        option_type VARCHAR,  -- 'call' or 'put'
        bid DOUBLE,
        ask DOUBLE,
        last DOUBLE,
        mark DOUBLE,
        volume INTEGER,
        open_interest INTEGER,
        implied_volatility DOUBLE,
        delta DOUBLE,
        gamma DOUBLE,
        theta DOUBLE,
        vega DOUBLE,
        rho DOUBLE,
        moneyness DOUBLE,  -- strike / spot_price
        dte INTEGER,  -- days to expiration
        PRIMARY KEY (ticker, fetch_date, expiry, strike, option_type)
    );
    """)
    
    # ============================================================
    # 5. Create signals table
    # ============================================================
    migrations.append("""
    CREATE TABLE IF NOT EXISTS signals (
        ticker VARCHAR,
        date DATE,
        signal_name VARCHAR,
        signal_type VARCHAR,  -- 'FILTER', 'SCORE', 'RANK', 'EVENT'
        value DOUBLE,
        metadata JSON,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (ticker, date, signal_name)
    );
    """)
    
    # ============================================================
    # 6. Create screener_summary view
    # ============================================================
    migrations.append("""
    CREATE OR REPLACE VIEW screener_summary AS
    WITH latest_prices AS (
        SELECT 
            ticker,
            date,
            close AS price,
            volume,
            ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY date DESC) AS rn
        FROM prices
    ),
    latest_fundamentals AS (
        SELECT 
            ticker,
            period_end,
            pe_ratio,
            forward_pe,
            peg_ratio,
            pb_ratio,
            ps_ratio,
            roe,
            roa,
            gross_margin,
            operating_margin,
            net_margin,
            revenue_growth_yoy,
            earnings_growth_yoy,
            debt_equity,
            current_ratio,
            dividend_yield,
            payout_ratio,
            ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY period_end DESC) AS rn
        FROM fundamentals
    ),
    latest_technicals AS (
        SELECT 
            ticker,
            date,
            sma_20,
            sma_50,
            sma_200,
            rsi_14,
            macd,
            beta,
            atr_14,
            relative_volume,
            distance_52w_high,
            distance_52w_low,
            ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY date DESC) AS rn
        FROM technicals
    )
    SELECT 
        s.ticker,
        s.name,
        s.sector,
        s.industry,
        s.exchange,
        s.market_cap,
        p.price,
        p.date AS price_date,
        (p.price - LAG(p.price) OVER (PARTITION BY s.ticker ORDER BY p.date)) AS price_change,
        ((p.price / LAG(p.price) OVER (PARTITION BY s.ticker ORDER BY p.date)) - 1) * 100 AS price_change_pct,
        p.volume,
        f.pe_ratio,
        f.forward_pe,
        f.peg_ratio,
        f.pb_ratio,
        f.ps_ratio,
        f.roe,
        f.roa,
        f.gross_margin,
        f.operating_margin,
        f.net_margin,
        f.revenue_growth_yoy,
        f.earnings_growth_yoy,
        f.debt_equity,
        f.current_ratio,
        f.dividend_yield,
        f.payout_ratio,
        t.sma_20,
        t.sma_50,
        t.sma_200,
        t.rsi_14,
        t.macd,
        t.beta,
        t.atr_14,
        t.relative_volume,
        t.distance_52w_high,
        t.distance_52w_low
    FROM stocks s
    LEFT JOIN latest_prices p ON s.ticker = p.ticker AND p.rn = 1
    LEFT JOIN latest_fundamentals f ON s.ticker = f.ticker AND f.rn = 1
    LEFT JOIN latest_technicals t ON s.ticker = t.ticker AND t.rn = 1
    WHERE s.is_active = TRUE;
    """)
    
    # ============================================================
    # Execute migrations
    # ============================================================
    if dry_run:
        logger.info("\n=== DRY RUN - SQL STATEMENTS ===")
        for i, sql in enumerate(migrations, 1):
            logger.info(f"\n--- Migration {i} ---")
            logger.info(sql.strip())
        logger.info("\n=== END DRY RUN ===")
        return True
    
    try:
        for i, sql in enumerate(migrations, 1):
            logger.info(f"Running migration {i}/{len(migrations)}...")
            con.execute(sql)
        
        con.commit()
        logger.info("✅ Migration completed successfully")
        
        # Show table counts
        tables = ['stocks', 'prices', 'fundamentals', 'technicals', 'options_chain', 'signals']
        logger.info("\n=== Table Status ===")
        for table in tables:
            try:
                count = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                logger.info(f"  {table:20s}: {count:>10,d} rows")
            except:
                logger.info(f"  {table:20s}: (not yet created)")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        con.rollback()
        return False
    finally:
        con.close()


def main():
    parser = argparse.ArgumentParser(description="Migrate database to screener schema")
    parser.add_argument("--dry-run", action="store_true", help="Show SQL without executing")
    parser.add_argument("--db-path", type=Path, default=RESEARCH_DB_PATH, help="Database path")
    
    args = parser.parse_args()
    
    success = migrate_schema(args.db_path, dry_run=args.dry_run)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
