"""
Simple Regime Detection (200-Day Moving Average)

Strategies behave differently in bull vs bear markets. Without regime awareness,
you might deploy a momentum strategy right before a crash.

This is the MVP regime detector. More complex methods (CUSUM, SADF, entropy)
are deferred to V2.
"""

from dataclasses import dataclass
from enum import Enum

import pandas as pd


class Regime(Enum):
    """Market regime classification."""

    BULL = "bull"
    BEAR = "bear"
    NEUTRAL = "neutral"


@dataclass
class RegimeSignal:
    """
    Result of regime detection.

    Attributes
    ----------
    current_regime : Regime
        Current market regime
    regime_series : pd.Series
        Regime at each timestamp
    ma_series : pd.Series
        Moving average values
    days_in_regime : int
        Days since last regime change
    last_change : pd.Timestamp
        Date of last regime change
    """

    current_regime: Regime
    regime_series: pd.Series
    ma_series: pd.Series
    days_in_regime: int
    last_change: pd.Timestamp | None


def regime_200ma(
    prices: pd.Series,
    ma_period: int = 200,
    buffer_pct: float = 0.0,
) -> RegimeSignal:
    """
    Detect market regime using 200-day moving average.

    - Price > MA(200): Bull market
    - Price < MA(200): Bear market
    - Optional buffer zone for neutral

    Parameters
    ----------
    prices : pd.Series
        Price series with DatetimeIndex
    ma_period : int
        Moving average period (default 200)
    buffer_pct : float
        Buffer zone around MA for neutral (default 0 = no neutral zone)
        e.g., 0.02 means within 2% of MA is neutral

    Returns
    -------
    RegimeSignal
        Regime classification and history

    Example
    -------
    >>> signal = regime_200ma(spy_prices)
    >>> if signal.current_regime == Regime.BEAR:
    ...     print("Caution: Bear market - reduce momentum exposure")
    """
    # Compute moving average
    ma = prices.rolling(window=ma_period, min_periods=ma_period).mean()

    # Compute distance from MA
    distance = (prices - ma) / ma

    # Classify regime
    def classify(dist: float) -> str:
        if pd.isna(dist):
            return Regime.NEUTRAL.value
        if dist > buffer_pct:
            return Regime.BULL.value
        elif dist < -buffer_pct:
            return Regime.BEAR.value
        else:
            return Regime.NEUTRAL.value

    regime_series = distance.apply(classify)

    # Current regime
    current = regime_series.iloc[-1] if len(regime_series) > 0 else Regime.NEUTRAL.value
    current_regime = Regime(current)

    # Find last regime change
    regime_changes = regime_series != regime_series.shift(1)
    change_dates = regime_series.index[regime_changes]

    if len(change_dates) > 1:
        last_change = change_dates[-1]
        days_in_regime = len(regime_series.loc[last_change:]) - 1
    else:
        last_change = None
        days_in_regime = len(regime_series)

    return RegimeSignal(
        current_regime=current_regime,
        regime_series=regime_series,
        ma_series=ma,
        days_in_regime=days_in_regime,
        last_change=last_change,
    )


def is_bull_market(prices: pd.Series, ma_period: int = 200) -> bool:
    """Quick check if currently in bull market."""
    signal = regime_200ma(prices, ma_period)
    return signal.current_regime == Regime.BULL


def is_bear_market(prices: pd.Series, ma_period: int = 200) -> bool:
    """Quick check if currently in bear market."""
    signal = regime_200ma(prices, ma_period)
    return signal.current_regime == Regime.BEAR
