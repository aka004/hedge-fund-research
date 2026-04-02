"""Exit management with barrier-based exits for the event-driven engine."""

from dataclasses import dataclass
from datetime import date

from strategy.backtest.portfolio import RoundTripTrade


@dataclass
class ExitSignal:
    """Emitted when a barrier is breached. Queued for next-day execution."""

    symbol: str
    reason: str  # "profit_target" | "stop_loss" | "timeout"
    trigger_date: date  # day barrier was breached (at close)
    trigger_price: float  # close price on trigger day


@dataclass
class ExitConfig:
    """Configuration for barrier-based exits."""

    profit_take_mult: float = 2.0  # x daily vol
    stop_loss_mult: float = 2.0  # x daily vol
    max_holding_days: int = 21  # timeout
    vol_window: int = 100  # EWMA span for daily vol
    use_cusum_reversal: bool = True  # enable CUSUM reversal exit (priority 2)


class ExitManager:
    """Checks open positions daily and emits ExitSignals when barriers are breached.

    Barrier computation:
        upper = entry_price * (1 + profit_take_mult * current_daily_vol)
        lower = entry_price * (1 - stop_loss_mult * current_daily_vol)

    Barriers are recomputed daily using rolling vol (not frozen at entry).

    Check priority: profit target > stop loss > timeout.
    If a volatile day touches both barriers, profit target wins.
    """

    def __init__(self, config: ExitConfig) -> None:
        self.config = config

    def check_exits(
        self,
        positions: dict[str, RoundTripTrade],
        today: date,
        prices: dict[str, float],
        vol: dict[str, float],
        cusum_downside: set[str] | None = None,
    ) -> list[ExitSignal]:
        """Check all open positions for barrier breaches.

        Args:
            positions: Currently open positions keyed by symbol.
            today: Current date (close of day).
            prices: Today's close prices per symbol.
            vol: Today's daily volatility per symbol.
            cusum_downside: Symbols where downside CUSUM fired today.

        Returns:
            List of ExitSignals for positions that breached a barrier.

        Priority: profit_target > cusum_reversal > stop_loss > timeout.
        """
        if cusum_downside is None:
            cusum_downside = set()

        signals: list[ExitSignal] = []

        for symbol, trade in positions.items():
            if symbol not in prices:
                continue

            close_price = prices[symbol]
            daily_vol = vol.get(symbol, 0.0)

            # Compute dynamic barriers
            upper = trade.entry_price * (1.0 + self.config.profit_take_mult * daily_vol)
            lower = trade.entry_price * (1.0 - self.config.stop_loss_mult * daily_vol)

            # Check order: profit_target > cusum_reversal > stop_loss > timeout
            if close_price >= upper:
                signals.append(
                    ExitSignal(
                        symbol=symbol,
                        reason="profit_target",
                        trigger_date=today,
                        trigger_price=close_price,
                    )
                )
            elif self.config.use_cusum_reversal and symbol in cusum_downside:
                signals.append(
                    ExitSignal(
                        symbol=symbol,
                        reason="cusum_reversal",
                        trigger_date=today,
                        trigger_price=close_price,
                    )
                )
            elif close_price <= lower:
                signals.append(
                    ExitSignal(
                        symbol=symbol,
                        reason="stop_loss",
                        trigger_date=today,
                        trigger_price=close_price,
                    )
                )
            elif self._is_timed_out(trade, today):
                signals.append(
                    ExitSignal(
                        symbol=symbol,
                        reason="timeout",
                        trigger_date=today,
                        trigger_price=close_price,
                    )
                )

        return signals

    def _is_timed_out(self, trade: RoundTripTrade, today: date) -> bool:
        """Check if trade has exceeded max holding days."""
        holding_days = (today - trade.entry_date).days
        return holding_days >= self.config.max_holding_days
