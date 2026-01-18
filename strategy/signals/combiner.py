"""Signal combiner for multi-factor strategies."""

import logging
from dataclasses import dataclass
from datetime import date

from strategy.signals.base import Signal, SignalGenerator

logger = logging.getLogger(__name__)


@dataclass
class SignalWeight:
    """Weight configuration for a signal."""

    signal_name: str
    weight: float
    min_score: float | None = None  # Minimum score to include


class SignalCombiner:
    """Combines multiple signals into a composite score."""

    def __init__(
        self,
        generators: list[SignalGenerator],
        weights: list[SignalWeight] | None = None,
    ) -> None:
        """Initialize signal combiner.

        Args:
            generators: List of signal generators
            weights: Optional weight configuration (defaults to equal weights)
        """
        self.generators = {g.name: g for g in generators}

        if weights:
            self.weights = {w.signal_name: w for w in weights}
        else:
            # Equal weights by default
            equal_weight = 1.0 / len(generators)
            self.weights = {
                g.name: SignalWeight(g.name, equal_weight) for g in generators
            }

    def generate_combined(
        self,
        symbols: list[str],
        as_of_date: date,
    ) -> list[Signal]:
        """Generate combined signals for all symbols.

        Args:
            symbols: List of ticker symbols
            as_of_date: Date to generate signals as of

        Returns:
            List of combined signals sorted by score
        """
        # Generate all component signals
        all_signals: dict[str, dict[str, Signal]] = {}

        for name, generator in self.generators.items():
            signals = generator.generate(symbols, as_of_date)
            for signal in signals:
                if signal.symbol not in all_signals:
                    all_signals[signal.symbol] = {}
                all_signals[signal.symbol][name] = signal

        # Combine signals for each symbol
        combined_signals = []

        for symbol, signal_dict in all_signals.items():
            combined_score = 0.0
            total_weight = 0.0
            component_scores = {}
            passes_all = True

            for signal_name, weight_config in self.weights.items():
                if signal_name not in signal_dict:
                    continue

                signal = signal_dict[signal_name]

                # Check minimum score threshold
                if weight_config.min_score is not None and signal.score < weight_config.min_score:
                    passes_all = False

                component_scores[signal_name] = signal.score
                combined_score += signal.score * weight_config.weight
                total_weight += weight_config.weight

            if total_weight > 0:
                normalized_score = combined_score / total_weight if passes_all else 0.0
            else:
                normalized_score = 0.0

            combined_signals.append(
                Signal(
                    symbol=symbol,
                    date=as_of_date,
                    signal_name="combined",
                    score=normalized_score,
                    metadata={
                        "component_scores": component_scores,
                        "passes_all_filters": passes_all,
                        "weights": {n: w.weight for n, w in self.weights.items()},
                    },
                )
            )

        # Sort by score and add ranks
        combined_signals.sort(key=lambda s: s.score, reverse=True)
        for rank, signal in enumerate(combined_signals, 1):
            signal.rank = rank

        return combined_signals

    def get_top_picks(
        self,
        symbols: list[str],
        as_of_date: date,
        n_picks: int = 20,
        min_combined_score: float = 0.0,
    ) -> list[Signal]:
        """Get top N stock picks based on combined signal.

        Args:
            symbols: List of ticker symbols
            as_of_date: Date to generate signals as of
            n_picks: Number of top picks to return
            min_combined_score: Minimum combined score threshold

        Returns:
            Top N signals by combined score
        """
        combined = self.generate_combined(symbols, as_of_date)

        # Filter by minimum score
        filtered = [s for s in combined if s.score >= min_combined_score]

        return filtered[:n_picks]
