"""Data Fetch Tests - Validate data availability for agents.

This module tests that the data pipeline can fetch all required data
without requiring alpha strategies to be implemented.

Usage:
    # Run all data fetch tests (hits real APIs)
    pytest tests/test_data_fetch.py -v

    # Run quick smoke test (single symbol)
    pytest tests/test_data_fetch.py -v -m smoke

    # Run full universe test (all S&P 500 symbols)
    pytest tests/test_data_fetch.py -v -m universe
"""

import logging
from datetime import date, timedelta

import pytest

from data.providers.yahoo import YahooFinanceProvider
from data.storage.universe import SP500_SYMBOLS

logger = logging.getLogger(__name__)


# =============================================================================
# Test Configuration
# =============================================================================

# Momentum Researcher data requirements (from design doc)
REQUIRED_YEARS = 7  # 7-10 years of daily OHLCV
REQUIRED_COLUMNS = ["date", "open", "high", "low", "close", "volume", "adj_close"]
MIN_TRADING_DAYS_PER_YEAR = 200  # ~252 trading days/year, allow some slack

# Test symbols for quick validation
SMOKE_TEST_SYMBOLS = ["AAPL", "MSFT", "GOOGL", "AMZN", "META"]


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def yahoo_provider():
    """Create Yahoo Finance provider with relaxed rate limits for testing."""
    return YahooFinanceProvider()


@pytest.fixture
def end_date():
    """Use a fixed end date to avoid weekend/holiday issues."""
    today = date.today()
    # Go back to last Friday if weekend
    days_since_friday = (today.weekday() - 4) % 7
    if days_since_friday == 0 and today.weekday() > 4:
        days_since_friday = 7
    return today - timedelta(days=days_since_friday) if days_since_friday else today


@pytest.fixture
def start_date(end_date):
    """Calculate start date for required history."""
    return end_date - timedelta(days=REQUIRED_YEARS * 365)


# =============================================================================
# Data Availability Tests
# =============================================================================


class TestDataAvailability:
    """Test that data can be fetched from providers."""

    @pytest.mark.smoke
    def test_yahoo_connection(self, yahoo_provider):
        """Verify Yahoo Finance API is reachable."""
        # Just fetch 5 days for a single symbol
        df = yahoo_provider.get_historical_prices(
            "AAPL",
            date.today() - timedelta(days=10),
            date.today(),
        )
        assert df is not None, "Yahoo Finance API not reachable"
        assert len(df) > 0, "No data returned from Yahoo Finance"

    @pytest.mark.smoke
    @pytest.mark.parametrize("symbol", SMOKE_TEST_SYMBOLS)
    def test_fetch_smoke_symbols(self, yahoo_provider, symbol, start_date, end_date):
        """Smoke test: Fetch required history for key symbols."""
        df = yahoo_provider.get_historical_prices(symbol, start_date, end_date)

        assert df is not None, f"No data for {symbol}"
        assert len(df) > 0, f"Empty dataframe for {symbol}"

        # Check we have required columns
        missing_cols = set(REQUIRED_COLUMNS) - set(df.columns)
        assert not missing_cols, f"Missing columns for {symbol}: {missing_cols}"


# =============================================================================
# Data Completeness Tests
# =============================================================================


class TestDataCompleteness:
    """Test that fetched data meets agent requirements."""

    @pytest.mark.smoke
    @pytest.mark.parametrize("symbol", SMOKE_TEST_SYMBOLS)
    def test_sufficient_history(self, yahoo_provider, symbol, start_date, end_date):
        """Verify we have enough historical data (7+ years)."""
        df = yahoo_provider.get_historical_prices(symbol, start_date, end_date)

        if df is None or len(df) == 0:
            pytest.skip(f"No data available for {symbol}")

        # Calculate date range
        first_date = df["date"].min()
        last_date = df["date"].max()
        date_range_days = (last_date - first_date).days

        min_required_days = REQUIRED_YEARS * 365 - 30  # Allow 30-day slack
        assert date_range_days >= min_required_days, (
            f"{symbol}: Only {date_range_days} days of history, "
            f"need {min_required_days}+ days ({REQUIRED_YEARS} years)"
        )

    @pytest.mark.smoke
    @pytest.mark.parametrize("symbol", SMOKE_TEST_SYMBOLS)
    def test_trading_day_density(self, yahoo_provider, symbol, start_date, end_date):
        """Verify we have enough trading days per year (not sparse data)."""
        df = yahoo_provider.get_historical_prices(symbol, start_date, end_date)

        if df is None or len(df) == 0:
            pytest.skip(f"No data available for {symbol}")

        # Count trading days
        total_days = len(df)
        first_date = df["date"].min()
        last_date = df["date"].max()
        years_covered = (last_date - first_date).days / 365

        if years_covered > 0:
            days_per_year = total_days / years_covered
            assert days_per_year >= MIN_TRADING_DAYS_PER_YEAR, (
                f"{symbol}: Only {days_per_year:.0f} trading days/year, "
                f"need {MIN_TRADING_DAYS_PER_YEAR}+"
            )


# =============================================================================
# Data Quality Tests
# =============================================================================


class TestDataQuality:
    """Test data quality (no zeros, proper values, etc.)."""

    @pytest.mark.smoke
    @pytest.mark.parametrize("symbol", SMOKE_TEST_SYMBOLS)
    def test_no_zero_prices(self, yahoo_provider, symbol, start_date, end_date):
        """Verify no zero values in price columns (indicates missing data)."""
        df = yahoo_provider.get_historical_prices(symbol, start_date, end_date)

        if df is None or len(df) == 0:
            pytest.skip(f"No data available for {symbol}")

        price_cols = ["open", "high", "low", "close", "adj_close"]
        for col in price_cols:
            if col in df.columns:
                zero_count = (df[col] == 0).sum()
                assert zero_count == 0, (
                    f"{symbol}: Found {zero_count} zero values in '{col}' "
                    "(likely missing data)"
                )

    @pytest.mark.smoke
    @pytest.mark.parametrize("symbol", SMOKE_TEST_SYMBOLS)
    def test_no_negative_prices(self, yahoo_provider, symbol, start_date, end_date):
        """Verify no negative prices (data corruption)."""
        df = yahoo_provider.get_historical_prices(symbol, start_date, end_date)

        if df is None or len(df) == 0:
            pytest.skip(f"No data available for {symbol}")

        price_cols = ["open", "high", "low", "close", "adj_close"]
        for col in price_cols:
            if col in df.columns:
                negative_count = (df[col] < 0).sum()
                assert (
                    negative_count == 0
                ), f"{symbol}: Found {negative_count} negative values in '{col}'"

    @pytest.mark.smoke
    @pytest.mark.parametrize("symbol", SMOKE_TEST_SYMBOLS)
    def test_no_nan_prices(self, yahoo_provider, symbol, start_date, end_date):
        """Check for NaN values in critical columns."""
        df = yahoo_provider.get_historical_prices(symbol, start_date, end_date)

        if df is None or len(df) == 0:
            pytest.skip(f"No data available for {symbol}")

        # adj_close is critical for momentum calculation
        nan_count = df["adj_close"].isna().sum()
        nan_pct = nan_count / len(df) * 100

        # Allow up to 1% NaN (some historical gaps are normal)
        assert nan_pct <= 1.0, (
            f"{symbol}: {nan_pct:.1f}% NaN values in adj_close "
            f"({nan_count}/{len(df)} rows)"
        )

    @pytest.mark.smoke
    @pytest.mark.parametrize("symbol", SMOKE_TEST_SYMBOLS)
    def test_price_ordering(self, yahoo_provider, symbol, start_date, end_date):
        """Verify OHLC ordering: low <= open/close <= high."""
        df = yahoo_provider.get_historical_prices(symbol, start_date, end_date)

        if df is None or len(df) == 0:
            pytest.skip(f"No data available for {symbol}")

        # Check: low <= high
        invalid_lh = df[df["low"] > df["high"]]
        assert len(invalid_lh) == 0, f"{symbol}: {len(invalid_lh)} rows with low > high"

        # Check: low <= open <= high
        invalid_open = df[(df["open"] < df["low"]) | (df["open"] > df["high"])]
        assert (
            len(invalid_open) == 0
        ), f"{symbol}: {len(invalid_open)} rows with open outside low-high range"

        # Check: low <= close <= high
        invalid_close = df[(df["close"] < df["low"]) | (df["close"] > df["high"])]
        assert (
            len(invalid_close) == 0
        ), f"{symbol}: {len(invalid_close)} rows with close outside low-high range"


# =============================================================================
# Momentum-Specific Requirements
# =============================================================================


class TestMomentumRequirements:
    """Test data requirements specific to Momentum Researcher."""

    @pytest.mark.smoke
    @pytest.mark.parametrize("symbol", SMOKE_TEST_SYMBOLS)
    def test_momentum_calculation_feasible(
        self, yahoo_provider, symbol, start_date, end_date
    ):
        """Verify we can calculate 12-1 month momentum."""
        df = yahoo_provider.get_historical_prices(symbol, start_date, end_date)

        if df is None or len(df) == 0:
            pytest.skip(f"No data available for {symbol}")

        # Need at least 12 months + 1 month = ~273 trading days
        min_days_for_momentum = 13 * 21  # 13 months * ~21 trading days
        assert len(df) >= min_days_for_momentum, (
            f"{symbol}: Only {len(df)} days, need {min_days_for_momentum}+ "
            "for 12-1 month momentum"
        )

    @pytest.mark.smoke
    @pytest.mark.parametrize("symbol", SMOKE_TEST_SYMBOLS)
    def test_ma200_calculation_feasible(
        self, yahoo_provider, symbol, start_date, end_date
    ):
        """Verify we can calculate 200-day moving average."""
        df = yahoo_provider.get_historical_prices(symbol, start_date, end_date)

        if df is None or len(df) == 0:
            pytest.skip(f"No data available for {symbol}")

        min_days_for_ma200 = 200
        assert (
            len(df) >= min_days_for_ma200
        ), f"{symbol}: Only {len(df)} days, need {min_days_for_ma200}+ for 200-day MA"


# =============================================================================
# Universe Tests (Full S&P 500)
# =============================================================================


class TestUniverseCoverage:
    """Test data availability across the full universe."""

    @pytest.mark.universe
    def test_universe_fetch_success_rate(self, yahoo_provider, start_date, end_date):
        """Test fetch success rate across S&P 500 universe."""
        success_count = 0
        failure_count = 0
        failures = []

        # Test a sample of the universe (full test would be slow)
        sample_size = min(20, len(SP500_SYMBOLS))
        import random

        sample = random.sample(SP500_SYMBOLS, sample_size)

        for symbol in sample:
            try:
                df = yahoo_provider.get_historical_prices(
                    symbol,
                    end_date - timedelta(days=30),  # Just 30 days for speed
                    end_date,
                )
                if df is not None and len(df) > 0:
                    success_count += 1
                else:
                    failure_count += 1
                    failures.append(symbol)
            except Exception as e:
                failure_count += 1
                failures.append(f"{symbol}: {e}")

        success_rate = success_count / sample_size * 100
        logger.info(f"Universe fetch success rate: {success_rate:.1f}%")

        # Require 90%+ success rate
        assert (
            success_rate >= 90
        ), f"Only {success_rate:.1f}% success rate. Failures: {failures}"


# =============================================================================
# Data Summary Report
# =============================================================================


class TestDataReport:
    """Generate a data availability report."""

    @pytest.mark.smoke
    def test_generate_data_report(self, yahoo_provider, start_date, end_date, capsys):
        """Generate summary report of data availability."""
        report = []
        report.append("\n" + "=" * 60)
        report.append("DATA AVAILABILITY REPORT")
        report.append("=" * 60)
        report.append(f"Required history: {REQUIRED_YEARS} years")
        report.append(f"Date range: {start_date} to {end_date}")
        report.append("-" * 60)

        for symbol in SMOKE_TEST_SYMBOLS:
            try:
                df = yahoo_provider.get_historical_prices(symbol, start_date, end_date)
                if df is not None and len(df) > 0:
                    first_date = df["date"].min()
                    last_date = df["date"].max()
                    years = (last_date - first_date).days / 365
                    nan_pct = df["adj_close"].isna().sum() / len(df) * 100

                    status = "OK" if years >= REQUIRED_YEARS else "INSUFFICIENT"
                    report.append(
                        f"{symbol:6} | {status:12} | {len(df):5} rows | "
                        f"{years:.1f} years | {nan_pct:.1f}% NaN"
                    )
                else:
                    report.append(
                        f"{symbol:6} | NO DATA      | -     rows | - years | - NaN"
                    )
            except Exception as e:
                report.append(f"{symbol:6} | ERROR        | {str(e)[:30]}")

        report.append("=" * 60)

        # Print report
        print("\n".join(report))

        # Always pass - this is just for reporting
        assert True
