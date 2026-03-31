"""Tests for afml/regime_composite.py — 3-layer regime multiplier."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from afml.regime_composite import compute_regime_multiplier


def _make_macro(n=300, yield_spread=0.5, hyg_trend="flat"):
    """Synthetic macro data: ^TNX, ^IRX, HYG, LQD."""
    dates = pd.date_range("2023-01-01", periods=n, freq="B")
    tnx = pd.Series(4.0, index=dates)
    irx = pd.Series(4.0 - yield_spread, index=dates)
    base = pd.Series(1.0, index=dates)
    if hyg_trend == "falling":
        base = pd.Series(np.linspace(1.0, 0.85, n), index=dates)
    hyg = pd.Series(80.0, index=dates) * base
    lqd = pd.Series(110.0, index=dates)
    return {"^TNX": tnx, "^IRX": irx, "HYG": hyg, "LQD": lqd}


def _make_sentiment(n=300, spy_above_ma=True, vix_level=15.0):
    dates = pd.date_range("2023-01-01", periods=n, freq="B")
    spy = pd.Series(np.linspace(100, 130 if spy_above_ma else 80, n), index=dates)
    vix = pd.Series(vix_level, index=dates)
    return {"SPY": spy, "^VIX": vix}


def test_expansion_bull_returns_full_multiplier():
    """Normal expansion + bull sentiment → multiplier = 1.0."""
    macro = _make_macro(yield_spread=0.5)
    sentiment = _make_sentiment(spy_above_ma=True, vix_level=15.0)
    as_of = date(2024, 1, 2)

    state = compute_regime_multiplier(macro, sentiment, as_of)
    assert state.multiplier == pytest.approx(1.0)
    assert state.macro_label == "expansion"
    assert state.sentiment_label == "bull"


def test_inverted_curve_reduces_multiplier():
    """Inverted yield curve → macro caution → multiplier ≤ 0.5."""
    macro = _make_macro(yield_spread=-0.3)
    sentiment = _make_sentiment(spy_above_ma=True, vix_level=15.0)
    as_of = date(2024, 1, 2)

    state = compute_regime_multiplier(macro, sentiment, as_of)
    assert state.multiplier <= 0.5
    assert state.macro_label in ("caution", "stress")


def test_bear_sentiment_reduces_multiplier():
    """SPY below 200MA → sentiment bear → multiplier reduced."""
    macro = _make_macro(yield_spread=0.5)
    sentiment = _make_sentiment(spy_above_ma=False, vix_level=15.0)
    as_of = date(2024, 1, 2)

    state = compute_regime_multiplier(macro, sentiment, as_of)
    assert state.multiplier < 1.0
    assert state.sentiment_label == "bear"


def test_stress_scenario_minimum_multiplier():
    """Inverted curve + falling HYG + bear → multiplier = 0.25."""
    macro = _make_macro(yield_spread=-0.6, hyg_trend="falling")
    sentiment = _make_sentiment(spy_above_ma=False, vix_level=30.0)
    as_of = date(2024, 1, 2)

    state = compute_regime_multiplier(macro, sentiment, as_of)
    assert state.multiplier == pytest.approx(0.25)


def test_insufficient_history_returns_neutral():
    """Less than 200 days of SPY → not enough history → multiplier = 0.5."""
    dates = pd.date_range("2023-01-01", periods=50, freq="B")
    macro = {
        "^TNX": pd.Series(4.0, index=dates),
        "^IRX": pd.Series(3.5, index=dates),
        "HYG": pd.Series(80.0, index=dates),
        "LQD": pd.Series(110.0, index=dates),
    }
    sentiment = {
        "SPY": pd.Series(100.0, index=dates),
        "^VIX": pd.Series(15.0, index=dates),
    }
    state = compute_regime_multiplier(macro, sentiment, date(2023, 3, 31))
    assert state.multiplier == pytest.approx(0.5)
    assert state.macro_label == "neutral"
