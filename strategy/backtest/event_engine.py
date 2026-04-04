"""Event-driven backtest engine with barrier-based exits."""

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd

from afml.bet_sizing import kelly_criterion
from afml.portfolio import hrp
from afml.regime_composite import compute_regime_multiplier
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
    position_sizing: str = "equal"  # "equal" | "signal_weighted" | "kelly" | "hrp"
    transaction_costs: TransactionCosts = field(default_factory=TransactionCosts)
    exit_config: ExitConfig = field(default_factory=ExitConfig)
    benchmark_symbol: str = "SPY"
    # Phase 2: CUSUM / regime / meta-label controls
    cusum_recency_days: int = 5  # days to look back for recent upside CUSUM fire
    meta_label_min_samples: int = 50  # min CUSUM events before meta-label activates
    use_cusum_gate: bool = True  # enable CUSUM entry gate
    use_regime_multiplier: bool = True  # enable 3-layer regime multiplier
    use_meta_labeling: bool = True  # enable rolling meta-label sizing
    # Hard entry filter based on a regime detector.
    # "vix"  — skip all new entries on days where VIX >= 28 (sideways/bear block).
    # None   — no filter applied (default, fully backward-compatible).
    regime_filter: str | None = None


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
    engine_stats: dict = field(default_factory=dict)  # CUSUM/meta trace data for AutoAgent analysis


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
        macro_prices: pd.DataFrame | None = None,
        sentiment_prices: pd.DataFrame | None = None,
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
        returns = close_prices.ffill().pct_change()
        daily_vol = returns.ewm(span=self.config.exit_config.vol_window).std()

        # Compute rebalance dates
        rebalance_dates = self._get_rebalance_dates(trading_days)

        # Pre-compute CUSUM event sets for all symbols (once at startup)
        if self.config.use_cusum_gate:
            cusum_upside_dates, cusum_downside_dates = self._precompute_cusum(
                close_prices
            )
        else:
            cusum_upside_dates = {}
            cusum_downside_dates = {}

        # Prepare macro/sentiment series dicts for regime computation
        macro_series: dict[str, pd.Series] = {}
        sentiment_series: dict[str, pd.Series] = {}
        if macro_prices is not None and self.config.use_regime_multiplier:
            macro_norm = self._normalize_index(macro_prices)
            for col in macro_norm.columns:
                s = macro_norm[col].dropna()
                s.index = pd.to_datetime(s.index)
                macro_series[col] = s
        if sentiment_prices is not None and self.config.use_regime_multiplier:
            sentiment_norm = self._normalize_index(sentiment_prices)
            for col in sentiment_norm.columns:
                s = sentiment_norm[col].dropna()
                s.index = pd.to_datetime(s.index)
                sentiment_series[col] = s

        # VIX hard entry gate — build lookup series once at startup
        _vix_series: pd.Series | None = None
        if self.config.regime_filter == "vix" and sentiment_prices is not None:
            sent_norm = self._normalize_index(sentiment_prices)
            vix_col = "^VIX" if "^VIX" in sent_norm.columns else None
            if vix_col:
                # Shift VIX by 1 day to avoid look-ahead bias: VIX closes after market,
                # so today's entry gate must use yesterday's VIX reading.
                _vix_series = sent_norm[vix_col].shift(1).dropna()
                logger.info(
                    f"VIX hard entry gate active: {len(_vix_series)} VIX observations loaded "
                    f"(lagged 1 day — no look-ahead bias)"
                )
            else:
                logger.warning(
                    "regime_filter='vix' requested but ^VIX not found in sentiment_prices — "
                    "gate will be inactive"
                )

        # Meta-label state (retrained at each rebalance)
        meta_label_clf = None

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

        # --- Trace stats accumulation ---
        _cusum_total = 0      # total new signal candidates across all rebalances
        _cusum_passed = 0     # signals that cleared the CUSUM gate
        _meta_probs: list[float] = []  # P(win) collected per entry
        _vix_rebalances_skipped = 0   # rebalance days blocked by VIX gate
        _vix_rebalances_allowed = 0   # rebalance days allowed through VIX gate

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
                # Look up today's VIX level for the hard entry gate
                vix_today: float | None = None
                if _vix_series is not None:
                    idx = _vix_series.index
                    if today in idx:
                        vix_today = float(_vix_series[today])
                    else:
                        prior = [d for d in idx if d <= today]
                        if prior:
                            vix_today = float(_vix_series[prior[-1]])

                # Compute which symbols had upside CUSUM fire within recency window
                if self.config.use_cusum_gate:
                    recency_cutoff = today - timedelta(
                        days=self.config.cusum_recency_days
                    )
                    upside_cusum = {
                        sym
                        for sym, dates in cusum_upside_dates.items()
                        if any(recency_cutoff <= d <= today for d in dates)
                    }
                else:
                    upside_cusum = set(close_prices.columns)  # allow all

                # Compute regime multiplier for today
                if (
                    self.config.use_regime_multiplier
                    and macro_series
                    and sentiment_series
                ):
                    regime_state = compute_regime_multiplier(
                        macro_series, sentiment_series, today
                    )
                    regime_mult = regime_state.multiplier
                else:
                    regime_mult = 1.0

                # Retrain meta-label model at each rebalance
                if self.config.use_meta_labeling:
                    yesterday = today - timedelta(days=1)
                    meta_label_clf = self._train_meta_label(close_prices, yesterday)

                cash, positions, completed_trades, reb_stats = self._handle_rebalance(
                    today=today,
                    universe=universe,
                    today_open=today_open,
                    cash=cash,
                    positions=positions,
                    completed_trades=completed_trades,
                    upside_cusum=upside_cusum,
                    regime_mult=regime_mult,
                    meta_label_clf=meta_label_clf,
                    close_prices=close_prices,
                    vix_today=vix_today,
                )
                _cusum_total += reb_stats["cusum_total"]
                _cusum_passed += reb_stats["cusum_passed"]
                _meta_probs.extend(reb_stats["meta_probs"])
                _vix_rebalances_skipped += reb_stats.get("vix_rebalances_skipped", 0)
                _vix_rebalances_allowed += reb_stats.get("vix_rebalances_allowed", 0)

            # --- Step C: Mark-to-market at today's CLOSE ---
            for symbol, trade in positions.items():
                if symbol in today_close:
                    current_return = (
                        today_close[symbol] - trade.entry_price
                    ) / trade.entry_price
                    trade.max_favorable = max(trade.max_favorable, current_return)
                    trade.max_adverse = min(trade.max_adverse, current_return)

            # --- Step D: Check exit barriers at today's CLOSE ---
            today_downside = cusum_downside_dates.get("_today_fires_", set())
            if self.config.use_cusum_gate and cusum_downside_dates:
                today_downside = {
                    sym for sym, dates in cusum_downside_dates.items() if today in dates
                }
            new_exits = self.exit_manager.check_exits(
                positions,
                today,
                today_close,
                today_vol,
                cusum_downside=today_downside,
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

        if self.config.regime_filter == "vix" and (_vix_rebalances_skipped + _vix_rebalances_allowed) > 0:
            total_reb = _vix_rebalances_skipped + _vix_rebalances_allowed
            logger.info(
                f"VIX gate summary: {_vix_rebalances_allowed}/{total_reb} rebalance days allowed "
                f"({_vix_rebalances_allowed/total_reb*100:.0f}%), "
                f"{_vix_rebalances_skipped} skipped (VIX >= 28)"
            )

        return self._build_result(
            actual_start,
            actual_end,
            equity_records,
            completed_trades,
            positions,
            bench_start_price,
            engine_stats={
                "cusum_total": _cusum_total,
                "cusum_passed": _cusum_passed,
                "meta_probs": _meta_probs,
                "vix_rebalances_skipped": _vix_rebalances_skipped,
                "vix_rebalances_allowed": _vix_rebalances_allowed,
            },
        )

    def _handle_rebalance(
        self,
        today: date,
        universe: list[str],
        today_open: dict[str, float],
        cash: float,
        positions: dict[str, RoundTripTrade],
        completed_trades: list[RoundTripTrade],
        upside_cusum: set[str] | None = None,
        regime_mult: float = 1.0,
        meta_label_clf=None,
        close_prices: pd.DataFrame | None = None,
        vix_today: float | None = None,
    ) -> tuple[float, dict[str, RoundTripTrade], list[RoundTripTrade], dict]:
        """Process rebalance: exit stale, enter new. Returns (cash, positions, completed, stats)."""
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

        # --- VIX hard entry gate ---
        # When regime_filter="vix", block all new entries on days where VIX >= 28.
        # Existing positions are still managed (exits proceed above); only new entries
        # are suppressed. This isolates alpha to low-volatility bull regime days.
        if self.config.regime_filter == "vix" and vix_today is not None:
            if vix_today >= 28.0:
                logger.debug(
                    f"{today}: VIX={vix_today:.1f} >= 28 — entry gate CLOSED, "
                    f"skipping {len([s for s in signals if s.symbol not in positions])} new entries"
                )
                return cash, positions, completed_trades, {
                    "cusum_total": 0,
                    "cusum_passed": 0,
                    "meta_probs": [],
                    "vix_rebalances_skipped": 1,
                    "vix_rebalances_allowed": 0,
                }
            else:
                logger.debug(f"{today}: VIX={vix_today:.1f} < 28 — entry gate OPEN")

        vix_allowed_stat = 1 if self.config.regime_filter == "vix" and vix_today is not None else 0

        # Enter new positions for symbols not already held
        new_symbols = [s for s in signals if s.symbol not in positions]
        if not new_symbols:
            return cash, positions, completed_trades, {
                "cusum_total": 0,
                "cusum_passed": 0,
                "meta_probs": [],
                "vix_rebalances_skipped": 0,
                "vix_rebalances_allowed": vix_allowed_stat,
            }

        # Compute current equity for weight calculation
        position_value = sum(
            trade.shares * today_open.get(sym, 0.0) for sym, trade in positions.items()
        )
        current_equity = cash + position_value

        # Calculate weights (Kelly uses completed_trades history; HRP uses close_prices)
        weights = self._calculate_weights(
            new_symbols, completed_trades, close_prices=close_prices, as_of_date=today
        )

        # Trace stats: CUSUM gate pass rate and meta-label probabilities
        _reb_cusum_total = 0
        _reb_cusum_passed = 0
        _reb_meta_probs: list[float] = []

        for symbol, weight in weights.items():
            if symbol not in today_open:
                continue
            if len(positions) >= self.config.max_positions:
                break

            # CUSUM entry gate: skip if no recent upside fire
            _reb_cusum_total += 1  # Count all CUSUM gate candidates
            if self.config.use_cusum_gate and upside_cusum is not None:
                if symbol not in upside_cusum:
                    continue

            # Meta-label P(win) — scales position size
            meta_prob = (
                self._get_meta_label_prob(meta_label_clf, close_prices, symbol, today)
                if self.config.use_meta_labeling and close_prices is not None
                else 0.5
            )

            # Cap at max_position_weight, then apply regime_mult and meta_prob
            capped_weight = min(weight, self.config.max_position_weight)
            target_value = (
                capped_weight * current_equity * regime_mult * (meta_prob * 2)
            )
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
            _reb_cusum_passed += 1  # Count only symbols that actually entered
            _reb_meta_probs.append(meta_prob)  # Collect entry P(win) for trace analysis
            positions[symbol] = RoundTripTrade(
                symbol=symbol,
                entry_date=today,
                entry_price=price,
                entry_reason="signal_rebalance",
                shares=shares,
            )

        return cash, positions, completed_trades, {
            "cusum_total": _reb_cusum_total,
            "cusum_passed": _reb_cusum_passed,
            "meta_probs": _reb_meta_probs,
            "vix_rebalances_skipped": 0,
            "vix_rebalances_allowed": vix_allowed_stat,
        }

    def _precompute_cusum(
        self,
        close_prices: pd.DataFrame,
    ) -> tuple[dict[str, set], dict[str, set]]:
        """Pre-compute CUSUM upside and downside fire dates for all symbols.

        Returns
        -------
        upside_dates : dict[str, set[date]]
            Per-symbol set of dates where upside CUSUM fired.
        downside_dates : dict[str, set[date]]
            Per-symbol set of dates where downside CUSUM fired.
        """
        from afml.cusum import cusum_filter

        upside_dates: dict[str, set] = {}
        downside_dates: dict[str, set] = {}

        for symbol in close_prices.columns:
            col = close_prices[symbol].dropna()
            if len(col) < 30:
                upside_dates[symbol] = set()
                downside_dates[symbol] = set()
                continue

            try:
                result = cusum_filter(col)
            except Exception:
                upside_dates[symbol] = set()
                downside_dates[symbol] = set()
                continue

            # Upside fires: cusum_positive drops to 0 from a positive value (reset on event)
            pos = result.cusum_positive
            upside_resets = pos[(pos == 0.0) & (pos.shift(1) > 0)]
            upside_dates[symbol] = {
                pd.Timestamp(ts).date() for ts in upside_resets.index
            }

            # Downside fires: cusum_negative rises to 0 from a negative value
            neg = result.cusum_negative
            downside_resets = neg[(neg == 0.0) & (neg.shift(1) < 0)]
            downside_dates[symbol] = {
                pd.Timestamp(ts).date() for ts in downside_resets.index
            }

        return upside_dates, downside_dates

    def _build_meta_label_features(
        self,
        close_prices: pd.DataFrame,
        as_of: date,
    ):
        """Build features and labels from CUSUM events up to as_of.

        Returns (X, y, label_end_times) DataFrame/Series or None if insufficient.
        Features: trailing_return_20d, trailing_vol_20d, cusum_days_since_fire.
        Labels: triple_barrier outcome (1=win, 0=loss/timeout).
        """
        from afml.cusum import cusum_filter
        from afml.labels import triple_barrier

        all_x, all_y, all_ends = [], [], []

        for symbol in close_prices.columns:
            col = close_prices[symbol].dropna()
            col_ts = col.copy()
            col_ts.index = pd.to_datetime(col_ts.index)
            col_asof = col_ts[col_ts.index <= pd.Timestamp(as_of)]
            if len(col_asof) < 60:
                continue

            try:
                cusum_result = cusum_filter(col_asof)
            except Exception:
                continue

            if len(cusum_result.events) < 5:
                continue

            try:
                tb = triple_barrier(
                    col_asof,
                    events=cusum_result.events,
                    profit_take=self.config.exit_config.profit_take_mult,
                    stop_loss=self.config.exit_config.stop_loss_mult,
                    max_holding=self.config.exit_config.max_holding_days,
                )
            except Exception:
                continue

            for event_time in cusum_result.events:
                if event_time not in col_asof.index:
                    continue
                if event_time not in tb.labels.index:
                    continue

                idx = col_asof.index.get_loc(event_time)
                if idx < 20:
                    continue

                window = col_asof.iloc[max(0, idx - 20) : idx + 1]
                ret_20d = float((window.iloc[-1] / window.iloc[0]) - 1)
                vol_20d = float(window.pct_change().std())

                prior_events = cusum_result.events[cusum_result.events < event_time]
                days_since = (
                    (event_time - prior_events[-1]).days
                    if len(prior_events) > 0
                    else 999
                )

                label = 1 if tb.labels.loc[event_time] == 1 else 0
                exit_time = tb.exit_times.loc[event_time]

                all_x.append(
                    {
                        "trailing_return_20d": ret_20d,
                        "trailing_vol_20d": vol_20d,
                        "cusum_days_since_fire": min(days_since, 999),
                    }
                )
                all_y.append(label)
                all_ends.append(exit_time)

        if len(all_x) < self.config.meta_label_min_samples:
            return None

        return pd.DataFrame(all_x), pd.Series(all_y), pd.Series(all_ends)

    def _train_meta_label(self, close_prices: pd.DataFrame, as_of: date):
        """Train RF meta-label model. Returns fitted model or None if insufficient data."""
        from sklearn.ensemble import RandomForestClassifier

        data = self._build_meta_label_features(close_prices, as_of)
        if data is None:
            return None

        X, y, _ = data
        if y.nunique() < 2:
            return None  # cannot train on single class

        X = X.reset_index(drop=True)
        y = y.reset_index(drop=True)

        clf = RandomForestClassifier(n_estimators=50, random_state=42, n_jobs=1)
        try:
            clf.fit(X, y)
        except Exception:
            return None
        return clf

    def _get_meta_label_prob(
        self,
        clf,
        close_prices: pd.DataFrame,
        symbol: str,
        as_of: date,
    ) -> float:
        """Get P(win) for a symbol. Returns 0.5 (neutral) if model unavailable."""
        if clf is None:
            return 0.5

        if symbol not in close_prices.columns:
            return 0.5

        col = close_prices[symbol].dropna()
        col_ts = col.copy()
        col_ts.index = pd.to_datetime(col_ts.index)
        col_asof = col_ts[col_ts.index <= pd.Timestamp(as_of)]
        if len(col_asof) < 21:
            return 0.5

        from afml.cusum import cusum_filter

        try:
            cusum_result = cusum_filter(col_asof)
        except Exception:
            return 0.5

        idx = len(col_asof) - 1
        window = col_asof.iloc[max(0, idx - 20) : idx + 1]
        ret_20d = float((window.iloc[-1] / window.iloc[0]) - 1)
        vol_20d = float(window.pct_change().std())

        prior = cusum_result.events[cusum_result.events <= pd.Timestamp(as_of)]
        days_since = (pd.Timestamp(as_of) - prior[-1]).days if len(prior) > 0 else 999

        X = pd.DataFrame(
            [
                {
                    "trailing_return_20d": ret_20d,
                    "trailing_vol_20d": vol_20d,
                    "cusum_days_since_fire": min(days_since, 999),
                }
            ]
        )
        try:
            prob = float(clf.predict_proba(X)[0][1])
        except Exception:
            return 0.5
        return prob

    def _kelly_fraction(self, completed_trades: list, lookback: int = 100) -> float:
        """Compute half-Kelly portfolio fraction from recent completed trades.

        Uses afml.kelly_criterion (AFML Chapter 10) for the calculation.
        Returns a fraction in [0.10, 1.0] — the proportion of equity to deploy.
        """
        recent = [t for t in completed_trades[-lookback:] if t.exit_price and t.entry_price > 0]
        if len(recent) < 20:
            return 0.5  # not enough history — deploy 50% of target weight

        pnl_pcts = [(t.exit_price - t.entry_price) / t.entry_price for t in recent]
        wins = [p for p in pnl_pcts if p > 0]
        losses = [abs(p) for p in pnl_pcts if p < 0]

        if not wins or not losses:
            return 0.5

        prob_win = len(wins) / len(pnl_pcts)
        avg_win = sum(wins) / len(wins)
        avg_loss = sum(losses) / len(losses)
        odds = avg_win / avg_loss  # win/loss ratio (b)

        result = kelly_criterion(prob_win=prob_win, odds=odds)
        # half-Kelly clamped to [0.10, 1.0]
        return max(0.10, min(1.0, result.half_kelly))

    def _calculate_weights(
        self,
        signals: list,
        completed_trades: list | None = None,
        close_prices: pd.DataFrame | None = None,
        as_of_date: date | None = None,
    ) -> dict[str, float]:
        """Calculate target weights from signals.

        Sizing modes:
          equal           — 1/N equal weight (baseline)
          signal_weighted — proportional to momentum score
          kelly           — signal-weighted, then scaled by afml half-Kelly fraction
          hrp             — Hierarchical Risk Parity (AFML Chapter 16); uses 60-day
                            return covariance to allocate less to correlated clusters
        """
        if not signals:
            return {}

        n = len(signals)

        if self.config.position_sizing == "signal_weighted":
            total_score = sum(max(0, s.score) for s in signals)
            if total_score > 0:
                return {s.symbol: max(0, s.score) / total_score for s in signals}
            return {s.symbol: 1.0 / n for s in signals}

        if self.config.position_sizing == "kelly":
            # Base: signal-proportional (higher momentum signal → larger slice)
            total_score = sum(max(0, s.score) for s in signals)
            if total_score > 0:
                base = {s.symbol: max(0, s.score) / total_score for s in signals}
            else:
                base = {s.symbol: 1.0 / n for s in signals}

            # Scale the whole portfolio allocation by half-Kelly fraction
            kf = self._kelly_fraction(completed_trades or [])
            return {sym: w * kf for sym, w in base.items()}

        if self.config.position_sizing == "hrp":
            # Hierarchical Risk Parity: use 60-day return covariance to weight
            # assets, allocating less to correlated clusters.
            if close_prices is not None and as_of_date is not None:
                syms = [s.symbol for s in signals if s.symbol in close_prices.columns]
                if len(syms) >= 2:
                    # Locate as_of_date row in the DatetimeIndex
                    idx = close_prices.index
                    if not isinstance(idx, pd.DatetimeIndex):
                        idx = pd.to_datetime(idx)
                        close_prices = close_prices.copy()
                        close_prices.index = idx

                    as_of_ts = pd.Timestamp(as_of_date)
                    pos = idx.get_indexer([as_of_ts], method="pad")[0]
                    start = max(0, pos - 59)  # 60-day window
                    price_slice = close_prices.iloc[start : pos + 1][syms]
                    # Log returns for HRP covariance: more symmetric, additive over
                    # time, less skewed by large moves (e.g. NVDA +300% outliers).
                    # P&L accounting elsewhere stays on simple returns.
                    import numpy as np
                    returns = np.log(price_slice / price_slice.shift(1)).dropna()
                    # Drop columns with any NaN (symbol missing data in window)
                    returns = returns.dropna(axis=1, how="any")

                    if len(returns) >= 20 and len(returns.columns) >= 2:
                        try:
                            hrp_result = hrp(returns)
                            # Re-align to the full signal list (missing = 0)
                            weights = {s.symbol: float(hrp_result.weights.get(s.symbol, 0.0)) for s in signals}
                            total = sum(weights.values())
                            if total > 0:
                                return {sym: w / total for sym, w in weights.items()}
                        except Exception as e:
                            logger.debug("HRP failed, falling back to equal weight: %s", e)

            # Fallback: equal weight if HRP can't run
            return {s.symbol: 1.0 / n for s in signals}

        # Default: equal weight
        return {s.symbol: 1.0 / n for s in signals}

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
            engine_stats={},
        )

    def _build_result(
        self,
        start: date,
        end: date,
        equity_records: list[dict],
        completed_trades: list[RoundTripTrade],
        open_positions: dict[str, RoundTripTrade],
        bench_start_price: float | None,
        engine_stats: dict | None = None,
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
            engine_stats=engine_stats or {},
        )
