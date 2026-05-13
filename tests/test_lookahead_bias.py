"""Regression tests for look-ahead bias fixes (2026-05-13 code review).

CLAUDE.md states the project's Backtest Safety rule:
"No look-ahead bias: only use data available at decision time."

These tests close three CRITICAL findings:

1. SocialSignal.generate read the most recent cached sentiment via
   `iloc[-1]` regardless of `as_of_date` — future sentiment leaked into
   historical signals.
2. PoliticianSignal._get_politician_win_rate called
   `tracker.calculate_performance()` with no `end_date`, so future trade
   outcomes weighted today's signal.
3. PoliticianTracker._calculate_trade_returns marked open positions to
   `date.today()` — pure future-price look-ahead during backtests.
"""

import sys
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from analysis.politician_tracker import PoliticianTracker
from strategy.signals.politician import PoliticianSignal
from strategy.signals.social import SocialSignal


class TestSocialSignalLookahead:
    """SocialSignal must not read sentiment rows after as_of_date."""

    def _build_storage(self, sentiment_df: pd.DataFrame) -> MagicMock:
        storage = MagicMock()
        storage.load_sentiment.return_value = sentiment_df
        return storage

    def test_future_sentiment_row_is_ignored(self):
        # Two rows: a positive one BEFORE as_of_date and a negative one
        # AFTER. With the bug, iloc[-1] picks the future negative row.
        df = pd.DataFrame(
            {
                "date": [date(2024, 1, 1), date(2024, 12, 31)],
                "message_count": [100, 100],
                "sentiment_score": [0.8, -0.8],
                "watchlist_count": [1000, 1000],
                "bullish_count": [80, 20],
                "bearish_count": [20, 80],
            }
        )
        signal = SocialSignal(self._build_storage(df), min_message_count=1)

        signals = signal.generate(["AAPL"], as_of_date=date(2024, 6, 1))

        assert len(signals) == 1, "expected exactly one signal"
        assert signals[0].raw_value > 0, (
            "look-ahead leak: signal used future negative sentiment, "
            "should have used pre-as_of_date positive sentiment"
        )

    def test_no_data_before_as_of_date_returns_empty(self):
        df = pd.DataFrame(
            {
                "date": [date(2025, 1, 1)],
                "message_count": [100],
                "sentiment_score": [0.5],
                "watchlist_count": [1000],
                "bullish_count": [50],
                "bearish_count": [50],
            }
        )
        signal = SocialSignal(self._build_storage(df), min_message_count=1)

        signals = signal.generate(["AAPL"], as_of_date=date(2024, 6, 1))

        assert signals == [], "no pre-as_of_date data should produce no signal"


class TestPoliticianSignalLookahead:
    """PoliticianSignal must request win-rate as of as_of_date, not all-time."""

    def test_win_rate_calculated_with_end_date(self, monkeypatch):
        from analysis import politician_tracker as pt_module

        # Spy on PoliticianTracker.calculate_performance to record kwargs.
        calls = []

        def fake_calculate_performance(self_ignore, name, **kwargs):
            calls.append({"politician": name, **kwargs})
            perf = MagicMock()
            perf.win_rate = 60.0
            return perf

        monkeypatch.setattr(
            pt_module.PoliticianTracker,
            "calculate_performance",
            fake_calculate_performance,
        )

        trade_storage = MagicMock()
        trade_storage.get_all_trades.return_value = pd.DataFrame(
            {
                "symbol": ["AAPL"],
                "politician_name": ["Test Politician"],
                "transaction_type": ["Buy"],
                "transaction_date": [date(2024, 1, 15)],
                "shares": [100.0],
                "price": [150.0],
            }
        )
        price_storage = MagicMock()

        sig = PoliticianSignal(
            trade_storage=trade_storage,
            price_storage=price_storage,
            lookback_days=180,
        )

        as_of = date(2024, 6, 1)
        sig.generate(["AAPL"], as_of_date=as_of)

        assert calls, "calculate_performance was never invoked"
        assert calls[0].get("end_date") == as_of, (
            f"look-ahead leak: calculate_performance called with "
            f"end_date={calls[0].get('end_date')!r}, expected {as_of!r}"
        )


class TestPoliticianTrackerLookahead:
    """Open positions must be priced as of end_date, not date.today()."""

    def test_open_position_uses_end_date_not_today(self):
        trades = pd.DataFrame(
            {
                "symbol": ["AAPL"],
                "politician_name": ["Test"],
                "transaction_type": ["Buy"],
                "transaction_date": [date(2023, 1, 15)],
                "shares": [100.0],
                "price": [150.0],
            }
        )

        trade_storage = MagicMock()
        trade_storage.load_trades.return_value = trades

        price_storage = MagicMock()
        captured_dates = []

        def fake_load_prices(symbol, start_date=None, end_date=None, **_):
            captured_dates.append((start_date, end_date))
            return pd.DataFrame(
                {"adj_close": [200.0]}, index=[pd.Timestamp(start_date)]
            )

        price_storage.load_prices.side_effect = fake_load_prices

        tracker = PoliticianTracker(trade_storage, price_storage)
        analysis_end = date(2023, 6, 30)

        tracker.calculate_performance("Test", end_date=analysis_end)

        assert captured_dates, "price storage was never asked for an exit price"
        # The exit-price lookup should be at the analysis end date, not
        # at the buy date (a different existing bug) and not today.
        start, _ = captured_dates[0]
        assert start == analysis_end, (
            f"look-ahead leak: open position priced at {start!r}, "
            f"expected analysis end_date {analysis_end!r}"
        )
