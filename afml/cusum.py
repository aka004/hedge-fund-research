"""
CUSUM Filter (AFML Chapter 2)

Most event-driven strategies oversample: generating signals at every bar
creates redundant labels. The CUSUM filter detects structural breaks,
triggering events only when cumulative deviation exceeds a threshold.

DO NOT sample at every bar. Use CUSUM to select meaningful events.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class CUSUMResult:
    """
    Result of CUSUM filter.

    Attributes
    ----------
    events : pd.DatetimeIndex
        Timestamps where filter triggers
    cusum_positive : pd.Series
        Positive CUSUM values over time
    cusum_negative : pd.Series
        Negative CUSUM values over time
    threshold : float
        Threshold used
    """

    events: pd.DatetimeIndex
    cusum_positive: pd.Series
    cusum_negative: pd.Series
    threshold: float


def cusum_filter(
    prices: pd.Series,
    threshold: float | None = None,
    use_log_returns: bool = True,
) -> CUSUMResult:
    """
    Symmetric CUSUM filter for structural break detection.

    Algorithm:
        S_t^+ = max(0, S_{t-1}^+ + (r_t - E[r]))
        S_t^- = min(0, S_{t-1}^- + (r_t - E[r]))
        Event when S_t^+ > h or S_t^- < -h (reset to 0 after event).

    Parameters
    ----------
    prices : pd.Series
        Price series with DatetimeIndex
    threshold : float, optional
        CUSUM threshold. If None, auto-computed as daily_std.
    use_log_returns : bool
        If True, use log returns; otherwise use simple returns (default True)

    Returns
    -------
    CUSUMResult
        Detected events and CUSUM series

    Example
    -------
    >>> result = cusum_filter(spy_prices)
    >>> events = result.events
    >>> labels = triple_barrier(prices, events=events)
    """
    # Compute returns
    if use_log_returns:
        returns = np.log(prices / prices.shift(1)).dropna()
    else:
        returns = prices.pct_change().dropna()

    # Auto-compute threshold as daily standard deviation
    if threshold is None:
        threshold = returns.std()

    mean_return = returns.mean()

    # Run CUSUM
    s_pos = 0.0
    s_neg = 0.0
    events = []
    cusum_pos_values = []
    cusum_neg_values = []

    for t, r in returns.items():
        deviation = r - mean_return

        s_pos = max(0.0, s_pos + deviation)
        s_neg = min(0.0, s_neg + deviation)

        cusum_pos_values.append(s_pos)
        cusum_neg_values.append(s_neg)

        if s_pos > threshold:
            events.append(t)
            s_pos = 0.0
        elif s_neg < -threshold:
            events.append(t)
            s_neg = 0.0

    cusum_positive = pd.Series(cusum_pos_values, index=returns.index)
    cusum_negative = pd.Series(cusum_neg_values, index=returns.index)

    return CUSUMResult(
        events=pd.DatetimeIndex(events),
        cusum_positive=cusum_positive,
        cusum_negative=cusum_negative,
        threshold=threshold,
    )
