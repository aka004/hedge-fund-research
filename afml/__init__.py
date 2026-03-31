"""
AFML - Advances in Financial Machine Learning

Implementation of key techniques from López de Prado's AFML book.
All agents MUST use these functions for the specified operations.

Reference: López de Prado, M. (2018). Advances in Financial Machine Learning. Wiley.
"""

from .bet_sizing import KellyResult, discrete_kelly, kelly_criterion
from .bootstrap import average_uniqueness, sequential_bootstrap
from .checks import (
    AdfResult,
    RollingStationarityResult,
    rolling_statn,
    stationarity_check,
)
from .cpcv import CombPurgedKFold, CPCVResult
from .cusum import CUSUMResult, cusum_filter
from .cv import PurgedKFold, purged_kfold
from .diagnostics import (
    ChooserResult,
    CscvResult,
    EntropyDiagnosticResult,
    McptResult,
    cscv_symmetric,
    entropy_diagnostic,
    monte_carlo_permutation_test,
    parameter_chooser,
)
from .labels import TripleBarrierLabels, triple_barrier
from .meta_labeling import MetaLabelResult, meta_label_fit, meta_label_predict
from .metrics import deflated_sharpe, expected_max_sharpe, psr
from .portfolio import hierarchical_risk_parity, hrp
from .regime import Regime, RegimeSignal, regime_200ma
from .regime_composite import RegimeState, compute_regime_multiplier
from .weights import sample_uniqueness

__all__ = [
    # Cross-Validation (Ch 7)
    "purged_kfold",
    "PurgedKFold",
    # Combinatorial Purged CV (Ch 12)
    "CombPurgedKFold",
    "CPCVResult",
    # Labeling (Ch 3)
    "triple_barrier",
    "TripleBarrierLabels",
    # Sample Weights (Ch 4)
    "sample_uniqueness",
    # Sequential Bootstrap (Ch 4)
    "sequential_bootstrap",
    "average_uniqueness",
    # Bet Sizing / Kelly (Ch 10)
    "kelly_criterion",
    "discrete_kelly",
    "KellyResult",
    # CUSUM Filter (Ch 2)
    "cusum_filter",
    "CUSUMResult",
    # Meta-Labeling (Ch 3)
    "meta_label_fit",
    "meta_label_predict",
    "MetaLabelResult",
    # Metrics (Ch 14)
    "deflated_sharpe",
    "expected_max_sharpe",
    "psr",
    # Portfolio (Ch 16)
    "hrp",
    "hierarchical_risk_parity",
    # Regime
    "regime_200ma",
    "RegimeSignal",
    "Regime",
    # Regime Composite (Phase 2)
    "compute_regime_multiplier",
    "RegimeState",
    # Checks
    "stationarity_check",
    "AdfResult",
    "rolling_statn",
    "RollingStationarityResult",
    # Diagnostics (Masters)
    "entropy_diagnostic",
    "EntropyDiagnosticResult",
    "monte_carlo_permutation_test",
    "McptResult",
    "parameter_chooser",
    "ChooserResult",
    "cscv_symmetric",
    "CscvResult",
]

__version__ = "0.1.0"
