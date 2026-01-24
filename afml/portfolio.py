"""
Hierarchical Risk Parity (AFML Chapter 16)

Mean-variance optimization requires inverting a covariance matrix. When assets
are correlated or you have more assets than observations, this produces extreme
weights.

HRP uses hierarchical clustering + recursive bisection for stable weights.

DO NOT use mean-variance optimization for portfolio construction.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import leaves_list, linkage
from scipy.spatial.distance import squareform


@dataclass
class HRPResult:
    """
    Result of HRP portfolio optimization.

    Attributes
    ----------
    weights : pd.Series
        Portfolio weights (sum to 1.0)
    cluster_order : List[str]
        Assets ordered by hierarchical clustering
    linkage_matrix : np.ndarray
        Hierarchical clustering linkage matrix
    """

    weights: pd.Series
    cluster_order: list[str]
    linkage_matrix: np.ndarray


def correlation_distance(corr: pd.DataFrame) -> pd.DataFrame:
    """
    Convert correlation matrix to distance matrix.

    d_ij = sqrt(0.5 * (1 - corr_ij))

    Parameters
    ----------
    corr : pd.DataFrame
        Correlation matrix

    Returns
    -------
    pd.DataFrame
        Distance matrix
    """
    return np.sqrt(0.5 * (1 - corr))


def quasi_diagonalize(link: np.ndarray, n_assets: int) -> list[int]:
    """
    Reorder assets to quasi-diagonalize the covariance matrix.

    Uses the dendrogram leaf ordering from hierarchical clustering.

    Parameters
    ----------
    link : np.ndarray
        Linkage matrix from scipy.cluster.hierarchy.linkage
    n_assets : int
        Number of assets

    Returns
    -------
    List[int]
        Reordered asset indices
    """
    return list(leaves_list(link))


def recursive_bisection(
    cov: pd.DataFrame,
    sorted_indices: list[int],
) -> pd.Series:
    """
    Allocate weights via recursive bisection.

    At each level, split the portfolio in two and allocate based on
    inverse variance of each cluster.

    Parameters
    ----------
    cov : pd.DataFrame
        Covariance matrix
    sorted_indices : List[int]
        Asset indices in clustered order

    Returns
    -------
    pd.Series
        Portfolio weights
    """
    weights = pd.Series(1.0, index=cov.index)
    cluster_items = [sorted_indices]

    while len(cluster_items) > 0:
        # Split each cluster
        cluster_items_new = []

        for cluster in cluster_items:
            if len(cluster) <= 1:
                continue

            # Split in half
            mid = len(cluster) // 2
            left = cluster[:mid]
            right = cluster[mid:]

            # Compute cluster variances
            left_assets = [cov.index[i] for i in left]
            right_assets = [cov.index[i] for i in right]

            left_var = cluster_variance(cov.loc[left_assets, left_assets])
            right_var = cluster_variance(cov.loc[right_assets, right_assets])

            # Allocate by inverse variance
            total_inv_var = 1 / left_var + 1 / right_var
            left_weight = (1 / left_var) / total_inv_var
            right_weight = (1 / right_var) / total_inv_var

            # Apply weights
            weights[left_assets] *= left_weight
            weights[right_assets] *= right_weight

            # Continue recursion
            if len(left) > 1:
                cluster_items_new.append(left)
            if len(right) > 1:
                cluster_items_new.append(right)

        cluster_items = cluster_items_new

    return weights


def cluster_variance(cov: pd.DataFrame) -> float:
    """
    Compute variance of an equal-weight portfolio within a cluster.

    Parameters
    ----------
    cov : pd.DataFrame
        Covariance matrix of cluster assets

    Returns
    -------
    float
        Cluster portfolio variance
    """
    n = len(cov)
    if n == 0:
        return 1.0

    # Equal weight within cluster
    w = np.ones(n) / n

    # Portfolio variance = w' Σ w
    return float(w @ cov.values @ w)


def hrp(
    returns: pd.DataFrame,
    method: str = "single",
) -> HRPResult:
    """
    Compute Hierarchical Risk Parity portfolio weights.

    Parameters
    ----------
    returns : pd.DataFrame
        Asset returns (rows = dates, columns = assets)
    method : str
        Clustering method: 'single', 'complete', 'average', 'ward'
        Default 'single' (as in AFML)

    Returns
    -------
    HRPResult
        Portfolio weights and clustering info

    Example
    -------
    >>> result = hrp(returns_df)
    >>> print(result.weights)
    >>> # Rebalance portfolio to these weights
    """
    # Compute correlation and covariance
    corr = returns.corr()
    cov = returns.cov()

    # Step 1: Compute distance matrix
    dist = correlation_distance(corr)

    # Convert to condensed form for scipy
    dist_condensed = squareform(dist.values, checks=False)

    # Handle any NaN/inf
    dist_condensed = np.nan_to_num(dist_condensed, nan=1.0, posinf=1.0, neginf=0.0)

    # Step 2: Hierarchical clustering
    link = linkage(dist_condensed, method=method)

    # Step 3: Quasi-diagonalize
    sorted_indices = quasi_diagonalize(link, len(corr))
    cluster_order = [corr.index[i] for i in sorted_indices]

    # Step 4: Recursive bisection
    weights = recursive_bisection(cov, sorted_indices)

    # Normalize
    weights = weights / weights.sum()

    return HRPResult(
        weights=weights,
        cluster_order=cluster_order,
        linkage_matrix=link,
    )


# Alias
hierarchical_risk_parity = hrp
