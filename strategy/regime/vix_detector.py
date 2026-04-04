"""VIX-threshold regime detector.

Classifies each day by its VIX closing level:
    VIX < 18          → bull    (2)
    18 ≤ VIX < 28     → sideways (1)
    VIX ≥ 28          → bear    (0)

Thresholds are consistent with common practitioner usage and match the
long-run VIX distribution (median ≈ 18, 75th pctile ≈ 24, crisis ≥ 30).
"""

from __future__ import annotations

import logging
from datetime import date

import pandas as pd

from strategy.regime.detector_base import RegimeDetector

logger = logging.getLogger(__name__)


class VIXRegimeDetector(RegimeDetector):
    """Threshold-based regime detector using VIX closing levels.

    Parameters
    ----------
    bull_threshold:
        VIX below this level is classified as bull (default 18).
    bear_threshold:
        VIX at or above this level is classified as bear (default 28).
    """

    def __init__(
        self,
        bull_threshold: float = 18.0,
        bear_threshold: float = 28.0,
    ) -> None:
        self.bull_threshold = bull_threshold
        self.bear_threshold = bear_threshold
        self._vix: pd.Series | None = None

    def fit(self, returns: pd.Series, vix: pd.Series | None = None) -> "VIXRegimeDetector":
        """Store VIX series for lookups. Returns is ignored (not used here).

        Parameters
        ----------
        returns:
            Not used by this detector; accepted for API compatibility.
        vix:
            Daily VIX closing levels indexed by date. Required.
        """
        if vix is None or vix.empty:
            raise ValueError("VIXRegimeDetector requires a non-empty vix series")
        # Normalise index to plain date objects
        if isinstance(vix.index, pd.DatetimeIndex):
            vix = vix.copy()
            vix.index = vix.index.date
        self._vix = vix.dropna().sort_index()
        logger.info(
            f"VIXRegimeDetector fitted on {len(self._vix)} days "
            f"({self._vix.index[0]} → {self._vix.index[-1]})"
        )
        return self

    def predict(self, as_of: date) -> int:
        """Classify a single date by its VIX level.

        Uses exact date lookup; falls back to nearest prior date if the exact
        date is missing (e.g. holidays, weekends).
        """
        if self._vix is None:
            raise RuntimeError("Call fit() before predict()")

        # Convert Timestamp to date if needed
        if hasattr(as_of, "date"):
            as_of = as_of.date()

        idx = self._vix.index
        if as_of in idx:
            vix_val = self._vix[as_of]
        else:
            prior = [d for d in idx if d <= as_of]
            if not prior:
                logger.debug(f"No VIX data on or before {as_of} — defaulting to sideways")
                return 1
            vix_val = self._vix[prior[-1]]

        if vix_val < self.bull_threshold:
            return 2
        if vix_val >= self.bear_threshold:
            return 0
        return 1

    def confidence(self, as_of: date) -> float:
        """VIX detector is deterministic — always 1.0."""
        return 1.0
