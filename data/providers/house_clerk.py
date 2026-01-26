"""Free congressional stock trades provider using House Stock Watcher data.

Uses the free, community-maintained House Stock Watcher JSON endpoint
which provides pre-parsed congressional trades from STOCK Act disclosures.
No API key or paid subscription required.
"""

import logging
from datetime import date

import pandas as pd
import requests

from data.providers.base import DataProvider, ProviderConfig

logger = logging.getLogger(__name__)


class HouseClerkProvider(DataProvider):
    """Free data provider for congressional trades using House Stock Watcher.
    
    Uses the free JSON endpoint from house-stock-watcher-data which provides
    pre-parsed congressional trades. No API key needed.
    """

    # Free JSON endpoint from House Stock Watcher community project
    DATA_URL = "https://house-stock-watcher-data.s3-us-west-2.amazonaws.com/data/all_transactions.json"

    def __init__(self, config: ProviderConfig | None = None) -> None:
        super().__init__(config)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (compatible; HedgeFundResearch/1.0)"
        })

    @property
    def provider_name(self) -> str:
        return "house_clerk"

    def get_historical_prices(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        """Not implemented - House Clerk doesn't provide price data."""
        raise NotImplementedError(
            "House Clerk provider doesn't provide price data. "
            "Use YahooFinanceProvider for historical prices."
        )

    def get_fundamentals(self, symbol: str) -> dict:
        """Not implemented - House Clerk doesn't provide fundamental data."""
        raise NotImplementedError(
            "House Clerk provider doesn't provide fundamental data. "
            "Use YahooFinanceProvider for fundamentals."
        )

    def get_congressional_trades(
        self,
        politician_name: str | None = None,
        ticker: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> pd.DataFrame:
        """Get congressional trades from free House Stock Watcher JSON endpoint.
        
        Args:
            politician_name: Optional specific politician name (partial match)
            ticker: Optional stock ticker to filter by
            start_date: Optional start date filter
            end_date: Optional end date filter
            
        Returns:
            DataFrame with congressional trades
        """
        try:
            logger.info("Fetching congressional trades from House Stock Watcher")
            
            # Download JSON data
            response = self.session.get(self.DATA_URL, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            if not data:
                logger.warning("No data returned from House Stock Watcher")
                return pd.DataFrame()
            
            # Convert to DataFrame
            df = pd.DataFrame(data)
            
            # Normalize column names
            df.columns = df.columns.str.lower().str.replace(" ", "_")
            
            # Map common column name variations
            column_mapping = {
                "representative": "politician_name",
                "senator": "politician_name",
                "name": "politician_name",
                "transaction_date": "transaction_date",
                "date": "transaction_date",
                "ticker": "ticker",
                "symbol": "ticker",
                "type": "transaction_type",
                "transaction_type": "transaction_type",
                "amount": "amount_range",
                "amount_range": "amount_range",
                "disclosure_date": "disclosure_date",
            }
            
            for old_col, new_col in column_mapping.items():
                if old_col in df.columns and new_col not in df.columns:
                    df[new_col] = df[old_col]
            
            # Ensure politician_name exists
            if "politician_name" not in df.columns:
                # Try to find name column
                for col in ["representative", "senator", "name", "politician"]:
                    if col in df.columns:
                        df["politician_name"] = df[col]
                        break
            
            # Ensure disclosure_date exists (important for filing delay tracking)
            if "disclosure_date" not in df.columns:
                logger.warning("disclosure_date column not found - filing delay tracking unavailable")
            
            # Filter by politician name (case-insensitive partial match)
            if politician_name:
                if "politician_name" in df.columns:
                    df = df[
                        df["politician_name"].str.contains(
                            politician_name, case=False, na=False
                        )
                    ]
                else:
                    logger.warning("Cannot filter by politician_name - column not found")
            
            # Filter by ticker
            if ticker:
                ticker_col = None
                for col in ["ticker", "symbol"]:
                    if col in df.columns:
                        ticker_col = col
                        break
                
                if ticker_col:
                    df = df[df[ticker_col].str.upper() == ticker.upper()]
                else:
                    logger.warning("Cannot filter by ticker - column not found")
            
            # Filter by date
            if start_date or end_date:
                date_col = None
                for col in ["transaction_date", "date"]:
                    if col in df.columns:
                        date_col = col
                        break
                
                if date_col:
                    # Convert to date if string
                    df[date_col] = pd.to_datetime(df[date_col], errors="coerce").dt.date
                    
                    if start_date:
                        df = df[df[date_col] >= start_date]
                    if end_date:
                        df = df[df[date_col] <= end_date]
                else:
                    logger.warning("Cannot filter by date - date column not found")
            
            logger.info(f"Fetched {len(df)} congressional trades from House Stock Watcher")
            return df
            
        except Exception as e:
            logger.error(f"Error fetching congressional trades: {e}")
            raise

    def get_insider_trades(
        self,
        ticker: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> pd.DataFrame:
        """Not implemented - House Stock Watcher only has congressional trades.
        
        For insider trading (corporate insiders), you would need SEC EDGAR data.
        """
        raise NotImplementedError(
            "House Stock Watcher only provides congressional trades, not corporate insider trades. "
            "For insider trading, use SEC EDGAR or another data source."
        )
