"""
Momentum Researcher Agent

Generates alpha signals using AFML techniques.
Clearance: Research

MUST use:
- afml.triple_barrier() for labeling
- afml.regime_200ma() for regime context
"""

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from agents.base import Agent, AgentConfig, Clearance
from agents.events import Event, EventBus, EventType

# AFML imports - MANDATORY
from afml import triple_barrier, regime_200ma, Regime

logger = logging.getLogger(__name__)


@dataclass
class AlphaSignal:
    """Represents a generated alpha signal."""
    
    symbol: str
    entry_date: date
    signal_strength: float  # -1 to 1
    regime: str
    labels: object  # TripleBarrierLabels
    metadata: dict


@dataclass
class AlphaStrategy:
    """Configuration for an alpha strategy."""
    
    name: str
    lookback_months: int = 12
    skip_months: int = 1
    profit_take: float = 2.0
    stop_loss: float = 2.0
    max_holding: int = 10
    min_signals: int = 5
    regime_filter: bool = True  # Only trade in bull regime


class MomentumResearcher(Agent):
    """
    Generates alpha signals using momentum strategies.
    
    Uses AFML techniques:
    - triple_barrier() for trade labeling
    - regime_200ma() for market regime detection
    
    Clearance: Research (can read data, compute signals, propose alphas)
    """
    
    def __init__(
        self,
        event_bus: EventBus,
        config: AgentConfig | None = None,
        data_path: Path | None = None,
        strategy: AlphaStrategy | None = None,
    ) -> None:
        super().__init__(event_bus, config)
        
        # Data path for Parquet files
        if data_path is None:
            from config import STORAGE_PATH
            data_path = STORAGE_PATH
        self.data_path = Path(data_path)
        
        # Strategy configuration
        self.strategy = strategy or AlphaStrategy(name="momentum_12_1")
        
        # State
        self._signals: list[AlphaSignal] = []
        self._iteration: int = 0
        self._max_iterations: int = 3  # Max rejection retries
    
    @property
    def name(self) -> str:
        return "momentum_researcher"
    
    @property
    def clearance(self) -> Clearance:
        return Clearance.RESEARCH
    
    def _subscribe_events(self) -> None:
        """Subscribe to events that trigger research."""
        # Start workflow when system starts
        self.event_bus.subscribe(EventType.SYSTEM_START, self._on_system_start)
        # Retry on rejection
        self.event_bus.subscribe(EventType.ALPHA_REJECTED, self._on_alpha_rejected)
        # Continue when data becomes available
        self.event_bus.subscribe(EventType.DATA_AVAILABLE, self._on_data_available)
    
    def _on_system_start(self, event: Event) -> None:
        """Start alpha generation when system starts."""
        self.log("System started, beginning alpha generation")
        self.generate_alpha()
    
    def _on_alpha_rejected(self, event: Event) -> None:
        """Handle alpha rejection - adjust and retry."""
        self._iteration += 1
        
        if self._iteration >= self._max_iterations:
            self.log(f"Max iterations ({self._max_iterations}) reached, stopping")
            self.emit(EventType.WORKFLOW_COMPLETE, {
                "status": "failed",
                "reason": "max_iterations_reached",
                "iterations": self._iteration,
            })
            return
        
        # Adjust strategy based on feedback
        rejection_reason = event.payload.get("reason", "unknown")
        self._adjust_strategy(rejection_reason)
        
        # Retry
        self.log(f"Iteration {self._iteration}: Adjusting strategy and retrying")
        self.generate_alpha()
    
    def _on_data_available(self, event: Event) -> None:
        """Continue when requested data becomes available."""
        self.log("Data available, resuming alpha generation")
        self.generate_alpha()
    
    def _adjust_strategy(self, reason: str) -> None:
        """Adjust strategy parameters based on rejection reason."""
        if "psr" in reason.lower() or "sharpe" in reason.lower():
            # Tighten risk parameters
            self.strategy.stop_loss = max(1.0, self.strategy.stop_loss - 0.5)
            self.strategy.max_holding = max(5, self.strategy.max_holding - 2)
            self.log(f"Adjusted: stop_loss={self.strategy.stop_loss}, max_holding={self.strategy.max_holding}")
        
        elif "sample" in reason.lower() or "data" in reason.lower():
            # Increase minimum signals
            self.strategy.min_signals = max(3, self.strategy.min_signals - 1)
            self.log(f"Adjusted: min_signals={self.strategy.min_signals}")
    
    def generate_alpha(self, symbols: list[str] | None = None) -> None:
        """
        Generate alpha signals for given symbols.
        
        Uses AFML techniques:
        1. regime_200ma() to detect market regime
        2. triple_barrier() to label trades
        """
        # Default test symbols
        if symbols is None:
            symbols = self._get_available_symbols()
        
        if not symbols:
            self.log("No symbols available, requesting data", level="warning")
            self.request_data({
                "type": "historical_prices",
                "symbols": ["AAPL", "MSFT", "GOOGL", "AMZN", "META"],
                "years": 7,
            })
            return
        
        self.log(f"Generating alpha for {len(symbols)} symbols")
        self._signals = []
        
        for symbol in symbols:
            try:
                signal = self._process_symbol(symbol)
                if signal:
                    self._signals.append(signal)
            except Exception as e:
                self.log(f"Error processing {symbol}: {e}", level="warning")
                continue
        
        if len(self._signals) < self.strategy.min_signals:
            self.log(f"Only {len(self._signals)} signals, need {self.strategy.min_signals}", level="warning")
            self.request_data({
                "type": "historical_prices",
                "reason": "insufficient_signals",
                "current_count": len(self._signals),
                "required_count": self.strategy.min_signals,
            })
            return
        
        # Emit alpha.ready event
        self.emit(EventType.ALPHA_READY, {
            "strategy_name": self.strategy.name,
            "iteration": self._iteration,
            "n_signals": len(self._signals),
            "signals": [self._signal_to_dict(s) for s in self._signals],
            "strategy_config": {
                "lookback_months": self.strategy.lookback_months,
                "skip_months": self.strategy.skip_months,
                "profit_take": self.strategy.profit_take,
                "stop_loss": self.strategy.stop_loss,
                "max_holding": self.strategy.max_holding,
                "regime_filter": self.strategy.regime_filter,
            },
        })
    
    def _get_available_symbols(self) -> list[str]:
        """Get list of symbols with available data."""
        prices_dir = self.data_path / "prices"
        if not prices_dir.exists():
            return []
        
        symbols = []
        for f in prices_dir.glob("*.parquet"):
            symbols.append(f.stem)
        
        return symbols  # Use all available symbols
    
    def _process_symbol(self, symbol: str) -> AlphaSignal | None:
        """
        Process a single symbol to generate an alpha signal.
        
        Uses AFML:
        - regime_200ma() for regime detection
        - triple_barrier() for trade labeling
        """
        # Load price data
        prices = self._load_prices(symbol)
        if prices is None or len(prices) < 252:  # Need at least 1 year
            return None
        
        # Check regime using AFML
        regime_signal = regime_200ma(prices, ma_period=200)
        current_regime = regime_signal.current_regime
        
        # Apply regime filter if enabled
        if self.strategy.regime_filter and current_regime == Regime.BEAR:
            self.log(f"{symbol}: Skipping due to bear regime", level="debug")
            return None
        
        # Generate labels using triple-barrier (AFML)
        labels = triple_barrier(
            prices=prices,
            profit_take=self.strategy.profit_take,
            stop_loss=self.strategy.stop_loss,
            max_holding=self.strategy.max_holding,
        )
        
        # Calculate signal strength based on label distribution
        if len(labels.labels) == 0:
            return None
        
        win_rate = (labels.labels == 1).mean()
        signal_strength = (win_rate - 0.5) * 2  # Scale to -1 to 1
        
        # Calculate momentum (12-1)
        momentum = self._calculate_momentum(prices)
        
        # Convert labels to serializable format for passing to backtest
        # Keep ALL individual labels, not just averages
        labels_df = labels.to_dataframe()
        labels_data = {
            "dates": [str(d) for d in labels_df.index],
            "labels": labels_df["label"].tolist(),
            "returns": labels_df["return"].tolist(),
            "exit_types": labels_df["exit_type"].tolist(),
        }
        
        return AlphaSignal(
            symbol=symbol,
            entry_date=prices.index[-1].date() if hasattr(prices.index[-1], 'date') else prices.index[-1],
            signal_strength=signal_strength,
            regime=current_regime.value,
            labels=labels,
            metadata={
                "momentum_12_1": momentum,
                "win_rate": win_rate,
                "n_labels": len(labels.labels),
                "regime_days": regime_signal.days_in_regime,
                "labels_data": labels_data,  # Pass ALL labels for proper CV
            },
        )
    
    def _load_prices(self, symbol: str) -> pd.Series | None:
        """Load adjusted close prices for a symbol."""
        file_path = self.data_path / "prices" / f"{symbol}.parquet"
        if not file_path.exists():
            return None
        
        try:
            df = pd.read_parquet(file_path)
            
            # Handle different column naming
            price_col = "adj_close" if "adj_close" in df.columns else "close"
            if price_col not in df.columns:
                return None
            
            # Ensure date index
            if "date" in df.columns:
                df["date"] = pd.to_datetime(df["date"])
                df = df.set_index("date")
            
            prices = df[price_col].sort_index()
            
            # Check for zeros (missing data warning from CLAUDE.md)
            zero_count = (prices == 0).sum()
            if zero_count > 0:
                self.log(f"{symbol}: {zero_count} zero values detected (possible missing data)", level="warning")
                prices = prices.replace(0, np.nan).dropna()
            
            return prices
        
        except Exception as e:
            self.log(f"Error loading {symbol}: {e}", level="warning")
            return None
    
    def _calculate_momentum(self, prices: pd.Series) -> float:
        """Calculate 12-1 month momentum."""
        if len(prices) < 252:  # Need ~1 year of data
            return 0.0
        
        # Skip most recent month, use previous 11 months
        skip_days = 21  # ~1 month
        lookback_days = 252  # ~12 months
        
        recent_price = prices.iloc[-(skip_days + 1)]
        old_price = prices.iloc[-(lookback_days + 1)]
        
        if old_price == 0:
            return 0.0
        
        return (recent_price - old_price) / old_price
    
    def _signal_to_dict(self, signal: AlphaSignal) -> dict:
        """Convert signal to dictionary for event payload."""
        return {
            "symbol": signal.symbol,
            "entry_date": str(signal.entry_date),
            "signal_strength": signal.signal_strength,
            "regime": signal.regime,
            "metadata": signal.metadata,
        }
    
    def get_signals(self) -> list[AlphaSignal]:
        """Get current signals."""
        return self._signals
    
    def test_data_availability(self, symbols: list[str] | None = None) -> dict:
        """
        Test if required data is available for alpha generation.
        
        Returns dict with:
        - all_available: bool
        - symbols_tested: int
        - symbols_ok: int
        - symbols_failed: list
        - issues: list of problems found
        """
        from datetime import date, timedelta
        from data.providers.yahoo import YahooFinanceProvider
        from afml import triple_barrier, regime_200ma
        
        # Use provided symbols or get from cache
        if symbols is None:
            symbols = self._get_available_symbols()
        
        if not symbols:
            return {
                "all_available": False,
                "symbols_tested": 0,
                "symbols_ok": 0,
                "symbols_failed": [],
                "issues": ["No symbols to test"],
            }
        
        provider = YahooFinanceProvider()
        end_date = date.today() - timedelta(days=1)
        start_date = end_date - timedelta(days=365)  # 1 year
        
        symbols_ok = []
        symbols_failed = []
        issues = []
        
        for symbol in symbols:
            try:
                # Try to fetch data
                df = provider.get_historical_prices(symbol, start_date, end_date)
                
                if df is None or len(df) == 0:
                    symbols_failed.append(symbol)
                    issues.append(f"{symbol}: No data returned")
                    continue
                
                # Check for required columns
                required = ["date", "adj_close"]
                missing = [c for c in required if c not in df.columns]
                if missing:
                    symbols_failed.append(symbol)
                    issues.append(f"{symbol}: Missing columns {missing}")
                    continue
                
                # Check for zeros
                zeros = (df["adj_close"] == 0).sum()
                if zeros > 0:
                    issues.append(f"{symbol}: {zeros} zero values (possible missing data)")
                
                # Test AFML functions
                prices = pd.Series(df["adj_close"].values, index=pd.to_datetime(df["date"]))
                
                # Test triple_barrier
                labels = triple_barrier(prices, max_holding=10)
                if len(labels.labels) == 0:
                    issues.append(f"{symbol}: triple_barrier produced no labels")
                
                # Test regime_200ma (needs 200+ days)
                if len(prices) >= 200:
                    regime = regime_200ma(prices)
                    # Success - regime detection works
                
                symbols_ok.append(symbol)
                
            except Exception as e:
                symbols_failed.append(symbol)
                issues.append(f"{symbol}: {str(e)}")
        
        return {
            "all_available": len(symbols_failed) == 0,
            "symbols_tested": len(symbols),
            "symbols_ok": len(symbols_ok),
            "symbols_failed": symbols_failed,
            "issues": issues,
        }
