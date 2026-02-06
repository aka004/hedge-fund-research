#!/usr/bin/env python3
"""
Create derived tables for AFML Research Dashboard.

These tables store backtest results, signals, portfolio weights,
and AFML validation metrics produced by the backtesting pipeline.

Usage:
    python scripts/migrate_derived_tables.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import logging

import duckdb

from config import RESEARCH_DB_PATH

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

DERIVED_TABLES = {
    "derived_backtest_runs": """
        CREATE TABLE IF NOT EXISTS derived_backtest_runs (
            run_id VARCHAR PRIMARY KEY,
            strategy_name VARCHAR,
            start_date DATE,
            end_date DATE,
            universe VARCHAR,
            n_assets INT,
            sharpe_raw DOUBLE,
            psr DOUBLE,
            deflated_sharpe DOUBLE,
            pbo DOUBLE,
            caveats VARCHAR,
            is_mock BOOLEAN,
            created_at TIMESTAMP DEFAULT current_timestamp
        )
    """,
    "derived_backtest_equity": """
        CREATE TABLE IF NOT EXISTS derived_backtest_equity (
            run_id VARCHAR,
            date DATE,
            equity DOUBLE,
            benchmark_equity DOUBLE,
            drawdown DOUBLE,
            daily_return DOUBLE,
            PRIMARY KEY (run_id, date)
        )
    """,
    "derived_backtest_trades": """
        CREATE TABLE IF NOT EXISTS derived_backtest_trades (
            run_id VARCHAR,
            trade_id VARCHAR,
            date DATE,
            ticker VARCHAR,
            side VARCHAR,
            shares DOUBLE,
            price DOUBLE,
            commission DOUBLE,
            PRIMARY KEY (run_id, trade_id)
        )
    """,
    "derived_signals": """
        CREATE TABLE IF NOT EXISTS derived_signals (
            run_id VARCHAR,
            date DATE,
            ticker VARCHAR,
            signal_name VARCHAR,
            score DOUBLE,
            rank INT,
            metadata VARCHAR,
            PRIMARY KEY (run_id, date, ticker, signal_name)
        )
    """,
    "derived_portfolio_weights": """
        CREATE TABLE IF NOT EXISTS derived_portfolio_weights (
            run_id VARCHAR,
            date DATE,
            ticker VARCHAR,
            weight DOUBLE,
            hrp_weight DOUBLE,
            kelly_fraction DOUBLE,
            signal_source VARCHAR,
            is_mock BOOLEAN,
            PRIMARY KEY (run_id, date, ticker)
        )
    """,
    "derived_afml_metrics": """
        CREATE TABLE IF NOT EXISTS derived_afml_metrics (
            run_id VARCHAR,
            metric_name VARCHAR,
            metric_value DOUBLE,
            details VARCHAR,
            is_mock BOOLEAN,
            caveats VARCHAR,
            PRIMARY KEY (run_id, metric_name)
        )
    """,
    "derived_cv_paths": """
        CREATE TABLE IF NOT EXISTS derived_cv_paths (
            run_id VARCHAR,
            path_id INT,
            day_index INT,
            equity DOUBLE,
            PRIMARY KEY (run_id, path_id, day_index)
        )
    """,
    "derived_regime_history": """
        CREATE TABLE IF NOT EXISTS derived_regime_history (
            date DATE PRIMARY KEY,
            regime VARCHAR,
            ma_200 DOUBLE,
            price DOUBLE,
            distance_pct DOUBLE,
            cusum_value DOUBLE,
            days_in_regime INT
        )
    """,
}


def check_db_reachable(db_path: Path) -> bool:
    """Check that the database file or its symlink target is reachable."""
    resolved = db_path.resolve()
    if db_path.is_symlink():
        target = db_path.resolve()
        mount_point = target.parts[1:3]  # e.g. ('Volumes', 'Data_2026')
        mount_path = Path("/") / mount_point[0] / mount_point[1]
        if not mount_path.exists():
            logger.error(f"External drive not mounted: {mount_path}")
            return False
    # Parent directory must exist
    if not resolved.parent.exists():
        logger.error(f"Parent directory missing: {resolved.parent}")
        return False
    return True


def migrate():
    """Create all derived tables."""
    db_path = RESEARCH_DB_PATH

    logger.info(f"Database path: {db_path}")
    logger.info(f"Resolved path: {db_path.resolve()}")

    if not check_db_reachable(db_path):
        logger.error("Database is not reachable. Aborting.")
        sys.exit(1)

    conn = duckdb.connect(str(db_path), read_only=False)
    created = []

    for table_name, ddl in DERIVED_TABLES.items():
        try:
            conn.execute(ddl)
            created.append(table_name)
            logger.info(f"OK  {table_name}")
        except Exception as e:
            logger.error(f"FAIL  {table_name}: {e}")

    conn.close()

    logger.info(f"\nCreated {len(created)}/{len(DERIVED_TABLES)} derived tables.")
    if len(created) == len(DERIVED_TABLES):
        logger.info("Migration complete.")
    else:
        missing = set(DERIVED_TABLES) - set(created)
        logger.error(f"Failed tables: {', '.join(missing)}")
        sys.exit(1)


if __name__ == "__main__":
    migrate()
