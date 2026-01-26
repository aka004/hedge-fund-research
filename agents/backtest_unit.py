"""
Backtest Unit Agent

Validates alpha signals using purged k-fold cross-validation.
Clearance: Validation

MUST use:
- afml.purged_kfold() for cross-validation (NOT sklearn KFold)
"""

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from agents.base import Agent, AgentConfig, Clearance
from agents.events import Event, EventBus, EventType

# AFML imports - MANDATORY
from afml import purged_kfold

logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    """Results from backtesting an alpha strategy."""
    
    n_folds: int
    fold_returns: list[float]
    avg_return: float
    std_return: float
    sharpe_estimate: float  # Raw, not PSR
    win_rate: float
    n_trades: int
    passed: bool
    reason: str


class BacktestUnit(Agent):
    """
    Validates alpha signals using purged k-fold cross-validation.
    
    Uses AFML techniques:
    - purged_kfold() for proper CV without information leakage
    
    Clearance: Validation (can read data/signals, run validation)
    """
    
    def __init__(
        self,
        event_bus: EventBus,
        config: AgentConfig | None = None,
        data_path: Path | None = None,
        n_folds: int = 5,
        embargo_pct: float = 0.01,
        min_sharpe: float = 0.5,
    ) -> None:
        super().__init__(event_bus, config)
        
        # Data path for Parquet files
        if data_path is None:
            from config import STORAGE_PATH
            data_path = STORAGE_PATH
        self.data_path = Path(data_path)
        
        # CV parameters
        self.n_folds = n_folds
        self.embargo_pct = embargo_pct
        
        # Validation thresholds
        self.min_sharpe = min_sharpe
        
        # Results storage
        self._last_result: BacktestResult | None = None
    
    @property
    def name(self) -> str:
        return "backtest_unit"
    
    @property
    def clearance(self) -> Clearance:
        return Clearance.VALIDATION
    
    def _subscribe_events(self) -> None:
        """Subscribe to alpha.ready events."""
        self.event_bus.subscribe(EventType.ALPHA_READY, self._on_alpha_ready)
    
    def _on_alpha_ready(self, event: Event) -> None:
        """Handle new alpha signals for validation."""
        self.log("Received alpha.ready, starting backtest validation")
        
        signals = event.payload.get("signals", [])
        strategy_config = event.payload.get("strategy_config", {})
        
        if not signals:
            self.log("No signals to validate", level="warning")
            self.emit(EventType.BACKTEST_FAILED, {
                "reason": "no_signals",
                "n_signals": 0,
            })
            return
        
        # Run backtest
        result = self.validate_alpha(signals, strategy_config)
        self._last_result = result
        
        if result.passed:
            self.emit(EventType.BACKTEST_PASSED, {
                "n_folds": result.n_folds,
                "avg_return": result.avg_return,
                "std_return": result.std_return,
                "sharpe_estimate": result.sharpe_estimate,
                "win_rate": result.win_rate,
                "n_trades": result.n_trades,
                "fold_returns": result.fold_returns,
            })
        else:
            self.emit(EventType.BACKTEST_FAILED, {
                "reason": result.reason,
                "n_folds": result.n_folds,
                "avg_return": result.avg_return,
                "sharpe_estimate": result.sharpe_estimate,
            })
    
    def validate_alpha(
        self,
        signals: list[dict],
        strategy_config: dict,
    ) -> BacktestResult:
        """
        Validate alpha signals using purged k-fold CV.
        
        Uses AFML purged_kfold() on the TIME SERIES of all triple-barrier
        labels to properly evaluate out-of-sample performance.
        """
        self.log(f"Validating {len(signals)} signals with {self.n_folds}-fold CV")
        
        # Build combined time series from ALL labels across symbols
        X, y, labels_end_times = self._prepare_labels_timeseries(signals, strategy_config)
        
        if len(X) < self.n_folds * 10:
            return BacktestResult(
                n_folds=0,
                fold_returns=[],
                avg_return=0.0,
                std_return=0.0,
                sharpe_estimate=0.0,
                win_rate=0.0,
                n_trades=0,
                passed=False,
                reason=f"insufficient_data: need {self.n_folds * 10}, have {len(X)}",
            )
        
        self.log(f"Total labels across all symbols: {len(X)}")
        
        # Run purged k-fold cross-validation (AFML) on TIME SERIES
        all_test_returns = []  # Collect ALL individual test returns
        fold_returns = []
        fold_trades = []
        fold_wins = []
        
        for fold_idx, (train_idx, test_idx) in enumerate(
            purged_kfold(
                X,
                y,
                n_splits=self.n_folds,
                embargo_pct=self.embargo_pct,
                labels_end_times=labels_end_times,
            )
        ):
            self.log(f"Fold {fold_idx + 1}/{self.n_folds}: train={len(train_idx)}, test={len(test_idx)}")
            
            # Get test set returns (these are actual triple-barrier returns)
            test_returns = y.iloc[test_idx]
            
            # Collect individual returns for proper Sharpe calculation
            all_test_returns.extend(test_returns.tolist())
            
            fold_return = test_returns.mean()
            fold_returns.append(fold_return)
            fold_trades.append(len(test_idx))
            fold_wins.append((test_returns > 0).sum())
        
        # Calculate aggregate metrics from ALL test returns (not fold means)
        all_test_returns = np.array(all_test_returns)
        total_trades = len(all_test_returns)
        
        if total_trades == 0:
            return BacktestResult(
                n_folds=self.n_folds,
                fold_returns=fold_returns,
                avg_return=0.0,
                std_return=0.0,
                sharpe_estimate=0.0,
                win_rate=0.0,
                n_trades=0,
                passed=False,
                reason="no_test_returns",
            )
        
        avg_return = all_test_returns.mean()
        std_return = all_test_returns.std()
        total_wins = (all_test_returns > 0).sum()
        win_rate = total_wins / total_trades
        
        # Sharpe on individual trade returns
        # Annualize based on avg holding period (assume ~5 days per trade)
        trades_per_year = 252 / 5  # ~50 trades per year per position
        sharpe_estimate = (avg_return / std_return * np.sqrt(trades_per_year)) if std_return > 0 else 0.0
        
        # Check if passes threshold
        passed = sharpe_estimate >= self.min_sharpe
        reason = "" if passed else f"sharpe_below_threshold: {sharpe_estimate:.3f} < {self.min_sharpe}"
        
        result = BacktestResult(
            n_folds=self.n_folds,
            fold_returns=all_test_returns.tolist(),  # Pass ALL returns, not just fold means
            avg_return=avg_return,
            std_return=std_return,
            sharpe_estimate=sharpe_estimate,
            win_rate=win_rate,
            n_trades=total_trades,
            passed=passed,
            reason=reason,
        )
        
        self.log(f"Backtest complete: n_trades={total_trades}, avg_return={avg_return:.4f}, sharpe={sharpe_estimate:.3f}, passed={passed}")
        return result
    
    def _prepare_labels_timeseries(
        self,
        signals: list[dict],
        strategy_config: dict,
    ) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
        """
        Build combined time series from ALL triple-barrier labels.
        
        This extracts the individual labels from each signal (not averages)
        and combines them into a single time series for purged k-fold CV.
        
        Returns:
            X: Feature DataFrame with DatetimeIndex (all labels across symbols)
            y: Returns Series (actual triple-barrier returns)
            labels_end_times: End times for purging
        """
        rows = []
        max_holding = strategy_config.get("max_holding", 10)
        
        for signal in signals:
            symbol = signal.get("symbol", "")
            metadata = signal.get("metadata", {})
            labels_data = metadata.get("labels_data", {})
            
            # Extract individual labels from the signal
            dates = labels_data.get("dates", [])
            returns = labels_data.get("returns", [])
            labels = labels_data.get("labels", [])
            
            if not dates or not returns:
                # Fallback: regenerate labels from price data
                self.log(f"{symbol}: No labels_data, regenerating from prices", level="warning")
                labels_result = self._regenerate_labels(symbol, strategy_config)
                if labels_result is None:
                    continue
                dates, returns, labels = labels_result
            
            # Add each individual label as a row
            for i, (date_str, ret, label) in enumerate(zip(dates, returns, labels)):
                rows.append({
                    "date": date_str,
                    "symbol": symbol,
                    "return": ret,
                    "label": label,
                    "signal_strength": signal.get("signal_strength", 0),
                    "momentum": metadata.get("momentum_12_1", 0),
                })
        
        if not rows:
            return pd.DataFrame(), pd.Series(dtype=float), pd.Series(dtype='datetime64[ns]')
        
        df = pd.DataFrame(rows)
        
        # Parse dates and sort by time
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date")
        df = df.set_index("date")
        
        self.log(f"Built time series: {len(df)} labels from {df.index.min()} to {df.index.max()}")
        
        # Features (for potential ML model, but mainly for CV structure)
        feature_cols = ["signal_strength", "momentum"]
        X = df[feature_cols]
        
        # Labels (actual triple-barrier returns)
        y = df["return"]
        
        # Label end times for purging (entry + max_holding days)
        labels_end_times = pd.Series(
            df.index + pd.Timedelta(days=max_holding),
            index=df.index,
        )
        
        return X, y, labels_end_times
    
    def _regenerate_labels(
        self,
        symbol: str,
        strategy_config: dict,
    ) -> tuple[list, list, list] | None:
        """
        Regenerate triple-barrier labels from price data.
        
        Used as fallback when signals don't include labels_data.
        """
        from afml import triple_barrier
        
        file_path = self.data_path / "prices" / f"{symbol}.parquet"
        if not file_path.exists():
            return None
        
        try:
            df = pd.read_parquet(file_path)
            if "date" in df.columns:
                df["date"] = pd.to_datetime(df["date"])
                df = df.set_index("date")
            
            price_col = "adj_close" if "adj_close" in df.columns else "close"
            prices = df[price_col].sort_index()
            
            labels = triple_barrier(
                prices=prices,
                profit_take=strategy_config.get("profit_take", 2.0),
                stop_loss=strategy_config.get("stop_loss", 2.0),
                max_holding=strategy_config.get("max_holding", 10),
            )
            
            labels_df = labels.to_dataframe()
            return (
                [str(d) for d in labels_df.index],
                labels_df["return"].tolist(),
                labels_df["label"].tolist(),
            )
        except Exception as e:
            self.log(f"Error regenerating labels for {symbol}: {e}", level="warning")
            return None
    
    def _prepare_data(
        self,
        signals: list[dict],
    ) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
        """
        DEPRECATED: Use _prepare_labels_timeseries instead.
        
        Kept for backwards compatibility.
        """
        self.log("WARNING: Using deprecated _prepare_data method", level="warning")
        return self._prepare_labels_timeseries(signals, {})
    
    def _get_forward_returns(self, symbol: str, entry_date: str) -> float:
        """Get forward returns for a symbol from entry date."""
        file_path = self.data_path / "prices" / f"{symbol}.parquet"
        if not file_path.exists():
            return 0.0
        
        try:
            df = pd.read_parquet(file_path)
            if "date" in df.columns:
                df["date"] = pd.to_datetime(df["date"])
                df = df.set_index("date")
            
            entry_dt = pd.to_datetime(entry_date)
            
            # Get prices after entry
            future = df.loc[df.index > entry_dt, "adj_close"]
            if len(future) < 10:
                return 0.0
            
            entry_price = df.loc[df.index <= entry_dt, "adj_close"].iloc[-1]
            exit_price = future.iloc[9]  # 10-day forward
            
            return (exit_price - entry_price) / entry_price
        
        except Exception:
            return 0.0
    
    def get_last_result(self) -> BacktestResult | None:
        """Get the last backtest result."""
        return self._last_result
