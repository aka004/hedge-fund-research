"""Event-ordered backtest engine for Prediction Market Surprise Alpha.

Simulates per-event PEAD (Post-Earnings Announcement Drift) trades using fixed
percentage barriers: +2% profit target, -1% stop loss, T+5 timeout.

Key difference from EventDrivenEngine:
- Iterates over EVENTS (not calendar days)
- Fixed percentage barriers (not vol-scaled)
- One position per event_id
- Long-only (bearish surprises skipped)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd

from data.providers.prediction_market import EventRecord
from strategy.backtest.portfolio import TransactionCosts


@dataclass
class SurpriseBacktestConfig:
    """Configuration for the EventBacktestEngine."""

    initial_capital: float = 100_000.0
    position_size_pct: float = 0.05
    profit_take_pct: float = 0.02
    stop_loss_pct: float = 0.01
    max_holding_days: int = 5
    max_concurrent_positions: int = 10
    min_surprise_bits: float = 4.0
    transaction_costs: TransactionCosts = field(default_factory=TransactionCosts)


@dataclass
class SurpriseBacktestResult:
    """Results from a completed EventBacktestEngine run."""

    config: SurpriseBacktestConfig
    equity_curve: pd.DataFrame
    trade_log: pd.DataFrame
    event_returns: pd.Series
    daily_returns: pd.Series
    open_positions: list
    n_events_total: int
    n_events_traded: int
    n_events_filtered: int


class EventBacktestEngine:
    """Event-ordered backtest engine for Prediction Market Surprise Alpha.

    Iterates over EventRecord objects sorted by event_date.
    Enters positions at T+1 open after event resolution.
    Exits via fixed barriers: +2% profit, -1% stop, T+5 timeout.
    """

    def __init__(
        self,
        config: SurpriseBacktestConfig,
        price_data: dict[str, pd.DataFrame],
    ) -> None:
        self._config = config
        self._prices = price_data
        self._price_index: dict[str, pd.DataFrame] = {}

    def run(
        self,
        events: list[EventRecord],
        start_date: date,
        end_date: date,
    ) -> SurpriseBacktestResult:
        """Run backtest over provided events."""
        filtered, tradeable = self._filter_events(events, start_date, end_date)
        n_total = len(events)
        n_filtered = n_total - len(tradeable)

        self._build_price_index(tradeable)

        trading_days = self._get_trading_days(start_date, end_date)
        events_by_entry_date = self._group_events_by_entry_date(tradeable)

        capital = self._config.initial_capital
        open_positions: list[dict] = []
        closed_positions: list[dict] = []
        equity_rows: list[dict] = []
        n_events_traded = 0
        entered_event_ids: set[str] = set()

        for today in trading_days:
            # Enter new positions: events that resolved on (today - 1)
            entry_events = events_by_entry_date.get(today, [])
            for event in entry_events:
                if event.event_id in entered_event_ids:
                    continue  # Skip duplicate
                if len(open_positions) >= self._config.max_concurrent_positions:
                    n_filtered += 1
                    continue
                entry_price = self._get_price(event.symbol, today, "open")
                if entry_price is None:
                    n_filtered += 1
                    continue
                pos = self._enter_position(event, entry_price, today, capital)
                if pos is not None:
                    cost = pos["shares"] * pos["entry_price"]
                    commission, slippage = self._config.transaction_costs.calculate(
                        pos["shares"], pos["entry_price"]
                    )
                    capital -= cost + commission + slippage
                    pos["entry_commission"] = commission + slippage
                    open_positions.append(pos)
                    entered_event_ids.add(event.event_id)
                    n_events_traded += 1
                else:
                    n_filtered += 1

            # Check exit barriers at today's close
            still_open: list[dict] = []
            for pos in open_positions:
                close_price = self._get_price(pos["symbol"], today, "close")
                if close_price is None:
                    still_open.append(pos)
                    continue
                self._update_mfe_mae(pos, close_price)
                exit_reason = self._check_barriers(pos, close_price, today)
                if exit_reason:
                    commission, slippage = self._config.transaction_costs.calculate(
                        pos["shares"], close_price
                    )
                    proceeds = pos["shares"] * close_price - commission - slippage
                    capital += proceeds
                    pos["exit_date"] = today
                    pos["exit_price"] = close_price
                    pos["exit_reason"] = exit_reason
                    pos["exit_commission"] = commission + slippage
                    closed_positions.append(pos)
                else:
                    still_open.append(pos)
            open_positions = still_open

            # Mark-to-market equity
            mtm_value = capital
            for pos in open_positions:
                close_price = self._get_price(pos["symbol"], today, "close")
                if close_price is not None:
                    mtm_value += pos["shares"] * close_price
                else:
                    mtm_value += pos["shares"] * pos["entry_price"]

            equity_rows.append(
                {
                    "date": today,
                    "equity": mtm_value,
                    "n_active_positions": len(open_positions),
                }
            )

        # Force-close remaining positions at end_date close
        for pos in open_positions:
            close_price = (
                self._get_price(pos["symbol"], end_date, "close") or pos["entry_price"]
            )
            commission, slippage = self._config.transaction_costs.calculate(
                pos["shares"], close_price
            )
            proceeds = pos["shares"] * close_price - commission - slippage
            capital += proceeds
            pos["exit_date"] = end_date
            pos["exit_price"] = close_price
            pos["exit_reason"] = "timeout"
            pos["exit_commission"] = commission + slippage
            closed_positions.append(pos)

        equity_curve = (
            pd.DataFrame(equity_rows)
            if equity_rows
            else pd.DataFrame(columns=["date", "equity", "n_active_positions"])
        )
        trade_log = self._build_trade_log(closed_positions)
        event_returns = self._build_event_returns(closed_positions)
        daily_returns = self._build_daily_returns(equity_curve)

        return SurpriseBacktestResult(
            config=self._config,
            equity_curve=equity_curve,
            trade_log=trade_log,
            event_returns=event_returns,
            daily_returns=daily_returns,
            open_positions=open_positions,
            n_events_total=n_total,
            n_events_traded=n_events_traded,
            n_events_filtered=n_filtered,
        )

    def _filter_events(
        self,
        events: list[EventRecord],
        start_date: date,
        end_date: date,
    ) -> tuple[list[EventRecord], list[EventRecord]]:
        """Separate events into filtered-out and tradeable lists."""
        filtered: list[EventRecord] = []
        tradeable: list[EventRecord] = []
        for event in events:
            if not self._passes_filters(event, start_date, end_date):
                filtered.append(event)
            else:
                tradeable.append(event)
        tradeable.sort(key=lambda e: e.event_date)
        return filtered, tradeable

    def _passes_filters(
        self, event: EventRecord, start_date: date, end_date: date
    ) -> bool:
        """Return True if the event passes all entry filters."""
        if not event.outcome_confirmed:
            return False
        if event.direction != 1:
            return False
        if not event.liquidity_ok:
            return False
        if event.surprise_score is None:
            return False
        if event.surprise_score < self._config.min_surprise_bits:
            return False
        if event.event_date < start_date or event.event_date > end_date:
            return False
        return True

    def _build_price_index(self, events: list[EventRecord]) -> None:
        """Pre-index price DataFrames by date for fast lookup."""
        symbols = {e.symbol for e in events}
        for symbol in symbols:
            if symbol in self._prices:
                df = self._prices[symbol].copy()
                if "date" in df.columns:
                    df = df.set_index("date")
                self._price_index[symbol] = df

    def _get_trading_days(self, start_date: date, end_date: date) -> list[date]:
        """Return weekdays in [start_date, end_date]."""
        days: list[date] = []
        current = start_date
        while current <= end_date:
            if current.weekday() < 5:
                days.append(current)
            current += timedelta(days=1)
        return days

    def _group_events_by_entry_date(
        self, events: list[EventRecord]
    ) -> dict[date, list[EventRecord]]:
        """Map T+1 entry date → list of events resolved on T."""
        result: dict[date, list[EventRecord]] = {}
        for event in events:
            entry_date = self._next_trading_day(event.event_date)
            result.setdefault(entry_date, []).append(event)
        return result

    def _next_trading_day(self, from_date: date) -> date:
        """Return the next weekday after from_date."""
        next_day = from_date + timedelta(days=1)
        while next_day.weekday() >= 5:
            next_day += timedelta(days=1)
        return next_day

    def _enter_position(
        self,
        event: EventRecord,
        entry_price: float,
        entry_date: date,
        capital: float,
    ) -> dict | None:
        """Attempt to enter a long position for an event."""
        if math.isnan(entry_price) or entry_price <= 0:
            return None
        position_value = capital * self._config.position_size_pct
        shares = math.floor(position_value / entry_price)
        if shares <= 0:
            return None
        cost = shares * entry_price
        commission, slippage = self._config.transaction_costs.calculate(
            shares, entry_price
        )
        if cost + commission + slippage > capital:
            return None

        profit_target = entry_price * (1 + self._config.profit_take_pct)
        stop_loss = entry_price * (1 - self._config.stop_loss_pct)
        max_holding_date = entry_date + timedelta(
            days=self._config.max_holding_days - 1
        )

        return {
            "event_id": event.event_id,
            "symbol": event.symbol,
            "entry_date": entry_date,
            "entry_price": entry_price,
            "shares": shares,
            "direction": 1,
            "surprise_score": event.surprise_score,
            "profit_target": profit_target,
            "stop_loss": stop_loss,
            "max_holding_date": max_holding_date,
            "max_favorable": 0.0,
            "max_adverse": 0.0,
        }

    def _check_barriers(
        self, position: dict, today_close: float, today: date
    ) -> str | None:
        """Check if any exit barrier is hit. Priority: profit > stop > timeout."""
        if today_close >= position["profit_target"]:
            return "profit_target"
        if today_close <= position["stop_loss"]:
            return "stop_loss"
        if today >= position["max_holding_date"]:
            return "timeout"
        return None

    def _update_mfe_mae(self, position: dict, today_close: float) -> None:
        """Update max favorable excursion and max adverse excursion."""
        entry = position["entry_price"]
        ret = (today_close - entry) / entry
        if ret > position["max_favorable"]:
            position["max_favorable"] = ret
        if ret < position["max_adverse"]:
            position["max_adverse"] = ret

    def _get_price(
        self, symbol: str, price_date: date, price_type: str
    ) -> float | None:
        """Look up a price for a symbol on a date."""
        df = self._price_index.get(symbol)
        if df is None:
            return None
        try:
            value = df.loc[price_date, price_type]
            if math.isnan(float(value)) or float(value) == 0:
                return None
            return float(value)
        except (KeyError, TypeError, ValueError):
            return None

    def _build_trade_log(self, closed_positions: list[dict]) -> pd.DataFrame:
        """Build trade_log DataFrame from closed positions."""
        if not closed_positions:
            return pd.DataFrame(
                columns=[
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
                    "event_id",
                    "surprise_score",
                ]
            )
        rows = []
        for pos in closed_positions:
            entry_price = pos["entry_price"]
            exit_price = pos["exit_price"]
            shares = pos["shares"]
            holding_days = (pos["exit_date"] - pos["entry_date"]).days
            total_costs = pos.get("entry_commission", 0) + pos.get("exit_commission", 0)
            pnl = (exit_price - entry_price) * shares - total_costs
            return_pct = (
                pnl / (entry_price * shares) if entry_price and shares else None
            )
            rows.append(
                {
                    "symbol": pos["symbol"],
                    "entry_date": pos["entry_date"],
                    "entry_price": entry_price,
                    "entry_reason": "surprise_alpha",
                    "exit_date": pos["exit_date"],
                    "exit_price": exit_price,
                    "exit_reason": pos["exit_reason"],
                    "shares": shares,
                    "holding_days": holding_days,
                    "pnl": pnl,
                    "return_pct": return_pct,
                    "max_favorable": pos["max_favorable"],
                    "max_adverse": pos["max_adverse"],
                    "event_id": pos["event_id"],
                    "surprise_score": pos["surprise_score"],
                }
            )
        return pd.DataFrame(rows)

    def _build_event_returns(self, closed_positions: list[dict]) -> pd.Series:
        """Build event_returns Series indexed by event_id."""
        if not closed_positions:
            return pd.Series(dtype=float)
        data = {}
        for pos in closed_positions:
            ep = pos["entry_price"]
            xp = pos["exit_price"]
            ret = (xp - ep) / ep if ep else float("nan")
            data[pos["event_id"]] = ret
        return pd.Series(data)

    def _build_daily_returns(self, equity_curve: pd.DataFrame) -> pd.Series:
        """Build daily_returns Series from equity_curve."""
        if equity_curve.empty or len(equity_curve) < 2:
            return pd.Series(dtype=float)
        eq = equity_curve.set_index("date")["equity"]
        return eq.pct_change().dropna()
