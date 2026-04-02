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
    """Rolling mean over d days."""
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

    Vectorized: for each column, compares current value to rolling min/max
    to compute approximate percentile position. Much faster than .apply().
    """
    r_min = x.rolling(d, min_periods=max(2, d // 2)).min()
    r_max = x.rolling(d, min_periods=max(2, d // 2)).max()
    denom = r_max - r_min
    # Where range is zero (all values equal), return 0.5
    return (x - r_min) / denom.replace(0, np.nan).fillna(1.0)


def ts_corr(x: pd.DataFrame, y: pd.DataFrame, d: int) -> pd.DataFrame:
    """Rolling correlation between x and y over d days."""
    result = {}
    for col in x.columns:
        if col in y.columns:
            result[col] = x[col].rolling(d, min_periods=max(3, d // 2)).corr(y[col])
    return pd.DataFrame(result, index=x.index)


def ts_delta(x: pd.DataFrame, d: int) -> pd.DataFrame:
    """x[t] - x[t-d]."""
    return x - x.shift(d)


# ── Cross-sectional operators (across stocks, single day) ─────────────────────


def cs_rank(x: pd.DataFrame) -> pd.DataFrame:
    """Rank across stocks each day (0 to 1, percentile)."""
    return x.rank(axis=1, pct=True, na_option="keep")


def cs_zscore(x: pd.DataFrame) -> pd.DataFrame:
    """Z-score across stocks each day."""
    row_mean = x.mean(axis=1)
    row_std = x.std(axis=1)
    # Avoid division by zero
    row_std = row_std.replace(0, np.nan)
    return x.sub(row_mean, axis=0).div(row_std, axis=0)


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
    # Time-series (1 expr + window)
    "ts_mean":  OperatorSpec(func=ts_mean,  n_expr_args=1, has_window=True),
    "ts_std":   OperatorSpec(func=ts_std,   n_expr_args=1, has_window=True),
    "ts_sum":   OperatorSpec(func=ts_sum,   n_expr_args=1, has_window=True),
    "ts_max":   OperatorSpec(func=ts_max,   n_expr_args=1, has_window=True),
    "ts_min":   OperatorSpec(func=ts_min,   n_expr_args=1, has_window=True),
    "ts_rank":  OperatorSpec(func=ts_rank,  n_expr_args=1, has_window=True),
    "ts_delta": OperatorSpec(func=ts_delta, n_expr_args=1, has_window=True),
    "delta":    OperatorSpec(func=ts_delta, n_expr_args=1, has_window=True),
    # Time-series (2 expr + window)
    "ts_corr":  OperatorSpec(func=ts_corr,  n_expr_args=2, has_window=True),
    # Cross-sectional (1 expr, no window)
    "cs_rank":   OperatorSpec(func=cs_rank,   n_expr_args=1, has_window=False),
    "cs_zscore": OperatorSpec(func=cs_zscore, n_expr_args=1, has_window=False),
    # Scalar / element-wise (1 expr, no window)
    "abs":  OperatorSpec(func=op_abs,  n_expr_args=1, has_window=False),
    "log":  OperatorSpec(func=op_log,  n_expr_args=1, has_window=False),
    "sign": OperatorSpec(func=op_sign, n_expr_args=1, has_window=False),
}

# Column names the expression engine recognises as data inputs
VALID_COLUMNS = {
    # OHLCV
    "open", "high", "low", "close", "volume", "returns",
    # Fundamentals (45-day filing lag, forward-filled quarterly)
    "earnings_yield", "revenue_growth", "profit_margin", "expense_ratio",
}
