"""Momentum signal generator."""

import logging
from datetime import date

from data.storage.duckdb_store import DuckDBStore
from strategy.signals.base import Signal, SignalGenerator

logger = logging.getLogger(__name__)


class MomentumSignal(SignalGenerator):
    """Generate momentum signals based on 12-1 month returns and price vs MA."""

    def __init__(
        self,
        duckdb_store: DuckDBStore,
        lookback_months: int = 12,
        skip_months: int = 1,
        ma_window_days: int = 200,
    ) -> None:
        """Initialize momentum signal generator.

        Args:
            duckdb_store: DuckDB store for data access
            lookback_months: Months to calculate return over
            skip_months: Recent months to skip (avoid mean reversion)
            ma_window_days: Days for moving average calculation
        """
        self._store = duckdb_store
        self.lookback_months = lookback_months
        self.skip_months = skip_months
        self.ma_window_days = ma_window_days

    @property
    def name(self) -> str:
        return "momentum"

    def generate(
        self,
        symbols: list[str],
        as_of_date: date,
    ) -> list[Signal]:
        """Generate momentum signals.

        A stock passes the momentum filter if:
        1. 12-1 month return is positive
        2. Current price is above 200-day MA

        Score is the 12-1 month return normalized.
        """
        signals = []

        for symbol in symbols:
            try:
                momentum = self._store.get_momentum(
                    symbol,
                    as_of_date,
                    self.lookback_months,
                    self.skip_months,
                )

                if momentum is None:
                    continue

                ma200 = self._store.get_moving_average(
                    symbol,
                    as_of_date,
                    self.ma_window_days,
                )

                # Get current price
                file_path = self._store.parquet_path / "prices" / f"{symbol}.parquet"
                if not file_path.exists():
                    continue

                current_price_query = f"""
                    SELECT adj_close FROM read_parquet('{file_path}')
                    WHERE date <= '{as_of_date}'
                    ORDER BY date DESC
                    LIMIT 1
                """
                result = self._store._conn.execute(current_price_query).fetchone()
                if not result:
                    continue

                current_price = result[0]

                # Calculate signal
                above_ma = ma200 is not None and current_price > ma200
                positive_momentum = momentum > 0

                # Score: momentum return, but 0 if fails MA filter
                score = momentum if (positive_momentum and above_ma) else 0.0

                signals.append(
                    Signal(
                        symbol=symbol,
                        date=as_of_date,
                        signal_name=self.name,
                        score=score,
                        raw_value=momentum,
                        metadata={
                            "momentum_12_1": momentum,
                            "ma_200": ma200,
                            "current_price": current_price,
                            "above_ma": above_ma,
                        },
                    )
                )

            except Exception as e:
                logger.warning(f"Failed to generate momentum signal for {symbol}: {e}")
                continue

        return self._rank_signals(signals)
