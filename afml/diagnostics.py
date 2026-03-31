"""
Masters Diagnostic Pipeline (Testing and Tuning Market Trading Systems)

Implements 4 mandatory validation tools before strategy go-live:
- ENTROPY: Bin-wise entropy of surprise score vs. label direction
- MCPT: Monte Carlo Permutation Test for statistical significance
- CHOOSER: Statistical parameter selection via Deflated Sharpe
- CSCV: Combinatorial Symmetric CV overfitting test
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Tool 2: Entropy Diagnostic
# ---------------------------------------------------------------------------


@dataclass
class EntropyDiagnosticResult:
    """Result of entropy diagnostic (Masters ENTROPY).

    Attributes
    ----------
    bucket_entropies : pd.Series
        Shannon entropy H per Surprise Score bucket (index = bucket label)
    h_max : float
        Theoretical maximum entropy = log2(n_unique_classes)
    fraction_below_max : float
        Fraction of buckets with H < H_max
    passes : bool
        True if ALL bins have H < H_max (signal exists in every bin)
    bucket_stats : pd.DataFrame
        Columns: bucket_label, count, entropy
    """

    bucket_entropies: pd.Series
    h_max: float
    fraction_below_max: float
    passes: bool
    bucket_stats: pd.DataFrame


def _shannon_entropy(labels: pd.Series) -> float:
    """Compute Shannon entropy H = -sum(p * log2(p)) over label distribution."""
    if len(labels) == 0:
        return 0.0
    counts = labels.value_counts()
    probs = counts / counts.sum()
    probs = probs[probs > 0]
    return float(-np.sum(probs * np.log2(probs)))


def entropy_diagnostic(
    surprise_scores: pd.Series,
    labels: pd.Series,
    n_bins: int = 5,
) -> EntropyDiagnosticResult:
    """Entropy diagnostic (Masters ENTROPY).

    Bins events by surprise score magnitude, computes Shannon entropy
    of the label distribution in each bin. Lower entropy = more predictable.

    Parameters
    ----------
    surprise_scores : pd.Series
        Surprise score magnitude per event
    labels : pd.Series
        Direction labels: +1 / -1 / 0 per event
    n_bins : int
        Number of quantile bins (default 5)

    Returns
    -------
    EntropyDiagnosticResult
    """
    n_classes = len(labels.unique())
    h_max = math.log2(n_classes) if n_classes > 1 else 0.0

    bins = pd.qcut(surprise_scores, n_bins, duplicates="drop")

    rows = []
    for bucket in bins.cat.categories:
        mask = bins == bucket
        bucket_labels = labels[mask]
        h = _shannon_entropy(bucket_labels)
        rows.append(
            {"bucket_label": str(bucket), "count": int(mask.sum()), "entropy": h}
        )

    bucket_stats = pd.DataFrame(rows)
    bucket_entropies = pd.Series(
        bucket_stats["entropy"].values,
        index=bucket_stats["bucket_label"].values,
    )

    # Use a relative tolerance of 0.5% so near-maximum entropy (near-uniform distribution)
    # is treated as reaching H_max. This prevents near-equal floating-point values
    # from being incorrectly counted as informative signal.
    _eps = h_max * 0.005
    fraction_below_max = (
        float((bucket_entropies < h_max - _eps).mean()) if h_max > 0 else 1.0
    )
    passes = bool((bucket_entropies < h_max - _eps).all()) if h_max > 0 else True

    return EntropyDiagnosticResult(
        bucket_entropies=bucket_entropies,
        h_max=h_max,
        fraction_below_max=fraction_below_max,
        passes=passes,
        bucket_stats=bucket_stats,
    )


# ---------------------------------------------------------------------------
# Tool 3: Monte Carlo Permutation Test
# ---------------------------------------------------------------------------


@dataclass
class McptResult:
    """Result of Monte Carlo Permutation Test (Masters MCPT).

    Attributes
    ----------
    observed_sharpe : float
        Annualized Sharpe ratio of original event returns
    permutation_sharpes : list[float]
        Sharpe ratio for each permutation
    p_value : float
        Fraction of permutations where Sharpe >= observed_sharpe
    n_permutations : int
        Number of permutations run
    passes : bool
        True if p_value < significance
    significance : float
        Significance threshold used
    """

    observed_sharpe: float
    permutation_sharpes: list[float]
    p_value: float
    n_permutations: int
    passes: bool
    significance: float


def _compute_sharpe(returns: np.ndarray) -> float:
    """Annualized Sharpe with sqrt(252) scaling.

    If std=0 and mean>0: returns large positive (perfect positive signal).
    If std=0 and mean<0: returns large negative.
    If std=0 and mean=0: returns 0.
    """
    std = np.std(returns, ddof=1) if len(returns) > 1 else 0.0
    mean = float(np.mean(returns))
    if std == 0:
        if mean > 0:
            return 1e9
        elif mean < 0:
            return -1e9
        return 0.0
    return float(mean / std * np.sqrt(252))


def monte_carlo_permutation_test(
    event_returns: pd.Series,
    n_permutations: int = 1000,
    significance: float = 0.05,
    random_seed: int = 42,
) -> McptResult:
    """Monte Carlo Permutation Test (Masters MCPT).

    Tests H0: signal has no predictive value by shuffling event-level
    returns and comparing to the observed Sharpe ratio.

    Parameters
    ----------
    event_returns : pd.Series
        One return per event, indexed by event_id
    n_permutations : int
        Number of shuffle permutations (default 1000)
    significance : float
        p-value threshold for rejection (default 0.05)
    random_seed : int
        Random seed for reproducibility

    Returns
    -------
    McptResult
    """
    rng = np.random.default_rng(random_seed)
    returns_arr = event_returns.values.astype(float)
    observed_sharpe = _compute_sharpe(returns_arr)

    permutation_sharpes = []
    for _ in range(n_permutations):
        # Sign permutation: randomly flip signs of returns.
        # This tests whether the positive mean is statistically significant.
        # Unlike shuffle permutation, sign flips change the mean (and thus Sharpe),
        # allowing meaningful null-distribution separation for high-drift series.
        signs = rng.choice([-1.0, 1.0], size=len(returns_arr))
        permutation_sharpes.append(_compute_sharpe(returns_arr * signs))

    perm_arr = np.array(permutation_sharpes)
    # Spec: p_value = fraction of permutations where perm_sharpe >= observed_sharpe
    p_value = float(np.mean(perm_arr >= observed_sharpe))
    passes = p_value < significance

    return McptResult(
        observed_sharpe=observed_sharpe,
        permutation_sharpes=permutation_sharpes,
        p_value=p_value,
        n_permutations=n_permutations,
        passes=passes,
        significance=significance,
    )


# ---------------------------------------------------------------------------
# Tool 4: Parameter Chooser
# ---------------------------------------------------------------------------


@dataclass
class ChooserResult:
    """Result of parameter selection (Masters CHOOSER).

    Attributes
    ----------
    best_params : dict
        Parameters of the variant with highest PSR
    best_psr : float
        PSR of the best variant
    param_scores : pd.DataFrame
        Columns: params_repr, psr, passes, sharpe
    method : str
        Selection method used
    n_variants : int
        Number of variants evaluated
    """

    best_params: dict
    best_psr: float
    param_scores: pd.DataFrame
    method: str
    n_variants: int


def parameter_chooser(
    variants: list[dict],
    n_strategies_tested: int | None = None,
) -> ChooserResult:
    """Parameter Chooser (Masters CHOOSER).

    Evaluates multiple parameter variants using Deflated Sharpe Ratio
    and selects the variant with the highest PSR.

    Parameters
    ----------
    variants : list[dict]
        Each dict: {"params": {...}, "returns": pd.Series}
    n_strategies_tested : int, optional
        Passed to deflated_sharpe() for selection bias adjustment.
        Defaults to len(variants).

    Returns
    -------
    ChooserResult
    """
    from afml.metrics import deflated_sharpe

    n = n_strategies_tested if n_strategies_tested is not None else len(variants)

    rows = []
    for v in variants:
        result = deflated_sharpe(v["returns"], n_strategies_tested=n)
        rows.append(
            {
                "params_repr": str(v["params"]),
                "psr": result.psr,
                "passes": result.passes_threshold,
                "sharpe": result.sharpe,
                "_params": v["params"],
            }
        )

    best_row = max(rows, key=lambda r: r["psr"])
    best_params = best_row["_params"]
    best_psr = best_row["psr"]

    param_scores = pd.DataFrame(
        [
            {
                "params_repr": r["params_repr"],
                "psr": r["psr"],
                "passes": r["passes"],
                "sharpe": r["sharpe"],
            }
            for r in rows
        ]
    )

    return ChooserResult(
        best_params=best_params,
        best_psr=best_psr,
        param_scores=param_scores,
        method="highest_psr",
        n_variants=len(variants),
    )


# ---------------------------------------------------------------------------
# Tool 5: CSCV Symmetric
# ---------------------------------------------------------------------------


@dataclass
class CscvResult:
    """Result of Combinatorial Symmetric Cross-Validation (Masters CSCV extension).

    Attributes
    ----------
    pbo : float
        Fraction of paths with negative total return (standard CPCV PBO)
    pbo_rank : float
        Masters extension: fraction of paths where IS rank > OOS rank
    n_paths : int
        Number of CV paths evaluated
    path_sharpes_oos : list[float]
        OOS Sharpe ratio for each path
    path_sharpes_is : list[float]
        IS Sharpe ratio for each path's training set
    passes : bool
        True if pbo_rank < pbo_rank_threshold
    pbo_rank_threshold : float
        Threshold for pbo_rank pass/fail
    """

    pbo: float
    pbo_rank: float
    n_paths: int
    path_sharpes_oos: list[float]
    path_sharpes_is: list[float]
    passes: bool
    pbo_rank_threshold: float


def cscv_symmetric(
    returns: pd.Series,
    features: pd.DataFrame | None = None,
    n_splits: int = 6,
    n_test_groups: int = 2,
    embargo_pct: float = 0.01,
    pbo_rank_threshold: float = 0.5,
) -> CscvResult:
    """Combinatorial Symmetric Cross-Validation (Masters CSCV extension).

    Wraps CombPurgedKFold.split() and adds IS vs OOS Sharpe rank comparison.

    Parameters
    ----------
    returns : pd.Series
        DatetimeIndex, one return per event date
    features : pd.DataFrame, optional
        Feature matrix. If None, returns is reshaped as single feature.
    n_splits : int
        Number of CPCV groups (default 6)
    n_test_groups : int
        Groups per test combination (default 2)
    embargo_pct : float
        Embargo fraction (default 0.01)
    pbo_rank_threshold : float
        pbo_rank must be below this to pass (default 0.5)

    Returns
    -------
    CscvResult
    """
    from afml.cpcv import CombPurgedKFold

    if features is None:
        X = returns.to_frame(name="returns")
    else:
        X = features

    cpcv = CombPurgedKFold(
        n_splits=n_splits, n_test_groups=n_test_groups, embargo_pct=embargo_pct
    )

    is_sharpes: list[float] = []
    oos_sharpes: list[float] = []

    for train_idx, test_idx in cpcv.split(X):
        is_ret = returns.iloc[train_idx].values.astype(float)
        oos_ret = returns.iloc[test_idx].values.astype(float)
        is_sharpes.append(_compute_sharpe(is_ret))
        oos_sharpes.append(_compute_sharpe(oos_ret))

    n_paths = len(is_sharpes)

    if n_paths == 0:
        return CscvResult(
            pbo=1.0,
            pbo_rank=1.0,
            n_paths=0,
            path_sharpes_oos=[],
            path_sharpes_is=[],
            passes=False,
            pbo_rank_threshold=pbo_rank_threshold,
        )

    # PBO: fraction of paths with negative OOS total return
    # Approximate from OOS Sharpe sign (negative Sharpe ~ negative return)
    oos_arr = np.array(oos_sharpes)
    pbo = float(np.mean(oos_arr < 0))

    # pbo_rank: fraction of paths where IS rank (descending) > OOS rank (descending)
    is_arr = np.array(is_sharpes)
    is_ranks = pd.Series(is_arr).rank(ascending=False).values
    oos_ranks = pd.Series(oos_arr).rank(ascending=False).values
    pbo_rank = float(np.mean(is_ranks > oos_ranks))

    passes = pbo_rank < pbo_rank_threshold

    return CscvResult(
        pbo=pbo,
        pbo_rank=pbo_rank,
        n_paths=n_paths,
        path_sharpes_oos=oos_sharpes,
        path_sharpes_is=is_sharpes,
        passes=passes,
        pbo_rank_threshold=pbo_rank_threshold,
    )
