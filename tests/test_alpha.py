"""Alpha Strategy Tests - Full backtest with momentum signals.

This module runs a complete backtest of the momentum alpha strategy
using cached Parquet data.

Usage:
    pytest tests/test_alpha.py -v
    pytest tests/test_alpha.py -v -s  # Show full report
"""

from datetime import date
from pathlib import Path

import pytest

from data.storage.duckdb_store import DuckDBStore
from data.storage.parquet import ParquetStorage
from data.storage.universe import SP500_SYMBOLS
from strategy.backtest.engine import BacktestConfig, BacktestEngine
from strategy.signals.combiner import SignalCombiner
from strategy.signals.momentum import MomentumSignal

# =============================================================================
# Configuration
# =============================================================================

DEFAULT_CACHE_PATH = Path(__file__).parent.parent / "data" / "cache"

# Backtest period (use data we have)
BACKTEST_START = date(2020, 1, 1)
BACKTEST_END = date(2025, 12, 31)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def parquet_storage():
    """Create Parquet storage instance."""
    return ParquetStorage(DEFAULT_CACHE_PATH)


@pytest.fixture
def duckdb_store():
    """Create DuckDB store instance."""
    store = DuckDBStore(DEFAULT_CACHE_PATH)
    yield store
    store.close()


@pytest.fixture
def cached_symbols():
    """Get symbols with cached data."""
    return [
        s
        for s in SP500_SYMBOLS
        if (DEFAULT_CACHE_PATH / "prices" / f"{s}.parquet").exists()
    ]


@pytest.fixture
def momentum_signal(duckdb_store):
    """Create momentum signal generator."""
    return MomentumSignal(duckdb_store)


@pytest.fixture
def signal_combiner(momentum_signal):
    """Create signal combiner with momentum only."""
    return SignalCombiner([momentum_signal])


@pytest.fixture
def backtest_config():
    """Create backtest configuration."""
    return BacktestConfig(
        initial_capital=100000.0,
        max_positions=20,
        rebalance_frequency="monthly",
        position_sizing="equal",
    )


@pytest.fixture
def backtest_engine(parquet_storage, duckdb_store, signal_combiner, backtest_config):
    """Create backtest engine."""
    return BacktestEngine(
        parquet_storage=parquet_storage,
        duckdb_store=duckdb_store,
        signal_combiner=signal_combiner,
        config=backtest_config,
    )


# =============================================================================
# Basic Backtest Tests
# =============================================================================


class TestBacktestRuns:
    """Test that backtest runs without errors."""

    def test_backtest_completes(self, backtest_engine, cached_symbols):
        """Test that backtest completes without errors."""
        # Use shorter period for quick test
        result = backtest_engine.run(
            universe=cached_symbols[:100],  # Subset for speed
            start_date=date(2024, 1, 1),
            end_date=date(2024, 6, 30),
        )

        assert result is not None
        assert result.start_date == date(2024, 1, 1)
        assert result.end_date == date(2024, 6, 30)

    def test_backtest_returns_equity_curve(self, backtest_engine, cached_symbols):
        """Test that backtest returns equity curve."""
        result = backtest_engine.run(
            universe=cached_symbols[:100],
            start_date=date(2024, 1, 1),
            end_date=date(2024, 6, 30),
        )

        assert not result.equity_curve.empty
        assert "equity" in result.equity_curve.columns
        assert "date" in result.equity_curve.columns

    def test_backtest_generates_trades(self, backtest_engine, cached_symbols):
        """Test that backtest generates trades."""
        result = backtest_engine.run(
            universe=cached_symbols[:100],
            start_date=date(2024, 1, 1),
            end_date=date(2024, 6, 30),
        )

        assert result.trade_count > 0


# =============================================================================
# Performance Tests
# =============================================================================


class TestBacktestPerformance:
    """Test backtest performance metrics."""

    def test_total_return_is_reasonable(self, backtest_engine, cached_symbols):
        """Test that total return is within reasonable bounds."""
        result = backtest_engine.run(
            universe=cached_symbols[:100],
            start_date=date(2023, 1, 1),
            end_date=date(2024, 12, 31),
        )

        # Expect return between -50% and +200% over 2 years
        assert (
            -0.5 <= result.total_return <= 2.0
        ), f"Total return {result.total_return:.1%} outside reasonable bounds"

    def test_cagr_is_calculated(self, backtest_engine, cached_symbols):
        """Test that CAGR is calculated correctly."""
        result = backtest_engine.run(
            universe=cached_symbols[:100],
            start_date=date(2023, 1, 1),
            end_date=date(2024, 12, 31),
        )

        # CAGR should be finite and reasonable
        assert -0.5 <= result.cagr <= 1.0, f"CAGR {result.cagr:.1%} outside bounds"

    def test_equity_grows_from_initial_capital(self, backtest_engine, cached_symbols):
        """Test that equity starts at initial capital."""
        result = backtest_engine.run(
            universe=cached_symbols[:100],
            start_date=date(2024, 1, 1),
            end_date=date(2024, 6, 30),
        )

        if not result.equity_curve.empty:
            first_equity = result.equity_curve["equity"].iloc[0]
            # Should be close to initial capital (minus first trades)
            assert 90000 <= first_equity <= 110000


# =============================================================================
# Full Alpha Test
# =============================================================================


class TestMomentumAlpha:
    """Full momentum alpha strategy test."""

    def test_full_backtest_5_years(self, backtest_engine, cached_symbols):
        """Run full 5-year backtest."""
        result = backtest_engine.run(
            universe=cached_symbols,
            start_date=BACKTEST_START,
            end_date=BACKTEST_END,
        )

        # Basic sanity checks
        assert result.trade_count > 100, "Expected many trades over 5 years"
        assert not result.equity_curve.empty, "Expected non-empty equity curve"

        # Strategy should produce some return (positive or negative)
        assert result.total_return != 0, "Expected non-zero return"


# =============================================================================
# Alpha Report
# =============================================================================


class TestAlphaReport:
    """Generate alpha strategy report."""

    def test_generate_alpha_report(self, backtest_engine, cached_symbols, capsys):
        """Generate full alpha strategy report."""
        # Run backtest
        result = backtest_engine.run(
            universe=cached_symbols,
            start_date=BACKTEST_START,
            end_date=BACKTEST_END,
        )

        # Calculate metrics
        if not result.daily_returns.empty:
            sharpe = (result.daily_returns.mean() / result.daily_returns.std()) * (
                252**0.5
            )
            max_dd = (
                (result.equity_curve["equity"].cummax() - result.equity_curve["equity"])
                / result.equity_curve["equity"].cummax()
            ).max()
            volatility = result.daily_returns.std() * (252**0.5)
        else:
            sharpe = 0
            max_dd = 0
            volatility = 0

        # Print report
        print("\n" + "=" * 70)
        print("MOMENTUM ALPHA STRATEGY REPORT")
        print("=" * 70)
        print(f"Backtest Period: {BACKTEST_START} to {BACKTEST_END}")
        print(f"Universe: {len(cached_symbols)} symbols")
        print(f"Initial Capital: ${backtest_engine.config.initial_capital:,.0f}")
        print(f"Max Positions: {backtest_engine.config.max_positions}")
        print(f"Rebalance: {backtest_engine.config.rebalance_frequency}")
        print("-" * 70)

        print("\nPERFORMANCE METRICS:")
        print(f"  Total Return:    {result.total_return:>10.1%}")
        print(f"  CAGR:            {result.cagr:>10.1%}")
        print(f"  Sharpe Ratio:    {sharpe:>10.2f}")
        print(f"  Max Drawdown:    {max_dd:>10.1%}")
        print(f"  Volatility:      {volatility:>10.1%}")
        print(f"  Total Trades:    {result.trade_count:>10}")

        if not result.equity_curve.empty:
            final_equity = result.equity_curve["equity"].iloc[-1]
            print(f"\n  Final Equity:    ${final_equity:>10,.0f}")

        print("-" * 70)

        # Equity curve summary
        if not result.equity_curve.empty:
            print("\nEQUITY CURVE (sampled):")
            print(f"{'Date':<12} {'Equity':>12} {'Positions':>10}")
            sample = result.equity_curve.iloc[::12]  # Every 12th row
            for _, row in sample.iterrows():
                d = row["date"]
                if hasattr(d, "strftime"):
                    d = d.strftime("%Y-%m-%d")
                print(f"{d:<12} ${row['equity']:>11,.0f} {row['position_count']:>10}")

        print("=" * 70)

        # Always pass - this is for reporting
        assert True
