"""Social sentiment signal generator."""

import logging
from datetime import date

import pandas as pd  # noqa: F401  # used in as_of_date filter (line ~63)

from data.storage.parquet import ParquetStorage
from strategy.signals.base import Signal, SignalGenerator

logger = logging.getLogger(__name__)


class SocialSignal(SignalGenerator):
    """Generate signals based on social sentiment (StockTwits)."""

    def __init__(
        self,
        parquet_storage: ParquetStorage,
        min_message_count: int = 5,
        lookback_hours: int = 24,
    ) -> None:
        """Initialize social signal generator.

        Args:
            parquet_storage: Storage for sentiment data
            min_message_count: Minimum messages to consider valid signal
            lookback_hours: Hours of data to consider
        """
        self._storage = parquet_storage
        self.min_message_count = min_message_count
        self.lookback_hours = lookback_hours

    @property
    def name(self) -> str:
        return "social"

    def generate(
        self,
        symbols: list[str],
        as_of_date: date,
    ) -> list[Signal]:
        """Generate social sentiment signals.

        Score combines:
        1. Sentiment score (-1 to +1 from StockTwits)
        2. Attention (message count / watchlist count)

        Higher attention + positive sentiment = higher score
        """
        signals = []

        for symbol in symbols:
            try:
                sentiment_df = self._storage.load_sentiment(symbol)
                if sentiment_df is None or sentiment_df.empty:
                    continue

                # Prevent look-ahead bias: only consider rows on or
                # before as_of_date. load_sentiment returns the full
                # cached history, so iloc[-1] alone would read the
                # most recent row regardless of the simulation date.
                if "date" in sentiment_df.columns:
                    row_dates = pd.to_datetime(sentiment_df["date"]).dt.date
                    sentiment_df = sentiment_df[row_dates <= as_of_date]
                elif isinstance(sentiment_df.index, pd.DatetimeIndex):
                    sentiment_df = sentiment_df[sentiment_df.index.date <= as_of_date]

                if sentiment_df.empty:
                    continue

                # Get most recent sentiment data available as of as_of_date.
                latest = sentiment_df.iloc[-1].to_dict()

                message_count = latest.get("message_count", 0)
                sentiment_score = latest.get("sentiment_score", 0.0)
                watchlist_count = latest.get("watchlist_count", 0)
                bullish_count = latest.get("bullish_count", 0)
                bearish_count = latest.get("bearish_count", 0)

                # Skip if insufficient data
                if message_count < self.min_message_count:
                    continue

                # Calculate attention score (normalized)
                attention_score = 0.0
                if watchlist_count > 0:
                    # More messages relative to watchlist = higher attention
                    attention_score = min(1.0, message_count / (watchlist_count * 0.1))

                # Combined score: sentiment * attention factor
                # Range: -1 to +1, weighted by attention
                combined_score = sentiment_score * (0.5 + 0.5 * attention_score)

                signals.append(
                    Signal(
                        symbol=symbol,
                        date=as_of_date,
                        signal_name=self.name,
                        score=combined_score,
                        raw_value=sentiment_score,
                        metadata={
                            "sentiment_score": sentiment_score,
                            "message_count": message_count,
                            "watchlist_count": watchlist_count,
                            "bullish_count": bullish_count,
                            "bearish_count": bearish_count,
                            "attention_score": attention_score,
                        },
                    )
                )

            except Exception as e:
                logger.warning(f"Failed to generate social signal for {symbol}: {e}")
                continue

        return self._rank_signals(signals)
