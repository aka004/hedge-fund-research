"""Politician copy-trading signal generator.

Generates buy/sell signals based on politician stock trades from SEC Form 4 filings.
"""

import logging
from datetime import date, timedelta

import pandas as pd

from config import POLITICIAN_SIGNAL_LOOKBACK_DAYS
from data.storage.parquet import ParquetStorage
from data.storage.politician_trades import PoliticianTradeStorage
from strategy.signals.base import Signal, SignalGenerator

logger = logging.getLogger(__name__)


class PoliticianSignal(SignalGenerator):
    """Signal generator based on politician trades.

    Generates signals when politicians buy or sell stocks.
    Signal strength is based on:
    - Politician's historical win rate
    - Trade size (larger = more conviction)
    - Time decay (older trades = weaker signal)
    """

    def __init__(
        self,
        trade_storage: PoliticianTradeStorage,
        price_storage: ParquetStorage,
        lookback_days: int | None = None,
    ) -> None:
        """Initialize politician signal generator.

        Args:
            trade_storage: Storage for politician trades
            price_storage: Storage for price data (for performance calculation)
            lookback_days: Days to look back for trades (defaults to config)
        """
        self.trade_storage = trade_storage
        self.price_storage = price_storage
        self.lookback_days = lookback_days or POLITICIAN_SIGNAL_LOOKBACK_DAYS

        # Cache for politician performance metrics
        self._performance_cache: dict[str, float] = {}

    @property
    def name(self) -> str:
        return "politician"

    def generate(
        self,
        symbols: list[str],
        as_of_date: date,
    ) -> list[Signal]:
        """Generate signals based on politician trades.

        Args:
            symbols: List of ticker symbols to generate signals for
            as_of_date: Date to generate signals as of (prevents look-ahead bias)

        Returns:
            List of Signal objects
        """
        # Get recent trades (respecting as_of_date to prevent look-ahead)
        start_date = as_of_date - timedelta(days=self.lookback_days)
        recent_trades = self.trade_storage.get_all_trades(
            start_date=start_date, end_date=as_of_date
        )

        if recent_trades.empty:
            logger.debug("No recent politician trades found")
            return []

        # Filter to symbols we care about
        if "symbol" in recent_trades.columns:
            recent_trades = recent_trades[recent_trades["symbol"].isin(symbols)]
        else:
            logger.warning("No 'symbol' column in trades DataFrame")
            return []

        signals = []

        for _, trade in recent_trades.iterrows():
            symbol = trade.get("symbol")
            politician_name = trade.get("politician_name", "Unknown")
            transaction_type = str(trade.get("transaction_type", "")).upper()
            transaction_date = pd.to_datetime(trade.get("transaction_date")).date()
            shares = float(trade.get("shares", 0))
            price = float(trade.get("price", 0))

            if not symbol or symbol not in symbols:
                continue

            # Generate buy signal for purchases
            if "BUY" in transaction_type or transaction_type.startswith("P"):
                score = self._calculate_buy_signal_strength(
                    politician_name, shares, price, transaction_date, as_of_date
                )
                
                signals.append(
                    Signal(
                        symbol=symbol,
                        date=as_of_date,
                        signal_name="politician_buy",
                        score=score,
                        metadata={
                            "politician": politician_name,
                            "transaction_date": transaction_date.isoformat(),
                            "shares": shares,
                            "price": price,
                        },
                    )
                )

            # Generate sell signal for sales (negative score)
            elif "SELL" in transaction_type or transaction_type.startswith("S"):
                score = self._calculate_sell_signal_strength(
                    politician_name, shares, price, transaction_date, as_of_date
                )
                
                signals.append(
                    Signal(
                        symbol=symbol,
                        date=as_of_date,
                        signal_name="politician_sell",
                        score=score,  # Negative for sell
                        metadata={
                            "politician": politician_name,
                            "transaction_date": transaction_date.isoformat(),
                            "shares": shares,
                            "price": price,
                        },
                    )
                )

        # Rank signals
        self._rank_signals(signals)

        logger.info(f"Generated {len(signals)} politician signals for {as_of_date}")

        return signals

    def _calculate_buy_signal_strength(
        self,
        politician_name: str,
        shares: float,
        price: float,
        transaction_date: date,
        as_of_date: date,
    ) -> float:
        """Calculate buy signal strength.

        Args:
            politician_name: Name of politician
            shares: Number of shares
            price: Price per share
            transaction_date: Date of transaction
            as_of_date: Current date (for time decay)

        Returns:
            Signal strength score (0 to 1, where 1 is strongest)
        """
        # Base score (neutral buy)
        base_score = 0.5

        # Boost by politician's win rate
        win_rate = self._get_politician_win_rate(politician_name)
        win_rate_boost = win_rate / 100.0 * 0.3  # Up to +0.3 boost

        # Boost by trade size (larger = more conviction)
        # Normalize by typical trade size (assume $10k-100k is normal)
        trade_value = shares * price
        size_boost = min(trade_value / 100000.0, 1.0) * 0.2  # Up to +0.2 boost

        # Time decay (older trades = weaker signal)
        days_old = (as_of_date - transaction_date).days
        time_decay = max(0.0, 1.0 - (days_old / self.lookback_days)) * 0.3

        score = base_score + win_rate_boost + size_boost + time_decay

        # Clamp to [0, 1]
        return max(0.0, min(1.0, score))

    def _calculate_sell_signal_strength(
        self,
        politician_name: str,
        shares: float,
        price: float,
        transaction_date: date,
        as_of_date: date,
    ) -> float:
        """Calculate sell signal strength (returns negative score).

        Args:
            politician_name: Name of politician
            shares: Number of shares
            price: Price per share
            transaction_date: Date of transaction
            as_of_date: Current date (for time decay)

        Returns:
            Signal strength score (-1 to 0, where -1 is strongest sell)
        """
        # Calculate buy strength, then negate
        buy_strength = self._calculate_buy_signal_strength(
            politician_name, shares, price, transaction_date, as_of_date
        )
        
        # Convert to sell signal (negative)
        return -buy_strength

    def _get_politician_win_rate(self, politician_name: str) -> float:
        """Get politician's historical win rate.

        Args:
            politician_name: Name of politician

        Returns:
            Win rate as percentage (0-100)
        """
        # Check cache first
        if politician_name in self._performance_cache:
            return self._performance_cache[politician_name]

        # Calculate win rate from historical performance
        try:
            from analysis.politician_tracker import PoliticianTracker

            tracker = PoliticianTracker(self.trade_storage, self.price_storage)
            performance = tracker.calculate_performance(politician_name)
            win_rate = performance.win_rate

            # Cache result
            self._performance_cache[politician_name] = win_rate

            return win_rate
        except Exception as e:
            logger.warning(f"Could not calculate win rate for {politician_name}: {e}")
            # Default to 50% (neutral)
            return 50.0
