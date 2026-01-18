"""Base interface for data providers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date

import pandas as pd


@dataclass
class ProviderConfig:
    """Configuration for data providers."""

    rate_limit_requests: int = 100
    rate_limit_period_seconds: int = 60
    max_retries: int = 3
    retry_delay_seconds: float = 1.0
    timeout_seconds: float = 30.0


class DataProvider(ABC):
    """Abstract base class for market data providers."""

    def __init__(self, config: ProviderConfig | None = None) -> None:
        self.config = config or ProviderConfig()

    @abstractmethod
    def get_historical_prices(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        """Fetch historical OHLCV data for a symbol.

        Args:
            symbol: Ticker symbol (e.g., 'AAPL')
            start_date: Start date for data range
            end_date: End date for data range

        Returns:
            DataFrame with columns: date, open, high, low, close, volume, adj_close
        """
        pass

    @abstractmethod
    def get_fundamentals(self, symbol: str) -> dict:
        """Fetch fundamental data for a symbol.

        Args:
            symbol: Ticker symbol

        Returns:
            Dictionary with fundamental metrics (P/E, revenue, earnings, etc.)
        """
        pass

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the name of this data provider."""
        pass
