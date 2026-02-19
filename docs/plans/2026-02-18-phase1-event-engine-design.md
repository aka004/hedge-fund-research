# Phase 1: Event-Driven Backtest Engine — Design Doc

**Created:** 2026-02-18
**Status:** APPROVED
**Parent:** [Unified Roadmap](2026-02-18-unified-backtest-roadmap.md) Phase 1

---

## Goal

Build an `EventDrivenEngine` that tracks individual trades from entry to exit with reasons, runs daily mark-to-market, handles mid-period barrier exits, and produces a complete trade log for downstream analysis.

The existing `BacktestEngine` (rebalance-only) stays untouched.

---

## Decision Log (from brainstorm)

| Parameter | Decision | Rationale |
|-----------|----------|-----------|
| Exit execution price | Next-day open | Detect breach at close, execute next morning. No look-ahead. |
| Engine architecture | New `EventDrivenEngine` alongside existing | Clean separation. No risk to working pipeline. |
| Barrier params | Independent from labeling config | Labeling can use tight barriers for training; live uses wider. |
| Live `max_holding_days` | 21 days | Clears flat trades after ~1 month. Stop loss handles losers. |
| Cash after mid-period exit | Wait for next rebalance | Avoids overtrading. Entries = signal-driven, exits = barrier-driven. |
| Max single position weight | 10% of equity | Prevents concentration risk. |
| Daily step mode | Trading days only | Step on days with price data. No holiday calendar needed. |
| Re-entry after exit | Allowed immediately | Each entry is independent. Re-enter at next rebalance if signal persists. |
| Benchmark | SPY | Track SPY equity alongside strategy. |
| Barrier volatility | Rolling (dynamic) | Recompute barriers daily with current vol. Adapts to regime changes. |

---

## Data Model

### RoundTripTrade (new dataclass in `portfolio.py`)

Tracks full lifecycle of a position from entry to exit.

```
symbol: str
entry_date: date
entry_price: float           # open price on entry day
entry_reason: str            # "signal_rebalance" | "cusum_event" (Phase 2)
exit_date: date | None
exit_price: float | None     # open price on day AFTER barrier breach
exit_reason: str | None      # "profit_target" | "stop_loss" | "timeout" | "rebalance_out"
shares: float
max_favorable: float         # best unrealized return during hold (MFE)
max_adverse: float           # worst unrealized return during hold (MAE)
```

Computed properties: `holding_days`, `pnl`, `return_pct`.

The existing `Trade` dataclass (single buy/sell execution) is unchanged.

### ExitSignal (new dataclass in `exit_manager.py`)

Emitted when a barrier is breached. Queued for next-day execution.

```
symbol: str
reason: str                  # "profit_target" | "stop_loss" | "timeout"
trigger_date: date           # day barrier was breached (at close)
trigger_price: float         # close price on trigger day
```

---

## Components

### 1. ExitManager (`strategy/backtest/exit_manager.py` — NEW)

Single responsibility: check open positions daily, emit `ExitSignal`s.

**ExitConfig:**
```
profit_take_mult: float = 2.0      # x daily vol
stop_loss_mult: float = 2.0        # x daily vol
max_holding_days: int = 21         # timeout
vol_window: int = 100              # EWMA span for daily vol
```

**Barrier computation:**
- `upper = entry_price * (1 + profit_take_mult * current_daily_vol)`
- `lower = entry_price * (1 - stop_loss_mult * current_daily_vol)`
- Barriers recomputed daily using rolling vol (not frozen at entry).

**Check order:** profit target > stop loss > timeout.
If a volatile day touches both barriers, profit target wins (conservative).

**Interface:**
```python
class ExitManager:
    def __init__(self, config: ExitConfig) -> None
    def check_exits(
        self,
        positions: dict[str, RoundTripTrade],
        today: date,
        prices: dict[str, float],       # today's close prices
        vol: dict[str, float],           # today's daily vol per symbol
    ) -> list[ExitSignal]
```

### 2. EventDrivenEngine (`strategy/backtest/event_engine.py` — NEW)

Daily-step engine. Creates positions at rebalance via signals, exits via barriers.

**EventEngineConfig:**
```
initial_capital: float = 100_000.0
max_positions: int = 20
max_position_weight: float = 0.10   # 10% cap
rebalance_frequency: str = "monthly"
position_sizing: str = "equal"       # "equal" | "signal_weighted"
transaction_costs: TransactionCosts
exit_config: ExitConfig
benchmark_symbol: str = "SPY"
```

**EventEngineResult:**
```
config: EventEngineConfig
start_date: date
end_date: date
equity_curve: pd.DataFrame    # daily: date, equity, cash, positions, benchmark
trade_log: pd.DataFrame       # completed RoundTripTrade rows
daily_returns: pd.Series
benchmark_returns: pd.Series
open_positions: list[RoundTripTrade]  # still open at backtest end
```

**Daily loop (pseudocode):**
```
for each trading_day in price_index:

    Step A — Execute yesterday's queued exits at today's OPEN
        For each pending ExitSignal:
            open_price = today's open for that symbol
            Complete the RoundTripTrade (set exit_date, exit_price, exit_reason)
            Add sale proceeds (minus costs) to cash
            Move trade to completed list

    Step B — If rebalance day, enter new positions at today's OPEN
        Generate signals using data through YESTERDAY (no look-ahead)
        Calculate target weights (capped at max_position_weight)
        For each target symbol NOT already in portfolio:
            Compute shares from weight * equity / open_price
            Deduct cost from cash
            Create new RoundTripTrade with entry_reason="signal_rebalance"
        For each held symbol NOT in new target set:
            Queue exit with reason="rebalance_out" (immediate, not next-day)

    Step C — Mark-to-market at today's CLOSE
        Update all position current_prices
        Update MFE/MAE on each open RoundTripTrade

    Step D — Check exit barriers at today's CLOSE
        pending_exits = exit_manager.check_exits(positions, today, close_prices, vol)
        These execute tomorrow (Step A of next iteration)

    Step E — Record daily equity snapshot
        equity = cash + sum(position market values at close)
        Record: date, equity, cash, position_count, benchmark_close
```

**Price loading:**
- All prices loaded upfront as a `date x symbol` DataFrame (close prices).
- Open prices loaded separately as a `date x symbol` DataFrame.
- Daily vol computed as EWMA of returns with `vol_window` span.
- SPY loaded separately for benchmark tracking.

**Entry signals use yesterday's data:**
- `signal_combiner.get_top_picks(universe, as_of_date=yesterday)` on rebalance days.
- Execution at today's open. This is the standard "signal at close, trade at next open" pattern.

**Rebalance-out exits:**
- When a symbol drops out of the signal set at rebalance, it exits immediately at today's open (same execution pass as entries). No next-day delay since the decision is made pre-market.

### 3. Updated PerformanceMetrics (`analysis/metrics.py` — EDIT)

New function `calculate_trade_metrics(trade_log: pd.DataFrame)` that computes:

```
total_trades: int
win_rate: float              # % of trades with pnl > 0
profit_factor: float         # gross_wins / gross_losses
avg_win: float               # mean return of winners
avg_loss: float              # mean return of losers
avg_holding_days: float
median_holding_days: float
max_favorable_avg: float     # mean MFE across all trades
max_adverse_avg: float       # mean MAE across all trades
exit_breakdown: dict         # {"profit_target": 0.35, "stop_loss": 0.25, ...}
```

The existing `calculate_metrics()` function stays unchanged.

---

## File Plan

| File | Action | Changes |
|------|--------|---------|
| `strategy/backtest/portfolio.py` | Edit | Add `RoundTripTrade` dataclass |
| `strategy/backtest/exit_manager.py` | New | `ExitConfig`, `ExitSignal`, `ExitManager` |
| `strategy/backtest/event_engine.py` | New | `EventEngineConfig`, `EventEngineResult`, `EventDrivenEngine` |
| `analysis/metrics.py` | Edit | Add `calculate_trade_metrics()` |
| `strategy/backtest/__init__.py` | Edit | Export new classes |
| `tests/test_event_engine.py` | New | Tests for `ExitManager` + `EventDrivenEngine` |

**Not touched:** `engine.py`, `backtest_runner.py`, `agents/`, `afml/`.

---

## Implementation Sequence

Build in this order (each step testable independently):

1. **`RoundTripTrade`** in `portfolio.py` — pure dataclass, no dependencies
2. **`ExitManager`** in `exit_manager.py` — depends only on `RoundTripTrade`
3. **`ExitManager` tests** — unit test barrier logic with synthetic prices
4. **`EventDrivenEngine`** in `event_engine.py` — wires everything together
5. **`EventDrivenEngine` tests** — integration test with small universe
6. **`calculate_trade_metrics()`** in `metrics.py` — operates on trade log DataFrame
7. **Export updates** in `__init__.py`

---

## Test Strategy

### ExitManager unit tests
- Profit target hit: price crosses upper barrier → emits signal
- Stop loss hit: price crosses lower barrier → emits signal
- Timeout: holding period exceeds max_holding_days → emits signal
- No exit: price within barriers and under timeout → no signal
- Priority: price crosses both barriers same day → profit_target wins
- Rolling vol: barriers widen when vol increases

### EventDrivenEngine integration tests
- Synthetic 3-symbol universe, 60 trading days
- Verify entries happen only on rebalance dates at open prices
- Verify exits happen at next-day open after barrier breach
- Verify daily equity curve has an entry for every trading day
- Verify cash increases on exit, decreases on entry
- Verify trade log has correct entry/exit reasons
- Verify MFE/MAE tracked correctly
- Verify position weight cap (10%) enforced
- Verify SPY benchmark tracked in equity curve

### Trade metrics tests
- Known trade log → verify win_rate, profit_factor, exit_breakdown

---

## Open Questions (deferred to Phase 2)

- CUSUM event generation replaces rebalance-based entries
- Meta-labeling scales position sizes
- Kelly x HRP determines allocation weights
- These are Phase 2 integration points — the engine's `entry_reason` and position sizing are designed to accommodate them.
