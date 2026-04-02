"""
ExpressionSignal — SignalGenerator that evaluates alpha expressions on OHLCV data.

Wraps the expression engine (parser + evaluator) behind the standard
SignalGenerator interface so it plugs directly into SignalCombiner and
EventDrivenEngine without any changes to downstream code.
"""

from __future__ import annotations

import logging
from datetime import date

import pandas as pd

from strategy.signals.base import Signal, SignalGenerator
from strategy.signals.expression.evaluator import evaluate_expression
from strategy.signals.expression.parser import parse

logger = logging.getLogger(__name__)


class ExpressionSignal(SignalGenerator):
    """Generate trading signals from an alpha factor expression.

    Args:
        expression: Alpha expression string, e.g.
            "cs_rank(ts_corr(close, volume, 10)) - cs_rank(delta(close, 21))"
        ohlcv: Dict mapping column names to DataFrames (dates × symbols).
            Keys: "open", "high", "low", "close", "volume"
    """

    def __init__(self, expression: str, ohlcv: dict[str, pd.DataFrame]) -> None:
        self.expression = expression
        self.ohlcv = ohlcv
        # Validate expression at construction time — fail fast
        self._ast = parse(expression)

    @property
    def name(self) -> str:
        return f"expr_{hash(self.expression) % 10000:04d}"

    def generate(self, symbols: list[str], as_of_date: date) -> list[Signal]:
        """Evaluate expression and return scored signals for requested symbols."""
        # Filter OHLCV to only the requested symbols (columns)
        available = set()
        for df in self.ohlcv.values():
            available.update(df.columns)
        valid_symbols = [s for s in symbols if s in available]

        if not valid_symbols:
            logger.warning("No symbols with OHLCV data available")
            return []

        filtered_ohlcv = {
            col: df[[s for s in valid_symbols if s in df.columns]]
            for col, df in self.ohlcv.items()
        }

        try:
            scores = evaluate_expression(self.expression, filtered_ohlcv, as_of_date)
        except Exception as e:
            logger.error(f"Expression evaluation failed: {e}")
            return []

        # Build Signal objects for non-NaN scores
        signals = []
        for symbol in valid_symbols:
            score = scores.get(symbol)
            if score is None or pd.isna(score):
                continue
            signals.append(
                Signal(
                    symbol=symbol,
                    date=as_of_date,
                    signal_name=self.name,
                    score=float(score),
                    raw_value=float(score),
                    metadata={"expression": self.expression},
                )
            )

        return self._rank_signals(signals)
