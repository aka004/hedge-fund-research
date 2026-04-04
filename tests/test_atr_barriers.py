"""Tests for ATR-scaled triple barriers in ExitManager."""

from datetime import date
import pytest

from strategy.backtest.exit_manager import ExitConfig, ExitManager
from strategy.backtest.portfolio import RoundTripTrade


def _make_trade(symbol: str, entry_price: float) -> RoundTripTrade:
    return RoundTripTrade(
        symbol=symbol,
        entry_date=date(2023, 1, 1),
        entry_price=entry_price,
        shares=100,
        entry_reason="signal_rebalance",
    )


def test_atr_barriers_trigger_profit_target():
    """ATR upper barrier: price above entry + atr_mult * atr triggers profit_target."""
    cfg = ExitConfig()
    em = ExitManager(cfg)

    entry = 100.0
    atr = 2.0  # $2 ATR
    atr_mult = 1.5
    # upper = 100 + 1.5 * 2 = 103; price at 104 should trigger
    trade = _make_trade("AAPL", entry)
    signals = em.check_exits(
        positions={"AAPL": trade},
        today=date(2023, 1, 10),
        prices={"AAPL": 104.0},
        vol={"AAPL": 0.0},
        atr={"AAPL": atr},
        atr_multiplier=atr_mult,
    )
    assert len(signals) == 1
    assert signals[0].reason == "profit_target"


def test_atr_barriers_trigger_stop_loss():
    """ATR lower barrier: price below entry - atr_mult * atr triggers stop_loss."""
    cfg = ExitConfig()
    em = ExitManager(cfg)

    entry = 100.0
    atr = 2.0
    atr_mult = 1.5
    # lower = 100 - 3 = 97; price at 96 should trigger
    trade = _make_trade("AAPL", entry)
    signals = em.check_exits(
        positions={"AAPL": trade},
        today=date(2023, 1, 10),
        prices={"AAPL": 96.0},
        vol={"AAPL": 0.0},
        atr={"AAPL": atr},
        atr_multiplier=atr_mult,
    )
    assert len(signals) == 1
    assert signals[0].reason == "stop_loss"


def test_atr_barriers_no_trigger_within_band():
    """Price within ATR band should not trigger any exit."""
    cfg = ExitConfig()
    em = ExitManager(cfg)

    entry = 100.0
    atr = 2.0
    atr_mult = 1.5
    # band = [97, 103]; price at 101 should NOT trigger
    trade = _make_trade("AAPL", entry)
    signals = em.check_exits(
        positions={"AAPL": trade},
        today=date(2023, 1, 10),
        prices={"AAPL": 101.0},
        vol={"AAPL": 0.0},
        atr={"AAPL": atr},
        atr_multiplier=atr_mult,
    )
    # No exit (not timed out either — holding_days = 9 < 21)
    assert len(signals) == 0


def test_vol_fallback_when_atr_zero():
    """When atr value is 0, falls back to vol-based barriers."""
    cfg = ExitConfig(profit_take_mult=2.0, stop_loss_mult=2.0)
    em = ExitManager(cfg)

    entry = 100.0
    vol = 0.01  # 1% daily vol → upper = 102, lower = 98
    # price at 103 with atr=0 should use vol → upper=102 → triggers
    trade = _make_trade("AAPL", entry)
    signals = em.check_exits(
        positions={"AAPL": trade},
        today=date(2023, 1, 10),
        prices={"AAPL": 103.0},
        vol={"AAPL": vol},
        atr={"AAPL": 0.0},
        atr_multiplier=1.5,
    )
    assert len(signals) == 1
    assert signals[0].reason == "profit_target"


def test_atr_multiplier_zero_uses_vol():
    """atr_multiplier=0 should disable ATR barriers and use vol-based."""
    cfg = ExitConfig(profit_take_mult=2.0)
    em = ExitManager(cfg)

    entry = 100.0
    vol = 0.01  # upper = 102
    trade = _make_trade("AAPL", entry)
    signals = em.check_exits(
        positions={"AAPL": trade},
        today=date(2023, 1, 10),
        prices={"AAPL": 103.0},
        vol={"AAPL": vol},
        atr={"AAPL": 5.0},   # high ATR but multiplier=0 so ignored
        atr_multiplier=0.0,
    )
    assert len(signals) == 1
    assert signals[0].reason == "profit_target"
