"""Analysis module for tracking politician trading performance."""

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

import pandas as pd

from data.storage.parquet import ParquetStorage
from data.storage.politician_trades import PoliticianTradeStorage

logger = logging.getLogger(__name__)


@dataclass
class PoliticianPerformance:
    """Performance metrics for a politician's trading activity."""

    politician_name: str
    total_trades: int
    buy_trades: int
    sell_trades: int
    win_rate: float  # Percentage of profitable trades
    avg_return: float  # Average return per trade
    avg_holding_period_days: float  # Average days held
    sharpe_ratio: Optional[float] = None  # Sharpe ratio if sufficient trades
    total_return: float = 0.0  # Total cumulative return
    best_trade_return: Optional[float] = None
    worst_trade_return: Optional[float] = None
    # Filing delay metrics (STOCK Act compliance)
    avg_filing_delay_days: float = 0.0  # Average days between trade and disclosure
    max_filing_delay_days: int = 0  # Longest delay (suspicious if >45 days)
    late_filings_count: int = 0  # Number of trades filed after 45-day limit
    late_filings_pct: float = 0.0  # Percentage of late filings


class PoliticianTracker:
    """Tracks and analyzes politician trading performance."""

    def __init__(
        self,
        trade_storage: PoliticianTradeStorage,
        price_storage: ParquetStorage,
    ) -> None:
        """Initialize politician tracker.

        Args:
            trade_storage: Storage for politician trades
            price_storage: Storage for price data (to calculate returns)
        """
        self.trade_storage = trade_storage
        self.price_storage = price_storage

    def calculate_performance(
        self,
        politician_name: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> PoliticianPerformance:
        """Calculate performance metrics for a politician.

        Args:
            politician_name: Name of politician
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            PoliticianPerformance with calculated metrics
        """
        # Load trades
        trades = self.trade_storage.load_trades(
            politician_name, start_date=start_date, end_date=end_date
        )

        if trades is None or trades.empty:
            logger.warning(f"No trades found for {politician_name}")
            return PoliticianPerformance(
                politician_name=politician_name,
                total_trades=0,
                buy_trades=0,
                sell_trades=0,
                win_rate=0.0,
                avg_return=0.0,
                avg_holding_period_days=0.0,
            )

        # Separate buy and sell trades
        buy_trades = trades[trades["transaction_type"].str.contains("Buy|P", case=False, na=False)]
        sell_trades = trades[trades["transaction_type"].str.contains("Sell|S", case=False, na=False)]

        # Calculate returns for each trade
        trade_returns = self._calculate_trade_returns(trades)

        # Calculate filing delay metrics
        delay_metrics = self._calculate_filing_delays(trades)

        # Calculate metrics
        total_trades = len(trades)
        buy_count = len(buy_trades)
        sell_count = len(sell_trades)

        if trade_returns.empty:
            win_rate = 0.0
            avg_return = 0.0
            avg_holding_period = 0.0
            sharpe_ratio = None
            total_return = 0.0
            best_return = None
            worst_return = None
        else:
            profitable = trade_returns[trade_returns["return"] > 0]
            win_rate = len(profitable) / len(trade_returns) * 100 if len(trade_returns) > 0 else 0.0
            avg_return = trade_returns["return"].mean() * 100  # Convert to percentage
            avg_holding_period = trade_returns["holding_period_days"].mean()
            total_return = trade_returns["return"].sum() * 100

            # Sharpe ratio (annualized) if we have enough trades
            if len(trade_returns) >= 10:
                returns_series = trade_returns["return"]
                sharpe_ratio = (
                    returns_series.mean() / returns_series.std() * (252**0.5)
                    if returns_series.std() > 0
                    else None
                )
            else:
                sharpe_ratio = None

            best_return = trade_returns["return"].max() * 100
            worst_return = trade_returns["return"].min() * 100

        return PoliticianPerformance(
            politician_name=politician_name,
            total_trades=total_trades,
            buy_trades=buy_count,
            sell_trades=sell_count,
            win_rate=win_rate,
            avg_return=avg_return,
            avg_holding_period_days=avg_holding_period,
            sharpe_ratio=sharpe_ratio,
            total_return=total_return,
            best_trade_return=best_return,
            worst_trade_return=worst_return,
            avg_filing_delay_days=delay_metrics["avg_delay"],
            max_filing_delay_days=delay_metrics["max_delay"],
            late_filings_count=delay_metrics["late_count"],
            late_filings_pct=delay_metrics["late_pct"],
        )

    def _calculate_trade_returns(self, trades: pd.DataFrame) -> pd.DataFrame:
        """Calculate returns for each trade by matching buys with sells.

        Args:
            trades: DataFrame with trades

        Returns:
            DataFrame with calculated returns
        """
        if trades.empty or "symbol" not in trades.columns:
            return pd.DataFrame()

        returns_data = []

        # Group by symbol
        for symbol, symbol_trades in trades.groupby("symbol"):
            symbol_trades = symbol_trades.sort_values("transaction_date")

            # Match buys with sells
            buys = symbol_trades[
                symbol_trades["transaction_type"].str.contains("Buy|P", case=False, na=False)
            ]
            sells = symbol_trades[
                symbol_trades["transaction_type"].str.contains("Sell|S", case=False, na=False)
            ]

            for _, buy in buys.iterrows():
                buy_date = pd.to_datetime(buy["transaction_date"]).date()
                buy_price = buy.get("price", 0.0)
                buy_shares = buy.get("shares", 0.0)

                if buy_price <= 0 or buy_shares <= 0:
                    continue

                # Find matching sell (next sell after buy)
                matching_sells = sells[sells["transaction_date"] > buy_date]
                if matching_sells.empty:
                    # No sell yet - use current price if available
                    current_price = self._get_current_price(symbol, buy_date)
                    if current_price:
                        exit_price = current_price
                        exit_date = date.today()
                    else:
                        continue  # Skip if we can't determine exit
                else:
                    # Use first sell
                    sell = matching_sells.iloc[0]
                    exit_price = sell.get("price", 0.0)
                    exit_date = pd.to_datetime(sell["transaction_date"]).date()

                if exit_price <= 0:
                    continue

                # Calculate return
                return_pct = (exit_price - buy_price) / buy_price
                holding_period = (exit_date - buy_date).days

                returns_data.append({
                    "symbol": symbol,
                    "buy_date": buy_date,
                    "sell_date": exit_date,
                    "buy_price": buy_price,
                    "sell_price": exit_price,
                    "return": return_pct,
                    "holding_period_days": holding_period,
                })

        if not returns_data:
            return pd.DataFrame()

        return pd.DataFrame(returns_data)

    def _get_current_price(self, symbol: str, as_of_date: date) -> float | None:
        """Get current price for a symbol as of a given date.

        Args:
            symbol: Stock symbol
            as_of_date: Date to get price for

        Returns:
            Price as float, or None if not available
        """
        try:
            prices = self.price_storage.load_prices(
                symbol, start_date=as_of_date, end_date=as_of_date
            )
            if prices is not None and not prices.empty and "adj_close" in prices.columns:
                return float(prices.iloc[0]["adj_close"])
        except Exception as e:
            logger.debug(f"Could not get price for {symbol} on {as_of_date}: {e}")

        return None

    def _calculate_filing_delays(self, trades: pd.DataFrame) -> dict:
        """Calculate filing delay metrics from trades.

        Args:
            trades: DataFrame with trades (must have transaction_date and disclosure_date)

        Returns:
            Dict with delay metrics: avg_delay, max_delay, late_count, late_pct
        """
        if trades.empty:
            return {
                "avg_delay": 0.0,
                "max_delay": 0,
                "late_count": 0,
                "late_pct": 0.0,
            }

        # Check if we have both date columns
        if "transaction_date" not in trades.columns or "disclosure_date" not in trades.columns:
            logger.warning("Missing transaction_date or disclosure_date for delay calculation")
            return {
                "avg_delay": 0.0,
                "max_delay": 0,
                "late_count": 0,
                "late_pct": 0.0,
            }

        # Convert to datetime if needed
        trans_dates = pd.to_datetime(trades["transaction_date"])
        disc_dates = pd.to_datetime(trades["disclosure_date"])

        # Calculate delay in days
        delays = (disc_dates - trans_dates).dt.days

        # Filter out invalid delays (negative or NaN)
        valid_delays = delays[delays.notna() & (delays >= 0)]

        if valid_delays.empty:
            return {
                "avg_delay": 0.0,
                "max_delay": 0,
                "late_count": 0,
                "late_pct": 0.0,
            }

        # STOCK Act requires disclosure within 30-45 days (use 45 as threshold)
        LATE_THRESHOLD = 45
        late_filings = valid_delays[valid_delays > LATE_THRESHOLD]

        return {
            "avg_delay": float(valid_delays.mean()),
            "max_delay": int(valid_delays.max()),
            "late_count": len(late_filings),
            "late_pct": (len(late_filings) / len(valid_delays) * 100) if len(valid_delays) > 0 else 0.0,
        }

    def get_suspicious_trades(
        self,
        politician_name: str | None = None,
        delay_threshold_days: int = 45,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> pd.DataFrame:
        """Get trades with suspicious filing delays.

        Args:
            politician_name: Optional specific politician filter
            delay_threshold_days: Minimum delay to flag as suspicious (default: 45)
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            DataFrame with suspicious trades sorted by delay
        """
        if politician_name:
            trades = self.trade_storage.load_trades(
                politician_name, start_date=start_date, end_date=end_date
            )
            if trades is None or trades.empty:
                return pd.DataFrame()
        else:
            trades = self.trade_storage.get_all_trades(
                start_date=start_date, end_date=end_date
            )

        if trades.empty:
            return pd.DataFrame()

        # Calculate filing delay
        if "transaction_date" not in trades.columns or "disclosure_date" not in trades.columns:
            logger.warning("Missing date columns for suspicious trade detection")
            return pd.DataFrame()

        trans_dates = pd.to_datetime(trades["transaction_date"])
        disc_dates = pd.to_datetime(trades["disclosure_date"])
        
        trades = trades.copy()
        trades["filing_delay_days"] = (disc_dates - trans_dates).dt.days

        # Filter for suspicious delays
        suspicious = trades[trades["filing_delay_days"] > delay_threshold_days]
        
        # Sort by delay (longest first)
        if not suspicious.empty:
            suspicious = suspicious.sort_values("filing_delay_days", ascending=False)

        return suspicious

    def get_recent_trades(
        self,
        politician_name: str | None = None,
        lookback_days: int = 45,
        as_of_date: date | None = None,
    ) -> pd.DataFrame:
        """Get recent trades from politicians.

        Args:
            politician_name: Optional specific politician, or None for all
            lookback_days: Number of days to look back
            as_of_date: Date to calculate lookback from (defaults to today)

        Returns:
            DataFrame with recent trades
        """
        if as_of_date is None:
            as_of_date = date.today()

        start_date = as_of_date - timedelta(days=lookback_days)

        if politician_name:
            trades = self.trade_storage.load_trades(
                politician_name, start_date=start_date, end_date=as_of_date
            )
            if trades is None:
                return pd.DataFrame()
            return trades
        else:
            return self.trade_storage.get_all_trades(
                start_date=start_date, end_date=as_of_date
            )
