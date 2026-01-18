"""Tests for signal generators."""

import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from data.storage.parquet import ParquetStorage
from strategy.signals.base import Signal, SignalGenerator
from strategy.signals.combiner import SignalCombiner, SignalWeight
from strategy.signals.social import SocialSignal
from strategy.signals.value import ValueSignal


class TestSignal:
    """Tests for Signal dataclass."""

    def test_signal_creation(self):
        signal = Signal(
            symbol="AAPL",
            date=date(2024, 1, 1),
            signal_name="test",
            score=0.5,
        )

        assert signal.symbol == "AAPL"
        assert signal.score == 0.5
        assert signal.rank is None

    def test_signal_with_metadata(self):
        signal = Signal(
            symbol="AAPL",
            date=date(2024, 1, 1),
            signal_name="test",
            score=0.5,
            metadata={"extra": "data"},
        )

        assert signal.metadata is not None
        assert signal.metadata["extra"] == "data"


class TestValueSignal:
    """Tests for ValueSignal."""

    @pytest.fixture
    def storage(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = ParquetStorage(Path(tmpdir))

            # Add test fundamentals
            storage.save_fundamentals(
                "AAPL",
                {
                    "symbol": "AAPL",
                    "pe_ratio": 25.0,
                    "earnings": 10000000,
                    "revenue_growth": 0.1,
                },
            )
            storage.save_fundamentals(
                "HIGH_PE",
                {
                    "symbol": "HIGH_PE",
                    "pe_ratio": 100.0,
                    "earnings": 5000000,
                    "revenue_growth": 0.05,
                },
            )
            storage.save_fundamentals(
                "NEGATIVE",
                {
                    "symbol": "NEGATIVE",
                    "pe_ratio": 15.0,
                    "earnings": -1000000,
                    "revenue_growth": -0.1,
                },
            )

            yield storage

    def test_value_signal_passes(self, storage):
        signal_gen = ValueSignal(storage)
        signals = signal_gen.generate(["AAPL"], date(2024, 1, 1))

        assert len(signals) == 1
        assert signals[0].score > 0
        assert signals[0].metadata is not None
        assert signals[0].metadata["passes_filter"] is True

    def test_value_signal_high_pe_fails(self, storage):
        signal_gen = ValueSignal(storage)
        signals = signal_gen.generate(["HIGH_PE"], date(2024, 1, 1))

        assert len(signals) == 1
        assert signals[0].score == 0.0
        assert signals[0].metadata is not None
        assert signals[0].metadata["passes_filter"] is False
        assert "pe_too_high" in signals[0].metadata["fail_reasons"]

    def test_value_signal_negative_earnings_fails(self, storage):
        signal_gen = ValueSignal(storage, require_positive_earnings=True)
        signals = signal_gen.generate(["NEGATIVE"], date(2024, 1, 1))

        assert len(signals) == 1
        assert signals[0].score == 0.0
        assert signals[0].metadata is not None
        assert "negative_earnings" in signals[0].metadata["fail_reasons"]


class TestSocialSignal:
    """Tests for SocialSignal."""

    @pytest.fixture
    def storage(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = ParquetStorage(Path(tmpdir))

            storage.save_sentiment(
                "AAPL",
                {
                    "symbol": "AAPL",
                    "message_count": 100,
                    "bullish_count": 60,
                    "bearish_count": 20,
                    "sentiment_score": 0.5,
                    "watchlist_count": 10000,
                },
            )
            storage.save_sentiment(
                "LOW_MSG",
                {
                    "symbol": "LOW_MSG",
                    "message_count": 2,
                    "bullish_count": 1,
                    "bearish_count": 1,
                    "sentiment_score": 0.0,
                    "watchlist_count": 100,
                },
            )

            yield storage

    def test_social_signal_positive(self, storage):
        signal_gen = SocialSignal(storage, min_message_count=5)
        signals = signal_gen.generate(["AAPL"], date(2024, 1, 1))

        assert len(signals) == 1
        assert signals[0].score > 0

    def test_social_signal_low_message_count_skipped(self, storage):
        signal_gen = SocialSignal(storage, min_message_count=5)
        signals = signal_gen.generate(["LOW_MSG"], date(2024, 1, 1))

        # Should be filtered out due to low message count
        assert len(signals) == 0


class TestSignalCombiner:
    """Tests for SignalCombiner."""

    def test_combine_equal_weights(self):
        # Create mock generators
        mock_gen1 = MagicMock(spec=SignalGenerator)
        mock_gen1.name = "signal1"
        mock_gen1.generate.return_value = [
            Signal("AAPL", date(2024, 1, 1), "signal1", 0.8),
            Signal("GOOGL", date(2024, 1, 1), "signal1", 0.6),
        ]

        mock_gen2 = MagicMock(spec=SignalGenerator)
        mock_gen2.name = "signal2"
        mock_gen2.generate.return_value = [
            Signal("AAPL", date(2024, 1, 1), "signal2", 0.4),
            Signal("GOOGL", date(2024, 1, 1), "signal2", 0.8),
        ]

        combiner = SignalCombiner([mock_gen1, mock_gen2])
        combined = combiner.generate_combined(["AAPL", "GOOGL"], date(2024, 1, 1))

        assert len(combined) == 2
        # AAPL: (0.8 + 0.4) / 2 = 0.6
        # GOOGL: (0.6 + 0.8) / 2 = 0.7
        aapl_signal = next(s for s in combined if s.symbol == "AAPL")
        googl_signal = next(s for s in combined if s.symbol == "GOOGL")

        assert aapl_signal.score == pytest.approx(0.6, rel=0.01)
        assert googl_signal.score == pytest.approx(0.7, rel=0.01)

    def test_get_top_picks(self):
        mock_gen = MagicMock(spec=SignalGenerator)
        mock_gen.name = "test"
        mock_gen.generate.return_value = [
            Signal("AAPL", date(2024, 1, 1), "test", 0.9),
            Signal("GOOGL", date(2024, 1, 1), "test", 0.8),
            Signal("MSFT", date(2024, 1, 1), "test", 0.7),
            Signal("AMZN", date(2024, 1, 1), "test", 0.6),
        ]

        combiner = SignalCombiner([mock_gen])
        top = combiner.get_top_picks(["AAPL", "GOOGL", "MSFT", "AMZN"], date(2024, 1, 1), n_picks=2)

        assert len(top) == 2
        assert top[0].symbol == "AAPL"
        assert top[1].symbol == "GOOGL"

    def test_weighted_combiner(self):
        mock_gen1 = MagicMock(spec=SignalGenerator)
        mock_gen1.name = "high_weight"
        mock_gen1.generate.return_value = [
            Signal("AAPL", date(2024, 1, 1), "high_weight", 1.0),
        ]

        mock_gen2 = MagicMock(spec=SignalGenerator)
        mock_gen2.name = "low_weight"
        mock_gen2.generate.return_value = [
            Signal("AAPL", date(2024, 1, 1), "low_weight", 0.0),
        ]

        weights = [
            SignalWeight("high_weight", 0.8),
            SignalWeight("low_weight", 0.2),
        ]

        combiner = SignalCombiner([mock_gen1, mock_gen2], weights)
        combined = combiner.generate_combined(["AAPL"], date(2024, 1, 1))

        # Expected: (1.0 * 0.8 + 0.0 * 0.2) / 1.0 = 0.8
        assert combined[0].score == pytest.approx(0.8, rel=0.01)
