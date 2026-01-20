"""Reddit social sentiment data provider."""

import logging
import os
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime

import pandas as pd
import praw

from data.providers.base import DataProvider, ProviderConfig

logger = logging.getLogger(__name__)

# Subreddits to monitor for stock sentiment
DEFAULT_SUBREDDITS = [
    "wallstreetbets",
    "stocks",
    "investing",
    "options",
    "stockmarket",
]


@dataclass
class RedditConfig(ProviderConfig):
    """Configuration specific to Reddit API."""

    rate_limit_requests: int = 60
    rate_limit_period_seconds: int = 60
    subreddits: list[str] | None = None

    def __post_init__(self) -> None:
        if self.subreddits is None:
            self.subreddits = DEFAULT_SUBREDDITS


class RedditProvider(DataProvider):
    """Data provider for Reddit social sentiment data."""

    def __init__(self, config: RedditConfig | None = None) -> None:
        self._config = config or RedditConfig()
        super().__init__(self._config)

        # Initialize PRAW client
        self._reddit = praw.Reddit(
            client_id=os.getenv("REDDIT_CLIENT_ID"),
            client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
            user_agent=os.getenv("REDDIT_USER_AGENT", "hedge-fund-research:v1.0"),
        )

    @property
    def provider_name(self) -> str:
        return "reddit"

    @property
    def _reddit_config(self) -> RedditConfig:
        """Type-safe access to Reddit config."""
        return self._config  # type: ignore[return-value]

    def get_historical_prices(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        """Reddit does not provide price data."""
        raise NotImplementedError(
            "Reddit does not provide price data. Use YahooFinanceProvider instead."
        )

    def get_fundamentals(self, symbol: str) -> dict:
        """Reddit does not provide fundamental data."""
        raise NotImplementedError(
            "Reddit does not provide fundamental data. Use YahooFinanceProvider instead."
        )

    def _extract_tickers(self, text: str) -> list[str]:
        """Extract stock tickers from text (e.g., $AAPL or AAPL)."""
        # Match $TICKER or standalone uppercase 2-5 letter words
        pattern = r"\$([A-Z]{1,5})\b|(?<![A-Za-z])([A-Z]{2,5})(?![A-Za-z])"
        matches = re.findall(pattern, text)
        tickers = []
        for match in matches:
            ticker = match[0] or match[1]
            if ticker:
                tickers.append(ticker)
        return list(set(tickers))

    def _analyze_sentiment(self, text: str) -> float:
        """Simple keyword-based sentiment analysis.

        Returns score from -1 (bearish) to +1 (bullish).
        """
        text_lower = text.lower()

        bullish_words = [
            "buy",
            "long",
            "calls",
            "moon",
            "rocket",
            "bullish",
            "up",
            "gain",
            "profit",
            "green",
            "yolo",
            "diamond hands",
            "hold",
            "undervalued",
            "squeeze",
            "breakout",
            "rally",
        ]
        bearish_words = [
            "sell",
            "short",
            "puts",
            "crash",
            "bearish",
            "down",
            "loss",
            "red",
            "dump",
            "overvalued",
            "drop",
            "tank",
            "paper hands",
            "bubble",
            "correction",
        ]

        bullish_count = sum(1 for word in bullish_words if word in text_lower)
        bearish_count = sum(1 for word in bearish_words if word in text_lower)

        total = bullish_count + bearish_count
        if total == 0:
            return 0.0
        return (bullish_count - bearish_count) / total

    def get_sentiment(self, symbol: str, limit: int = 100) -> dict:
        """Fetch sentiment data for a symbol from Reddit.

        Args:
            symbol: Ticker symbol
            limit: Maximum posts to analyze per subreddit

        Returns:
            Dictionary with sentiment metrics
        """
        mentions = []
        total_score = 0.0
        total_comments = 0

        subreddits = self._reddit_config.subreddits or DEFAULT_SUBREDDITS

        for subreddit_name in subreddits:
            try:
                subreddit = self._reddit.subreddit(subreddit_name)

                # Search for symbol mentions
                for submission in subreddit.search(
                    f"${symbol} OR {symbol}",
                    limit=limit,
                    time_filter="week",
                ):
                    text = f"{submission.title} {submission.selftext}"
                    tickers = self._extract_tickers(text)

                    if symbol.upper() in tickers:
                        sentiment = self._analyze_sentiment(text)
                        mentions.append(
                            {
                                "subreddit": subreddit_name,
                                "title": submission.title,
                                "score": submission.score,
                                "num_comments": submission.num_comments,
                                "sentiment": sentiment,
                                "created_utc": datetime.fromtimestamp(
                                    submission.created_utc, tz=UTC
                                ).isoformat(),
                            }
                        )
                        total_score += sentiment
                        total_comments += submission.num_comments

            except Exception as e:
                logger.warning(f"Error fetching from r/{subreddit_name}: {e}")

        mention_count = len(mentions)
        avg_sentiment = total_score / mention_count if mention_count > 0 else 0.0

        return {
            "symbol": symbol,
            "mention_count": mention_count,
            "total_comments": total_comments,
            "sentiment_score": avg_sentiment,  # -1 (bearish) to +1 (bullish)
            "subreddits_searched": subreddits,
            "mentions": mentions[:10],  # Top 10 mentions for reference
            "timestamp": datetime.now(UTC).isoformat(),
        }

    def get_trending_tickers(self, limit: int = 50) -> list[dict]:
        """Get trending tickers across monitored subreddits.

        Returns:
            List of tickers with mention counts and sentiment
        """
        ticker_data: dict[str, dict] = {}
        subreddits = self._reddit_config.subreddits or DEFAULT_SUBREDDITS

        for subreddit_name in subreddits:
            try:
                subreddit = self._reddit.subreddit(subreddit_name)

                for submission in subreddit.hot(limit=limit):
                    text = f"{submission.title} {submission.selftext}"
                    tickers = self._extract_tickers(text)
                    sentiment = self._analyze_sentiment(text)

                    for ticker in tickers:
                        if ticker not in ticker_data:
                            ticker_data[ticker] = {
                                "symbol": ticker,
                                "mention_count": 0,
                                "total_score": 0,
                                "total_sentiment": 0.0,
                            }
                        ticker_data[ticker]["mention_count"] += 1
                        ticker_data[ticker]["total_score"] += submission.score
                        ticker_data[ticker]["total_sentiment"] += sentiment

            except Exception as e:
                logger.warning(f"Error fetching hot posts from r/{subreddit_name}: {e}")

        # Calculate averages and sort by mentions
        results = []
        for ticker, data in ticker_data.items():
            if data["mention_count"] >= 2:  # Filter noise
                results.append(
                    {
                        "symbol": data["symbol"],
                        "mention_count": data["mention_count"],
                        "total_score": data["total_score"],
                        "avg_sentiment": data["total_sentiment"]
                        / data["mention_count"],
                    }
                )

        results.sort(key=lambda x: x["mention_count"], reverse=True)
        return results[:20]  # Top 20 trending
