"""
Triple-Barrier Labeling (AFML Chapter 3)

Fixed-time labeling assumes returns arrive on schedule. Reality: trades exit
at stop-loss, profit target, OR time limit. Triple-barrier captures actual
trading dynamics.

DO NOT use fixed-time returns for strategy labeling.
"""

from dataclasses import dataclass

import pandas as pd


@dataclass
class TripleBarrierLabels:
    """
    Result of triple-barrier labeling.

    Attributes
    ----------
    labels : pd.Series
        Label for each sample: 1 (profit), -1 (loss), 0 (timeout)
    returns : pd.Series
        Actual return at exit
    exit_times : pd.Series
        Timestamp when each position exited
    exit_types : pd.Series
        Which barrier was hit: 'profit', 'stop', 'timeout'
    """

    labels: pd.Series
    returns: pd.Series
    exit_times: pd.Series
    exit_types: pd.Series

    def to_dataframe(self) -> pd.DataFrame:
        """Convert to DataFrame for inspection."""
        return pd.DataFrame(
            {
                "label": self.labels,
                "return": self.returns,
                "exit_time": self.exit_times,
                "exit_type": self.exit_types,
            }
        )


def triple_barrier(
    prices: pd.Series,
    events: pd.DatetimeIndex = None,
    volatility: pd.Series = None,
    profit_take: float = 2.0,
    stop_loss: float = 2.0,
    max_holding: int = 10,
    side: pd.Series | None = None,
) -> TripleBarrierLabels:
    """
    Apply triple-barrier labeling to price series.

    Parameters
    ----------
    prices : pd.Series
        Price series with DatetimeIndex
    events : pd.DatetimeIndex, optional
        Timestamps to label. If None, uses all prices.
    volatility : pd.Series, optional
        Daily volatility for barrier sizing. If None, computed as 20-day std.
    profit_take : float
        Upper barrier as multiple of volatility (default 2.0)
    stop_loss : float
        Lower barrier as multiple of volatility (default 2.0)
    max_holding : int
        Maximum holding period in days (default 10)
    side : pd.Series, optional
        Trade direction: 1 for long, -1 for short. If None, assumes long.

    Returns
    -------
    TripleBarrierLabels
        Labeled dataset with returns and exit information

    Example
    -------
    >>> labels = triple_barrier(prices, profit_take=2.0, stop_loss=2.0, max_holding=10)
    >>> df = labels.to_dataframe()
    >>> print(df.exit_type.value_counts())
    """
    # Default to all timestamps
    if events is None:
        events = prices.index[:-max_holding]  # Leave room for holding period

    # Compute volatility if not provided
    if volatility is None:
        volatility = prices.pct_change().rolling(20).std()

    # Default to long positions
    if side is None:
        side = pd.Series(1, index=events)

    labels = []
    returns = []
    exit_times = []
    exit_types = []

    for event_time in events:
        if event_time not in prices.index:
            continue

        entry_price = prices.loc[event_time]
        vol = volatility.loc[event_time] if event_time in volatility.index else 0.02
        position_side = side.loc[event_time] if event_time in side.index else 1

        # Barrier levels (adjusted for side)
        upper_barrier = entry_price * (1 + profit_take * vol * position_side)
        lower_barrier = entry_price * (1 - stop_loss * vol * position_side)

        # Get future prices within holding period
        future_mask = prices.index > event_time
        future_prices = prices[future_mask].head(max_holding)

        if len(future_prices) == 0:
            continue

        # Find first barrier touch
        label = 0
        exit_return = 0.0
        exit_time = future_prices.index[-1]  # Default: timeout
        exit_type = "timeout"

        for t, price in future_prices.items():
            ret = (price / entry_price - 1) * position_side

            # Check upper barrier (profit)
            if position_side == 1 and price >= upper_barrier or position_side == -1 and price <= upper_barrier:
                label = 1
                exit_return = ret
                exit_time = t
                exit_type = "profit"
                break

            # Check lower barrier (stop-loss)
            if position_side == 1 and price <= lower_barrier or position_side == -1 and price >= lower_barrier:
                label = -1
                exit_return = ret
                exit_time = t
                exit_type = "stop"
                break
        else:
            # Timeout - use final return
            final_price = future_prices.iloc[-1]
            exit_return = (final_price / entry_price - 1) * position_side
            label = 1 if exit_return > 0 else (-1 if exit_return < 0 else 0)

        labels.append(label)
        returns.append(exit_return)
        exit_times.append(exit_time)
        exit_types.append(exit_type)

    return TripleBarrierLabels(
        labels=pd.Series(labels, index=events[: len(labels)]),
        returns=pd.Series(returns, index=events[: len(returns)]),
        exit_times=pd.Series(exit_times, index=events[: len(exit_times)]),
        exit_types=pd.Series(exit_types, index=events[: len(exit_types)]),
    )
