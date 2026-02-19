"""Event-driven backtest engine with barrier-based exits."""

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd

from strategy.backtest.exit_manager import ExitConfig, ExitManager, ExitSignal
from strategy.backtest.portfolio import RoundTripTrade, TransactionCosts
from strategy.signals.combiner import SignalCombiner

logger = logging.getLogger(__name__)


@dataclass
class EventEngineConfig:
    """Configuration for the event-driven backtest engine."""

    initial_capital: float = 100_000.0
    max_positions: int = 20
    max_position_weight: float = 0.10  # 10% cap
    rebalance_frequency: str = "monthly"
    position_sizing: str = "equal"  # "equal" | "signal_weighted"
    transaction_costs: TransactionCosts = field(default_factory=TransactionCosts)
    exit_config: ExitConfig = field(default_factory=ExitConfig)
    benchmark_symbol: str = "SPY"


@dataclass
class EventEngineResult:
    """Results from an event-driven backtest run."""

    config: EventEngineConfig
    start_date: date
    end_date: date
    equity_curve: pd.DataFrame
    trade_log: pd.DataFrame
    daily_returns: pd.Series
    benchmark_returns: pd.Series
    open_positions: list[RoundTripTrade]


class EventDrivenEngine:
    """Daily-step engine. Entries via signals, exits via barriers. No storage dependency."""

    def __init__(
        self,
        signal_combiner: SignalCombiner,
        config: EventEngineConfig | None = None,
    ) -> None:
        self.signal_combiner = signal_combiner
        self.config = config or EventEngineConfig()
        self.exit_manager = ExitManager(self.config.exit_config)

    def run(
        self,
        universe: list[str],
        close_prices: pd.DataFrame,
        open_prices: pd.DataFrame,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> EventEngineResult:
        """Run event-driven backtest over the given price data."""
        close_prices = self._normalize_index(close_prices)
        open_prices = self._normalize_index(open_prices)

        trading_days = sorted(close_prices.index)
        if start_date:
            trading_days = [d for d in trading_days if d >= start_date]
        if end_date:
            trading_days = [d for d in trading_days if d <= end_date]

        if not trading_days:
            return self._empty_result(
                start_date or date.today(), end_date or date.today()
            )

        actual_start = trading_days[0]
        actual_end = trading_days[-1]

        # Compute daily vol (EWMA of returns)
        returns = close_prices.pct_change()
        daily_vol = returns.ewm(span=self.config.exit_config.vol_window).std()

        # Compute rebalance dates
        rebalance_dates = self._get_rebalance_dates(trading_days)

        # State
        cash = self.config.initial_capital
        positions: dict[str, RoundTripTrade] = {}
        completed_trades: list[RoundTripTrade] = []
        pending_exits: list[ExitSignal] = []
        equity_records: list[dict] = []

        # Benchmark tracking
        bench = self.config.benchmark_symbol
        bench_start_price = None
        if bench in close_prices.columns and actual_start in close_prices.index:
            bench_start_price = close_prices.loc[actual_start, bench]

        for today in trading_days:
            today_open = self._get_prices_for_date(open_prices, today)
            today_close = self._get_prices_for_date(close_prices, today)
            today_vol = self._get_vol_for_date(daily_vol, today)

            # --- Step A: Execute yesterday's queued exits at today's OPEN ---
            remaining_exits: list[ExitSignal] = []
            for signal in pending_exits:
                if signal.symbol not in positions:
                    continue
                if signal.symbol not in today_open:
                    remaining_exits.append(signal)
                    continue

                trade = positions[signal.symbol]
                exit_price = today_open[signal.symbol]

                # Complete the round-trip trade
                trade.exit_date = today
                trade.exit_price = exit_price
                trade.exit_reason = signal.reason

                # Add sale proceeds minus costs
                gross_proceeds = trade.shares * exit_price
                commission, slippage = self.config.transaction_costs.calculate(
                    trade.shares, exit_price
                )
                cash += gross_proceeds - commission - slippage

                completed_trades.append(trade)
                del positions[signal.symbol]

            pending_exits = remaining_exits

            # --- Step B: If rebalance day, enter new positions at today's OPEN ---
            if today in rebalance_dates:
                cash, positions, completed_trades = self._handle_rebalance(
                    today=today,
                    universe=universe,
                    today_open=today_open,
                    cash=cash,
                    positions=positions,
                    completed_trades=completed_trades,
                )

            # --- Step C: Mark-to-market at today's CLOSE ---
            for symbol, trade in positions.items():
                if symbol in today_close:
                    current_return = (
                        today_close[symbol] - trade.entry_price
                    ) / trade.entry_price
                    trade.max_favorable = max(trade.max_favorable, current_return)
                    trade.max_adverse = min(trade.max_adverse, current_return)

            # --- Step D: Check exit barriers at today's CLOSE ---
            new_exits = self.exit_manager.check_exits(
                positions, today, today_close, today_vol
            )
            pending_exits.extend(new_exits)

            # --- Step E: Record daily equity snapshot ---
            position_value = sum(
                trade.shares * today_close.get(symbol, 0.0)
                for symbol, trade in positions.items()
            )
            equity = cash + position_value

            bench_close = None
            if bench in close_prices.columns and today in close_prices.index:
                bench_close = close_prices.loc[today, bench]

            equity_records.append(
                {
                    "date": today,
                    "equity": equity,
                    "cash": cash,
                    "positions": len(positions),
                    "benchmark": bench_close,
                }
            )

        return self._build_result(
            actual_start,
            actual_end,
            equity_records,
            completed_trades,
            positions,
            bench_start_price,
        )

    def _handle_rebalance(
        self,
        today: date,
        universe: list[str],
        today_open: dict[str, float],
        cash: float,
        positions: dict[str, RoundTripTrade],
        completed_trades: list[RoundTripTrade],
    ) -> tuple[float, dict[str, RoundTripTrade], list[RoundTripTrade]]:
        """Process rebalance: exit stale, enter new. Returns (cash, positions, completed)."""
        # Generate signals using data through YESTERDAY (no look-ahead)
        yesterday = today - timedelta(days=1)
        signals = self.signal_combiner.get_top_picks(
            universe,
            as_of_date=yesterday,
            n_picks=self.config.max_positions,
        )

        target_symbols = {s.symbol for s in signals}

        # Exit positions not in new target set (rebalance_out) at today's open
        for symbol in list(positions.keys()):
            if symbol not in target_symbols and symbol in today_open:
                trade = positions[symbol]
                exit_price = today_open[symbol]

                trade.exit_date = today
                trade.exit_price = exit_price
                trade.exit_reason = "rebalance_out"

                gross_proceeds = trade.shares * exit_price
                commission, slippage = self.config.transaction_costs.calculate(
                    trade.shares, exit_price
                )
                cash += gross_proceeds - commission - slippage

                completed_trades.append(trade)
                del positions[symbol]

        # Enter new positions for symbols not already held
        new_symbols = [s for s in signals if s.symbol not in positions]
        if not new_symbols:
            return cash, positions, completed_trades

        # Compute current equity for weight calculation
        position_value = sum(
            trade.shares * today_open.get(sym, 0.0) for sym, trade in positions.items()
        )
        current_equity = cash + position_value

        # Calculate weights
        weights = self._calculate_weights(new_symbols)

        for symbol, weight in weights.items():
            if symbol not in today_open:
                continue
            if len(positions) >= self.config.max_positions:
                break

            # Cap at max_position_weight
            capped_weight = min(weight, self.config.max_position_weight)
            target_value = capped_weight * current_equity
            price = today_open[symbol]

            if price <= 0:
                continue

            shares = target_value / price
            commission, slippage = self.config.transaction_costs.calculate(
                shares, price
            )
            total_cost = shares * price + commission + slippage

            if total_cost > cash:
                # Buy what we can afford
                affordable = cash * 0.99  # small buffer
                shares = affordable / (
                    price * (1 + self.config.transaction_costs.slippage_bps / 10000)
                )
                if shares <= 0:
                    continue
                commission, slippage = self.config.transaction_costs.calculate(
                    shares, price
                )
                total_cost = shares * price + commission + slippage

            cash -= total_cost
            positions[symbol] = RoundTripTrade(
                symbol=symbol,
                entry_date=today,
                entry_price=price,
                entry_reason="signal_rebalance",
                shares=shares,
            )

        return cash, positions, completed_trades

    def _calculate_weights(
        self,
        signals: list,
    ) -> dict[str, float]:
        """Calculate target weights from signals."""
        if not signals:
            return {}

        if self.config.position_sizing == "signal_weighted":
            total_score = sum(max(0, s.score) for s in signals)
            if total_score > 0:
                return {s.symbol: max(0, s.score) / total_score for s in signals}

        # Default: equal weight
        weight = 1.0 / len(signals)
        return {s.symbol: weight for s in signals}

    def _get_rebalance_dates(self, trading_days: list[date]) -> set[date]:
        """Determine which trading days are rebalance days."""
        if not trading_days:
            return set()

        freq = self.config.rebalance_frequency
        rebalance = set()

        if freq == "daily":
            return set(trading_days)

        current_period = None
        for day in trading_days:
            if freq == "weekly":
                period = day.isocalendar()[:2]  # (year, week)
            elif freq == "monthly":
                period = (day.year, day.month)
            else:
                period = (day.year, day.month)

            if period != current_period:
                rebalance.add(day)
                current_period = period

        return rebalance

    @staticmethod
    def _normalize_index(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)
        df.index = df.index.date
        return df

    @staticmethod
    def _get_prices_for_date(df: pd.DataFrame, day: date) -> dict[str, float]:
        if day not in df.index:
            return {}
        row = df.loc[day]
        return {col: row[col] for col in df.columns if pd.notna(row[col])}

    @staticmethod
    def _get_vol_for_date(vol_df: pd.DataFrame, day: date) -> dict[str, float]:
        if day not in vol_df.index:
            return {}
        row = vol_df.loc[day]
        return {col: row[col] for col in vol_df.columns if pd.notna(row[col])}

    def _empty_result(self, start: date, end: date) -> EventEngineResult:
        return EventEngineResult(
            config=self.config,
            start_date=start,
            end_date=end,
            equity_curve=pd.DataFrame(
                columns=["date", "equity", "cash", "positions", "benchmark"]
            ),
            trade_log=pd.DataFrame(),
            daily_returns=pd.Series(dtype=float),
            benchmark_returns=pd.Series(dtype=float),
            open_positions=[],
        )

    def _build_result(
        self,
        start: date,
        end: date,
        equity_records: list[dict],
        completed_trades: list[RoundTripTrade],
        open_positions: dict[str, RoundTripTrade],
        bench_start_price: float | None,
    ) -> EventEngineResult:
        """Assemble the final EventEngineResult."""
        # Equity curve
        eq_df = pd.DataFrame(equity_records)
        eq_df["date"] = pd.to_datetime(eq_df["date"])
        eq_df = eq_df.set_index("date")

        # Daily returns
        daily_returns = eq_df["equity"].pct_change().dropna()

        # Benchmark returns
        if "benchmark" in eq_df.columns and bench_start_price and bench_start_price > 0:
            benchmark_returns = eq_df["benchmark"].pct_change().dropna()
        else:
            benchmark_returns = pd.Series(dtype=float)

        # Trade log DataFrame
        fields = [
            "symbol",
            "entry_date",
            "entry_price",
            "entry_reason",
            "exit_date",
            "exit_price",
            "exit_reason",
            "shares",
            "holding_days",
            "pnl",
            "return_pct",
            "max_favorable",
            "max_adverse",
        ]
        trade_rows = [{f: getattr(t, f) for f in fields} for t in completed_trades]
        trade_log = pd.DataFrame(trade_rows) if trade_rows else pd.DataFrame()

        return EventEngineResult(
            config=self.config,
            start_date=start,
            end_date=end,
            equity_curve=eq_df.reset_index(),
            trade_log=trade_log,
            daily_returns=daily_returns,
            benchmark_returns=benchmark_returns,
            open_positions=list(open_positions.values()),
        )
