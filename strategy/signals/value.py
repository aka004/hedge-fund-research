"""Value signal generator."""

import logging
from datetime import date

from data.storage.parquet import ParquetStorage
from strategy.signals.base import Signal, SignalGenerator

logger = logging.getLogger(__name__)


class ValueSignal(SignalGenerator):
    """Generate value signals based on fundamental metrics."""

    def __init__(
        self,
        parquet_storage: ParquetStorage,
        max_pe: float = 50.0,
        require_positive_earnings: bool = True,
        require_revenue_growth: bool = True,
    ) -> None:
        """Initialize value signal generator.

        Args:
            parquet_storage: Storage for fundamental data
            max_pe: Maximum P/E ratio to pass filter
            require_positive_earnings: Require positive earnings
            require_revenue_growth: Require positive revenue growth
        """
        self._storage = parquet_storage
        self.max_pe = max_pe
        self.require_positive_earnings = require_positive_earnings
        self.require_revenue_growth = require_revenue_growth

    @property
    def name(self) -> str:
        return "value"

    def generate(
        self,
        symbols: list[str],
        as_of_date: date,
    ) -> list[Signal]:
        """Generate value signals.

        A stock passes the value filter if:
        1. P/E < 50 (not wildly overvalued)
        2. Positive earnings (if required)
        3. Positive revenue growth (if required)

        Score is inverse of P/E (higher score = lower P/E = cheaper)
        """
        signals = []

        for symbol in symbols:
            try:
                fundamentals = self._storage.load_fundamentals(symbol)
                if fundamentals is None:
                    continue

                pe_ratio = fundamentals.get("pe_ratio")
                earnings = fundamentals.get("earnings")
                revenue_growth = fundamentals.get("revenue_growth")

                # Check filters
                passes_filter = True
                fail_reasons = []

                if pe_ratio is None or pe_ratio <= 0:
                    passes_filter = False
                    fail_reasons.append("no_valid_pe")
                elif pe_ratio > self.max_pe:
                    passes_filter = False
                    fail_reasons.append("pe_too_high")

                if self.require_positive_earnings and (earnings is None or earnings <= 0):
                    passes_filter = False
                    fail_reasons.append("negative_earnings")

                if self.require_revenue_growth and (revenue_growth is None or revenue_growth <= 0):
                    passes_filter = False
                    fail_reasons.append("no_revenue_growth")

                # Calculate score: inverse P/E normalized (lower P/E = higher score)
                if passes_filter and pe_ratio and pe_ratio > 0:
                    # Score: 1/PE normalized to roughly 0-1 range
                    score = min(1.0, 10.0 / pe_ratio)
                else:
                    score = 0.0

                signals.append(
                    Signal(
                        symbol=symbol,
                        date=as_of_date,
                        signal_name=self.name,
                        score=score,
                        raw_value=pe_ratio,
                        metadata={
                            "pe_ratio": pe_ratio,
                            "earnings": earnings,
                            "revenue_growth": revenue_growth,
                            "passes_filter": passes_filter,
                            "fail_reasons": fail_reasons,
                        },
                    )
                )

            except Exception as e:
                logger.warning(f"Failed to generate value signal for {symbol}: {e}")
                continue

        return self._rank_signals(signals)
