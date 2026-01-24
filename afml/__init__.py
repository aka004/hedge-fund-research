"""
AFML - Advances in Financial Machine Learning

Implementation of key techniques from López de Prado's AFML book.
All agents MUST use these functions for the specified operations.

Reference: López de Prado, M. (2018). Advances in Financial Machine Learning. Wiley.
"""

from .checks import AdfResult, stationarity_check
from .cv import PurgedKFold, purged_kfold
from .labels import TripleBarrierLabels, triple_barrier
from .metrics import deflated_sharpe, psr
from .portfolio import hierarchical_risk_parity, hrp
from .regime import Regime, RegimeSignal, regime_200ma
from .weights import sample_uniqueness

__all__ = [
    # Cross-Validation (Ch 7)
    "purged_kfold",
    "PurgedKFold",
    # Labeling (Ch 3)
    "triple_barrier",
    "TripleBarrierLabels",
    # Sample Weights (Ch 4)
    "sample_uniqueness",
    # Metrics (Ch 14)
    "deflated_sharpe",
    "psr",
    # Portfolio (Ch 16)
    "hrp",
    "hierarchical_risk_parity",
    # Regime
    "regime_200ma",
    "RegimeSignal",
    "Regime",
    # Checks
    "stationarity_check",
    "AdfResult",
]

__version__ = "0.1.0"
