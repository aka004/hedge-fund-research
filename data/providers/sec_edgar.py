"""SEC EDGAR data provider for politician Form 4 filings."""

import logging
import os
from datetime import date
from typing import Any

import pandas as pd

from config import SEC_EDGAR_IDENTITY
from data.providers.base import DataProvider, ProviderConfig

logger = logging.getLogger(__name__)

try:
    from edgar import Company, set_identity
except ImportError:
    logger.warning("edgartools not installed. Install with: pip install edgartools")
    Company = None  # type: ignore
    set_identity = None  # type: ignore


class SECEdgarProvider(DataProvider):
    """Data provider for SEC EDGAR Form 4 filings using edgartools library."""

    def __init__(self, config: ProviderConfig | None = None) -> None:
        super().__init__(config)
        if set_identity is not None:
            # Set SEC identity (required by SEC)
            identity = os.getenv("SEC_EDGAR_IDENTITY", SEC_EDGAR_IDENTITY)
            set_identity(identity)
            logger.info(f"SEC EDGAR identity set to: {identity}")

    @property
    def provider_name(self) -> str:
        return "sec_edgar"

    def get_historical_prices(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        """Not implemented - SEC EDGAR doesn't provide price data.
        
        Use YahooFinanceProvider for price data instead.
        """
        raise NotImplementedError(
            "SEC EDGAR provider doesn't provide price data. "
            "Use YahooFinanceProvider for historical prices."
        )

    def get_fundamentals(self, symbol: str) -> dict:
        """Not implemented - SEC EDGAR doesn't provide fundamental data.
        
        Use YahooFinanceProvider for fundamentals instead.
        """
        raise NotImplementedError(
            "SEC EDGAR provider doesn't provide fundamental data. "
            "Use YahooFinanceProvider for fundamentals."
        )

    def get_form4_filings(
        self,
        cik: str,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int | None = None,
    ) -> pd.DataFrame:
        """Fetch Form 4 insider trading filings for a given CIK.
        
        Args:
            cik: Central Index Key (SEC identifier) for the politician/insider
            start_date: Optional start date filter
            end_date: Optional end date filter
            limit: Optional limit on number of filings to return
            
        Returns:
            DataFrame with Form 4 transaction data:
            - filing_date: Date filing was submitted
            - transaction_date: Date of transaction
            - symbol: Stock ticker symbol
            - transaction_type: Type of transaction (P, S, etc.)
            - shares: Number of shares
            - price: Transaction price per share
            - ownership_type: Direct, Indirect, or Joint
            - transaction_code: SEC transaction code
        """
        if Company is None:
            raise ImportError(
                "edgartools library not installed. "
                "Install with: pip install edgartools"
            )

        try:
            # Get company/filer by CIK
            company = Company(cik=cik)
            
            # Get Form 4 filings
            filings = company.get_filings(form="4")
            
            if limit:
                filings = filings.head(limit)
            
            # Parse each filing into transactions
            all_transactions = []
            
            for filing in filings:
                try:
                    # Get the ownership object which contains transaction data
                    ownership = filing.obj()
                    
                    # Convert to DataFrame
                    df = ownership.to_dataframe()
                    
                    if df is not None and not df.empty:
                        # Add filing metadata
                        df["filing_date"] = filing.filing_date
                        df["cik"] = cik
                        
                        # Filter by date if provided
                        if start_date or end_date:
                            if "transaction_date" in df.columns:
                                df["transaction_date"] = pd.to_datetime(
                                    df["transaction_date"]
                                ).dt.date
                                if start_date:
                                    df = df[df["transaction_date"] >= start_date]
                                if end_date:
                                    df = df[df["transaction_date"] <= end_date]
                        
                        all_transactions.append(df)
                        
                except Exception as e:
                    logger.warning(f"Error parsing filing {filing.accession_no}: {e}")
                    continue
            
            if not all_transactions:
                logger.warning(f"No transactions found for CIK {cik}")
                return pd.DataFrame()
            
            # Combine all transactions
            result = pd.concat(all_transactions, ignore_index=True)
            
            # Normalize column names
            result.columns = result.columns.str.lower().str.replace(" ", "_")
            
            # Ensure we have standard columns
            standard_columns = [
                "filing_date",
                "transaction_date",
                "symbol",
                "transaction_type",
                "shares",
                "price",
                "ownership_type",
                "transaction_code",
                "cik",
            ]
            
            # Select available columns
            available_columns = [c for c in standard_columns if c in result.columns]
            result = result[available_columns]
            
            # Sort by transaction date
            if "transaction_date" in result.columns:
                result = result.sort_values("transaction_date", ascending=False)
            
            logger.info(
                f"Fetched {len(result)} transactions for CIK {cik} "
                f"({len(all_transactions)} filings)"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error fetching Form 4 filings for CIK {cik}: {e}")
            raise

    def get_politician_trades(
        self,
        cik: str,
        politician_name: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> pd.DataFrame:
        """Get politician trades from Form 4 filings.
        
        Wrapper around get_form4_filings that adds politician name.
        
        Args:
            cik: Central Index Key for the politician
            politician_name: Name of the politician
            start_date: Optional start date filter
            end_date: Optional end date filter
            
        Returns:
            DataFrame with politician trades, including politician_name column
        """
        df = self.get_form4_filings(cik, start_date, end_date)
        
        if not df.empty:
            df["politician_name"] = politician_name
        
        return df
