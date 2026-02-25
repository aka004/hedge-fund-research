#!/usr/bin/env python3
"""
Fetch SPY price history and save as parquet.

Downloads SPY ETF data from Yahoo Finance to match the existing
stock data range (2021-01 to present) and saves it alongside
other price parquet files.

Usage:
    python scripts/fetch_spy.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import logging

import pandas as pd
import yfinance as yf

from config import STORAGE_PATH

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

PARQUET_DIR = STORAGE_PATH / "parquet" / "prices"


def fetch_spy():
    """Fetch SPY price history and save to parquet."""
    PARQUET_DIR.mkdir(parents=True, exist_ok=True)
    output_path = PARQUET_DIR / "SPY.parquet"

    logger.info("Fetching SPY price history (2021-01 to present)...")

    df = yf.download("SPY", start="2021-01-01", progress=False)

    if df.empty:
        logger.error("No data returned for SPY")
        sys.exit(1)

    # Reset index to get date as column
    df = df.reset_index()

    # Flatten multi-index columns if present
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [col[0] if isinstance(col, tuple) else col for col in df.columns]

    # Rename columns to match schema
    df = df.rename(
        columns={
            "Date": "date",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        }
    )

    # Use Close as adj_close if Adj Close is not available
    if "Adj Close" in df.columns:
        df = df.rename(columns={"Adj Close": "adj_close"})
    else:
        df["adj_close"] = df["close"]

    # Select only needed columns
    df = df[["date", "open", "high", "low", "close", "volume", "adj_close"]]
    df["date"] = pd.to_datetime(df["date"]).dt.date

    df.to_parquet(output_path, index=False)
    logger.info(f"Saved {len(df)} rows to {output_path}")
    logger.info(f"Date range: {df['date'].min()} to {df['date'].max()}")


if __name__ == "__main__":
    fetch_spy()
