"""Tests for ExitManager, EventDrivenEngine, and trade metrics."""

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from strategy.backtest.event_engine import (
    EventDrivenEngine,
    EventEngineConfig,
)
from strategy.backtest.exit_manager import ExitConfig, ExitManager
from strategy.backtest.portfolio import RoundTripTrade, TransactionCosts
from strategy.signals.base import Signal
from strategy.signals.combiner import SignalCombiner

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_trade(
    symbol: str = "AAPL",
    entry_date: date = date(2024, 1, 2),
    entry_price: float = 100.0,
    shares: float = 10.0,
) -> RoundTripTrade:
    return RoundTripTrade(
        symbol=symbol,
        entry_date=entry_date,
        entry_price=entry_price,
        entry_reason="signal_rebalance",
        shares=shares,
    )


def _make_synthetic_prices(
    symbols: list[str],
    n_days: int = 60,
    start: date = date(2024, 1, 2),
    base_price: float = 100.0,
    seed: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Create synthetic close and open price DataFrames.

    Returns (close_prices, open_prices) indexed by business-day dates.
    """
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start=start, periods=n_days)

    close_data = {}
    open_data = {}
    for sym in symbols:
        # Random walk for close prices
        daily_returns = rng.normal(0.0005, 0.015, size=n_days)
        cum_returns = np.cumprod(1 + daily_returns)
        closes = base_price * cum_returns
        # Open = previous close + small gap
        opens = np.concatenate([[base_price], closes[:-1]]) * (
            1 + rng.normal(0, 0.002, size=n_days)
        )
        close_data[sym] = closes
        open_data[sym] = opens

    close_df = pd.DataFrame(close_data, index=dates)
    open_df = pd.DataFrame(open_data, index=dates)
    return close_df, open_df


class StubSignalCombiner(SignalCombiner):
    """Stub combiner that returns fixed signals without any generators."""

    def __init__(self, picks: list[Signal]) -> None:
        # Bypass parent __init__ which requires generators
        self._picks = picks

    def get_top_picks(
        self,
        symbols: list[str],
        as_of_date: date,
        n_picks: int = 20,
        min_combined_score: float = 0.0,
    ) -> list[Signal]:
        return self._picks


# ---------------------------------------------------------------------------
# ExitManager tests
# ---------------------------------------------------------------------------


class TestExitManager:
    """Unit tests for barrier-based ExitManager."""

    def setup_method(self):
        self.config = ExitConfig(
            profit_take_mult=2.0,
            stop_loss_mult=2.0,
            max_holding_days=21,
        )
        self.manager = ExitManager(self.config)

    def test_profit_target_hit(self):
        """Price crosses upper barrier -> emits profit_target."""
        trade = _make_trade(entry_price=100.0)
        daily_vol = 0.02  # 2%
        # upper = 100 * (1 + 2.0 * 0.02) = 104.0
        signals = self.manager.check_exits(
            positions={"AAPL": trade},
            today=date(2024, 1, 10),
            prices={"AAPL": 105.0},  # above 104
            vol={"AAPL": daily_vol},
        )
        assert len(signals) == 1
        assert signals[0].reason == "profit_target"
        assert signals[0].symbol == "AAPL"
        assert signals[0].trigger_date == date(2024, 1, 10)

    def test_stop_loss_hit(self):
        """Price crosses lower barrier -> emits stop_loss."""
        trade = _make_trade(entry_price=100.0)
        daily_vol = 0.02
        # lower = 100 * (1 - 2.0 * 0.02) = 96.0
        signals = self.manager.check_exits(
            positions={"AAPL": trade},
            today=date(2024, 1, 10),
            prices={"AAPL": 95.0},  # below 96
            vol={"AAPL": daily_vol},
        )
        assert len(signals) == 1
        assert signals[0].reason == "stop_loss"
        assert signals[0].symbol == "AAPL"

    def test_timeout(self):
        """Holding exceeds max_holding_days -> emits timeout."""
        trade = _make_trade(entry_date=date(2024, 1, 2), entry_price=100.0)
        # 21 days later
        check_date = date(2024, 1, 2) + timedelta(days=21)
        signals = self.manager.check_exits(
            positions={"AAPL": trade},
            today=check_date,
            prices={"AAPL": 101.0},  # within barriers
            vol={"AAPL": 0.02},
        )
        assert len(signals) == 1
        assert signals[0].reason == "timeout"

    def test_no_exit(self):
        """Price within barriers and under timeout -> empty list."""
        trade = _make_trade(entry_date=date(2024, 1, 2), entry_price=100.0)
        daily_vol = 0.02
        # upper = 104, lower = 96, price = 101 -> no exit
        signals = self.manager.check_exits(
            positions={"AAPL": trade},
            today=date(2024, 1, 10),
            prices={"AAPL": 101.0},
            vol={"AAPL": daily_vol},
        )
        assert len(signals) == 0

    def test_priority_profit_wins(self):
        """If price crosses both barriers same check, profit_target wins.

        The implementation checks profit_target first (>=upper), then
        stop_loss (<=lower), so a price above the upper barrier always
        gets profit_target even if lower is also breached due to vol changes.
        """
        trade = _make_trade(entry_price=100.0)
        # With high vol, upper and lower can be very wide, but let's set
        # a scenario where a massive spike crosses upper: profit wins.
        daily_vol = 0.02
        # upper = 104, lower = 96
        # Price at 110 clearly triggers profit_target first
        signals = self.manager.check_exits(
            positions={"AAPL": trade},
            today=date(2024, 1, 10),
            prices={"AAPL": 110.0},
            vol={"AAPL": daily_vol},
        )
        assert len(signals) == 1
        assert signals[0].reason == "profit_target"

    def test_rolling_vol_widens_barriers(self):
        """Higher vol = wider barriers -> price that would trigger at low vol
        does not trigger at high vol."""
        trade = _make_trade(entry_price=100.0)

        # Low vol: upper = 100*(1+2*0.01) = 102, price 103 triggers
        signals_low = self.manager.check_exits(
            positions={"AAPL": trade},
            today=date(2024, 1, 10),
            prices={"AAPL": 103.0},
            vol={"AAPL": 0.01},
        )
        assert len(signals_low) == 1
        assert signals_low[0].reason == "profit_target"

        # High vol: upper = 100*(1+2*0.05) = 110, price 103 does NOT trigger
        signals_high = self.manager.check_exits(
            positions={"AAPL": trade},
            today=date(2024, 1, 10),
            prices={"AAPL": 103.0},
            vol={"AAPL": 0.05},
        )
        assert len(signals_high) == 0

    def test_cusum_reversal_exit(self):
        """Downside CUSUM fire on held position emits cusum_reversal."""
        trade = _make_trade(entry_price=100.0)
        # Price is within barriers — no profit/stop triggered
        signals = self.manager.check_exits(
            positions={"AAPL": trade},
            today=date(2024, 1, 10),
            prices={"AAPL": 99.0},  # within barriers
            vol={"AAPL": 0.02},
            cusum_downside={"AAPL"},  # CUSUM fired downside
        )
        assert len(signals) == 1
        assert signals[0].reason == "cusum_reversal"

    def test_cusum_reversal_priority_below_profit_target(self):
        """If profit target also triggers, profit_target wins over cusum_reversal."""
        trade = _make_trade(entry_price=100.0)
        # Price above upper barrier AND CUSUM downside fired
        signals = self.manager.check_exits(
            positions={"AAPL": trade},
            today=date(2024, 1, 10),
            prices={"AAPL": 110.0},  # above upper barrier (100*(1+2*0.02)=104)
            vol={"AAPL": 0.02},
            cusum_downside={"AAPL"},
        )
        assert len(signals) == 1
        assert signals[0].reason == "profit_target"

    def test_no_cusum_downside_no_reversal(self):
        """If cusum_downside is empty, no cusum_reversal emitted."""
        trade = _make_trade(entry_price=100.0)
        signals = self.manager.check_exits(
            positions={"AAPL": trade},
            today=date(2024, 1, 10),
            prices={"AAPL": 99.0},
            vol={"AAPL": 0.02},
            cusum_downside=set(),
        )
        assert len(signals) == 0


# ---------------------------------------------------------------------------
# EventDrivenEngine tests
# ---------------------------------------------------------------------------


class TestEventDrivenEngine:
    """Integration tests for the event-driven backtest engine."""

    @pytest.fixture()
    def universe(self):
        return ["AAPL", "MSFT", "GOOGL"]

    @pytest.fixture()
    def prices(self, universe):
        """60 trading days of synthetic prices including SPY for benchmark."""
        symbols = universe + ["SPY"]
        close_df, open_df = _make_synthetic_prices(
            symbols, n_days=60, start=date(2024, 1, 2), seed=42
        )
        return close_df, open_df

    @pytest.fixture()
    def stub_combiner(self, universe):
        """A combiner that always picks all three symbols with equal scores."""
        picks = [
            Signal(
                symbol=sym,
                date=date(2024, 1, 1),
                signal_name="test",
                score=0.8 - i * 0.1,
            )
            for i, sym in enumerate(universe)
        ]
        return StubSignalCombiner(picks)

    @pytest.fixture()
    def engine_config(self):
        return EventEngineConfig(
            initial_capital=100_000.0,
            max_positions=20,
            max_position_weight=0.10,
            rebalance_frequency="monthly",
            transaction_costs=TransactionCosts(
                commission_per_share=0.0,
                slippage_bps=10.0,
            ),
            exit_config=ExitConfig(
                profit_take_mult=2.0,
                stop_loss_mult=2.0,
                max_holding_days=21,
            ),
            benchmark_symbol="SPY",
        )

    @pytest.fixture()
    def result(self, stub_combiner, engine_config, universe, prices):
        close_df, open_df = prices
        engine = EventDrivenEngine(stub_combiner, engine_config)
        return engine.run(universe, close_df, open_df)

    def test_entries_at_rebalance_open(self, result, prices):
        """Positions created only on rebalance dates using open prices."""
        close_df, open_df = prices
        trade_log = result.trade_log
        if trade_log.empty:
            pytest.skip("No trades generated with this synthetic data")

        # All entry reasons should be signal_rebalance (from _handle_rebalance)
        entry_reasons = trade_log["entry_reason"].unique()
        assert "signal_rebalance" in entry_reasons

        # Check that entries happen at open prices
        for _, row in trade_log.iterrows():
            entry_d = row["entry_date"]
            sym = row["symbol"]
            if entry_d in open_df.index:
                open_price = open_df.loc[entry_d, sym]
                assert row["entry_price"] == pytest.approx(
                    open_price, rel=1e-6
                ), f"Entry for {sym} on {entry_d} not at open price"

    def test_exits_next_day_open(self, result, prices):
        """Barrier exits execute at next day's open (not same-day close)."""
        close_df, open_df = prices
        trade_log = result.trade_log
        if trade_log.empty:
            pytest.skip("No trades to check exit prices")

        # For barrier exits (profit_target, stop_loss, timeout):
        # exit_date should be the day AFTER the trigger, at that day's open
        barrier_exits = trade_log[
            trade_log["exit_reason"].isin(["profit_target", "stop_loss", "timeout"])
        ]
        for _, row in barrier_exits.iterrows():
            exit_d = row["exit_date"]
            sym = row["symbol"]
            if exit_d in open_df.index:
                open_price = open_df.loc[exit_d, sym]
                assert row["exit_price"] == pytest.approx(
                    open_price, rel=1e-6
                ), f"Exit for {sym} on {exit_d} not at open price"

    def test_daily_equity_curve(self, result, prices):
        """Every trading day has an equity record."""
        close_df, _ = prices
        trading_days = sorted(
            close_df.index.date if hasattr(close_df.index, "date") else close_df.index
        )
        eq = result.equity_curve
        assert len(eq) == len(
            trading_days
        ), f"Equity curve has {len(eq)} rows but expected {len(trading_days)} trading days"

    def test_cash_tracking(self, result, engine_config):
        """Cash decreases on entry and increases on exit."""
        eq = result.equity_curve
        initial = engine_config.initial_capital

        # First row: cash should still be initial (or slightly less if
        # rebalance happens day 1 and first day is a rebalance date)
        first_cash = eq.iloc[0]["cash"]
        assert first_cash <= initial, "Cash should not exceed initial capital"

        # If any trades occurred, cash should have changed at some point
        if not result.trade_log.empty:
            cash_values = eq["cash"].values
            assert not np.all(
                cash_values == initial
            ), "Cash never changed despite trades"

    def test_trade_log_reasons(self, result):
        """Trade log has correct entry/exit reasons."""
        trade_log = result.trade_log
        if trade_log.empty:
            pytest.skip("No trades generated")

        valid_entry_reasons = {"signal_rebalance"}
        valid_exit_reasons = {
            "profit_target",
            "stop_loss",
            "timeout",
            "rebalance_out",
            "cusum_reversal",
        }

        for reason in trade_log["entry_reason"].unique():
            assert reason in valid_entry_reasons, f"Unexpected entry reason: {reason}"

        for reason in trade_log["exit_reason"].dropna().unique():
            assert reason in valid_exit_reasons, f"Unexpected exit reason: {reason}"

    def test_mfe_mae_tracking(self, result):
        """Max favorable/adverse excursion correctly tracked."""
        trade_log = result.trade_log
        if trade_log.empty:
            pytest.skip("No trades generated")

        for _, row in trade_log.iterrows():
            # MFE >= 0 (best unrealized return)
            assert (
                row["max_favorable"] >= 0.0
            ), f"MFE should be >= 0, got {row['max_favorable']}"
            # MAE <= 0 (worst unrealized return)
            assert (
                row["max_adverse"] <= 0.0
            ), f"MAE should be <= 0, got {row['max_adverse']}"
            # MFE >= MAE (best is always >= worst)
            assert row["max_favorable"] >= row["max_adverse"]

    def test_position_weight_cap(self, stub_combiner, universe, prices):
        """No position exceeds max_position_weight (10%)."""
        close_df, open_df = prices
        config = EventEngineConfig(
            initial_capital=100_000.0,
            max_positions=20,
            max_position_weight=0.10,
            rebalance_frequency="monthly",
            transaction_costs=TransactionCosts(slippage_bps=0.0),
            exit_config=ExitConfig(
                profit_take_mult=100.0,  # very wide -> no barrier exits
                stop_loss_mult=100.0,
                max_holding_days=999,
            ),
            benchmark_symbol="SPY",
        )
        engine = EventDrivenEngine(stub_combiner, config)
        result = engine.run(universe, close_df, open_df)

        trade_log = result.trade_log
        if trade_log.empty and not result.open_positions:
            pytest.skip("No positions to check weight cap")

        # Check at entry: entry_value / equity <= 0.10 (with small tolerance)
        for pos in result.open_positions:
            entry_value = pos.shares * pos.entry_price
            assert (
                entry_value / config.initial_capital <= 0.10 + 1e-6
            ), f"{pos.symbol} entry weight {entry_value / config.initial_capital:.4f} > 10%"

    def test_benchmark_tracked(self, result):
        """SPY benchmark appears in equity curve."""
        eq = result.equity_curve
        assert "benchmark" in eq.columns, "benchmark column missing from equity curve"
        # At least some benchmark values should be non-null
        assert eq["benchmark"].notna().any(), "All benchmark values are NaN"


# ---------------------------------------------------------------------------
# Trade metrics tests
# ---------------------------------------------------------------------------


class TestTradeMetrics:
    """Test trade-level metrics from a known trade log."""

    def test_known_trade_log(self):
        """Verify win_rate, profit_factor, exit_breakdown from known data."""
        # Create 5 known trades
        trades = [
            RoundTripTrade(
                symbol="AAPL",
                entry_date=date(2024, 1, 2),
                entry_price=100.0,
                entry_reason="signal_rebalance",
                exit_date=date(2024, 1, 10),
                exit_price=110.0,
                exit_reason="profit_target",
                shares=10.0,
                max_favorable=0.12,
                max_adverse=-0.02,
            ),
            RoundTripTrade(
                symbol="MSFT",
                entry_date=date(2024, 1, 2),
                entry_price=200.0,
                entry_reason="signal_rebalance",
                exit_date=date(2024, 1, 15),
                exit_price=190.0,
                exit_reason="stop_loss",
                shares=5.0,
                max_favorable=0.03,
                max_adverse=-0.08,
            ),
            RoundTripTrade(
                symbol="GOOGL",
                entry_date=date(2024, 1, 2),
                entry_price=150.0,
                entry_reason="signal_rebalance",
                exit_date=date(2024, 1, 25),
                exit_price=160.0,
                exit_reason="profit_target",
                shares=8.0,
                max_favorable=0.10,
                max_adverse=-0.01,
            ),
            RoundTripTrade(
                symbol="AMZN",
                entry_date=date(2024, 1, 5),
                entry_price=120.0,
                entry_reason="signal_rebalance",
                exit_date=date(2024, 1, 26),
                exit_price=115.0,
                exit_reason="timeout",
                shares=6.0,
                max_favorable=0.04,
                max_adverse=-0.06,
            ),
            RoundTripTrade(
                symbol="TSLA",
                entry_date=date(2024, 1, 5),
                entry_price=80.0,
                entry_reason="signal_rebalance",
                exit_date=date(2024, 1, 12),
                exit_price=90.0,
                exit_reason="profit_target",
                shares=12.0,
                max_favorable=0.15,
                max_adverse=-0.03,
            ),
        ]

        # PnL per trade:
        # AAPL:  (110-100)*10 = +100
        # MSFT:  (190-200)*5  = -50
        # GOOGL: (160-150)*8  = +80
        # AMZN:  (115-120)*6  = -30
        # TSLA:  (90-80)*12   = +120

        pnls = [t.pnl for t in trades]
        assert pnls == [100.0, -50.0, 80.0, -30.0, 120.0]

        # Win rate: 3 winners / 5 total = 0.60
        winners = [p for p in pnls if p > 0]
        losers = [p for p in pnls if p < 0]
        win_rate = len(winners) / len(pnls)
        assert win_rate == pytest.approx(0.60)

        # Profit factor: sum(wins) / abs(sum(losses)) = 300 / 80 = 3.75
        gross_profit = sum(winners)
        gross_loss = abs(sum(losers))
        profit_factor = gross_profit / gross_loss
        assert profit_factor == pytest.approx(3.75)

        # Exit breakdown
        reasons = [t.exit_reason for t in trades]
        from collections import Counter

        breakdown = Counter(reasons)
        assert breakdown["profit_target"] == 3
        assert breakdown["stop_loss"] == 1
        assert breakdown["timeout"] == 1

        # Holding days
        holding_days = [t.holding_days for t in trades]
        assert holding_days == [8, 13, 23, 21, 7]

        # Return percentages
        returns = [t.return_pct for t in trades]
        assert returns[0] == pytest.approx(0.10)  # AAPL: +10%
        assert returns[1] == pytest.approx(-0.05)  # MSFT: -5%
        assert returns[2] == pytest.approx(10 / 150)  # GOOGL: ~6.67%
        assert returns[3] == pytest.approx(-5 / 120)  # AMZN: ~-4.17%
        assert returns[4] == pytest.approx(0.125)  # TSLA: +12.5%


# ---------------------------------------------------------------------------
# Phase 2 config + CUSUM gate tests
# ---------------------------------------------------------------------------


def test_engine_config_has_phase2_fields():
    """EventEngineConfig should have Phase 2 fields with correct defaults."""
    config = EventEngineConfig()
    assert hasattr(config, "cusum_recency_days")
    assert hasattr(config, "meta_label_min_samples")
    assert hasattr(config, "use_cusum_gate")
    assert hasattr(config, "use_regime_multiplier")
    assert hasattr(config, "use_meta_labeling")
    assert config.cusum_recency_days == 5
    assert config.meta_label_min_samples == 50
    assert config.use_cusum_gate is True
    assert config.use_regime_multiplier is True
    assert config.use_meta_labeling is True


class TestCUSUMGate:
    """CUSUM entry gate: only enter if upside fire within recency window."""

    @pytest.fixture()
    def universe(self):
        return ["AAPL", "MSFT", "GOOGL"]

    @pytest.fixture()
    def prices(self, universe):
        """260 trading days of synthetic prices including SPY."""
        symbols = universe + ["SPY"]
        close_df, open_df = _make_synthetic_prices(
            symbols, n_days=260, start=date(2023, 1, 2), seed=7
        )
        return close_df, open_df

    @pytest.fixture()
    def stub_combiner(self, universe):
        picks = [
            Signal(symbol=sym, date=date(2023, 1, 2), signal_name="test", score=0.8)
            for sym in universe
        ]
        return StubSignalCombiner(picks)

    def test_cusum_gate_disabled_allows_entries(self, universe, prices, stub_combiner):
        """With use_cusum_gate=False, entries happen as before (no CUSUM filter)."""
        close_df, open_df = prices
        config = EventEngineConfig(
            initial_capital=100_000.0,
            max_positions=20,
            max_position_weight=0.10,
            rebalance_frequency="monthly",
            exit_config=ExitConfig(
                profit_take_mult=100.0, stop_loss_mult=100.0, max_holding_days=999
            ),
            use_cusum_gate=False,
            use_regime_multiplier=False,
            use_meta_labeling=False,
        )
        engine = EventDrivenEngine(stub_combiner, config)
        result = engine.run(universe, close_df, open_df)

        # Without CUSUM gate, positions should be entered on rebalance day
        assert not result.trade_log.empty or len(result.open_positions) > 0

    def test_cusum_gate_enabled_engine_runs(self, universe, prices, stub_combiner):
        """Engine with CUSUM gate enabled should run without error."""
        close_df, open_df = prices
        config = EventEngineConfig(
            initial_capital=100_000.0,
            max_positions=20,
            max_position_weight=0.10,
            rebalance_frequency="monthly",
            exit_config=ExitConfig(
                profit_take_mult=100.0, stop_loss_mult=100.0, max_holding_days=999
            ),
            use_cusum_gate=True,
            cusum_recency_days=5,
            use_regime_multiplier=False,
            use_meta_labeling=False,
        )
        engine = EventDrivenEngine(stub_combiner, config)
        result = engine.run(universe, close_df, open_df)

        assert result.equity_curve is not None
        assert len(result.equity_curve) == len(close_df)

    def test_run_accepts_macro_and_sentiment_prices(
        self, universe, prices, stub_combiner
    ):
        """run() should accept optional macro_prices and sentiment_prices kwargs."""
        close_df, open_df = prices
        config = EventEngineConfig(
            use_cusum_gate=False, use_regime_multiplier=False, use_meta_labeling=False
        )
        engine = EventDrivenEngine(stub_combiner, config)

        # Passing None explicitly should work fine
        result = engine.run(
            universe, close_df, open_df, macro_prices=None, sentiment_prices=None
        )
        assert result.equity_curve is not None
