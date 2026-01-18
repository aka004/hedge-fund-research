"""Backtesting engine for strategy evaluation."""

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd

from data.storage.duckdb_store import DuckDBStore
from data.storage.parquet import ParquetStorage
from strategy.backtest.portfolio import PortfolioManager, Trade, TransactionCosts
from strategy.signals.base import Signal
from strategy.signals.combiner import SignalCombiner

logger = logging.getLogger(__name__)


@dataclass
class BacktestConfig:
    """Configuration for backtesting."""

    initial_capital: float = 100000.0
    max_positions: int = 20
    rebalance_frequency: str = "monthly"  # "daily", "weekly", "monthly"
    position_sizing: str = "equal"  # "equal", "signal_weighted"
    transaction_costs: TransactionCosts = field(default_factory=TransactionCosts)


@dataclass
class BacktestResult:
    """Results from a backtest run."""

    config: BacktestConfig
    start_date: date
    end_date: date
    equity_curve: pd.DataFrame
    trades: list[Trade]
    daily_returns: pd.Series
    positions_history: list[dict]

    @property
    def total_return(self) -> float:
        if self.equity_curve.empty:
            return 0.0
        start_equity = self.equity_curve["equity"].iloc[0]
        end_equity = self.equity_curve["equity"].iloc[-1]
        return (end_equity - start_equity) / start_equity

    @property
    def cagr(self) -> float:
        """Compound annual growth rate."""
        if self.equity_curve.empty:
            return 0.0
        days = (self.end_date - self.start_date).days
        if days <= 0:
            return 0.0
        years = days / 365.25
        return (1 + self.total_return) ** (1 / years) - 1

    @property
    def trade_count(self) -> int:
        return len(self.trades)


class BacktestEngine:
    """Engine for running backtests."""

    def __init__(
        self,
        parquet_storage: ParquetStorage,
        duckdb_store: DuckDBStore,
        signal_combiner: SignalCombiner,
        config: BacktestConfig | None = None,
    ) -> None:
        """Initialize backtest engine.

        Args:
            parquet_storage: Storage for data access
            duckdb_store: DuckDB for efficient queries
            signal_combiner: Signal generator for stock selection
            config: Backtest configuration
        """
        self.storage = parquet_storage
        self.duckdb = duckdb_store
        self.signal_combiner = signal_combiner
        self.config = config or BacktestConfig()

    def _get_rebalance_dates(
        self,
        start_date: date,
        end_date: date,
    ) -> list[date]:
        """Generate rebalance dates based on frequency."""
        dates = []
        current = start_date

        while current <= end_date:
            dates.append(current)

            if self.config.rebalance_frequency == "daily":
                current += timedelta(days=1)
            elif self.config.rebalance_frequency == "weekly":
                current += timedelta(weeks=1)
            elif self.config.rebalance_frequency == "monthly":
                # Move to same day next month
                if current.month == 12:
                    current = date(current.year + 1, 1, current.day)
                else:
                    try:
                        current = date(current.year, current.month + 1, current.day)
                    except ValueError:
                        # Handle months with fewer days
                        current = date(current.year, current.month + 2, 1) - timedelta(days=1)

        return dates

    def _get_prices_for_date(
        self,
        symbols: list[str],
        as_of_date: date,
    ) -> dict[str, float]:
        """Get prices for symbols as of a date."""
        prices = {}

        for symbol in symbols:
            df = self.storage.load_prices(symbol, end_date=as_of_date)
            if df is not None and not df.empty:
                # Get most recent price up to as_of_date
                df = df[df["date"] <= as_of_date]
                if not df.empty:
                    prices[symbol] = df.iloc[-1]["adj_close"]

        return prices

    def _calculate_target_weights(
        self,
        signals: list[Signal],
    ) -> dict[str, float]:
        """Calculate target portfolio weights from signals."""
        if not signals:
            return {}

        # Filter to top N
        top_signals = signals[: self.config.max_positions]

        if self.config.position_sizing == "equal":
            weight = 1.0 / len(top_signals)
            return {s.symbol: weight for s in top_signals}

        elif self.config.position_sizing == "signal_weighted":
            # Weight by signal score
            total_score = sum(max(0, s.score) for s in top_signals)
            if total_score == 0:
                weight = 1.0 / len(top_signals)
                return {s.symbol: weight for s in top_signals}

            return {
                s.symbol: max(0, s.score) / total_score
                for s in top_signals
            }

        return {}

    def run(
        self,
        universe: list[str],
        start_date: date,
        end_date: date,
    ) -> BacktestResult:
        """Run backtest over specified period.

        Args:
            universe: List of symbols to consider
            start_date: Backtest start date
            end_date: Backtest end date

        Returns:
            BacktestResult with performance data
        """
        logger.info(f"Starting backtest from {start_date} to {end_date}")

        portfolio_manager = PortfolioManager(
            initial_capital=self.config.initial_capital,
            transaction_costs=self.config.transaction_costs,
        )

        rebalance_dates = self._get_rebalance_dates(start_date, end_date)
        equity_records = []
        positions_history = []
        all_trades: list[Trade] = []

        for rebal_date in rebalance_dates:
            # Generate signals using only data available before rebal_date
            # This prevents look-ahead bias
            signals = self.signal_combiner.get_top_picks(
                universe,
                as_of_date=rebal_date,
                n_picks=self.config.max_positions,
            )

            # Get current prices
            all_symbols = set(universe) | set(portfolio_manager.portfolio.positions.keys())
            prices = self._get_prices_for_date(list(all_symbols), rebal_date)

            if not prices:
                continue

            # Calculate target weights
            target_weights = self._calculate_target_weights(signals)

            # Rebalance
            trades = portfolio_manager.rebalance_to_targets(
                target_weights,
                prices,
                rebal_date,
            )
            all_trades.extend(trades)

            # Record equity
            portfolio_manager.portfolio.update_prices(prices)
            equity_records.append({
                "date": rebal_date,
                "equity": portfolio_manager.portfolio.equity,
                "cash": portfolio_manager.portfolio.cash,
                "position_count": portfolio_manager.portfolio.position_count,
            })

            # Record positions
            positions_history.append({
                "date": rebal_date,
                "positions": portfolio_manager.portfolio.get_weights(),
            })

        # Create equity curve DataFrame
        equity_curve = pd.DataFrame(equity_records)
        if not equity_curve.empty:
            equity_curve["date"] = pd.to_datetime(equity_curve["date"])
            equity_curve = equity_curve.set_index("date")

        # Calculate daily returns
        daily_returns = pd.Series(dtype=float)
        if not equity_curve.empty:
            daily_returns = equity_curve["equity"].pct_change().dropna()

        return BacktestResult(
            config=self.config,
            start_date=start_date,
            end_date=end_date,
            equity_curve=equity_curve.reset_index(),
            trades=all_trades,
            daily_returns=daily_returns,
            positions_history=positions_history,
        )


class WalkForwardValidator:
    """Walk-forward validation for strategy robustness."""

    def __init__(
        self,
        backtest_engine: BacktestEngine,
        train_months: int = 12,
        test_months: int = 3,
    ) -> None:
        """Initialize walk-forward validator.

        Args:
            backtest_engine: Engine for running backtests
            train_months: Months of data for training/optimization
            test_months: Months of out-of-sample testing
        """
        self.engine = backtest_engine
        self.train_months = train_months
        self.test_months = test_months

    def run(
        self,
        universe: list[str],
        start_date: date,
        end_date: date,
    ) -> list[BacktestResult]:
        """Run walk-forward validation.

        Args:
            universe: List of symbols
            start_date: Overall start date
            end_date: Overall end date

        Returns:
            List of out-of-sample backtest results
        """
        results = []
        window_start = start_date

        while True:
            # Training period
            train_end = date(
                window_start.year + (window_start.month + self.train_months - 1) // 12,
                (window_start.month + self.train_months - 1) % 12 + 1,
                1,
            ) - timedelta(days=1)

            if train_end >= end_date:
                break

            # Test period
            test_start = train_end + timedelta(days=1)
            test_end = date(
                test_start.year + (test_start.month + self.test_months - 1) // 12,
                (test_start.month + self.test_months - 1) % 12 + 1,
                1,
            ) - timedelta(days=1)

            if test_end > end_date:
                test_end = end_date

            logger.info(f"Walk-forward window: train {window_start} to {train_end}, test {test_start} to {test_end}")

            # Run out-of-sample test
            result = self.engine.run(universe, test_start, test_end)
            results.append(result)

            # Move to next window
            window_start = test_start

        return results
