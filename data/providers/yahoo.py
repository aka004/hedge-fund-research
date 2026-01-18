"""Yahoo Finance data provider."""

import logging
import time
from collections.abc import Callable
from datetime import date
from typing import Any

import pandas as pd
import yfinance as yf

from data.providers.base import DataProvider, ProviderConfig

logger = logging.getLogger(__name__)


class YahooFinanceProvider(DataProvider):
    """Data provider using Yahoo Finance API via yfinance."""

    def __init__(self, config: ProviderConfig | None = None) -> None:
        super().__init__(config)
        self._last_request_time: float = 0.0

    @property
    def provider_name(self) -> str:
        return "yahoo_finance"

    def _rate_limit(self) -> None:
        """Apply rate limiting between requests."""
        min_interval = self.config.rate_limit_period_seconds / self.config.rate_limit_requests
        elapsed = time.time() - self._last_request_time
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        self._last_request_time = time.time()

    def _fetch_with_retry(self, fetch_func: Callable[[], Any]) -> Any:
        """Execute a fetch function with retry logic."""
        last_error: Exception | None = None
        for attempt in range(self.config.max_retries):
            try:
                self._rate_limit()
                return fetch_func()
            except Exception as e:
                last_error = e
                logger.warning(
                    f"Attempt {attempt + 1}/{self.config.max_retries} failed: {e}"
                )
                if attempt < self.config.max_retries - 1:
                    time.sleep(self.config.retry_delay_seconds * (attempt + 1))
        raise last_error  # type: ignore[misc]

    def get_historical_prices(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        """Fetch historical OHLCV data from Yahoo Finance.

        Returns DataFrame with columns: date, open, high, low, close, volume, adj_close
        """

        def fetch() -> pd.DataFrame:
            ticker = yf.Ticker(symbol)
            df = ticker.history(
                start=start_date.isoformat(),
                end=end_date.isoformat(),
                auto_adjust=False,
            )
            if df.empty:
                raise ValueError(f"No data returned for {symbol}")
            return df

        df = self._fetch_with_retry(fetch)

        # Normalize column names and structure
        df = df.reset_index()
        df.columns = df.columns.str.lower().str.replace(" ", "_")

        # Rename columns to standard format
        column_mapping = {
            "adj_close": "adj_close",
            "adj close": "adj_close",
        }
        df = df.rename(columns=column_mapping)

        # Select and order columns
        required_columns = ["date", "open", "high", "low", "close", "volume", "adj_close"]
        available_columns = [c for c in required_columns if c in df.columns]
        df = df[available_columns]

        # Ensure date is in proper format
        df["date"] = pd.to_datetime(df["date"]).dt.date

        return df

    def get_fundamentals(self, symbol: str) -> dict:
        """Fetch fundamental data from Yahoo Finance."""

        def fetch() -> dict:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            if not info:
                raise ValueError(f"No fundamental data for {symbol}")
            return info

        info = self._fetch_with_retry(fetch)

        # Extract relevant fundamentals
        return {
            "symbol": symbol,
            "pe_ratio": info.get("trailingPE"),
            "forward_pe": info.get("forwardPE"),
            "price_to_book": info.get("priceToBook"),
            "revenue": info.get("totalRevenue"),
            "revenue_growth": info.get("revenueGrowth"),
            "earnings": info.get("netIncomeToCommon"),
            "earnings_growth": info.get("earningsGrowth"),
            "market_cap": info.get("marketCap"),
            "dividend_yield": info.get("dividendYield"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
        }
