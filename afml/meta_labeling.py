"""
Meta-Labeling with Random Forest (AFML Chapter 3 / Stage 9)

A primary model generates directional signals (+1/-1). Meta-labeling
asks: "Given this signal, what is the probability it's correct?"

This separates signal generation (side) from bet sizing (confidence).
Use the meta-label probability to scale Kelly position sizes.

DO NOT use raw signal confidence. Train a meta-label model.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier

from .cv import PurgedKFold
from .labels import TripleBarrierLabels


@dataclass
class MetaLabelResult:
    """
    Result of meta-label model training.

    Attributes
    ----------
    probabilities : pd.Series
        P(primary model correct) per trade, 0-1
    model : object
        Fitted RandomForest model
    cv_scores : list[float]
        Per-fold accuracy scores
    feature_names : list[str]
        Feature names used in training
    """

    probabilities: pd.Series
    model: object
    cv_scores: list[float]
    feature_names: list[str]


def meta_label_fit(
    primary_signals: pd.Series,
    labels: TripleBarrierLabels,
    features: pd.DataFrame,
    labels_end_times: pd.Series,
    n_splits: int = 5,
    embargo_pct: float = 0.01,
) -> MetaLabelResult:
    """
    Train RF meta-label model using Purged K-Fold.

    Binary target: did primary signal direction match triple-barrier outcome?

    Parameters
    ----------
    primary_signals : pd.Series
        Directional signals (+1 or -1) from primary model
    labels : TripleBarrierLabels
        Actual outcomes from triple_barrier()
    features : pd.DataFrame
        Feature matrix for meta-label model
    labels_end_times : pd.Series
        End times for purged cross-validation
    n_splits : int
        Number of CV folds (default 5)
    embargo_pct : float
        Embargo fraction (default 0.01)

    Returns
    -------
    MetaLabelResult
        Trained model with OOS probabilities and CV scores

    Example
    -------
    >>> result = meta_label_fit(signals, labels, features, labels.exit_times)
    >>> sized_positions = signals * result.probabilities  # Scale by confidence
    """
    # Align indices across all inputs
    common_idx = (
        primary_signals.index.intersection(labels.labels.index)
        .intersection(features.index)
        .intersection(labels_end_times.index)
    )

    signals = primary_signals.loc[common_idx]
    actual_labels = labels.labels.loc[common_idx]
    X = features.loc[common_idx]
    end_times = labels_end_times.loc[common_idx]

    # Binary target: did signal direction match actual outcome?
    # Correct if both positive or both negative
    binary_correct = ((signals * actual_labels) > 0).astype(int)

    # Purged K-Fold CV for OOS predictions
    cv = PurgedKFold(n_splits=n_splits, embargo_pct=embargo_pct)
    oos_probs = pd.Series(np.nan, index=common_idx, dtype=float)
    cv_scores = []

    for train_idx, test_idx in cv.split(X, labels_end_times=end_times):
        X_train = X.iloc[train_idx]
        y_train = binary_correct.iloc[train_idx]
        X_test = X.iloc[test_idx]
        y_test = binary_correct.iloc[test_idx]

        rf = RandomForestClassifier(
            n_estimators=100,
            max_depth=5,
            random_state=42,
            n_jobs=-1,
        )
        rf.fit(X_train, y_train)

        # Predict probability of correct signal
        probs = rf.predict_proba(X_test)
        # Handle case where only one class is present in training
        if probs.shape[1] == 2:
            oos_probs.iloc[test_idx] = probs[:, 1]
        else:
            oos_probs.iloc[test_idx] = float(rf.classes_[0])

        # Score on test fold
        score = rf.score(X_test, y_test)
        cv_scores.append(score)

    # Final model: refit on all data
    final_rf = RandomForestClassifier(
        n_estimators=100,
        max_depth=5,
        random_state=42,
        n_jobs=-1,
    )
    final_rf.fit(X, binary_correct)

    # Fill any remaining NaN probabilities with final model
    nan_mask = oos_probs.isna()
    if nan_mask.any():
        fill_probs = final_rf.predict_proba(X.loc[nan_mask])
        if fill_probs.shape[1] == 2:
            oos_probs.loc[nan_mask] = fill_probs[:, 1]
        else:
            oos_probs.loc[nan_mask] = float(final_rf.classes_[0])

    return MetaLabelResult(
        probabilities=oos_probs,
        model=final_rf,
        cv_scores=cv_scores,
        feature_names=list(X.columns),
    )


def meta_label_predict(
    model: object,
    features: pd.DataFrame,
) -> pd.Series:
    """
    Predict P(correct) for new signals using trained meta-label model.

    Parameters
    ----------
    model : object
        Fitted RandomForest from meta_label_fit()
    features : pd.DataFrame
        Feature matrix for prediction

    Returns
    -------
    pd.Series
        Probability that primary signal is correct (0-1)
    """
    probs = model.predict_proba(features)
    if probs.shape[1] == 2:
        return pd.Series(probs[:, 1], index=features.index)
    return pd.Series(probs[:, 0], index=features.index)
