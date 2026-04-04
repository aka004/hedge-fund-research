"""Regime detection module.

Provides abstract base and concrete implementations for market regime classification.

Regimes:
    0 = bear
    1 = sideways
    2 = bull
"""

from strategy.regime.detector_base import RegimeDetector
from strategy.regime.hmm_detector import HMMRegimeDetector
from strategy.regime.vix_detector import VIXRegimeDetector

__all__ = ["RegimeDetector", "HMMRegimeDetector", "VIXRegimeDetector"]
