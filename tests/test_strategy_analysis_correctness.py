"""Regression tests for the strategy / analysis correctness fixes
(2026-05-13 code review, HIGH-severity findings).

Bugs covered:

1. `_rank_signals` returned the original (unsorted) list rather than the
   sorted copy that ranks were assigned to.
2. `MomentumSignal` emitted score=0.0 for stocks that failed the MA
   filter, polluting the combined-signal ranks alongside genuine zeros.
3. `compare_to_benchmark` computed `alpha = excess_strategy - beta *
   excess_benchmark` with no risk-free-rate subtraction — not Jensen's
   alpha. Off by ~`rf · (1 - β)` annually.
4. `PoliticianTracker` labelled `mean / std * sqrt(252)` as a Sharpe
   ratio applied to sparse round-trip trade returns. The 252-period
   annualisation assumed daily returns and massively overstated Sharpe
   for low-frequency traders.
"""

import sys
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pandas as pd

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from analysis.metrics import compare_to_benchmark
from analysis.politician_tracker import PoliticianTracker
from strategy.signals.base import Signal, SignalGenerator


class TestRankSignalsReturnsSorted:
    class _G(SignalGenerator):
        @property
        def name(self) -> str:
            return "test"

        def generate(self, symbols, as_of_date):
            return []

    def test_rank_signals_returns_in_score_descending_order(self):
        gen = self._G()
        signals = [
            Signal("A", date(2024, 1, 1), "x", 0.1),
            Signal("B", date(2024, 1, 1), "x", 0.9),
            Signal("C", date(2024, 1, 1), "x", 0.5),
        ]
        ranked = gen._rank_signals(signals)
        # The list returned should be sorted, not the original order.
        assert [s.symbol for s in ranked] == ["B", "C", "A"], (
            f"_rank_signals returned in original order: "
            f"{[s.symbol for s in ranked]}"
        )
        # Ranks should also be assigned in descending order.
        assert ranked[0].rank == 1 and ranked[0].symbol == "B"


class TestMomentumSentinelDoesNotPollute:
    """Stocks that fail the MA filter should be EXCLUDED from the
    signal list, not emitted with score=0.0 alongside legitimate
    near-zero-momentum stocks."""

    def test_failed_ma_filter_is_excluded(self, tmp_path):
        # Build a minimal momentum signal generator with a mocked store.
        from strategy.signals.momentum import MomentumSignal

        store = MagicMock()
        # Two symbols. Both have positive momentum, but only one is above MA.
        store.get_momentum.side_effect = lambda sym, *a, **k: {
            "GOOD": 0.20,
            "BAD": 0.30,
        }[sym]
        store.get_moving_average.side_effect = lambda sym, *a, **k: {
            "GOOD": 100.0,
            "BAD": 200.0,  # current price 150 will be below this
        }[sym]

        # Stub the parquet path / DuckDB lookup for current price.
        parquet_root = tmp_path / "prices"
        parquet_root.mkdir(parents=True)
        for sym in ("GOOD", "BAD"):
            (parquet_root / f"{sym}.parquet").touch()
        store.parquet_path = tmp_path

        # Return current_price=150 for both.
        store._conn = MagicMock()
        store._conn.execute.return_value.fetchone.return_value = (150.0,)

        sig = MomentumSignal(store)
        out = sig.generate(["GOOD", "BAD"], as_of_date=date(2024, 6, 1))

        # GOOD: current=150 > MA=100, positive momentum → kept
        # BAD : current=150 < MA=200 → must be excluded entirely
        emitted = {s.symbol for s in out}
        assert (
            "BAD" not in emitted
        ), f"Stock failing MA filter must be excluded; got {emitted}"
        assert "GOOD" in emitted


class TestAlphaIncludesRiskFreeRate:
    def test_alpha_subtracts_rf_from_both_legs(self):
        np.random.seed(0)
        n = 252
        # Strategy returns: drift 5%/yr, beta-like correlation to bench.
        bench = pd.Series(
            np.random.normal(loc=0.08 / 252, scale=0.01, size=n),
            index=pd.date_range("2024-01-01", periods=n),
        )
        strat = pd.Series(
            np.random.normal(loc=0.10 / 252, scale=0.01, size=n),
            index=bench.index,
        )
        rf = 0.04  # 4% risk-free

        out_rf = compare_to_benchmark(strat, bench, risk_free_rate=rf)
        out_no_rf = compare_to_benchmark(strat, bench, risk_free_rate=0.0)

        # With non-zero rf and beta ≠ 1, alpha must differ. The buggy
        # implementation returns the same alpha regardless of rf.
        assert abs(out_rf["alpha"] - out_no_rf["alpha"]) > 1e-6, (
            f"alpha did not change when rf was added (rf={rf}); "
            f"with rf: {out_rf['alpha']!r}, no rf: {out_no_rf['alpha']!r}. "
            f"Jensen's alpha must include the risk-free rate."
        )


class TestPoliticianSharpeRespectsHoldingPeriod:
    """The Sharpe assigned to PoliticianPerformance should annualise
    using the actual trade frequency, not assume daily-return data."""

    def test_sharpe_for_long_holding_periods_is_modest(self):
        trades = pd.DataFrame(
            {
                "symbol": ["AAA"] * 24,
                "politician_name": ["P"] * 24,
                "transaction_type": (["Buy", "Sell"]) * 12,
                # 12 round-trips, each ~60 days apart.
                "transaction_date": pd.date_range(
                    "2020-01-01", periods=24, freq="60D"
                ).date.tolist(),
                "shares": [100.0] * 24,
                # Alternate buy at 100, sell at 102 (= 2% per trade).
                "price": [100.0, 102.0] * 12,
            }
        )

        trade_storage = MagicMock()
        trade_storage.load_trades.return_value = trades
        price_storage = MagicMock()

        tracker = PoliticianTracker(trade_storage, price_storage)
        perf = tracker.calculate_performance("P")

        # The buggy formula multiplies by sqrt(252). For a ~60-day
        # holding period, the correct multiplier is sqrt(252/60) ≈ 2.05.
        # Each trade is +2% with zero variance, so std=0 and
        # sharpe_ratio is None. Build a noisy version to exercise the
        # std path.
        noisy = trades.copy()
        # Vary sell prices to produce non-zero std.
        noisy.loc[noisy["transaction_type"] == "Sell", "price"] = [
            101.0,
            103.0,
            102.0,
            104.0,
            101.5,
            102.5,
            103.5,
            100.5,
            102.0,
            104.5,
            101.0,
            103.0,
        ]
        trade_storage.load_trades.return_value = noisy

        perf = tracker.calculate_performance("P")
        assert perf.sharpe_ratio is not None
        # With sqrt(252) the value would be enormous (~5-15). With the
        # corrected sqrt(252 / avg_holding_days) it should be much
        # smaller. We assert it's below a sane threshold.
        assert perf.sharpe_ratio < 4.0, (
            f"sharpe_ratio={perf.sharpe_ratio:.2f} is too large for 60-day "
            f"holding periods — likely still using sqrt(252) annualisation."
        )
