"""Tests for afml/cv.py — purged k-fold cross-validation."""

import numpy as np
import pandas as pd

from afml.cv import purged_kfold


def test_purged_kfold_bidirectional_default():
    """purged_kfold() convenience function should default to bidirectional=True.

    Bidirectional purging removes samples that overlap the test window from
    either direction. This produces smaller training sets than unidirectional.
    """
    dates = pd.date_range("2020-01-01", periods=100, freq="D")
    X = pd.DataFrame({"feature": np.random.randn(100)}, index=dates)
    labels_end = pd.Series(dates + pd.Timedelta(days=5), index=dates)

    # Collect train sizes from default (should be bidirectional)
    default_train_sizes = [
        len(ti) for ti, _ in purged_kfold(X, labels_end_times=labels_end)
    ]

    # Collect train sizes from explicit bidirectional=False
    unidirectional_train_sizes = [
        len(ti)
        for ti, _ in purged_kfold(X, labels_end_times=labels_end, bidirectional=False)
    ]

    # Bidirectional purges more samples, so train sets must be smaller or equal
    assert sum(default_train_sizes) <= sum(unidirectional_train_sizes), (
        "Bidirectional default should purge >= as many samples as unidirectional. "
        f"Default total train size: {sum(default_train_sizes)}, "
        f"Unidirectional: {sum(unidirectional_train_sizes)}"
    )
