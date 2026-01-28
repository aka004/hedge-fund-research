#!/usr/bin/env python3
"""
Real Data Fetcher for Research Orchestrator
============================================

Fetches actual market data from DB first, then falls back to external sources.
Solves the hallucination problem by providing real data to agents.

Usage:
    from data_fetcher import DataFetcher
    
    fetcher = DataFetcher(db_path="path/to/research.duckdb")
    price_data = fetcher.get_price_data("BABA")
    fundamentals = fetcher.get_fundamentals("BABA")
"""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict
import json

try:
    import duckdb
    DUCKDB_AVAILABLE = True
except ImportError:
    DUCKDB_AVAILABLE = False

try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False


@dataclass
class PriceData:
    """Current and historical price data for a ticker."""
    ticker: str
    current_price: float
    previous_close: float
    change_pct: float
    day_high: float
    day_low: float
    week_52_high: float
    week_52_low: float
    volume: int
    avg_volume: int
    market_cap: float
    pe_ratio: Optional[float]
    eps: Optional[float]
    dividend_yield: Optional[float]
    beta: Optional[float]
    source: str  # "database" or "yfinance"
    fetched_at: str
    
    def to_context(self) -> str:
        """Format as context string for agent injection."""
        pe_str = f"{self.pe_ratio:.2f}" if self.pe_ratio else "N/A"
        eps_str = f"${self.eps:.2f}" if self.eps else "N/A"
        div_str = f"{self.dividend_yield*100:.2f}%" if self.dividend_yield else "N/A"
        beta_str = f"{self.beta:.2f}" if self.beta else "N/A"
        
        return f"""
## Current Market Data for {self.ticker}
**Source:** {self.source} (fetched {self.fetched_at})

| Metric | Value |
|--------|-------|
| Current Price | ${self.current_price:.2f} |
| Previous Close | ${self.previous_close:.2f} |
| Day Change | {self.change_pct:+.2f}% |
| Day Range | ${self.day_low:.2f} - ${self.day_high:.2f} |
| 52-Week Range | ${self.week_52_low:.2f} - ${self.week_52_high:.2f} |
| Volume | {self.volume:,} |
| Avg Volume | {self.avg_volume:,} |
| Market Cap | ${self.market_cap/1e9:.2f}B |
| P/E Ratio | {pe_str} |
| EPS (TTM) | {eps_str} |
| Dividend Yield | {div_str} |
| Beta | {beta_str} |
"""


@dataclass  
class FundamentalData:
    """Fundamental financial data for a ticker."""
    ticker: str
    revenue_ttm: Optional[float]
    net_income_ttm: Optional[float]
    gross_margin: Optional[float]
    operating_margin: Optional[float]
    profit_margin: Optional[float]
    roe: Optional[float]
    roa: Optional[float]
    debt_to_equity: Optional[float]
    current_ratio: Optional[float]
    book_value_per_share: Optional[float]
    free_cash_flow: Optional[float]
    source: str
    fetched_at: str
    
    def to_context(self) -> str:
        """Format as context string for agent injection."""
        def fmt(val, mult=1, suffix=""):
            if val is None:
                return "N/A"
            return f"{val*mult:.2f}{suffix}"
        
        def fmt_bn(val):
            if val is None:
                return "N/A"
            return f"${val/1e9:.2f}B"
        
        return f"""
## Fundamental Data for {self.ticker}
**Source:** {self.source} (fetched {self.fetched_at})

| Metric | Value |
|--------|-------|
| Revenue (TTM) | {fmt_bn(self.revenue_ttm)} |
| Net Income (TTM) | {fmt_bn(self.net_income_ttm)} |
| Gross Margin | {fmt(self.gross_margin, 100, '%')} |
| Operating Margin | {fmt(self.operating_margin, 100, '%')} |
| Profit Margin | {fmt(self.profit_margin, 100, '%')} |
| ROE | {fmt(self.roe, 100, '%')} |
| ROA | {fmt(self.roa, 100, '%')} |
| Debt/Equity | {fmt(self.debt_to_equity)} |
| Current Ratio | {fmt(self.current_ratio)} |
| Book Value/Share | {fmt(self.book_value_per_share, suffix='')} |
| Free Cash Flow | {fmt_bn(self.free_cash_flow)} |
"""


class DataFetcher:
    """
    Fetches real market data for research agents.
    
    Priority:
    1. Check local DuckDB database first
    2. Fall back to yfinance API if not in DB or stale
    3. Cache fetched data back to DB for future use
    """
    
    def __init__(self, db_path: Optional[str] = None, cache_to_db: bool = True):
        self.db_path = db_path
        self.cache_to_db = cache_to_db
        self.connection = None
        
        if db_path and DUCKDB_AVAILABLE:
            try:
                self.connection = duckdb.connect(db_path)
                self._ensure_tables()
            except Exception as e:
                print(f"Warning: Could not connect to DB: {e}")
                self.connection = None
    
    def _ensure_tables(self):
        """Ensure required tables exist."""
        if not self.connection:
            return
            
        self.connection.execute("""
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
            )
        """)
        
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS price_snapshots (
                ticker VARCHAR,
                snapshot_time TIMESTAMP,
                current_price DECIMAL,
                previous_close DECIMAL,
                day_high DECIMAL,
                day_low DECIMAL,
                week_52_high DECIMAL,
                week_52_low DECIMAL,
                volume BIGINT,
                avg_volume BIGINT,
                market_cap DECIMAL,
                pe_ratio DECIMAL,
                eps DECIMAL,
                dividend_yield DECIMAL,
                beta DECIMAL,
                source VARCHAR,
                PRIMARY KEY (ticker, snapshot_time)
            )
        """)
    
    def get_price_data(self, ticker: str, max_age_minutes: int = 15) -> Optional[PriceData]:
        """
        Get current price data for a ticker.
        
        Args:
            ticker: Stock ticker symbol
            max_age_minutes: Max age of cached data before refetching
            
        Returns:
            PriceData object or None if fetch failed
        """
        # Try database first
        db_data = self._get_price_from_db(ticker, max_age_minutes)
        if db_data:
            return db_data
        
        # Fall back to yfinance
        yf_data = self._fetch_price_from_yfinance(ticker)
        if yf_data:
            # Cache to DB
            if self.cache_to_db and self.connection:
                self._cache_price_to_db(yf_data)
            return yf_data
        
        return None
    
    def _get_price_from_db(self, ticker: str, max_age_minutes: int) -> Optional[PriceData]:
        """Try to get recent price data from database."""
        if not self.connection:
            return None
            
        try:
            cutoff = datetime.now() - timedelta(minutes=max_age_minutes)
            result = self.connection.execute("""
                SELECT * FROM price_snapshots 
                WHERE ticker = ? AND snapshot_time > ?
                ORDER BY snapshot_time DESC
                LIMIT 1
            """, [ticker, cutoff]).fetchone()
            
            if result:
                return PriceData(
                    ticker=result[0],
                    current_price=float(result[2]),
                    previous_close=float(result[3]),
                    change_pct=((float(result[2]) - float(result[3])) / float(result[3])) * 100,
                    day_high=float(result[4]),
                    day_low=float(result[5]),
                    week_52_high=float(result[6]),
                    week_52_low=float(result[7]),
                    volume=int(result[8]),
                    avg_volume=int(result[9]),
                    market_cap=float(result[10]),
                    pe_ratio=float(result[11]) if result[11] else None,
                    eps=float(result[12]) if result[12] else None,
                    dividend_yield=float(result[13]) if result[13] else None,
                    beta=float(result[14]) if result[14] else None,
                    source="database",
                    fetched_at=result[1].isoformat()
                )
        except Exception as e:
            print(f"DB fetch error: {e}")
        
        return None
    
    def _fetch_price_from_yfinance(self, ticker: str) -> Optional[PriceData]:
        """Fetch current price data from yfinance."""
        if not YFINANCE_AVAILABLE:
            print("Warning: yfinance not available. Install with: pip install yfinance")
            return None
            
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            
            if not info or 'currentPrice' not in info and 'regularMarketPrice' not in info:
                # Try fast_info for basic data
                fast = stock.fast_info
                current = getattr(fast, 'last_price', None)
                if not current:
                    print(f"Warning: Could not fetch price for {ticker}")
                    return None
                    
                return PriceData(
                    ticker=ticker,
                    current_price=current,
                    previous_close=getattr(fast, 'previous_close', current),
                    change_pct=((current - getattr(fast, 'previous_close', current)) / getattr(fast, 'previous_close', current)) * 100 if getattr(fast, 'previous_close', None) else 0,
                    day_high=getattr(fast, 'day_high', current),
                    day_low=getattr(fast, 'day_low', current),
                    week_52_high=getattr(fast, 'year_high', current),
                    week_52_low=getattr(fast, 'year_low', current),
                    volume=int(getattr(fast, 'last_volume', 0)),
                    avg_volume=int(getattr(fast, 'three_month_average_volume', 0)),
                    market_cap=float(getattr(fast, 'market_cap', 0)),
                    pe_ratio=None,
                    eps=None,
                    dividend_yield=None,
                    beta=None,
                    source="yfinance",
                    fetched_at=datetime.now().isoformat()
                )
            
            current = info.get('currentPrice') or info.get('regularMarketPrice', 0)
            prev_close = info.get('previousClose') or info.get('regularMarketPreviousClose', current)
            
            return PriceData(
                ticker=ticker,
                current_price=float(current),
                previous_close=float(prev_close),
                change_pct=((current - prev_close) / prev_close) * 100 if prev_close else 0,
                day_high=float(info.get('dayHigh', current)),
                day_low=float(info.get('dayLow', current)),
                week_52_high=float(info.get('fiftyTwoWeekHigh', current)),
                week_52_low=float(info.get('fiftyTwoWeekLow', current)),
                volume=int(info.get('volume', 0)),
                avg_volume=int(info.get('averageVolume', 0)),
                market_cap=float(info.get('marketCap', 0)),
                pe_ratio=info.get('trailingPE'),
                eps=info.get('trailingEps'),
                dividend_yield=info.get('dividendYield'),
                beta=info.get('beta'),
                source="yfinance",
                fetched_at=datetime.now().isoformat()
            )
            
        except Exception as e:
            print(f"yfinance fetch error for {ticker}: {e}")
            return None
    
    def _cache_price_to_db(self, data: PriceData):
        """Cache price data to database."""
        if not self.connection:
            return
            
        try:
            self.connection.execute("""
                INSERT OR REPLACE INTO price_snapshots 
                (ticker, snapshot_time, current_price, previous_close, day_high, day_low,
                 week_52_high, week_52_low, volume, avg_volume, market_cap, pe_ratio,
                 eps, dividend_yield, beta, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                data.ticker, datetime.now(), data.current_price, data.previous_close,
                data.day_high, data.day_low, data.week_52_high, data.week_52_low,
                data.volume, data.avg_volume, data.market_cap, data.pe_ratio,
                data.eps, data.dividend_yield, data.beta, data.source
            ])
        except Exception as e:
            print(f"DB cache error: {e}")
    
    def get_fundamentals(self, ticker: str) -> Optional[FundamentalData]:
        """Get fundamental financial data for a ticker."""
        if not YFINANCE_AVAILABLE:
            return None
            
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            
            return FundamentalData(
                ticker=ticker,
                revenue_ttm=info.get('totalRevenue'),
                net_income_ttm=info.get('netIncomeToCommon'),
                gross_margin=info.get('grossMargins'),
                operating_margin=info.get('operatingMargins'),
                profit_margin=info.get('profitMargins'),
                roe=info.get('returnOnEquity'),
                roa=info.get('returnOnAssets'),
                debt_to_equity=info.get('debtToEquity'),
                current_ratio=info.get('currentRatio'),
                book_value_per_share=info.get('bookValue'),
                free_cash_flow=info.get('freeCashflow'),
                source="yfinance",
                fetched_at=datetime.now().isoformat()
            )
        except Exception as e:
            print(f"Fundamentals fetch error: {e}")
            return None
    
    def get_historical_prices(self, ticker: str, days: int = 252) -> Optional[List[Dict]]:
        """Get historical daily prices."""
        if not YFINANCE_AVAILABLE or not PANDAS_AVAILABLE:
            return None
            
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period=f"{days}d")
            
            if hist.empty:
                return None
            
            return hist.reset_index().to_dict('records')
        except Exception as e:
            print(f"Historical fetch error: {e}")
            return None
    
    def close(self):
        """Close database connection."""
        if self.connection:
            self.connection.close()


# CLI for testing
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Fetch real market data")
    parser.add_argument("ticker", help="Stock ticker symbol")
    parser.add_argument("--db", help="Path to DuckDB database")
    
    args = parser.parse_args()
    
    fetcher = DataFetcher(db_path=args.db)
    
    print(f"\n=== Fetching data for {args.ticker} ===\n")
    
    price = fetcher.get_price_data(args.ticker)
    if price:
        print(price.to_context())
        print(f"\nRaw data: {asdict(price)}")
    else:
        print("Failed to fetch price data")
    
    fundamentals = fetcher.get_fundamentals(args.ticker)
    if fundamentals:
        print(fundamentals.to_context())
    
    fetcher.close()
