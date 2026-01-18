"""StockTwits social sentiment data provider."""

import logging
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime

import pandas as pd
import requests

from data.providers.base import DataProvider, ProviderConfig

logger = logging.getLogger(__name__)


@dataclass
class StockTwitsConfig(ProviderConfig):
    """Configuration specific to StockTwits API."""

    # Free tier: 200 requests per hour
    rate_limit_requests: int = 200
    rate_limit_period_seconds: int = 3600
    base_url: str = "https://api.stocktwits.com/api/2"


class StockTwitsProvider(DataProvider):
    """Data provider for StockTwits social sentiment data."""

    def __init__(self, config: StockTwitsConfig | None = None) -> None:
        self._config = config or StockTwitsConfig()
        super().__init__(self._config)
        self._last_request_time: float = 0.0
        self._session = requests.Session()

    @property
    def provider_name(self) -> str:
        return "stocktwits"

    @property
    def _stocktwits_config(self) -> StockTwitsConfig:
        """Type-safe access to StockTwits config."""
        return self._config  # type: ignore[return-value]

    def _rate_limit(self) -> None:
        """Apply rate limiting between requests."""
        min_interval = self.config.rate_limit_period_seconds / self.config.rate_limit_requests
        elapsed = time.time() - self._last_request_time
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        self._last_request_time = time.time()

    def _fetch_with_retry(self, url: str) -> dict:
        """Fetch URL with retry logic."""
        last_error: Exception | None = None
        for attempt in range(self.config.max_retries):
            try:
                self._rate_limit()
                response = self._session.get(url, timeout=self.config.timeout_seconds)
                response.raise_for_status()
                return response.json()
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
        """StockTwits does not provide price data."""
        raise NotImplementedError(
            "StockTwits does not provide price data. Use YahooFinanceProvider instead."
        )

    def get_fundamentals(self, symbol: str) -> dict:
        """StockTwits does not provide fundamental data."""
        raise NotImplementedError(
            "StockTwits does not provide fundamental data. Use YahooFinanceProvider instead."
        )

    def get_sentiment(self, symbol: str) -> dict:
        """Fetch current sentiment data for a symbol.

        Args:
            symbol: Ticker symbol

        Returns:
            Dictionary with sentiment metrics
        """
        url = f"{self._stocktwits_config.base_url}/streams/symbol/{symbol}.json"
        data = self._fetch_with_retry(url)

        symbol_data = data.get("symbol", {})
        messages = data.get("messages", [])

        # Calculate sentiment from messages
        bullish = 0
        bearish = 0
        for msg in messages:
            entities = msg.get("entities", {})
            sentiment = entities.get("sentiment")
            if sentiment:
                if sentiment.get("basic") == "Bullish":
                    bullish += 1
                elif sentiment.get("basic") == "Bearish":
                    bearish += 1

        total_with_sentiment = bullish + bearish
        sentiment_score = 0.0
        if total_with_sentiment > 0:
            sentiment_score = (bullish - bearish) / total_with_sentiment

        return {
            "symbol": symbol,
            "watchlist_count": symbol_data.get("watchlist_count", 0),
            "message_count": len(messages),
            "bullish_count": bullish,
            "bearish_count": bearish,
            "sentiment_score": sentiment_score,  # -1 (bearish) to +1 (bullish)
            "timestamp": datetime.now(UTC).isoformat(),
        }

    def get_trending_symbols(self) -> list[dict]:
        """Fetch currently trending symbols on StockTwits.

        Returns:
            List of trending symbol data
        """
        url = f"{self._stocktwits_config.base_url}/trending/symbols.json"
        data = self._fetch_with_retry(url)

        symbols = data.get("symbols", [])
        return [
            {
                "symbol": s.get("symbol"),
                "title": s.get("title"),
                "watchlist_count": s.get("watchlist_count", 0),
            }
            for s in symbols
        ]
