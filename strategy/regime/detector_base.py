"""Abstract base class for market regime detectors.

Regime integer encoding:
    0 = bear   (low returns, high vol)
    1 = sideways (neutral returns, moderate vol)
    2 = bull   (high returns, low vol)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

import pandas as pd


class RegimeDetector(ABC):
    """Abstract base for market regime classifiers.

    Concrete subclasses must implement fit() and predict().
    """

    REGIME_NAMES = {0: "bear", 1: "sideways", 2: "bull"}

    @abstractmethod
    def fit(self, returns: pd.Series, vix: pd.Series | None = None) -> "RegimeDetector":
        """Train the detector on historical data.

        Parameters
        ----------
        returns:
            Daily market returns (e.g. SPY), indexed by date.
        vix:
            Daily VIX closing levels, indexed by date. Optional for detectors
            that don't require it.

        Returns
        -------
        self
        """
        ...

    @abstractmethod
    def predict(self, as_of: date) -> int:
        """Return the regime integer for a given date.

        Parameters
        ----------
        as_of:
            The date to classify. Must be on or after the first fitted date.

        Returns
        -------
        int
            0 = bear, 1 = sideways, 2 = bull.
            Returns 1 (sideways) if no data is available for the date.
        """
        ...

    def confidence(self, as_of: date) -> float:
        """Return a confidence score in [0, 1] for the predicted regime.

        Default implementation returns 1.0 (deterministic). Override for
        probabilistic detectors.

        Parameters
        ----------
        as_of:
            The date to evaluate.

        Returns
        -------
        float
            Confidence in the predicted regime label.
        """
        return 1.0

    def predict_series(self, index: pd.DatetimeIndex | pd.Index) -> pd.Series:
        """Vectorised predict over an index of dates.

        Parameters
        ----------
        index:
            Sequence of dates or Timestamps to classify.

        Returns
        -------
        pd.Series
            Integer regime labels (0/1/2) indexed by the input index.
        """
        labels = [self.predict(d.date() if hasattr(d, "date") else d) for d in index]
        return pd.Series(labels, index=index, name="regime")

    def regime_name(self, regime: int) -> str:
        """Return the human-readable name for a regime integer."""
        return self.REGIME_NAMES.get(regime, "unknown")
