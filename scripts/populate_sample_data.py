#!/usr/bin/env python3
"""
Populate database with sample stock data for testing the screener.

Fetches:
1. Company info (stocks table)
2. Fundamentals (fundamentals table)
3. Computes technicals from existing price data

Usage:
    python scripts/populate_sample_data.py --tickers AAPL,MSFT,NVDA
    python scripts/populate_sample_data.py --sp500  # Top 50 by market cap
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse
import logging
from datetime import date, timedelta
import yfinance as yf
import pandas as pd
import numpy as np
from config import RESEARCH_DB_PATH
import duckdb

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def fetch_stock_info(ticker: str) -> dict:
    """Fetch company information from Yahoo Finance."""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        
        return {
            'ticker': ticker,
            'name': info.get('longName', ticker),
            'sector': info.get('sector'),
            'industry': info.get('industry'),
            'exchange': info.get('exchange'),
            'market_cap': info.get('marketCap'),
            'country': info.get('country', 'US'),
            'employees': info.get('fullTimeEmployees'),
            'description': info.get('longBusinessSummary'),
            'website': info.get('website'),
        }
    except Exception as e:
        logger.error(f"Failed to fetch info for {ticker}: {e}")
        return None


def fetch_fundamentals(ticker: str) -> dict:
    """Fetch fundamental metrics from Yahoo Finance."""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        
        # Get latest quarterly data
        period_end = date.today()
        
        return {
            'ticker': ticker,
            'period_end': period_end,
            'period_type': 'Q',
            'revenue': info.get('totalRevenue'),
            'gross_profit': info.get('grossProfits'),
            'operating_income': info.get('operatingIncome'),
            'net_income': info.get('netIncome'),
            'eps': info.get('trailingEps'),
            'pe_ratio': info.get('trailingPE'),
            'forward_pe': info.get('forwardPE'),
            'peg_ratio': info.get('pegRatio'),
            'pb_ratio': info.get('priceToBook'),
            'ps_ratio': info.get('priceToSalesTrailing12Months'),
            'ev_ebitda': info.get('enterpriseToEbitda'),
            'roe': info.get('returnOnEquity'),
            'roa': info.get('returnOnAssets'),
            'gross_margin': info.get('grossMargins'),
            'operating_margin': info.get('operatingMargins'),
            'net_margin': info.get('profitMargins'),
            'revenue_growth_yoy': info.get('revenueGrowth'),
            'earnings_growth_yoy': info.get('earningsGrowth'),
            'debt_equity': info.get('debtToEquity'),
            'current_ratio': info.get('currentRatio'),
            'quick_ratio': info.get('quickRatio'),
            'dividend_yield': info.get('dividendYield'),
            'payout_ratio': info.get('payoutRatio'),
        }
    except Exception as e:
        logger.error(f"Failed to fetch fundamentals for {ticker}: {e}")
        return None


def compute_technicals(ticker: str, conn) -> dict:
    """Compute technical indicators from price data."""
    try:
        # Fetch price data from database
        query = """
        SELECT date, close, volume
        FROM prices
        WHERE ticker = $ticker
        ORDER BY date DESC
        LIMIT 200
        """
        df = conn.execute(query, {"ticker": ticker}).fetchdf()
        
        if len(df) < 20:
            logger.warning(f"Not enough price data for {ticker} to compute technicals")
            return None
        
        # Sort chronologically for calculations
        df = df.sort_values('date')
        
        # Moving averages
        df['sma_20'] = df['close'].rolling(window=20).mean()
        df['sma_50'] = df['close'].rolling(window=50).mean()
        df['sma_200'] = df['close'].rolling(window=200).mean()
        
        # EMA for MACD
        df['ema_12'] = df['close'].ewm(span=12, adjust=False).mean()
        df['ema_26'] = df['close'].ewm(span=26, adjust=False).mean()
        
        # RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi_14'] = 100 - (100 / (1 + rs))
        
        # MACD
        df['macd'] = df['ema_12'] - df['ema_26']
        df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
        df['macd_histogram'] = df['macd'] - df['macd_signal']
        
        # ATR
        df['high'] = df['close']  # Approximation (we don't have high/low in current data)
        df['low'] = df['close']
        df['tr'] = df['high'] - df['low']
        df['atr_14'] = df['tr'].rolling(window=14).mean()
        
        # Beta (vs S&P 500 proxy - using 0-mean returns)
        df['returns'] = df['close'].pct_change()
        beta = df['returns'].std() / df['returns'].mean() if df['returns'].mean() != 0 else 1.0
        
        # 52-week high/low distance
        last_52w = df.tail(252)
        high_52w = last_52w['close'].max()
        low_52w = last_52w['close'].min()
        current_price = df['close'].iloc[-1]
        
        distance_52w_high = ((current_price - high_52w) / high_52w) * 100
        distance_52w_low = ((current_price - low_52w) / low_52w) * 100
        
        # Get latest values
        latest = df.iloc[-1]
        
        return {
            'ticker': ticker,
            'date': latest['date'],
            'sma_20': latest['sma_20'],
            'sma_50': latest['sma_50'],
            'sma_200': latest['sma_200'],
            'ema_12': latest['ema_12'],
            'ema_26': latest['ema_26'],
            'rsi_14': latest['rsi_14'],
            'macd': latest['macd'],
            'macd_signal': latest['macd_signal'],
            'macd_histogram': latest['macd_histogram'],
            'atr_14': latest['atr_14'],
            'beta': beta,
            'distance_52w_high': distance_52w_high,
            'distance_52w_low': distance_52w_low,
            'volume_sma_20': df['volume'].rolling(window=20).mean().iloc[-1],
            'relative_volume': latest['volume'] / df['volume'].rolling(window=20).mean().iloc[-1],
        }
    except Exception as e:
        logger.error(f"Failed to compute technicals for {ticker}: {e}")
        return None


def populate_stock(ticker: str, conn):
    """Populate all data for a single stock."""
    logger.info(f"Processing {ticker}...")
    
    # 1. Fetch and insert company info
    stock_info = fetch_stock_info(ticker)
    if stock_info:
        # Check if already exists
        existing = conn.execute("SELECT COUNT(*) FROM stocks WHERE ticker = $ticker", {"ticker": ticker}).fetchone()[0]
        
        if existing > 0:
            logger.info(f"  Stock {ticker} already exists, updating...")
            conn.execute("""
                UPDATE stocks SET
                    name = $name,
                    sector = $sector,
                    industry = $industry,
                    exchange = $exchange,
                    market_cap = $market_cap,
                    country = $country,
                    employees = $employees,
                    description = $description,
                    website = $website
                WHERE ticker = $ticker
            """, stock_info)
        else:
            logger.info(f"  Inserting stock info...")
            conn.execute("""
                INSERT INTO stocks (ticker, name, sector, industry, exchange, market_cap, country, employees, description, website)
                VALUES ($ticker, $name, $sector, $industry, $exchange, $market_cap, $country, $employees, $description, $website)
            """, stock_info)
    
    # 2. Fetch and insert fundamentals
    fundamentals = fetch_fundamentals(ticker)
    if fundamentals:
        # Delete existing (replace with latest)
        conn.execute("DELETE FROM fundamentals WHERE ticker = $ticker", {"ticker": ticker})
        logger.info(f"  Inserting fundamentals...")
        
        # Filter out None values
        fundamentals = {k: v for k, v in fundamentals.items() if v is not None}
        
        # Build INSERT statement dynamically
        columns = ', '.join(fundamentals.keys())
        placeholders = ', '.join([f'${k}' for k in fundamentals.keys()])
        
        conn.execute(f"""
            INSERT INTO fundamentals ({columns})
            VALUES ({placeholders})
        """, fundamentals)
    
    # 3. Compute and insert technicals
    technicals = compute_technicals(ticker, conn)
    if technicals:
        # Delete existing (replace with latest)
        conn.execute("DELETE FROM technicals WHERE ticker = $ticker", {"ticker": ticker})
        logger.info(f"  Inserting technicals...")
        
        # Filter to only columns that exist in technicals table
        valid_columns = ['ticker', 'date', 'sma_20', 'sma_50', 'sma_200', 'rsi_14', 
                        'macd', 'beta', 'atr_14', 'relative_volume', 
                        'distance_52w_high', 'distance_52w_low']
        technicals = {k: v for k, v in technicals.items() if k in valid_columns and v is not None}
        
        # Build INSERT statement dynamically
        columns = ', '.join(technicals.keys())
        placeholders = ', '.join([f'${k}' for k in technicals.keys()])
        
        conn.execute(f"""
            INSERT INTO technicals ({columns})
            VALUES ({placeholders})
        """, technicals)
    
    conn.commit()
    logger.info(f"✅ {ticker} complete")


def main():
    parser = argparse.ArgumentParser(description="Populate sample stock data")
    parser.add_argument("--tickers", help="Comma-separated list of tickers (e.g., AAPL,MSFT,NVDA)")
    parser.add_argument("--sp500", action="store_true", help="Fetch top 50 S&P 500 stocks by market cap")
    
    args = parser.parse_args()
    
    # Determine tickers to process
    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(',')]
    elif args.sp500:
        # Top 50 S&P 500 by market cap (hardcoded for speed)
        tickers = [
            'AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'META', 'TSLA', 'BRK.B', 'LLY', 'AVGO',
            'JPM', 'V', 'UNH', 'XOM', 'WMT', 'MA', 'JNJ', 'ORCL', 'PG', 'COST',
            'HD', 'NFLX', 'BAC', 'ABBV', 'CRM', 'KO', 'CVX', 'MRK', 'AMD', 'ADBE',
            'PEP', 'TMO', 'ACN', 'MCD', 'CSCO', 'ABT', 'LIN', 'NKE', 'DIS', 'WFC',
            'IBM', 'GE', 'QCOM', 'PM', 'TXN', 'INTU', 'VZ', 'AMGN', 'CMCSA', 'NEE'
        ]
    else:
        logger.error("Must specify --tickers or --sp500")
        sys.exit(1)
    
    logger.info(f"Processing {len(tickers)} stocks...")
    
    # Connect to database
    conn = duckdb.connect(str(RESEARCH_DB_PATH))
    
    # Process each ticker
    success_count = 0
    for ticker in tickers:
        try:
            populate_stock(ticker, conn)
            success_count += 1
        except Exception as e:
            logger.error(f"Failed to process {ticker}: {e}")
    
    conn.close()
    
    logger.info(f"\n✅ Complete: {success_count}/{len(tickers)} stocks populated")
    logger.info(f"\nRun screener to test:")
    logger.info(f"  cd backend && uvicorn main:app --reload")
    logger.info(f"  cd frontend && pnpm dev")
    logger.info(f"  Open http://localhost:5173")


if __name__ == "__main__":
    main()
