"""Finnhub social sentiment and news data provider."""

import logging
import os
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import finnhub
import pandas as pd

from data.providers.base import DataProvider, ProviderConfig

logger = logging.getLogger(__name__)


@dataclass
class FinnhubConfig(ProviderConfig):
    """Configuration specific to Finnhub API."""

    # Free tier: 60 API calls/minute
    rate_limit_requests: int = 60
    rate_limit_period_seconds: int = 60


class FinnhubProvider(DataProvider):
    """Data provider for Finnhub sentiment and news data."""

    def __init__(self, config: FinnhubConfig | None = None) -> None:
        self._config = config or FinnhubConfig()
        super().__init__(self._config)

        api_key = os.getenv("FINNHUB_API_KEY")
        if not api_key:
            raise ValueError("FINNHUB_API_KEY environment variable not set")

        self._client = finnhub.Client(api_key=api_key)

    @property
    def provider_name(self) -> str:
        return "finnhub"

    def get_historical_prices(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        """Fetch historical candle data from Finnhub.

        Note: Free tier has limited historical data.
        Consider using YahooFinanceProvider for extensive history.
        """
        start_ts = int(datetime.combine(start_date, datetime.min.time()).timestamp())
        end_ts = int(datetime.combine(end_date, datetime.max.time()).timestamp())

        data = self._client.stock_candles(symbol, "D", start_ts, end_ts)

        if data.get("s") != "ok":
            logger.warning(f"No data returned for {symbol}")
            return pd.DataFrame()

        df = pd.DataFrame(
            {
                "date": pd.to_datetime(data["t"], unit="s").date,
                "open": data["o"],
                "high": data["h"],
                "low": data["l"],
                "close": data["c"],
                "volume": data["v"],
            }
        )

        return df

    def get_fundamentals(self, symbol: str) -> dict:
        """Fetch basic financials from Finnhub."""
        try:
            metrics = self._client.company_basic_financials(symbol, "all")
            profile = self._client.company_profile2(symbol=symbol)

            return {
                "symbol": symbol,
                "name": profile.get("name"),
                "industry": profile.get("finnhubIndustry"),
                "market_cap": profile.get("marketCapitalization"),
                "metrics": metrics.get("metric", {}),
                "timestamp": datetime.now(UTC).isoformat(),
            }
        except Exception as e:
            logger.error(f"Error fetching fundamentals for {symbol}: {e}")
            return {"symbol": symbol, "error": str(e)}

    def get_sentiment(self, symbol: str) -> dict:
        """Fetch social sentiment data for a symbol.

        Returns aggregated sentiment from news and social media.
        """
        try:
            sentiment_data = self._client.news_sentiment(symbol)

            return {
                "symbol": symbol,
                "buzz": sentiment_data.get("buzz", {}),
                "sentiment": sentiment_data.get("sentiment", {}),
                "company_news_score": sentiment_data.get("companyNewsScore"),
                "sector_average_bullish_percent": sentiment_data.get(
                    "sectorAverageBullishPercent"
                ),
                "sector_average_news_score": sentiment_data.get(
                    "sectorAverageNewsScore"
                ),
                "timestamp": datetime.now(UTC).isoformat(),
            }
        except Exception as e:
            logger.error(f"Error fetching sentiment for {symbol}: {e}")
            return {"symbol": symbol, "error": str(e)}

    def get_news(
        self,
        symbol: str,
        days_back: int = 7,
    ) -> list[dict]:
        """Fetch recent news for a symbol.

        Args:
            symbol: Ticker symbol
            days_back: Number of days of news to fetch

        Returns:
            List of news articles with sentiment
        """
        end_date = datetime.now(UTC).date()
        start_date = end_date - timedelta(days=days_back)

        try:
            news = self._client.company_news(
                symbol,
                _from=start_date.isoformat(),
                to=end_date.isoformat(),
            )

            return [
                {
                    "headline": article.get("headline"),
                    "summary": article.get("summary"),
                    "source": article.get("source"),
                    "url": article.get("url"),
                    "datetime": datetime.fromtimestamp(
                        article.get("datetime", 0), tz=UTC
                    ).isoformat(),
                    "sentiment": article.get("sentiment"),
                }
                for article in news[:50]  # Limit to 50 articles
            ]
        except Exception as e:
            logger.error(f"Error fetching news for {symbol}: {e}")
            return []

    def get_social_sentiment(self, symbol: str) -> dict:
        """Fetch social media sentiment (Twitter/Reddit mentions).

        Note: This is a premium feature on Finnhub.
        Returns empty dict if not available.
        """
        try:
            data = self._client.stock_social_sentiment(symbol)
            return {
                "symbol": symbol,
                "reddit": data.get("reddit", []),
                "twitter": data.get("twitter", []),
                "timestamp": datetime.now(UTC).isoformat(),
            }
        except Exception as e:
            logger.warning(f"Social sentiment not available for {symbol}: {e}")
            return {"symbol": symbol, "reddit": [], "twitter": []}

    def get_insider_sentiment(self, symbol: str) -> dict:
        """Fetch insider sentiment (MSPR - Monthly Share Purchase Ratio).

        MSPR > 0: More insider buying than selling
        MSPR < 0: More insider selling than buying
        """
        try:
            end_date = datetime.now(UTC).date()
            start_date = end_date - timedelta(days=90)

            data = self._client.stock_insider_sentiment(
                symbol,
                start_date.isoformat(),
                end_date.isoformat(),
            )

            return {
                "symbol": symbol,
                "data": data.get("data", []),
                "timestamp": datetime.now(UTC).isoformat(),
            }
        except Exception as e:
            logger.error(f"Error fetching insider sentiment for {symbol}: {e}")
            return {"symbol": symbol, "data": [], "error": str(e)}

    def get_recommendation_trends(self, symbol: str) -> list[dict]:
        """Fetch analyst recommendation trends."""
        try:
            trends = self._client.recommendation_trends(symbol)
            return trends
        except Exception as e:
            logger.error(f"Error fetching recommendations for {symbol}: {e}")
            return []
