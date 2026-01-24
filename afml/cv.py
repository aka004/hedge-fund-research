"""
Purged K-Fold Cross-Validation (AFML Chapter 7)

Standard k-fold CV leaks information in financial time series because
observations have overlapping label periods. Purged K-Fold removes
training samples whose labels overlap with the test period.

DO NOT use sklearn's KFold for financial backtesting.
"""

from collections.abc import Generator
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class PurgedKFold:
    """
    Purged K-Fold cross-validator for financial time series.

    Parameters
    ----------
    n_splits : int
        Number of folds (default 5)
    embargo_pct : float
        Fraction of data to embargo after test set (default 0.01 = 1%)
    """

    n_splits: int = 5
    embargo_pct: float = 0.01

    def split(
        self,
        X: pd.DataFrame,
        y: pd.Series = None,
        labels_end_times: pd.Series = None,
    ) -> Generator[tuple[np.ndarray, np.ndarray], None, None]:
        """
        Generate train/test indices with purging and embargo.

        Parameters
        ----------
        X : pd.DataFrame
            Features with DatetimeIndex
        y : pd.Series, optional
            Target values (not used, for sklearn compatibility)
        labels_end_times : pd.Series
            End time of each label's evaluation period.
            Index should match X.index, values are the label end times.
            If None, assumes labels don't overlap (point-in-time).

        Yields
        ------
        train_indices : np.ndarray
            Indices for training set (purged)
        test_indices : np.ndarray
            Indices for test set
        """
        n_samples = len(X)
        indices = np.arange(n_samples)

        # Compute embargo size
        embargo_size = int(n_samples * self.embargo_pct)

        # Fold size
        fold_size = n_samples // self.n_splits

        for fold in range(self.n_splits):
            # Test indices for this fold
            test_start = fold * fold_size
            test_end = test_start + fold_size if fold < self.n_splits - 1 else n_samples
            test_indices = indices[test_start:test_end]

            # Get test period time range
            test_times = X.index[test_indices]
            test_start_time = test_times.min()
            test_end_time = test_times.max()

            # Start with all non-test indices
            train_mask = np.ones(n_samples, dtype=bool)
            train_mask[test_indices] = False

            # Apply embargo after test set
            embargo_end = min(test_end + embargo_size, n_samples)
            train_mask[test_end:embargo_end] = False

            # Purge: remove training samples whose labels overlap test period
            if labels_end_times is not None:
                for i in range(n_samples):
                    if train_mask[i]:
                        sample_time = X.index[i]
                        label_end = labels_end_times.iloc[i]

                        # If this training sample's label extends into test period
                        if (
                            sample_time < test_start_time
                            and label_end > test_start_time
                        ):
                            train_mask[i] = False

            train_indices = indices[train_mask]

            yield train_indices, test_indices

    def get_n_splits(self) -> int:
        """Return number of splits."""
        return self.n_splits


def purged_kfold(
    X: pd.DataFrame,
    y: pd.Series = None,
    n_splits: int = 5,
    embargo_pct: float = 0.01,
    labels_end_times: pd.Series = None,
) -> Generator[tuple[np.ndarray, np.ndarray], None, None]:
    """
    Convenience function for purged k-fold cross-validation.

    Parameters
    ----------
    X : pd.DataFrame
        Features with DatetimeIndex
    y : pd.Series, optional
        Target values
    n_splits : int
        Number of folds (default 5)
    embargo_pct : float
        Fraction to embargo after test (default 0.01)
    labels_end_times : pd.Series
        End times of labels for purging

    Yields
    ------
    train_indices, test_indices : tuple of np.ndarray

    Example
    -------
    >>> for train_idx, test_idx in purged_kfold(X, n_splits=5):
    ...     X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
    ...     model.fit(X_train, y.iloc[train_idx])
    ...     score = model.score(X_test, y.iloc[test_idx])
    """
    cv = PurgedKFold(n_splits=n_splits, embargo_pct=embargo_pct)
    yield from cv.split(X, y, labels_end_times)
