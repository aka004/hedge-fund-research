"""
Sequential Bootstrap (AFML Chapter 4)

Standard bootstrap draws with replacement, ignoring temporal overlap.
When labels span multiple bars, standard bootstrap oversamples redundant
observations. Sequential bootstrap weights each draw by its uniqueness
relative to already-selected samples.

DO NOT use standard bootstrap with overlapping labels.
"""

import numpy as np
import pandas as pd


def _build_indicator_matrix(
    labels_start: pd.Series,
    labels_end: pd.Series,
) -> np.ndarray:
    """
    Build binary indicator matrix: which time bars each label spans.

    Returns shape (n_labels, n_bars) where n_bars = number of unique
    time points covered by any label.
    """
    # Collect all unique time points, normalize to pd.Timestamp
    starts = [pd.Timestamp(t) for t in labels_start.values]
    ends = [pd.Timestamp(t) for t in labels_end.values]
    all_times = sorted(set(starts) | set(ends))
    time_to_idx = {t: i for i, t in enumerate(all_times)}
    n_bars = len(all_times)
    n_labels = len(labels_start)

    indicator = np.zeros((n_labels, n_bars), dtype=np.float64)

    for i in range(n_labels):
        start_idx = time_to_idx[starts[i]]
        end_idx = time_to_idx[ends[i]]
        indicator[i, start_idx : end_idx + 1] = 1.0

    return indicator


def average_uniqueness(
    labels_start: pd.Series,
    labels_end: pd.Series,
    sampled_indices: np.ndarray,
) -> float:
    """
    Compute average uniqueness of a set of sampled indices.

    Uniqueness at time t = 1 / (number of sampled labels active at t).
    Average uniqueness = mean over all (sample, time) pairs.

    Parameters
    ----------
    labels_start : pd.Series
        Start time of each label period
    labels_end : pd.Series
        End time of each label period
    sampled_indices : np.ndarray
        Indices of selected samples

    Returns
    -------
    float
        Average uniqueness (0 to 1, higher = more unique)
    """
    if len(sampled_indices) == 0:
        return 1.0

    indicator = _build_indicator_matrix(labels_start, labels_end)

    # Concurrency: how many sampled labels are active at each bar
    sampled_indicator = indicator[sampled_indices]
    concurrency = sampled_indicator.sum(axis=0)  # shape (n_bars,)

    total_uniqueness = 0.0
    total_count = 0

    for row in sampled_indicator:
        active_bars = row > 0
        if active_bars.sum() == 0:
            continue
        # Uniqueness for this sample = mean(1/concurrency) over its active bars
        bar_concurrency = concurrency[active_bars]
        # Avoid division by zero
        bar_uniqueness = np.where(bar_concurrency > 0, 1.0 / bar_concurrency, 0.0)
        total_uniqueness += bar_uniqueness.sum()
        total_count += len(bar_uniqueness)

    return total_uniqueness / total_count if total_count > 0 else 1.0


def sequential_bootstrap(
    labels_start: pd.Series,
    labels_end: pd.Series,
    n_samples: int | None = None,
) -> np.ndarray:
    """
    Draw samples using sequential bootstrap (AFML Ch. 4).

    At each draw, compute average uniqueness of each candidate sample
    given already-selected samples. Sample with probability proportional
    to uniqueness.

    Parameters
    ----------
    labels_start : pd.Series
        Start time of each label period
    labels_end : pd.Series
        End time of each label period
    n_samples : int, optional
        Number of samples to draw. If None, draws len(labels_start).

    Returns
    -------
    np.ndarray
        Array of selected indices

    Example
    -------
    >>> labels = triple_barrier(prices)
    >>> idx = sequential_bootstrap(labels.labels.index.to_series(), labels.exit_times)
    >>> X_boot = X.iloc[idx]
    """
    n_total = len(labels_start)
    if n_samples is None:
        n_samples = n_total

    indicator = _build_indicator_matrix(labels_start, labels_end)
    n_bars = indicator.shape[1]

    selected = []
    # Running concurrency count across bars
    concurrency = np.zeros(n_bars, dtype=np.float64)

    for _ in range(n_samples):
        # Compute uniqueness for each candidate given current selection
        uniqueness = np.zeros(n_total)

        for i in range(n_total):
            active_bars = indicator[i] > 0
            if active_bars.sum() == 0:
                uniqueness[i] = 1.0
                continue

            # Concurrency if we added this sample
            candidate_conc = concurrency[active_bars] + 1.0
            uniqueness[i] = np.mean(1.0 / candidate_conc)

        # Sample proportional to uniqueness
        total_u = uniqueness.sum()
        if total_u <= 0:
            # Fallback to uniform
            probs = np.ones(n_total) / n_total
        else:
            probs = uniqueness / total_u

        chosen = np.random.choice(n_total, p=probs)
        selected.append(chosen)

        # Update concurrency
        concurrency += indicator[chosen]

    return np.array(selected)
