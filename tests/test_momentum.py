"""Tests for Momentum Researcher signal generation.

This module tests the Momentum Researcher using cached Parquet data.
Run AFTER fetch_data.py has populated the cache.

Usage:
    pytest tests/test_momentum.py -v
"""

from datetime import date
from pathlib import Path

import pytest

from data.storage.duckdb_store import DuckDBStore
from data.storage.universe import SP500_SYMBOLS
from strategy.signals.momentum import MomentumSignal

# =============================================================================
# Configuration
# =============================================================================

DEFAULT_CACHE_PATH = Path(__file__).parent.parent / "data" / "cache"
TEST_DATE = date(2026, 1, 22)  # Recent date with data


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def store():
    """Create DuckDB store connected to cache."""
    store = DuckDBStore(DEFAULT_CACHE_PATH)
    yield store
    store.close()


@pytest.fixture
def cached_symbols():
    """Get symbols that have cached data."""
    return [
        s
        for s in SP500_SYMBOLS
        if (DEFAULT_CACHE_PATH / "prices" / f"{s}.parquet").exists()
    ]


@pytest.fixture
def momentum_signal(store):
    """Create Momentum signal generator."""
    return MomentumSignal(store)


# =============================================================================
# Basic Functionality Tests
# =============================================================================


class TestMomentumBasics:
    """Test basic momentum signal functionality."""

    def test_momentum_generator_name(self, momentum_signal):
        """Test that momentum generator has correct name."""
        assert momentum_signal.name == "momentum"

    def test_generate_signals_returns_list(self, momentum_signal, cached_symbols):
        """Test that generate returns a list of signals."""
        # Test with a few symbols
        test_symbols = cached_symbols[:10]
        signals = momentum_signal.generate(test_symbols, TEST_DATE)

        assert isinstance(signals, list)
        assert len(signals) > 0

    def test_signal_has_required_fields(self, momentum_signal, cached_symbols):
        """Test that signals have all required fields."""
        signals = momentum_signal.generate(cached_symbols[:5], TEST_DATE)

        for signal in signals:
            assert signal.symbol is not None
            assert signal.date == TEST_DATE
            assert signal.signal_name == "momentum"
            assert signal.score is not None
            assert signal.metadata is not None

    def test_signal_metadata_has_momentum_data(self, momentum_signal, cached_symbols):
        """Test that signal metadata contains momentum-specific data."""
        signals = momentum_signal.generate(cached_symbols[:5], TEST_DATE)

        for signal in signals:
            assert "momentum_12_1" in signal.metadata
            assert "ma_200" in signal.metadata
            assert "current_price" in signal.metadata
            assert "above_ma" in signal.metadata


# =============================================================================
# Signal Logic Tests
# =============================================================================


class TestMomentumLogic:
    """Test momentum signal calculation logic."""

    def test_positive_momentum_above_ma_has_positive_score(
        self, momentum_signal, cached_symbols
    ):
        """Test that stocks with positive momentum above MA have positive scores."""
        signals = momentum_signal.generate(cached_symbols[:100], TEST_DATE)

        # Find signals with positive momentum and above MA
        passing = [
            s
            for s in signals
            if s.metadata["momentum_12_1"] > 0 and s.metadata["above_ma"]
        ]

        for signal in passing:
            assert signal.score > 0, (
                f"{signal.symbol}: Expected positive score for "
                f"positive momentum ({signal.metadata['momentum_12_1']:.2%}) above MA"
            )

    def test_negative_momentum_has_zero_score(self, momentum_signal, cached_symbols):
        """Test that stocks with negative momentum have zero score."""
        signals = momentum_signal.generate(cached_symbols[:100], TEST_DATE)

        # Find signals with negative momentum
        negative = [s for s in signals if s.metadata["momentum_12_1"] < 0]

        for signal in negative:
            assert signal.score == 0, (
                f"{signal.symbol}: Expected zero score for "
                f"negative momentum ({signal.metadata['momentum_12_1']:.2%})"
            )

    def test_below_ma_has_zero_score(self, momentum_signal, cached_symbols):
        """Test that stocks below MA have zero score even with positive momentum."""
        signals = momentum_signal.generate(cached_symbols[:100], TEST_DATE)

        # Find signals below MA
        below_ma = [s for s in signals if not s.metadata["above_ma"]]

        for signal in below_ma:
            assert signal.score == 0, (
                f"{signal.symbol}: Expected zero score when below MA "
                f"(price: {signal.metadata['current_price']:.2f}, "
                f"MA: {signal.metadata['ma_200']:.2f})"
            )

    def test_score_equals_momentum_when_passing(self, momentum_signal, cached_symbols):
        """Test that score equals momentum return when passing all filters."""
        signals = momentum_signal.generate(cached_symbols[:50], TEST_DATE)

        passing = [s for s in signals if s.score > 0]

        for signal in passing:
            expected = signal.metadata["momentum_12_1"]
            assert signal.score == pytest.approx(expected, rel=0.01), (
                f"{signal.symbol}: Score {signal.score:.4f} != "
                f"momentum {expected:.4f}"
            )


# =============================================================================
# Universe Coverage Tests
# =============================================================================


class TestMomentumCoverage:
    """Test momentum signal coverage across universe."""

    def test_generates_signals_for_most_symbols(self, momentum_signal, cached_symbols):
        """Test that signals are generated for most cached symbols."""
        signals = momentum_signal.generate(cached_symbols, TEST_DATE)

        coverage = len(signals) / len(cached_symbols)
        assert (
            coverage >= 0.90
        ), f"Only {coverage:.1%} of symbols have signals, expected 90%+"

    def test_some_stocks_pass_filter(self, momentum_signal, cached_symbols):
        """Test that some stocks pass the momentum filter."""
        signals = momentum_signal.generate(cached_symbols, TEST_DATE)
        passing = [s for s in signals if s.score > 0]

        # At least 20% should pass in normal market conditions
        pass_rate = len(passing) / len(signals)
        assert pass_rate >= 0.20, f"Only {pass_rate:.1%} passing, expected at least 20%"

    def test_signals_have_ranks(self, momentum_signal, cached_symbols):
        """Test that all signals have ranks assigned."""
        signals = momentum_signal.generate(cached_symbols[:50], TEST_DATE)

        for signal in signals:
            assert signal.rank is not None
            assert signal.rank >= 1


# =============================================================================
# Data Quality Tests
# =============================================================================


class TestMomentumDataQuality:
    """Test data quality in momentum calculations."""

    def test_no_nan_momentum_values(self, momentum_signal, cached_symbols):
        """Test that momentum values are not NaN."""
        signals = momentum_signal.generate(cached_symbols[:100], TEST_DATE)

        for signal in signals:
            import math

            assert not math.isnan(
                signal.metadata["momentum_12_1"]
            ), f"{signal.symbol}: NaN momentum value"

    def test_no_nan_ma_values(self, momentum_signal, cached_symbols):
        """Test that MA values are not NaN for stocks with signals."""
        signals = momentum_signal.generate(cached_symbols[:100], TEST_DATE)

        for signal in signals:
            ma = signal.metadata["ma_200"]
            if ma is not None:
                import math

                assert not math.isnan(ma), f"{signal.symbol}: NaN MA value"

    def test_price_is_positive(self, momentum_signal, cached_symbols):
        """Test that current prices are positive."""
        signals = momentum_signal.generate(cached_symbols[:100], TEST_DATE)

        for signal in signals:
            price = signal.metadata["current_price"]
            assert price > 0, f"{signal.symbol}: Invalid price {price}"


# =============================================================================
# Performance Test
# =============================================================================


class TestMomentumPerformance:
    """Test momentum signal generation performance."""

    def test_full_universe_under_10_seconds(self, momentum_signal, cached_symbols):
        """Test that generating signals for full universe is fast."""
        import time

        start = time.time()
        signals = momentum_signal.generate(cached_symbols, TEST_DATE)
        elapsed = time.time() - start

        assert elapsed < 10, f"Signal generation took {elapsed:.1f}s, expected <10s"
        assert len(signals) > 400, f"Only {len(signals)} signals generated"


# =============================================================================
# Summary Report
# =============================================================================


class TestMomentumReport:
    """Generate momentum signal report."""

    def test_generate_momentum_report(self, momentum_signal, cached_symbols, capsys):
        """Generate summary report of momentum signals."""
        signals = momentum_signal.generate(cached_symbols, TEST_DATE)
        passing = [s for s in signals if s.score > 0]

        print("\n" + "=" * 70)
        print("MOMENTUM RESEARCHER REPORT")
        print("=" * 70)
        print(f"As of date: {TEST_DATE}")
        print(f"Universe size: {len(cached_symbols)}")
        print(f"Signals generated: {len(signals)}")
        print(f"Passing filter: {len(passing)} ({len(passing)/len(signals):.1%})")
        print("-" * 70)

        # Top 10
        print("\nTOP 10 MOMENTUM STOCKS:")
        top_10 = sorted(passing, key=lambda x: x.score, reverse=True)[:10]
        print(f"{'Rank':<6}{'Symbol':<8}{'Momentum':>12}{'Price':>12}{'MA200':>12}")
        for i, s in enumerate(top_10, 1):
            m = s.metadata
            print(
                f"{i:<6}{s.symbol:<8}{m['momentum_12_1']:>11.1%}"
                f"{m['current_price']:>12.2f}{m['ma_200']:>12.2f}"
            )

        print("=" * 70)

        # Always pass - this is for reporting
        assert True
