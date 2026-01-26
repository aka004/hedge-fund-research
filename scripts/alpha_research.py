#!/usr/bin/env python3
"""Alpha-seeking research loop for momentum factor discovery.

This script automates the exploration of momentum strategy parameter space,
testing combinations and logging results for analysis.

Usage:
    # Quick test (small parameter sweep, 3 months of data)
    python scripts/alpha_research.py --quick

    # Full exhaustive search (all parameter combinations)
    python scripts/alpha_research.py --full

    # Custom sweep with specific parameters
    python scripts/alpha_research.py --lookbacks 6 12 --rebalance monthly weekly

    # Resume from previous run
    python scripts/alpha_research.py --resume

    # Generate summary report from existing results
    python scripts/alpha_research.py --report-only
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import logging
import sys
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from analysis.metrics import PerformanceMetrics, calculate_metrics
from analysis.obsidian_reports import (
    generate_research_summary_obsidian,
    save_obsidian_note,
)
from data.storage.duckdb_store import DuckDBStore
from data.storage.parquet import ParquetStorage
from data.storage.universe import SP500_SYMBOLS
from strategy.backtest.engine import BacktestConfig, BacktestEngine, BacktestResult, WalkForwardValidator
from strategy.signals.combiner import SignalCombiner, SignalWeight
from strategy.signals.momentum import MomentumSignal
from strategy.signals.value import ValueSignal

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
from config import STORAGE_PATH
RESEARCH_PATH = PROJECT_ROOT / "research"


# =============================================================================
# Parameter Configuration
# =============================================================================

@dataclass
class ResearchConfig:
    """Configuration for a single research run."""
    
    # Momentum parameters
    lookback_months: int = 12
    skip_months: int = 1
    ma_window_days: int = 200
    
    # Value parameters
    max_pe: Optional[float] = 50.0  # None = no filter
    
    # Portfolio parameters
    rebalance_frequency: str = "monthly"  # "weekly", "monthly"
    max_positions: int = 20
    position_sizing: str = "equal"  # "equal", "signal_weighted"
    
    # Signal weights (must sum to 1.0)
    momentum_weight: float = 0.7
    value_weight: float = 0.3
    
    # Walk-forward settings
    train_months: int = 12
    test_months: int = 3
    
    def __post_init__(self):
        """Normalize weights if needed."""
        total = self.momentum_weight + self.value_weight
        if abs(total - 1.0) > 0.01:
            self.momentum_weight /= total
            self.value_weight /= total
    
    @property
    def config_hash(self) -> str:
        """Generate a unique hash for this configuration."""
        config_str = json.dumps(asdict(self), sort_keys=True)
        return hashlib.md5(config_str.encode()).hexdigest()[:12]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging."""
        return asdict(self)


@dataclass
class ParameterSpace:
    """Define the parameter space to search."""
    
    # Momentum lookback periods
    lookback_months: List[int] = field(default_factory=lambda: [6, 9, 12, 15])
    
    # Skip periods (avoid short-term mean reversion)
    skip_months: List[int] = field(default_factory=lambda: [0, 1, 2])
    
    # Moving average windows
    ma_window_days: List[int] = field(default_factory=lambda: [50, 100, 200])
    
    # P/E thresholds (None = no filter)
    max_pe: List[Optional[float]] = field(default_factory=lambda: [25.0, 50.0, 75.0, None])
    
    # Rebalancing frequency
    rebalance_frequency: List[str] = field(default_factory=lambda: ["weekly", "monthly"])
    
    # Position counts
    max_positions: List[int] = field(default_factory=lambda: [10, 15, 20, 30])
    
    # Signal weight combinations (momentum_weight, value_weight)
    weight_combinations: List[Tuple[float, float]] = field(
        default_factory=lambda: [
            (1.0, 0.0),   # Pure momentum
            (0.8, 0.2),   # Momentum-heavy
            (0.7, 0.3),   # Balanced momentum
            (0.6, 0.4),   # Slight momentum bias
            (0.5, 0.5),   # Equal weight
        ]
    )
    
    def get_quick_space(self) -> "ParameterSpace":
        """Get a reduced parameter space for quick testing."""
        return ParameterSpace(
            lookback_months=[12],
            skip_months=[1],
            ma_window_days=[200],
            max_pe=[50.0, None],
            rebalance_frequency=["monthly"],
            max_positions=[20],
            weight_combinations=[(0.7, 0.3), (1.0, 0.0)],
        )
    
    def generate_configs(self) -> List[ResearchConfig]:
        """Generate all configuration combinations."""
        configs = []
        
        for combo in itertools.product(
            self.lookback_months,
            self.skip_months,
            self.ma_window_days,
            self.max_pe,
            self.rebalance_frequency,
            self.max_positions,
            self.weight_combinations,
        ):
            lookback, skip, ma_window, pe, rebal, positions, weights = combo
            
            configs.append(ResearchConfig(
                lookback_months=lookback,
                skip_months=skip,
                ma_window_days=ma_window,
                max_pe=pe,
                rebalance_frequency=rebal,
                max_positions=positions,
                momentum_weight=weights[0],
                value_weight=weights[1],
            ))
        
        return configs
    
    @property
    def total_combinations(self) -> int:
        """Calculate total number of configurations to test."""
        return (
            len(self.lookback_months)
            * len(self.skip_months)
            * len(self.ma_window_days)
            * len(self.max_pe)
            * len(self.rebalance_frequency)
            * len(self.max_positions)
            * len(self.weight_combinations)
        )


# =============================================================================
# Research Result Tracking
# =============================================================================

@dataclass
class ResearchResult:
    """Result from a single research run."""
    
    config_hash: str
    config: Dict[str, Any]
    timestamp: str
    
    # Performance metrics
    total_return: float
    cagr: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    calmar_ratio: float
    annualized_volatility: float
    
    # Trade statistics
    total_trades: int
    win_rate: float
    profit_factor: float
    avg_win: float
    avg_loss: float
    
    # Higher moments
    skewness: float
    kurtosis: float
    
    # Walk-forward info
    wf_windows: int = 0
    wf_avg_return: float = 0.0
    wf_std_return: float = 0.0
    
    # Validation
    backtest_days: int = 0
    universe_size: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to flat dictionary for DataFrame."""
        result = {
            "config_hash": self.config_hash,
            "timestamp": self.timestamp,
            # Flatten config
            **{"param_{}".format(k): v for k, v in self.config.items()},
            # Metrics
            "total_return": self.total_return,
            "cagr": self.cagr,
            "sharpe_ratio": self.sharpe_ratio,
            "sortino_ratio": self.sortino_ratio,
            "max_drawdown": self.max_drawdown,
            "calmar_ratio": self.calmar_ratio,
            "annualized_volatility": self.annualized_volatility,
            "total_trades": self.total_trades,
            "win_rate": self.win_rate,
            "profit_factor": self.profit_factor,
            "avg_win": self.avg_win,
            "avg_loss": self.avg_loss,
            "skewness": self.skewness,
            "kurtosis": self.kurtosis,
            "wf_windows": self.wf_windows,
            "wf_avg_return": self.wf_avg_return,
            "wf_std_return": self.wf_std_return,
            "backtest_days": self.backtest_days,
            "universe_size": self.universe_size,
        }
        return result


class ResultsLogger:
    """Log and persist research results."""
    
    def __init__(self, output_dir: Path):
        """Initialize results logger.
        
        Args:
            output_dir: Directory for results files
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.results_file = self.output_dir / "alpha_research_results.csv"
        self.run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        
    def load_existing_results(self) -> pd.DataFrame:
        """Load existing results if available."""
        if self.results_file.exists():
            return pd.read_csv(self.results_file)
        return pd.DataFrame()
    
    def get_completed_hashes(self) -> Set[str]:
        """Get set of config hashes already completed."""
        df = self.load_existing_results()
        if df.empty:
            return set()
        return set(df["config_hash"].unique())
    
    def log_result(self, result: ResearchResult) -> None:
        """Log a single result to the CSV file."""
        result_dict = result.to_dict()
        result_dict["run_id"] = self.run_id
        
        df = pd.DataFrame([result_dict])
        
        # Append to file
        if self.results_file.exists():
            df.to_csv(self.results_file, mode="a", header=False, index=False)
        else:
            df.to_csv(self.results_file, index=False)
        
        logger.debug("Logged result for config {}".format(result.config_hash))
    
    def save_summary(self, results: List[ResearchResult], obsidian: bool = False) -> Path:
        """Save a summary report of results.
        
        Args:
            results: List of research results
            obsidian: If True, also save Obsidian-formatted report
            
        Returns:
            Path to summary file
        """
        summary_file = self.output_dir / "summary_{}.md".format(self.run_id)
        
        if not results:
            summary_file.write_text("# Research Summary\n\nNo results to report.\n")
            if obsidian:
                # Still save empty Obsidian note
                obsidian_content = generate_research_summary_obsidian([], self.run_id)
                save_obsidian_note(
                    obsidian_content,
                    f"{self.run_id}-summary.md",
                    subfolder="Research/Alpha-Research",
                )
            return summary_file
        
        # Convert to DataFrame for analysis
        df = pd.DataFrame([r.to_dict() for r in results])
        
        # Rank by Sharpe ratio
        df_sorted = df.sort_values("sharpe_ratio", ascending=False)
        
        # Generate markdown report
        lines = [
            "# Alpha Research Summary",
            "\n**Run ID:** {}".format(self.run_id),
            "**Generated:** {}".format(datetime.now().isoformat()),
            "**Configurations tested:** {}".format(len(results)),
            "",
            "## Top 10 Configurations by Sharpe Ratio",
            "",
        ]
        
        top_10 = df_sorted.head(10)
        for idx, row in top_10.iterrows():
            lines.extend([
                "### #{}: {}".format(list(df_sorted.index).index(idx) + 1, row['config_hash']),
                "- **Sharpe:** {:.3f}".format(row['sharpe_ratio']),
                "- **CAGR:** {:.2f}%".format(row['cagr']*100),
                "- **Max Drawdown:** {:.2f}%".format(row['max_drawdown']*100),
                "- **Sortino:** {:.3f}".format(row['sortino_ratio']),
                "",
                "**Parameters:**",
                "- Lookback: {}mo, Skip: {}mo".format(row['param_lookback_months'], row['param_skip_months']),
                "- MA Window: {}d".format(row['param_ma_window_days']),
                "- Max P/E: {}".format(row['param_max_pe'] if pd.notna(row['param_max_pe']) else 'None'),
                "- Rebalance: {}, Positions: {}".format(row['param_rebalance_frequency'], row['param_max_positions']),
                "- Weights: Mom={:.1f}, Val={:.1f}".format(row['param_momentum_weight'], row['param_value_weight']),
                "",
            ])
        
        # Parameter sensitivity analysis
        lines.extend([
            "## Parameter Sensitivity Analysis",
            "",
            "### Lookback Period Impact",
        ])
        
        for lookback in df["param_lookback_months"].unique():
            subset = df[df["param_lookback_months"] == lookback]
            lines.append(
                "- **{}mo:** Avg Sharpe={:.3f}, Std={:.3f}".format(
                    lookback, subset['sharpe_ratio'].mean(), subset['sharpe_ratio'].std()
                )
            )
        
        lines.extend(["", "### Rebalance Frequency Impact"])
        for rebal in df["param_rebalance_frequency"].unique():
            subset = df[df["param_rebalance_frequency"] == rebal]
            lines.append(
                "- **{}:** Avg Sharpe={:.3f}, Avg Turnover={:.0f} trades".format(
                    rebal, subset['sharpe_ratio'].mean(), subset['total_trades'].mean()
                )
            )
        
        lines.extend(["", "### Position Count Impact"])
        for positions in sorted(df["param_max_positions"].unique()):
            subset = df[df["param_max_positions"] == positions]
            lines.append(
                "- **{}:** Avg Sharpe={:.3f}, Avg CAGR={:.2f}%".format(
                    positions, subset['sharpe_ratio'].mean(), subset['cagr'].mean()*100
                )
            )
        
        # Statistics
        lines.extend([
            "",
            "## Overall Statistics",
            "",
            "- **Mean Sharpe:** {:.3f}".format(df['sharpe_ratio'].mean()),
            "- **Max Sharpe:** {:.3f}".format(df['sharpe_ratio'].max()),
            "- **Min Sharpe:** {:.3f}".format(df['sharpe_ratio'].min()),
            "- **Mean CAGR:** {:.2f}%".format(df['cagr'].mean()*100),
            "- **Mean Max DD:** {:.2f}%".format(df['max_drawdown'].mean()*100),
            "",
            "- **Positive Sharpe configs:** {} / {}".format((df['sharpe_ratio'] > 0).sum(), len(df)),
            "- **Sharpe > 0.5:** {} / {}".format((df['sharpe_ratio'] > 0.5).sum(), len(df)),
            "- **Sharpe > 1.0:** {} / {}".format((df['sharpe_ratio'] > 1.0).sum(), len(df)),
        ])
        
        summary_file.write_text("\n".join(lines))
        logger.info("Saved summary to {}".format(summary_file))
        
        # Save Obsidian version if requested
        if obsidian:
            obsidian_content = generate_research_summary_obsidian(
                [r.to_dict() for r in results],
                self.run_id,
            )
            obsidian_path = save_obsidian_note(
                obsidian_content,
                f"{self.run_id}-summary.md",
                subfolder="Research/Alpha-Research",
            )
            logger.info("Saved Obsidian report to {}".format(obsidian_path))
        
        return summary_file


# =============================================================================
# Research Engine
# =============================================================================

class AlphaResearchEngine:
    """Engine for running alpha research experiments."""
    
    def __init__(
        self,
        storage: ParquetStorage,
        duckdb: DuckDBStore,
        results_logger: ResultsLogger,
    ):
        """Initialize research engine.
        
        Args:
            storage: Parquet storage for data
            duckdb: DuckDB for queries
            results_logger: Logger for results
        """
        self.storage = storage
        self.duckdb = duckdb
        self.logger = results_logger
        
    def _create_signal_combiner(self, config: ResearchConfig) -> SignalCombiner:
        """Create a signal combiner from configuration."""
        # Create momentum signal with config params
        momentum = MomentumSignal(
            duckdb_store=self.duckdb,
            lookback_months=config.lookback_months,
            skip_months=config.skip_months,
            ma_window_days=config.ma_window_days,
        )
        
        # Create value signal with config params
        value = ValueSignal(
            parquet_storage=self.storage,
            max_pe=config.max_pe if config.max_pe else 9999.0,
            require_positive_earnings=True,
            require_revenue_growth=False,
        )
        
        # Create combiner with weights
        weights = [
            SignalWeight("momentum", config.momentum_weight),
            SignalWeight("value", config.value_weight),
        ]
        
        return SignalCombiner(
            generators=[momentum, value],
            weights=weights,
        )
    
    def run_single_config(
        self,
        config: ResearchConfig,
        universe: List[str],
        start_date: date,
        end_date: date,
        use_walk_forward: bool = True,
    ) -> ResearchResult:
        """Run a single configuration and return results.
        
        Args:
            config: Research configuration
            universe: List of symbols to trade
            start_date: Backtest start date
            end_date: Backtest end date
            use_walk_forward: Whether to use walk-forward validation
            
        Returns:
            ResearchResult with metrics
        """
        logger.debug("Running config {}".format(config.config_hash))
        
        # Create signal combiner
        combiner = self._create_signal_combiner(config)
        
        # Create backtest config
        bt_config = BacktestConfig(
            initial_capital=100000.0,
            max_positions=config.max_positions,
            rebalance_frequency=config.rebalance_frequency,
            position_sizing=config.position_sizing,
        )
        
        # Create backtest engine
        engine = BacktestEngine(
            parquet_storage=self.storage,
            duckdb_store=self.duckdb,
            signal_combiner=combiner,
            config=bt_config,
        )
        
        # Run backtest (walk-forward or simple)
        if use_walk_forward:
            validator = WalkForwardValidator(
                backtest_engine=engine,
                train_months=config.train_months,
                test_months=config.test_months,
            )
            wf_results = validator.run(universe, start_date, end_date)
            
            # Combine all walk-forward periods
            all_returns = pd.concat([r.daily_returns for r in wf_results if not r.daily_returns.empty])
            all_trades = [t for r in wf_results for t in r.trades]
            
            wf_returns = [r.total_return for r in wf_results]
            wf_windows = len(wf_results)
            wf_avg = sum(wf_returns) / len(wf_returns) if wf_returns else 0.0
            wf_std = pd.Series(wf_returns).std() if len(wf_returns) > 1 else 0.0
            
        else:
            result = engine.run(universe, start_date, end_date)
            all_returns = result.daily_returns
            all_trades = result.trades
            wf_windows = 1
            wf_avg = result.total_return
            wf_std = 0.0
        
        # Calculate metrics
        if all_returns.empty:
            metrics = PerformanceMetrics(
                total_return=0.0, cagr=0.0, annualized_volatility=0.0,
                sharpe_ratio=0.0, sortino_ratio=0.0, calmar_ratio=0.0,
                max_drawdown=0.0, max_drawdown_duration_days=0,
                total_trades=0, win_rate=0.0, profit_factor=0.0,
                avg_win=0.0, avg_loss=0.0, skewness=0.0, kurtosis=0.0,
            )
        else:
            metrics = calculate_metrics(all_returns, trades=all_trades)
        
        return ResearchResult(
            config_hash=config.config_hash,
            config=config.to_dict(),
            timestamp=datetime.now().isoformat(),
            total_return=metrics.total_return,
            cagr=metrics.cagr,
            sharpe_ratio=metrics.sharpe_ratio,
            sortino_ratio=metrics.sortino_ratio,
            max_drawdown=metrics.max_drawdown,
            calmar_ratio=metrics.calmar_ratio,
            annualized_volatility=metrics.annualized_volatility,
            total_trades=metrics.total_trades,
            win_rate=metrics.win_rate,
            profit_factor=metrics.profit_factor,
            avg_win=metrics.avg_win,
            avg_loss=metrics.avg_loss,
            skewness=metrics.skewness,
            kurtosis=metrics.kurtosis,
            wf_windows=wf_windows,
            wf_avg_return=wf_avg,
            wf_std_return=wf_std,
            backtest_days=(end_date - start_date).days,
            universe_size=len(universe),
        )
    
    def run_parameter_sweep(
        self,
        configs: List[ResearchConfig],
        universe: List[str],
        start_date: date,
        end_date: date,
        resume: bool = False,
        use_walk_forward: bool = True,
    ) -> List[ResearchResult]:
        """Run a full parameter sweep.
        
        Args:
            configs: List of configurations to test
            universe: List of symbols
            start_date: Backtest start
            end_date: Backtest end
            resume: Skip already-completed configs
            use_walk_forward: Use walk-forward validation
            
        Returns:
            List of results
        """
        results = []
        
        # Get completed configs if resuming
        completed = self.logger.get_completed_hashes() if resume else set()
        configs_to_run = [c for c in configs if c.config_hash not in completed]
        
        if resume and len(completed) > 0:
            logger.info("Resuming: {} already completed, {} remaining".format(len(completed), len(configs_to_run)))
        
        total = len(configs_to_run)
        
        for i, config in enumerate(configs_to_run, 1):
            logger.info(
                "[{}/{}] Testing: lookback={}mo, skip={}mo, MA={}d, PE={}, rebal={}, pos={}, weights=({:.1f},{:.1f})".format(
                    i, total,
                    config.lookback_months,
                    config.skip_months,
                    config.ma_window_days,
                    config.max_pe,
                    config.rebalance_frequency,
                    config.max_positions,
                    config.momentum_weight,
                    config.value_weight,
                )
            )
            
            try:
                result = self.run_single_config(
                    config=config,
                    universe=universe,
                    start_date=start_date,
                    end_date=end_date,
                    use_walk_forward=use_walk_forward,
                )
                
                results.append(result)
                self.logger.log_result(result)
                
                logger.info(
                    "    -> Sharpe={:.3f}, CAGR={:.2f}%, MaxDD={:.2f}%".format(
                        result.sharpe_ratio, result.cagr*100, result.max_drawdown*100
                    )
                )
                
            except Exception as e:
                logger.error("    -> FAILED: {}".format(e))
                continue
        
        return results


# =============================================================================
# CLI Entry Point
# =============================================================================

def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Alpha-seeking research loop for momentum strategies",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    # Mode selection
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--quick",
        action="store_true",
        help="Quick test mode: reduced parameter space, 1 year data",
    )
    mode_group.add_argument(
        "--full",
        action="store_true",
        help="Full exhaustive search: all parameter combinations",
    )
    mode_group.add_argument(
        "--report-only",
        action="store_true",
        help="Generate summary report from existing results",
    )
    
    # Execution options
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from previous run, skip completed configs",
    )
    parser.add_argument(
        "--no-walk-forward",
        action="store_true",
        help="Disable walk-forward validation (faster but less robust)",
    )
    
    # Custom parameters
    parser.add_argument(
        "--lookbacks",
        type=int,
        nargs="+",
        help="Custom lookback months to test (e.g., --lookbacks 6 12)",
    )
    parser.add_argument(
        "--skips",
        type=int,
        nargs="+",
        help="Custom skip months to test",
    )
    parser.add_argument(
        "--ma-windows",
        type=int,
        nargs="+",
        help="Custom MA windows to test",
    )
    parser.add_argument(
        "--max-pes",
        type=float,
        nargs="+",
        help="Custom max P/E thresholds (use 0 for no filter)",
    )
    parser.add_argument(
        "--rebalance",
        type=str,
        nargs="+",
        choices=["daily", "weekly", "monthly"],
        help="Rebalance frequencies to test",
    )
    parser.add_argument(
        "--positions",
        type=int,
        nargs="+",
        help="Position counts to test",
    )
    
    # Date range
    parser.add_argument(
        "--years",
        type=int,
        default=5,
        help="Years of history to backtest (default: 5)",
    )
    parser.add_argument(
        "--start-date",
        type=str,
        help="Start date (YYYY-MM-DD), overrides --years",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        help="End date (YYYY-MM-DD), defaults to today",
    )
    
    # Universe
    parser.add_argument(
        "--symbols",
        nargs="+",
        help="Specific symbols to test (default: S&P 500)",
    )
    parser.add_argument(
        "--max-symbols",
        type=int,
        default=None,
        help="Limit universe size (for testing)",
    )
    
    # Output
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=RESEARCH_PATH,
        help="Output directory for results",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose output",
    )
    parser.add_argument(
        "--obsidian",
        action="store_true",
        help="Generate Obsidian-formatted reports in vault",
    )
    
    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Initialize storage
    storage = ParquetStorage(STORAGE_PATH)
    duckdb = DuckDBStore(STORAGE_PATH)
    logger_obj = ResultsLogger(args.output_dir)
    
    # Handle report-only mode
    if args.report_only:
        df = logger_obj.load_existing_results()
        if df.empty:
            logger.error("No existing results found!")
            return 1
        
        # Convert to ResearchResult objects for summary generation
        results = []
        for _, row in df.iterrows():
            # Reconstruct config dict from param_ columns
            config_dict = {
                k.replace("param_", ""): v 
                for k, v in row.items() 
                if k.startswith("param_")
            }
            
            results.append(ResearchResult(
                config_hash=row["config_hash"],
                config=config_dict,
                timestamp=row["timestamp"],
                total_return=row["total_return"],
                cagr=row["cagr"],
                sharpe_ratio=row["sharpe_ratio"],
                sortino_ratio=row["sortino_ratio"],
                max_drawdown=row["max_drawdown"],
                calmar_ratio=row["calmar_ratio"],
                annualized_volatility=row["annualized_volatility"],
                total_trades=row["total_trades"],
                win_rate=row["win_rate"],
                profit_factor=row["profit_factor"],
                avg_win=row["avg_win"],
                avg_loss=row["avg_loss"],
                skewness=row["skewness"],
                kurtosis=row["kurtosis"],
                wf_windows=row.get("wf_windows", 0),
                wf_avg_return=row.get("wf_avg_return", 0),
                wf_std_return=row.get("wf_std_return", 0),
                backtest_days=row.get("backtest_days", 0),
                universe_size=row.get("universe_size", 0),
            ))
        
        summary_path = logger_obj.save_summary(results)
        print("\n✓ Summary saved to: {}".format(summary_path))
        return 0
    
    # Build parameter space
    if args.quick:
        logger.info("Quick mode: using reduced parameter space")
        param_space = ParameterSpace().get_quick_space()
        years = 1
    elif args.full:
        logger.info("Full mode: testing all parameter combinations")
        param_space = ParameterSpace()
        years = args.years
    else:
        # Custom parameter space
        param_space = ParameterSpace(
            lookback_months=args.lookbacks or [12],
            skip_months=args.skips or [1],
            ma_window_days=args.ma_windows or [200],
            max_pe=[None if pe == 0 else pe for pe in (args.max_pes or [50.0])],
            rebalance_frequency=args.rebalance or ["monthly"],
            max_positions=args.positions or [20],
        )
        years = args.years
    
    # Generate configurations
    configs = param_space.generate_configs()
    logger.info("Generated {} configurations to test".format(len(configs)))
    
    # Set date range
    end_date = date.today() if not args.end_date else date.fromisoformat(args.end_date)
    if args.start_date:
        start_date = date.fromisoformat(args.start_date)
    else:
        start_date = end_date - timedelta(days=years * 365)
    
    logger.info("Backtest period: {} to {}".format(start_date, end_date))
    
    # Build universe
    if args.symbols:
        universe = args.symbols
    else:
        universe = SP500_SYMBOLS
        if args.max_symbols:
            universe = universe[:args.max_symbols]
    
    logger.info("Universe: {} symbols".format(len(universe)))
    
    # Create engine and run
    engine = AlphaResearchEngine(storage, duckdb, logger_obj)
    
    print("\n" + "=" * 60)
    print("ALPHA RESEARCH LOOP")
    print("=" * 60)
    print("Configurations:  {}".format(len(configs)))
    print("Universe:        {} symbols".format(len(universe)))
    print("Period:          {} to {}".format(start_date, end_date))
    print("Walk-forward:    {}".format('Enabled' if not args.no_walk_forward else 'Disabled'))
    print("Resume mode:     {}".format('Yes' if args.resume else 'No'))
    print("=" * 60 + "\n")
    
    results = engine.run_parameter_sweep(
        configs=configs,
        universe=universe,
        start_date=start_date,
        end_date=end_date,
        resume=args.resume,
        use_walk_forward=not args.no_walk_forward,
    )
    
    if results:
        # Generate summary
        summary_path = logger_obj.save_summary(results, obsidian=args.obsidian)
        
        # Print top results
        print("\n" + "=" * 60)
        print("TOP 5 CONFIGURATIONS BY SHARPE RATIO")
        print("=" * 60)
        
        sorted_results = sorted(results, key=lambda r: r.sharpe_ratio, reverse=True)[:5]
        for i, r in enumerate(sorted_results, 1):
            print("\n#{}: {}".format(i, r.config_hash))
            print("    Sharpe: {:.3f}  |  CAGR: {:.2f}%  |  MaxDD: {:.2f}%".format(
                r.sharpe_ratio, r.cagr*100, r.max_drawdown*100
            ))
            print("    Params: lookback={}mo, skip={}mo, MA={}d".format(
                r.config['lookback_months'], r.config['skip_months'], r.config['ma_window_days']
            ))
            print("            PE={}, rebal={}, pos={}".format(
                r.config['max_pe'], r.config['rebalance_frequency'], r.config['max_positions']
            ))
        
        print("\n✓ Full results saved to: {}".format(logger_obj.results_file))
        print("✓ Summary saved to: {}".format(summary_path))
        if args.obsidian:
            print("✓ Obsidian report saved to vault")
    else:
        logger.warning("No results generated")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
