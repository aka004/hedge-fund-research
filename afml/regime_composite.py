"""
3-Layer Regime Composite Multiplier

Layer 1 (Macro):     yield curve spread (^TNX - ^IRX) + HYG/LQD ratio trend
Layer 2 (Sentiment): SPY vs 200MA + VIX vs 1Y rolling mean
Layer 3 (Stock):     CUSUM fires — handled in EventDrivenEngine, not here

Output: regime_multiplier in {0.25, 0.50, 0.75, 1.0} — scales position size.

All inputs are yfinance-compatible price series. No API key required.
"""

from dataclasses import dataclass
from datetime import date

import pandas as pd


@dataclass
class RegimeState:
    """Output of 3-layer regime assessment."""

    macro_mult: float  # 0.25, 0.50, or 1.0
    sentiment_mult: float  # 0.50, 0.75, or 1.0
    multiplier: float  # combined, snapped to 0.25 grid, min 0.25
    macro_label: str  # "expansion" | "caution" | "stress" | "neutral"
    sentiment_label: str  # "bull" | "neutral" | "bear"


_NEUTRAL = RegimeState(
    macro_mult=1.0,
    sentiment_mult=0.5,
    multiplier=0.5,
    macro_label="neutral",
    sentiment_label="neutral",
)


def compute_regime_multiplier(
    macro_data: dict[str, pd.Series],
    sentiment_data: dict[str, pd.Series],
    as_of: date,
    ma_window: int = 200,
    vix_window: int = 252,
    hyg_lqd_window: int = 126,
) -> RegimeState:
    """Compute position size multiplier from 3-layer regime assessment.

    Parameters
    ----------
    macro_data : dict
        Series keyed by: "^TNX" (10Y yield), "^IRX" (3M yield),
        "HYG" (HY bond ETF), "LQD" (IG bond ETF).
    sentiment_data : dict
        Series keyed by: "SPY" (equity index), "^VIX" (volatility).
    as_of : date
        Date to assess regime (uses data up to and including this date).
    ma_window : int
        SPY moving average window (default 200).
    vix_window : int
        VIX rolling mean window in trading days (default 252).
    hyg_lqd_window : int
        HYG/LQD rolling mean window in trading days (default 126 = ~6 months).

    Returns
    -------
    RegimeState
        Regime labels and position multiplier.
    """
    macro_mult, macro_label = _compute_macro(
        macro_data, as_of, hyg_lqd_window, ma_window
    )
    sentiment_mult, sentiment_label = _compute_sentiment(
        sentiment_data, as_of, ma_window, vix_window
    )

    combined = macro_mult * sentiment_mult
    multiplier = max(0.25, round(combined * 4) / 4)  # snap to 0.25 grid

    return RegimeState(
        macro_mult=macro_mult,
        sentiment_mult=sentiment_mult,
        multiplier=multiplier,
        macro_label=macro_label,
        sentiment_label=sentiment_label,
    )


def _get_as_of(series: pd.Series, as_of: date) -> pd.Series:
    """Slice series up to and including as_of date."""
    return series[series.index <= pd.Timestamp(as_of)]


def _compute_macro(
    macro_data: dict[str, pd.Series],
    as_of: date,
    hyg_lqd_window: int,
    min_history: int,
) -> tuple[float, str]:
    """Layer 1: yield curve spread + credit spread.

    Returns (multiplier, label).
    """
    required = {"^TNX", "^IRX", "HYG", "LQD"}
    if not required.issubset(macro_data.keys()):
        return 1.0, "neutral"

    tnx = _get_as_of(macro_data["^TNX"], as_of)
    irx = _get_as_of(macro_data["^IRX"], as_of)
    hyg = _get_as_of(macro_data["HYG"], as_of)
    lqd = _get_as_of(macro_data["LQD"], as_of)

    if len(tnx) < min_history or len(hyg) < hyg_lqd_window:
        return 1.0, "neutral"

    yield_spread = float(tnx.iloc[-1]) - float(irx.iloc[-1])

    hyg_lqd_ratio = hyg / lqd
    ratio_mean = hyg_lqd_ratio.rolling(hyg_lqd_window).mean().iloc[-1]
    ratio_now = hyg_lqd_ratio.iloc[-1]
    credit_stress = ratio_now < ratio_mean  # HYG underperforming LQD vs recent mean

    if yield_spread > 0 and not credit_stress:
        return 1.0, "expansion"
    elif yield_spread < -0.5 and credit_stress:
        return 0.25, "stress"
    else:
        return 0.5, "caution"


def _compute_sentiment(
    sentiment_data: dict[str, pd.Series],
    as_of: date,
    ma_window: int,
    vix_window: int,
) -> tuple[float, str]:
    """Layer 2: SPY 200MA + VIX regime.

    Returns (multiplier, label).
    """
    required = {"SPY", "^VIX"}
    if not required.issubset(sentiment_data.keys()):
        return 0.75, "neutral"

    spy = _get_as_of(sentiment_data["SPY"], as_of)
    vix = _get_as_of(sentiment_data["^VIX"], as_of)

    if len(spy) < ma_window:
        return 0.5, "neutral"

    spy_ma = spy.rolling(ma_window).mean().iloc[-1]
    spy_now = spy.iloc[-1]
    above_ma = spy_now > spy_ma

    vix_mean = (
        float(vix.rolling(min(vix_window, len(vix))).mean().iloc[-1])
        if len(vix) >= 20
        else 20.0
    )
    vix_now = float(vix.iloc[-1])
    vix_elevated = vix_now > vix_mean

    if above_ma and not vix_elevated:
        return 1.0, "bull"
    elif above_ma and vix_elevated:
        return 0.75, "neutral"
    else:
        return 0.5, "bear"
