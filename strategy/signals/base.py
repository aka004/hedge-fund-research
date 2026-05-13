"""Base signal generator interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date


@dataclass
class Signal:
    """Represents a trading signal for a symbol."""

    symbol: str
    date: date
    signal_name: str
    score: float  # Typically -1 to +1, or 0 to 1
    rank: int | None = None  # Rank within universe (1 = best)
    raw_value: float | None = None  # Underlying raw value
    metadata: dict | None = None


class SignalGenerator(ABC):
    """Abstract base class for signal generators."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the name of this signal."""
        pass

    @abstractmethod
    def generate(
        self,
        symbols: list[str],
        as_of_date: date,
    ) -> list[Signal]:
        """Generate signals for a list of symbols.

        Args:
            symbols: List of ticker symbols
            as_of_date: Date to generate signals as of

        Returns:
            List of Signal objects
        """
        pass

    def _rank_signals(
        self, signals: list[Signal], ascending: bool = False
    ) -> list[Signal]:
        """Add ranks to signals based on score and return them in rank order.

        Args:
            signals: List of signals to rank
            ascending: If True, lower scores get better (lower) ranks

        Returns:
            Signals sorted by score (descending by default), each with
            its ``rank`` attribute set. Callers should treat the input
            list as consumed and use the returned list as the source of
            truth — both reflect the same `Signal` objects, but only
            the return value is in rank order.
        """
        sorted_signals = sorted(
            signals,
            key=lambda s: s.score,
            reverse=not ascending,
        )
        for rank, signal in enumerate(sorted_signals, 1):
            signal.rank = rank
        return sorted_signals
