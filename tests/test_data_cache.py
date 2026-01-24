"""Data Cache Tests - Verify Parquet data is complete for agents.

This module tests that cached Parquet data meets agent requirements.
Run AFTER fetch_data.py has populated the cache.

Usage:
    # Check if cache is ready for Momentum Researcher
    pytest tests/test_data_cache.py -v

    # Check specific universe coverage
    pytest tests/test_data_cache.py::TestCacheCompleteness -v
"""

import logging
from datetime import date
from pathlib import Path

import pytest

from data.storage.parquet import ParquetStorage
from data.storage.universe import SP500_SYMBOLS

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================

# Default cache location
DEFAULT_CACHE_PATH = Path(__file__).parent.parent / "data" / "cache"

# Momentum Researcher requirements
REQUIRED_YEARS = 7
MIN_TRADING_DAYS = 200 * REQUIRED_YEARS  # ~252 trading days/year
MAX_STALE_DAYS = 5  # Data should be updated within 5 days

# Coverage thresholds
MIN_UNIVERSE_COVERAGE = 0.90  # 90% of S&P 500 should have data


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def storage():
    """Get Parquet storage instance."""
    return ParquetStorage(DEFAULT_CACHE_PATH)


@pytest.fixture
def cached_symbols(storage):
    """Get list of symbols with cached price data."""
    return storage.list_symbols("prices")


# =============================================================================
# Cache Existence Tests
# =============================================================================


class TestCacheExists:
    """Test that cache directory and data exist."""

    def test_cache_directory_exists(self):
        """Verify cache directory exists."""
        assert DEFAULT_CACHE_PATH.exists(), (
            f"Cache directory not found: {DEFAULT_CACHE_PATH}\n"
            "Run: python scripts/fetch_data.py --universe sp500 --years 7"
        )

    def test_prices_directory_exists(self):
        """Verify prices subdirectory exists."""
        prices_dir = DEFAULT_CACHE_PATH / "prices"
        assert prices_dir.exists(), (
            f"Prices directory not found: {prices_dir}\n"
            "Run: python scripts/fetch_data.py --universe sp500 --years 7"
        )

    def test_has_parquet_files(self, storage):
        """Verify at least some Parquet files exist."""
        symbols = storage.list_symbols("prices")
        assert len(symbols) > 0, (
            "No cached price data found.\n"
            "Run: python scripts/fetch_data.py --universe sp500 --years 7"
        )


# =============================================================================
# Cache Completeness Tests
# =============================================================================


class TestCacheCompleteness:
    """Test that cached data is complete enough for agents."""

    def test_universe_coverage(self, storage):
        """Test that enough S&P 500 symbols are cached."""
        cached = set(storage.list_symbols("prices"))
        required = set(SP500_SYMBOLS)

        coverage = len(cached & required) / len(required)

        assert coverage >= MIN_UNIVERSE_COVERAGE, (
            f"Only {coverage:.1%} of S&P 500 cached (need {MIN_UNIVERSE_COVERAGE:.0%})\n"
            f"Missing: {required - cached}\n"
            "Run: python scripts/fetch_data.py --universe sp500 --years 7"
        )

    def test_sufficient_history_coverage(self, storage, cached_symbols):
        """Test that cached symbols have enough history."""
        if not cached_symbols:
            pytest.skip("No cached symbols")

        symbols_with_enough = 0
        symbols_without = []

        for symbol in cached_symbols[:50]:  # Sample first 50
            df = storage.load_prices(symbol)
            if df is not None and len(df) >= MIN_TRADING_DAYS * 0.9:  # 90% slack
                symbols_with_enough += 1
            else:
                row_count = len(df) if df is not None else 0
                symbols_without.append(f"{symbol}({row_count})")

        coverage = symbols_with_enough / min(50, len(cached_symbols))
        assert coverage >= 0.90, (
            f"Only {coverage:.1%} of sampled symbols have {REQUIRED_YEARS}+ years\n"
            f"Insufficient: {symbols_without[:10]}..."
        )

    def test_data_freshness(self, storage, cached_symbols):
        """Test that cached data is recent (not stale)."""
        if not cached_symbols:
            pytest.skip("No cached symbols")

        stale_symbols = []
        today = date.today()

        for symbol in cached_symbols[:20]:  # Sample 20
            last_date = storage.get_last_date(symbol)
            if last_date:
                days_stale = (today - last_date).days
                if days_stale > MAX_STALE_DAYS:
                    stale_symbols.append(f"{symbol}({days_stale}d)")

        assert len(stale_symbols) == 0, (
            f"Stale data found (>{MAX_STALE_DAYS} days old): {stale_symbols}\n"
            "Run: python scripts/fetch_data.py --universe sp500"
        )


# =============================================================================
# Momentum Researcher Specific Tests
# =============================================================================


class TestMomentumCache:
    """Test cache meets Momentum Researcher requirements."""

    def test_momentum_symbols_cached(self, storage):
        """Test that key momentum symbols are cached."""
        key_symbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA"]
        cached = set(storage.list_symbols("prices"))

        missing = [s for s in key_symbols if s not in cached]
        assert len(missing) == 0, (
            f"Key symbols missing from cache: {missing}\n"
            f"Run: python scripts/fetch_data.py --symbols {' '.join(missing)}"
        )

    def test_momentum_calculation_ready(self, storage):
        """Test that cached data supports momentum calculation."""
        symbol = "AAPL"  # Test with AAPL
        df = storage.load_prices(symbol)

        if df is None:
            pytest.skip(f"{symbol} not in cache")

        # Need 13 months * 21 trading days for 12-1 momentum
        min_rows = 13 * 21
        assert (
            len(df) >= min_rows
        ), f"{symbol}: Only {len(df)} rows, need {min_rows}+ for momentum"

    def test_ma200_calculation_ready(self, storage):
        """Test that cached data supports 200-day MA."""
        symbol = "AAPL"
        df = storage.load_prices(symbol)

        if df is None:
            pytest.skip(f"{symbol} not in cache")

        assert len(df) >= 200, f"{symbol}: Only {len(df)} rows, need 200+ for MA"


# =============================================================================
# Data Quality in Cache
# =============================================================================


class TestCacheQuality:
    """Test quality of cached data."""

    def test_no_zero_prices_in_cache(self, storage, cached_symbols):
        """Verify no zero prices in cached data."""
        if not cached_symbols:
            pytest.skip("No cached symbols")

        symbols_with_zeros = []

        for symbol in cached_symbols[:20]:  # Sample 20
            df = storage.load_prices(symbol)
            if df is not None:
                zeros = (df["adj_close"] == 0).sum()
                if zeros > 0:
                    symbols_with_zeros.append(f"{symbol}({zeros})")

        assert (
            len(symbols_with_zeros) == 0
        ), f"Symbols with zero prices (missing data): {symbols_with_zeros}"

    def test_no_duplicate_dates(self, storage, cached_symbols):
        """Verify no duplicate dates in cached data."""
        if not cached_symbols:
            pytest.skip("No cached symbols")

        symbols_with_dupes = []

        for symbol in cached_symbols[:20]:
            df = storage.load_prices(symbol)
            if df is not None:
                dupes = df["date"].duplicated().sum()
                if dupes > 0:
                    symbols_with_dupes.append(f"{symbol}({dupes})")

        assert (
            len(symbols_with_dupes) == 0
        ), f"Symbols with duplicate dates: {symbols_with_dupes}"


# =============================================================================
# Status Report
# =============================================================================


class TestCacheReport:
    """Generate cache status report."""

    def test_generate_cache_report(self, storage, cached_symbols, capsys):
        """Generate summary report of cache status."""
        if not cached_symbols:
            print("\nNO CACHE DATA FOUND")
            print("Run: python scripts/fetch_data.py --universe sp500 --years 7")
            assert True
            return

        print("\n" + "=" * 60)
        print("CACHE STATUS REPORT")
        print("=" * 60)
        print(f"Cache path: {DEFAULT_CACHE_PATH}")
        print(f"Cached symbols: {len(cached_symbols)}")
        print(f"S&P 500 symbols: {len(SP500_SYMBOLS)}")

        # Coverage
        cached_set = set(cached_symbols)
        sp500_set = set(SP500_SYMBOLS)
        coverage = len(cached_set & sp500_set) / len(sp500_set)
        print(f"S&P 500 coverage: {coverage:.1%}")

        # Sample data quality
        print("-" * 60)
        print(f"{'Symbol':<8} {'Rows':>7} {'Years':>6} {'First':>12} {'Last':>12}")
        print("-" * 60)

        sample = cached_symbols[:10]
        for symbol in sample:
            df = storage.load_prices(symbol)
            if df is not None and len(df) > 0:
                first = df["date"].min()
                last = df["date"].max()
                years = (last - first).days / 365
                print(f"{symbol:<8} {len(df):>7} {years:>5.1f}y {first} {last}")

        print("=" * 60)

        # Always pass - this is for reporting
        assert True
