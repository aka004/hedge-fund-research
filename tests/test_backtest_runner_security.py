"""Ticker / date validation in DashboardBacktestRunner._fetch_prices.

Prevents SQL injection via the `tickers` and date arguments (which are
f-string-interpolated into a DuckDB query in the original code).
"""

import sys
from pathlib import Path

import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend"))

from app.services.backtest_runner import DashboardBacktestRunner


@pytest.fixture
def runner():
    return DashboardBacktestRunner()


class TestTickerValidation:
    def test_valid_tickers_pass_validation(self, runner):
        # The validation layer is what we're testing. The DB may not be
        # mounted in CI / dev — that's fine, we only care that valid
        # ticker shapes are NOT rejected by the regex.
        try:
            runner._fetch_prices(["AAPL", "GOOGL", "BRK.B"], "2024-01-01", "2024-01-31")
        except ValueError as e:
            if "ticker" in str(e).lower():
                pytest.fail(f"valid ticker rejected: {e}")
        except Exception:
            # Downstream DB / pivot errors are out of scope here.
            pass

    def test_sql_injection_in_ticker_rejected(self, runner):
        bad = ["AAPL", "GOOG'; DROP TABLE prices--"]
        with pytest.raises(ValueError, match="ticker"):
            runner._fetch_prices(bad, "2024-01-01", "2024-01-31")

    def test_quote_in_ticker_rejected(self, runner):
        with pytest.raises(ValueError, match="ticker"):
            runner._fetch_prices(["AAPL'"], "2024-01-01", "2024-01-31")

    def test_long_ticker_rejected(self, runner):
        with pytest.raises(ValueError, match="ticker"):
            runner._fetch_prices(["A" * 50], "2024-01-01", "2024-01-31")

    def test_empty_ticker_rejected(self, runner):
        with pytest.raises(ValueError, match="ticker"):
            runner._fetch_prices([""], "2024-01-01", "2024-01-31")


class TestDateValidation:
    def test_valid_iso_dates_pass(self, runner):
        try:
            runner._fetch_prices(["AAPL"], "2024-01-01", "2024-01-31")
        except ValueError as e:
            if "date" in str(e).lower():
                pytest.fail(f"valid date rejected: {e}")
        except Exception:
            pass

    def test_sql_injection_in_start_date_rejected(self, runner):
        with pytest.raises(ValueError, match="date"):
            runner._fetch_prices(
                ["AAPL"], "2024-01-01'; DROP TABLE prices--", "2024-01-31"
            )

    def test_sql_injection_in_end_date_rejected(self, runner):
        with pytest.raises(ValueError, match="date"):
            runner._fetch_prices(["AAPL"], "2024-01-01", "2024-01-31' OR '1'='1")
