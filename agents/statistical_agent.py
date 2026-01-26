"""
Statistical Agent

Validates strategy using Probabilistic Sharpe Ratio (PSR).
Clearance: Validation

MUST use:
- afml.deflated_sharpe() for PSR calculation
- afml.sample_uniqueness() for sample weights

PSR >= 0.95 required to pass (95% confidence).
"""

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from agents.base import Agent, AgentConfig, Clearance
from agents.events import Event, EventBus, EventType

# AFML imports - MANDATORY
from afml import deflated_sharpe, sample_uniqueness

logger = logging.getLogger(__name__)


@dataclass
class StatisticalResult:
    """Results from statistical validation."""
    
    psr: float
    sharpe: float
    passes_threshold: bool
    n_observations: int
    skewness: float
    kurtosis: float
    sample_weights: list[float] | None
    reason: str


class StatisticalAgent(Agent):
    """
    Validates strategies using Probabilistic Sharpe Ratio.
    
    Uses AFML techniques:
    - deflated_sharpe() for PSR calculation
    - sample_uniqueness() for sample weighting
    
    Threshold: PSR >= 0.95 (95% confidence)
    
    Clearance: Validation (can read data/signals, run validation)
    """
    
    PSR_THRESHOLD = 0.95
    
    def __init__(
        self,
        event_bus: EventBus,
        config: AgentConfig | None = None,
        data_path: Path | None = None,
        psr_threshold: float = 0.95,
        n_strategies_tested: int = 1,
    ) -> None:
        super().__init__(event_bus, config)
        
        # Data path for Parquet files
        if data_path is None:
            from config import STORAGE_PATH
            data_path = STORAGE_PATH
        self.data_path = Path(data_path)
        
        # Validation thresholds
        self.psr_threshold = psr_threshold
        self.n_strategies_tested = n_strategies_tested
        
        # Results storage
        self._last_result: StatisticalResult | None = None
        self._backtest_payload: dict | None = None
    
    @property
    def name(self) -> str:
        return "statistical_agent"
    
    @property
    def clearance(self) -> Clearance:
        return Clearance.VALIDATION
    
    def _subscribe_events(self) -> None:
        """Subscribe to backtest.passed events."""
        self.event_bus.subscribe(EventType.BACKTEST_PASSED, self._on_backtest_passed)
    
    def _on_backtest_passed(self, event: Event) -> None:
        """Handle passed backtest for statistical validation."""
        self.log("Received backtest.passed, running PSR validation")
        
        self._backtest_payload = event.payload
        
        # Get returns from backtest
        fold_returns = event.payload.get("fold_returns", [])
        
        if not fold_returns:
            self.log("No fold returns available", level="warning")
            self.emit(EventType.ALPHA_REJECTED, {
                "reason": "no_returns_data",
                "psr": 0.0,
            })
            return
        
        # Run statistical validation
        result = self.validate_statistics(fold_returns)
        self._last_result = result
        
        if result.passes_threshold:
            self.emit(EventType.ALPHA_SUCCESS, {
                "psr": result.psr,
                "sharpe": result.sharpe,
                "n_observations": result.n_observations,
                "skewness": result.skewness,
                "kurtosis": result.kurtosis,
                "backtest_metrics": {
                    "avg_return": event.payload.get("avg_return"),
                    "win_rate": event.payload.get("win_rate"),
                    "n_trades": event.payload.get("n_trades"),
                },
            })
        else:
            self.emit(EventType.ALPHA_REJECTED, {
                "reason": result.reason,
                "psr": result.psr,
                "sharpe": result.sharpe,
                "threshold": self.psr_threshold,
            })
    
    def validate_statistics(
        self,
        returns: list[float] | np.ndarray,
    ) -> StatisticalResult:
        """
        Validate returns using Probabilistic Sharpe Ratio.
        
        Uses AFML deflated_sharpe() which adjusts for:
        - Non-normal returns (skewness, kurtosis)
        - Multiple testing (n_strategies_tested)
        - Small sample size
        
        Returns:
            StatisticalResult with PSR and decision
        """
        returns = np.array(returns)
        
        # Require at least 10 observations for meaningful statistics
        # With proper CV, we should have hundreds/thousands of trade returns
        min_observations = 10
        if len(returns) < min_observations:
            return StatisticalResult(
                psr=0.0,
                sharpe=0.0,
                passes_threshold=False,
                n_observations=len(returns),
                skewness=0.0,
                kurtosis=0.0,
                sample_weights=None,
                reason=f"insufficient_observations: {len(returns)} < {min_observations} required",
            )
        
        self.log(f"Validating {len(returns)} trade returns")
        
        # Calculate PSR using AFML (MANDATORY)
        try:
            sharpe_result = deflated_sharpe(
                returns=returns,
                benchmark_sharpe=0.0,
                n_strategies_tested=self.n_strategies_tested,
                threshold=self.psr_threshold,
            )
            
            psr = sharpe_result.psr
            sharpe = sharpe_result.sharpe
            passes = sharpe_result.passes_threshold
            
            self.log(
                f"PSR Validation: PSR={psr:.3f}, Sharpe={sharpe:.3f}, "
                f"threshold={self.psr_threshold}, passed={passes}"
            )
            
            reason = "" if passes else f"psr_below_threshold: {psr:.3f} < {self.psr_threshold}"
            
            return StatisticalResult(
                psr=psr,
                sharpe=sharpe,
                passes_threshold=passes,
                n_observations=sharpe_result.n_observations,
                skewness=sharpe_result.skewness,
                kurtosis=sharpe_result.kurtosis,
                sample_weights=None,
                reason=reason,
            )
            
        except Exception as e:
            self.log(f"Error in PSR calculation: {e}", level="error")
            return StatisticalResult(
                psr=0.0,
                sharpe=0.0,
                passes_threshold=False,
                n_observations=len(returns),
                skewness=0.0,
                kurtosis=0.0,
                sample_weights=None,
                reason=f"calculation_error: {str(e)}",
            )
    
    def compute_sample_weights(
        self,
        labels_start: pd.Series,
        labels_end: pd.Series,
    ) -> pd.Series:
        """
        Compute sample weights using AFML sample_uniqueness().
        
        Downweights samples that overlap heavily with others.
        """
        return sample_uniqueness(labels_start, labels_end)
    
    def validate_with_weights(
        self,
        returns: np.ndarray,
        labels_start: pd.Series,
        labels_end: pd.Series,
    ) -> StatisticalResult:
        """
        Validate with sample uniqueness weighting.
        
        Applies sample_uniqueness() weights before calculating PSR.
        """
        # Compute sample weights (AFML)
        weights = self.compute_sample_weights(labels_start, labels_end)
        
        # Weight the returns
        weighted_returns = returns * weights.values[:len(returns)]
        
        # Run standard validation
        result = self.validate_statistics(weighted_returns)
        result.sample_weights = weights.tolist()
        
        return result
    
    def get_last_result(self) -> StatisticalResult | None:
        """Get the last validation result."""
        return self._last_result
