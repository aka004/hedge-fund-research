"""Surprise Alpha signal from prediction market events.

Uses Shannon information content (-log2 P) to quantify how surprising
a resolved event was relative to the market's prior probability.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta
from typing import ClassVar

from data.storage.event_store import EventStore
from strategy.signals.base import Signal, SignalGenerator


@dataclass
class SurpriseSignalConfig:
    """Configuration for the SurpriseSignal generator."""

    min_surprise_bits: float = 4.0  # Minimum bits to qualify (P_market < 6.25%)
    min_history: int = 20  # Minimum confirmed prior events for symbol
    lookback_days: int = 1  # Days back to look for resolved events


class SurpriseSignal(SignalGenerator):
    """Shannon information-theory surprise signal from prediction market events.

    Computes surprise_score = -log2(p_market_pre) for events resolved recently.
    Only emits signals for events with surprise > min_surprise_bits (default 4.0).

    Signal.score = direction * surprise_bits:
      > 0 → long candidate (bullish surprise)
      < 0 → short candidate (bearish surprise)
    """

    _name: ClassVar[str] = "surprise_alpha"

    def __init__(
        self,
        event_store: EventStore,
        config: SurpriseSignalConfig | None = None,
    ) -> None:
        self._store = event_store
        self._config = config or SurpriseSignalConfig()

    @property
    def name(self) -> str:
        return self._name

    @staticmethod
    def compute_surprise(p_market_pre: float, outcome: str) -> tuple[float, int]:
        """Compute surprise score in bits and direction.

        Args:
            p_market_pre: P(bullish outcome) at time of snapshot, 0-1
            outcome: "bullish" | "bearish" | "neutral"

        Returns:
            Tuple of (surprise_bits, direction) where:
              - surprise_bits: -log2(P(actual_outcome)) >= 0
              - direction: +1 (bullish), -1 (bearish), 0 (neutral)

        Notes:
            p_market_pre is P(bullish). So P(bearish) = 1 - p_market_pre.
            For a bullish outcome: surprise = -log2(p_market_pre)
            For a bearish outcome: surprise = -log2(1 - p_market_pre)
            For neutral outcome: surprise = 0, direction = 0
        """
        p = max(1e-9, min(1 - 1e-9, p_market_pre))
        if outcome == "bullish":
            return -math.log2(p), +1
        elif outcome == "bearish":
            return -math.log2(1.0 - p), -1
        else:  # neutral or pending
            return 0.0, 0

    def generate(
        self,
        symbols: list[str],
        as_of_date: date,
    ) -> list[Signal]:
        """Generate surprise signals for recently-resolved events.

        CRITICAL look-ahead bias prevention:
        Only returns events resolved on exactly as_of_date - lookback_days (yesterday
        by default). This generates daily PEAD signals for events that resolved on a
        single specific date, preventing stale events from re-generating signals on
        subsequent simulation days.

        Args:
            symbols: List of ticker symbols to generate signals for
            as_of_date: Current simulation date (signals are for next-day entry)

        Returns:
            List of Signal objects ranked by absolute score descending.
        """
        signals: list[Signal] = []
        latest_event_date = as_of_date - timedelta(days=self._config.lookback_days)

        for symbol in symbols:
            events = self._store.get_events_with_min_history(
                symbol=symbol,
                min_count=self._config.min_history,
            )
            if not events:
                continue

            window_events = [
                e
                for e in events
                if e.event_date == latest_event_date
                and e.outcome_confirmed
                and e.outcome != "pending"
                and e.liquidity_ok
            ]

            for event in window_events:
                bits, direction = self.compute_surprise(
                    event.p_market_pre, event.outcome
                )

                if bits < self._config.min_surprise_bits:
                    continue
                if direction == 0:
                    continue

                signals.append(
                    Signal(
                        symbol=symbol,
                        date=as_of_date,
                        signal_name=self._name,
                        score=direction * bits,
                        raw_value=bits,
                        metadata={
                            "event_id": event.event_id,
                            "p_market_pre": event.p_market_pre,
                            "outcome": event.outcome,
                            "direction": direction,
                            "surprise_bits": bits,
                            "n_historical_events": event.n_historical_events,
                            "event_type": event.event_type,
                        },
                    )
                )

        signals.sort(key=lambda s: abs(s.score), reverse=True)
        return self._rank_signals(signals)
