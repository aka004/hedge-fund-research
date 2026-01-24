"""
Sample Uniqueness Weighting (AFML Chapter 4)

When labels have overlapping return periods, they're correlated. Counting them
equally inflates sample size artificially. Weight by inverse concurrency.

DO NOT use equal sample weights with overlapping labels.
"""

import pandas as pd


def compute_concurrency(
    labels_start: pd.Series,
    labels_end: pd.Series,
) -> pd.Series:
    """
    Compute how many labels are active at each label's midpoint.

    Parameters
    ----------
    labels_start : pd.Series
        Start time of each label period (index = sample id)
    labels_end : pd.Series
        End time of each label period (index = sample id)

    Returns
    -------
    pd.Series
        Concurrency count for each sample
    """
    concurrency = pd.Series(index=labels_start.index, dtype=float)

    for idx in labels_start.index:
        start = labels_start[idx]
        end = labels_end[idx]

        # Count overlapping labels
        overlaps = ((labels_start <= end) & (labels_end >= start)).sum()

        concurrency[idx] = overlaps

    return concurrency


def sample_uniqueness(
    labels_start: pd.Series,
    labels_end: pd.Series,
    normalize: bool = True,
) -> pd.Series:
    """
    Compute sample weights based on uniqueness (inverse concurrency).

    Samples that overlap heavily with others get downweighted. This corrects
    for pseudo-replication in time-series data.

    Parameters
    ----------
    labels_start : pd.Series
        Start time of each label period
    labels_end : pd.Series
        End time of each label period
    normalize : bool
        If True, weights sum to 1.0 (default True)

    Returns
    -------
    pd.Series
        Sample weights (higher = more unique)

    Example
    -------
    >>> # From triple-barrier labels
    >>> labels = triple_barrier(prices)
    >>> weights = sample_uniqueness(
    ...     labels_start=prices.index[:len(labels.labels)],
    ...     labels_end=labels.exit_times,
    ... )
    >>> model.fit(X, y, sample_weight=weights)
    """
    concurrency = compute_concurrency(labels_start, labels_end)

    # Uniqueness = inverse of concurrency
    uniqueness = 1.0 / concurrency

    if normalize:
        uniqueness = uniqueness / uniqueness.sum()

    return uniqueness


def sample_uniqueness_from_labels(
    labels: "TripleBarrierLabels",
    entry_times: pd.DatetimeIndex = None,
    normalize: bool = True,
) -> pd.Series:
    """
    Convenience function to compute sample weights from TripleBarrierLabels.

    Parameters
    ----------
    labels : TripleBarrierLabels
        Output from triple_barrier()
    entry_times : pd.DatetimeIndex, optional
        Entry times. If None, uses labels.labels.index
    normalize : bool
        If True, weights sum to 1.0

    Returns
    -------
    pd.Series
        Sample weights
    """
    if entry_times is None:
        entry_times = labels.labels.index

    return sample_uniqueness(
        labels_start=pd.Series(entry_times, index=labels.labels.index),
        labels_end=labels.exit_times,
        normalize=normalize,
    )
