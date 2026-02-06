"""
Combinatorial Purged Cross-Validation (AFML Chapter 12)

Standard CV picks ONE train/test split per fold. CPCV generates ALL
combinations of test groups, building multiple equity paths from
out-of-sample predictions. This enables computing the Probability
of Backtest Overfitting (PBO).

DO NOT use standard k-fold for backtest overfitting assessment.
"""

from dataclasses import dataclass
from itertools import combinations

import numpy as np
import pandas as pd


@dataclass
class CPCVResult:
    """
    Result of Combinatorial Purged Cross-Validation.

    Attributes
    ----------
    paths : list[np.ndarray]
        Equity curves per combination
    n_paths : int
        Number of combinations (nCk)
    pbo : float
        Probability of Backtest Overfitting: fraction of paths
        with negative total return
    path_sharpes : list[float]
        Annualized Sharpe ratio of each path
    """

    paths: list[np.ndarray]
    n_paths: int
    pbo: float
    path_sharpes: list[float]


class CombPurgedKFold:
    """
    Combinatorial Purged K-Fold cross-validator.

    Generates C(n_splits, n_test_groups) train/test splits by
    selecting all combinations of groups as test sets.

    Parameters
    ----------
    n_splits : int
        Number of groups to divide data into (default 6)
    n_test_groups : int
        Number of groups to use as test in each combination (default 2)
    embargo_pct : float
        Fraction of data to embargo after test set (default 0.01)
    """

    def __init__(
        self,
        n_splits: int = 6,
        n_test_groups: int = 2,
        embargo_pct: float = 0.01,
    ):
        self.n_splits = n_splits
        self.n_test_groups = n_test_groups
        self.embargo_pct = embargo_pct

    def split(
        self,
        X: pd.DataFrame,
        labels_end_times: pd.Series = None,
    ):
        """
        Generate CPCV train/test splits.

        For each combination of n_test_groups from n_splits groups,
        use those as test, rest as train (with purging + embargo).

        Parameters
        ----------
        X : pd.DataFrame
            Features with DatetimeIndex
        labels_end_times : pd.Series, optional
            End time of each label's evaluation period for purging

        Yields
        ------
        train_indices : np.ndarray
            Indices for training set (purged)
        test_indices : np.ndarray
            Indices for test set
        """
        n_samples = len(X)
        indices = np.arange(n_samples)
        embargo_size = int(n_samples * self.embargo_pct)

        # Divide into groups
        group_size = n_samples // self.n_splits
        groups = []
        for g in range(self.n_splits):
            start = g * group_size
            end = start + group_size if g < self.n_splits - 1 else n_samples
            groups.append(indices[start:end])

        # Iterate over all combinations of test groups
        for test_group_ids in combinations(range(self.n_splits), self.n_test_groups):
            test_indices = np.concatenate([groups[g] for g in test_group_ids])
            test_indices.sort()

            # Start with all non-test indices
            train_mask = np.ones(n_samples, dtype=bool)
            train_mask[test_indices] = False

            # Apply embargo after each test group
            for g in test_group_ids:
                group_end = groups[g][-1] + 1
                embargo_end = min(group_end + embargo_size, n_samples)
                # Only embargo indices not already in test
                for idx in range(group_end, embargo_end):
                    if idx not in test_indices:
                        train_mask[idx] = False

            # Purge training samples whose labels overlap test period
            if labels_end_times is not None:
                test_times = X.index[test_indices]
                test_start_time = test_times.min()

                for i in range(n_samples):
                    if train_mask[i]:
                        sample_time = X.index[i]
                        label_end = labels_end_times.iloc[i]
                        if (
                            sample_time < test_start_time
                            and label_end > test_start_time
                        ):
                            train_mask[i] = False

            train_indices = indices[train_mask]
            yield train_indices, test_indices

    def backtest_paths(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        labels_end_times: pd.Series = None,
    ) -> CPCVResult:
        """
        Run CPCV and build equity paths from out-of-sample segments.

        Each combination contributes test-set returns. Paths are built
        by stitching together OOS segments in time order.

        Parameters
        ----------
        X : pd.DataFrame
            Features with DatetimeIndex
        y : pd.Series
            Returns for each sample
        labels_end_times : pd.Series, optional
            End times for purging

        Returns
        -------
        CPCVResult
            Equity paths and PBO estimate
        """
        paths = []
        path_sharpes = []

        for train_idx, test_idx in self.split(X, labels_end_times):
            # Extract OOS returns in time order
            oos_returns = y.iloc[test_idx].sort_index().values

            # Build equity curve from cumulative returns
            equity = np.cumprod(1.0 + oos_returns)
            paths.append(equity)

            # Compute Sharpe of this path
            if len(oos_returns) > 1 and np.std(oos_returns) > 0:
                sharpe = np.mean(oos_returns) / np.std(oos_returns) * np.sqrt(252)
            else:
                sharpe = 0.0
            path_sharpes.append(sharpe)

        n_paths = len(paths)

        # PBO = fraction of paths with negative total return
        if n_paths > 0:
            negative_paths = sum(1 for p in paths if p[-1] < 1.0)
            pbo = negative_paths / n_paths
        else:
            pbo = 1.0

        return CPCVResult(
            paths=paths,
            n_paths=n_paths,
            pbo=pbo,
            path_sharpes=path_sharpes,
        )
