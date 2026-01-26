"""Quiver Quantitative data provider for congressional trades and insider trading."""

import logging
import os
from datetime import date
from typing import Any

import pandas as pd

from data.providers.base import DataProvider, ProviderConfig

logger = logging.getLogger(__name__)

try:
    import quiverquant
except ImportError:
    logger.warning("quiverquant not installed. Install with: pip install quiverquant")
    quiverquant = None  # type: ignore


class QuiverProvider(DataProvider):
    """Data provider for Quiver Quantitative API (congressional trades & insider trading)."""

    def __init__(self, config: ProviderConfig | None = None) -> None:
        super().__init__(config)
        
        # Get API key from environment
        api_key = os.getenv("QUIVER_API_KEY")
        if not api_key:
            raise ValueError(
                "QUIVER_API_KEY environment variable not set. "
                "Get a free API key at https://api.quiverquant.com"
            )
        
        if quiverquant is None:
            raise ImportError(
                "quiverquant library not installed. "
                "Install with: pip install quiverquant"
            )
        
        self.client = quiverquant.quiver(api_key)
        logger.info("Quiver Quantitative client initialized")

    @property
    def provider_name(self) -> str:
        return "quiver_quantitative"

    def get_historical_prices(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        """Not implemented - Quiver doesn't provide price data.
        
        Use YahooFinanceProvider for price data instead.
        """
        raise NotImplementedError(
            "Quiver provider doesn't provide price data. "
            "Use YahooFinanceProvider for historical prices."
        )

    def get_fundamentals(self, symbol: str) -> dict:
        """Not implemented - Quiver doesn't provide fundamental data.
        
        Use YahooFinanceProvider for fundamentals instead.
        """
        raise NotImplementedError(
            "Quiver provider doesn't provide fundamental data. "
            "Use YahooFinanceProvider for fundamentals."
        )

    def get_congressional_trades(
        self,
        politician_name: str | None = None,
        ticker: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> pd.DataFrame:
        """Get congressional stock trades from Quiver Quantitative.
        
        Args:
            politician_name: Optional specific politician name
            ticker: Optional stock ticker to filter by
            start_date: Optional start date filter
            end_date: Optional end date filter
            
        Returns:
            DataFrame with congressional trades:
            - Representative/Senator name
            - Transaction date
            - Ticker symbol
            - Transaction type (Purchase/Sale)
            - Amount range
            - Filing date
        """
        try:
            # Get congressional trades
            if politician_name:
                # Get trades by specific politician
                df = self.client.congress_trading(politician_name, politician=True)
            elif ticker:
                # Get trades for specific ticker
                df = self.client.congress_trading(ticker)
            else:
                # Get all recent trades
                df = self.client.congress_trading()
            
            if df is None or df.empty:
                logger.warning("No congressional trades returned from Quiver")
                return pd.DataFrame()
            
            # Normalize column names
            df.columns = df.columns.str.lower().str.replace(" ", "_")
            
            # Filter by date if provided
            if start_date or end_date:
                date_col = None
                for col in ["transaction_date", "date", "trade_date"]:
                    if col in df.columns:
                        date_col = col
                        break
                
                if date_col:
                    df[date_col] = pd.to_datetime(df[date_col]).dt.date
                    if start_date:
                        df = df[df[date_col] >= start_date]
                    if end_date:
                        df = df[df[date_col] <= end_date]
            
            logger.info(f"Fetched {len(df)} congressional trades from Quiver")
            return df
            
        except Exception as e:
            logger.error(f"Error fetching congressional trades from Quiver: {e}")
            raise

    def get_insider_trades(
        self,
        ticker: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> pd.DataFrame:
        """Get insider trading data from Quiver Quantitative.
        
        Args:
            ticker: Optional stock ticker to filter by
            start_date: Optional start date filter
            end_date: Optional end date filter
            
        Returns:
            DataFrame with insider trades (from SEC Form 4 filings)
        """
        try:
            if ticker:
                # Get insider trades for specific ticker
                df = self.client.insider_trading(ticker)
            else:
                # Get all recent insider trades
                df = self.client.insider_trading()
            
            if df is None or df.empty:
                logger.warning("No insider trades returned from Quiver")
                return pd.DataFrame()
            
            # Normalize column names
            df.columns = df.columns.str.lower().str.replace(" ", "_")
            
            # Filter by date if provided
            if start_date or end_date:
                date_col = None
                for col in ["transaction_date", "date", "filing_date"]:
                    if col in df.columns:
                        date_col = col
                        break
                
                if date_col:
                    df[date_col] = pd.to_datetime(df[date_col]).dt.date
                    if start_date:
                        df = df[df[date_col] >= start_date]
                    if end_date:
                        df = df[df[date_col] <= end_date]
            
            logger.info(f"Fetched {len(df)} insider trades from Quiver")
            return df
            
        except Exception as e:
            logger.error(f"Error fetching insider trades from Quiver: {e}")
            raise
