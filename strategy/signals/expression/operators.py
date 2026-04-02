"""
Expression engine operators — pure functions on DataFrames.

Time-series operators work per-column (rolling window over days for one stock).
Cross-sectional operators work per-row (across all stocks on one day).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd


# ── Time-series operators (per stock, rolling window) ─────────────────────────


def ts_mean(x: pd.DataFrame, d: int) -> pd.DataFrame:
    """Rolling simple moving average over d days."""
    return x.rolling(d, min_periods=max(1, d // 2)).mean()


def ts_std(x: pd.DataFrame, d: int) -> pd.DataFrame:
    """Rolling standard deviation over d days."""
    return x.rolling(d, min_periods=max(2, d // 2)).std()


def ts_sum(x: pd.DataFrame, d: int) -> pd.DataFrame:
    """Rolling sum over d days."""
    return x.rolling(d, min_periods=max(1, d // 2)).sum()


def ts_max(x: pd.DataFrame, d: int) -> pd.DataFrame:
    """Rolling max over d days."""
    return x.rolling(d, min_periods=max(1, d // 2)).max()


def ts_min(x: pd.DataFrame, d: int) -> pd.DataFrame:
    """Rolling min over d days."""
    return x.rolling(d, min_periods=max(1, d // 2)).min()


def ts_rank(x: pd.DataFrame, d: int) -> pd.DataFrame:
    """Rolling percentile rank within the last d days (0 to 1).

    Vectorized: compares current value to rolling min/max
    to compute approximate percentile position.
    """
    r_min = x.rolling(d, min_periods=max(2, d // 2)).min()
    r_max = x.rolling(d, min_periods=max(2, d // 2)).max()
    denom = r_max - r_min
    return (x - r_min) / denom.replace(0, np.nan).fillna(1.0)


def ts_corr(x: pd.DataFrame, y: pd.DataFrame, d: int) -> pd.DataFrame:
    """Rolling correlation between x and y over d days."""
    result = {}
    for col in x.columns:
        if col in y.columns:
            result[col] = x[col].rolling(d, min_periods=max(3, d // 2)).corr(y[col])
    return pd.DataFrame(result, index=x.index)


def ts_cov(x: pd.DataFrame, y: pd.DataFrame, d: int) -> pd.DataFrame:
    """Rolling covariance between x and y over d days."""
    result = {}
    for col in x.columns:
        if col in y.columns:
            result[col] = x[col].rolling(d, min_periods=max(3, d // 2)).cov(y[col])
    return pd.DataFrame(result, index=x.index)


def ts_delta(x: pd.DataFrame, d: int) -> pd.DataFrame:
    """x[t] - x[t-d]."""
    return x - x.shift(d)


def ts_returns(x: pd.DataFrame, d: int) -> pd.DataFrame:
    """Simple returns over d days: x[t]/x[t-d] - 1."""
    shifted = x.shift(d)
    return (x / shifted.replace(0, np.nan)) - 1


def ts_ema(x: pd.DataFrame, d: int) -> pd.DataFrame:
    """Exponential moving average with span=d.

    More weight on recent data. Half-life ≈ d*ln(2)/2.
    """
    return x.ewm(span=d, min_periods=max(1, d // 2)).mean()


def ts_decay(x: pd.DataFrame, d: int) -> pd.DataFrame:
    """Linearly decaying weighted average over d days.

    Weight = d for most recent, d-1 for next, ..., 1 for oldest.
    """
    weights = np.arange(1, d + 1, dtype=float)
    weights /= weights.sum()

    def _wma(series: pd.Series) -> pd.Series:
        return series.rolling(d, min_periods=max(1, d // 2)).apply(
            lambda w: np.dot(w, weights[-len(w):]) if len(w) == d
            else np.dot(w, weights[-len(w):] / weights[-len(w):].sum()),
            raw=True,
        )

    return x.apply(_wma)


def ts_skew(x: pd.DataFrame, d: int) -> pd.DataFrame:
    """Rolling skewness over d days. Positive = right tail."""
    return x.rolling(d, min_periods=max(3, d // 2)).skew()


def ts_kurt(x: pd.DataFrame, d: int) -> pd.DataFrame:
    """Rolling kurtosis over d days. High = fat tails."""
    return x.rolling(d, min_periods=max(4, d // 2)).kurt()


def ts_zscore(x: pd.DataFrame, d: int) -> pd.DataFrame:
    """Time-series z-score: (x - rolling_mean) / rolling_std.

    How many std devs the current value is from its d-day mean.
    """
    m = x.rolling(d, min_periods=max(2, d // 2)).mean()
    s = x.rolling(d, min_periods=max(2, d // 2)).std()
    return (x - m) / s.replace(0, np.nan)


def ts_argmax(x: pd.DataFrame, d: int) -> pd.DataFrame:
    """Days since rolling d-day max. 0 = today is the max.

    Useful for "days since 52-week high" type signals.
    """
    def _argmax(series: pd.Series) -> pd.Series:
        return series.rolling(d, min_periods=max(1, d // 2)).apply(
            lambda w: d - 1 - np.argmax(w), raw=True,
        )
    return x.apply(_argmax)


def ts_argmin(x: pd.DataFrame, d: int) -> pd.DataFrame:
    """Days since rolling d-day min. 0 = today is the min."""
    def _argmin(series: pd.Series) -> pd.Series:
        return series.rolling(d, min_periods=max(1, d // 2)).apply(
            lambda w: d - 1 - np.argmin(w), raw=True,
        )
    return x.apply(_argmin)


def ts_prod(x: pd.DataFrame, d: int) -> pd.DataFrame:
    """Rolling product over d days. Useful for compound returns."""
    return x.rolling(d, min_periods=max(1, d // 2)).apply(np.prod, raw=True)


def ts_vwap(price: pd.DataFrame, vol: pd.DataFrame, d: int) -> pd.DataFrame:
    """Volume-weighted average price over d days.

    VWAP = sum(price * volume, d) / sum(volume, d)
    Institutional fair-value reference.
    """
    pv = price * vol
    sum_pv = pv.rolling(d, min_periods=max(1, d // 2)).sum()
    sum_v = vol.rolling(d, min_periods=max(1, d // 2)).sum()
    return sum_pv / sum_v.replace(0, np.nan)


# ── Cross-sectional operators (across stocks, single day) ─────────────────────


def cs_rank(x: pd.DataFrame) -> pd.DataFrame:
    """Rank across stocks each day (0 to 1, percentile)."""
    return x.rank(axis=1, pct=True, na_option="keep")


def cs_zscore(x: pd.DataFrame) -> pd.DataFrame:
    """Z-score across stocks each day."""
    row_mean = x.mean(axis=1)
    row_std = x.std(axis=1)
    row_std = row_std.replace(0, np.nan)
    return x.sub(row_mean, axis=0).div(row_std, axis=0)


def cs_demean(x: pd.DataFrame) -> pd.DataFrame:
    """Remove cross-sectional mean each day (market-neutral)."""
    return x.sub(x.mean(axis=1), axis=0)


# ── Scalar / element-wise operators ──────────────────────────────────────────


def op_abs(x: pd.DataFrame) -> pd.DataFrame:
    """Element-wise absolute value."""
    return x.abs()


def op_log(x: pd.DataFrame) -> pd.DataFrame:
    """Element-wise natural log (clipped to avoid log(0))."""
    return np.log(x.clip(lower=1e-10))


def op_sign(x: pd.DataFrame) -> pd.DataFrame:
    """Element-wise sign (-1, 0, +1)."""
    return np.sign(x)


# ── Operator registry ────────────────────────────────────────────────────────
#
# Maps operator name → OperatorSpec.
# n_expr_args = number of DataFrame arguments (not counting the int window param).
# has_window = whether the last argument is an integer window size.


@dataclass
class OperatorSpec:
    func: Callable
    n_expr_args: int  # number of DataFrame/expression arguments
    has_window: bool  # True if last arg to the function is an int window param


OPERATOR_REGISTRY: dict[str, OperatorSpec] = {
    # ── Time-series: 1 expr + window ─────────────────────────────────────
    "ts_mean":    OperatorSpec(func=ts_mean,    n_expr_args=1, has_window=True),
    "sma":        OperatorSpec(func=ts_mean,    n_expr_args=1, has_window=True),
    "ts_std":     OperatorSpec(func=ts_std,     n_expr_args=1, has_window=True),
    "ts_sum":     OperatorSpec(func=ts_sum,     n_expr_args=1, has_window=True),
    "ts_max":     OperatorSpec(func=ts_max,     n_expr_args=1, has_window=True),
    "ts_min":     OperatorSpec(func=ts_min,     n_expr_args=1, has_window=True),
    "ts_rank":    OperatorSpec(func=ts_rank,    n_expr_args=1, has_window=True),
    "ts_delta":   OperatorSpec(func=ts_delta,   n_expr_args=1, has_window=True),
    "delta":      OperatorSpec(func=ts_delta,   n_expr_args=1, has_window=True),
    "ts_returns": OperatorSpec(func=ts_returns, n_expr_args=1, has_window=True),
    "ts_ema":     OperatorSpec(func=ts_ema,     n_expr_args=1, has_window=True),
    "ema":        OperatorSpec(func=ts_ema,     n_expr_args=1, has_window=True),
    "ts_decay":   OperatorSpec(func=ts_decay,   n_expr_args=1, has_window=True),
    "ts_skew":    OperatorSpec(func=ts_skew,    n_expr_args=1, has_window=True),
    "ts_kurt":    OperatorSpec(func=ts_kurt,    n_expr_args=1, has_window=True),
    "ts_zscore":  OperatorSpec(func=ts_zscore,  n_expr_args=1, has_window=True),
    "ts_argmax":  OperatorSpec(func=ts_argmax,  n_expr_args=1, has_window=True),
    "ts_argmin":  OperatorSpec(func=ts_argmin,  n_expr_args=1, has_window=True),
    "ts_prod":    OperatorSpec(func=ts_prod,    n_expr_args=1, has_window=True),
    # ── Time-series: 2 expr + window ─────────────────────────────────────
    "ts_corr":    OperatorSpec(func=ts_corr,    n_expr_args=2, has_window=True),
    "ts_cov":     OperatorSpec(func=ts_cov,     n_expr_args=2, has_window=True),
    "ts_vwap":    OperatorSpec(func=ts_vwap,    n_expr_args=2, has_window=True),
    "vwap":       OperatorSpec(func=ts_vwap,    n_expr_args=2, has_window=True),
    # ── Cross-sectional: 1 expr, no window ───────────────────────────────
    "cs_rank":    OperatorSpec(func=cs_rank,    n_expr_args=1, has_window=False),
    "cs_zscore":  OperatorSpec(func=cs_zscore,  n_expr_args=1, has_window=False),
    "cs_demean":  OperatorSpec(func=cs_demean,  n_expr_args=1, has_window=False),
    # ── Scalar / element-wise: 1 expr, no window ────────────────────────
    "abs":        OperatorSpec(func=op_abs,     n_expr_args=1, has_window=False),
    "log":        OperatorSpec(func=op_log,     n_expr_args=1, has_window=False),
    "sign":       OperatorSpec(func=op_sign,    n_expr_args=1, has_window=False),
}

# Column names the expression engine recognises as data inputs
VALID_COLUMNS = {
    # OHLCV
    "open", "high", "low", "close", "volume", "returns",
    # Fundamentals (SEC EDGAR filing dates, forward-filled quarterly)
    "earnings_yield", "revenue_growth", "profit_margin", "expense_ratio",
}
