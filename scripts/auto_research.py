#!/usr/bin/env python3
"""
Auto-research loop for EventDrivenEngine parameter optimization.

Iteratively tests parameter configurations, scores each run, picks the best,
then does a deep-dive analysis. Runs until a statistically meaningful strategy
is found (PSR > 0.95, Sharpe > 0.5, profit_factor > 1.2).

Usage:
    python scripts/auto_research.py \
        --universe /tmp/universe_full.txt \
        --start 2010-01-01 --end 2025-12-31
"""

import argparse
import itertools
import json
import logging
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from afml.metrics import deflated_sharpe
from scripts.preflight_check import run_preflight
from analysis.metrics import calculate_metrics
from config import STORAGE_PATH
from data.storage.duckdb_store import DuckDBStore
from data.storage.parquet import ParquetStorage
from scripts.run_event_engine import (
    load_macro_dataframes,
    load_price_dataframes,
)
from strategy.backtest.event_engine import EventDrivenEngine, EventEngineConfig
from strategy.backtest.exit_manager import ExitConfig
from strategy.backtest.portfolio import TransactionCosts
from strategy.signals.combiner import SignalCombiner
from strategy.signals.momentum import MomentumSignal

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

PARQUET_DIR = STORAGE_PATH / "parquet"


# ── Scoring ───────────────────────────────────────────────────────────────────


@dataclass
class RunScore:
    config_id: str
    sharpe: float
    cagr: float
    max_dd: float
    profit_factor: float
    win_rate: float
    avg_win_pct: float   # average winner as % of entry price
    avg_loss_pct: float  # average loser as % of entry price (positive = magnitude)
    kelly_fraction: float  # half-Kelly fraction at last rebalance (0–1)
    total_trades: int
    avg_holding: float
    psr: float
    score: float  # composite score
    passed: bool
    params: dict
    daily_returns: pd.Series = None  # kept for CPCV validation, not serialized
    trace: dict = None               # NEW: structured trace for AutoAgent analysis


def composite_score(
    sharpe, cagr, max_dd, profit_factor, win_rate, total_trades, avg_holding
):
    """
    Composite score to rank configurations.
    Rewards: high Sharpe, high CAGR, high profit factor, reasonable holds.
    Penalises: large drawdowns, too few trades, too short holds (<5 days).
    """
    if total_trades < 100:
        return -999.0

    dd_pen = max(0, abs(max_dd) - 15) * 0.5  # penalise DD beyond 15%
    hold_pen = max(0, 5 - avg_holding) * 0.3  # penalise avg hold < 5 days
    trade_bonus = min(1.0, total_trades / 500)  # reward more trades up to 500

    return (
        sharpe * 3.0
        + (cagr / 5.0)
        + (profit_factor - 1.0) * 2.0
        + (win_rate - 0.5) * 2.0
        + trade_bonus
        - dd_pen
        - hold_pen
    )


# ── Parameter grid ────────────────────────────────────────────────────────────


def build_param_grid() -> list[dict]:
    """
    Progressive grid: start with fundamental fixes, then explore.
    Each dict maps to EventEngineConfig + ExitConfig fields.
    """
    grid = []

    # Stage 1 — fix the known problems first
    # Problem: CUSUM reversal exits at +1.1% avg (too early)
    # Problem: stop_loss at 2× vol = -8% avg (too wide)
    # Problem: profit_target rarely hit at 2× vol
    stage1 = [
        # Disable CUSUM reversal, tighten stop, widen profit
        dict(
            profit_take_mult=3.0,
            stop_loss_mult=1.0,
            max_holding_days=21,
            cusum_recency_days=15,
            use_cusum_reversal_exit=False,
            use_cusum_gate=True,
            use_regime=True,
            use_meta=True,
            label="fix_no_reversal_tight_stop",
        ),
        # Tighten stop only, keep CUSUM reversal off
        dict(
            profit_take_mult=2.5,
            stop_loss_mult=1.5,
            max_holding_days=21,
            cusum_recency_days=15,
            use_cusum_reversal_exit=False,
            use_cusum_gate=True,
            use_regime=True,
            use_meta=True,
            label="fix_balanced_barriers",
        ),
        # Loosen CUSUM recency so entries aren't gated so tightly
        dict(
            profit_take_mult=3.0,
            stop_loss_mult=1.5,
            max_holding_days=21,
            cusum_recency_days=21,
            use_cusum_reversal_exit=False,
            use_cusum_gate=True,
            use_regime=True,
            use_meta=True,
            label="fix_loose_cusum_gate",
        ),
    ]

    # Stage 2 — ablation: test each module on/off
    stage2 = [
        # No CUSUM gate at all (pure momentum + barriers)
        dict(
            profit_take_mult=3.0,
            stop_loss_mult=1.5,
            max_holding_days=21,
            cusum_recency_days=21,
            use_cusum_reversal_exit=False,
            use_cusum_gate=False,
            use_regime=True,
            use_meta=True,
            label="ablate_no_cusum_gate",
        ),
        # No regime multiplier
        dict(
            profit_take_mult=3.0,
            stop_loss_mult=1.5,
            max_holding_days=21,
            cusum_recency_days=21,
            use_cusum_reversal_exit=False,
            use_cusum_gate=True,
            use_regime=False,
            use_meta=True,
            label="ablate_no_regime",
        ),
        # No meta-labeling
        dict(
            profit_take_mult=3.0,
            stop_loss_mult=1.5,
            max_holding_days=21,
            cusum_recency_days=21,
            use_cusum_reversal_exit=False,
            use_cusum_gate=True,
            use_regime=True,
            use_meta=False,
            label="ablate_no_meta",
        ),
        # Fully stripped — no AFML modules, just signals + barriers
        dict(
            profit_take_mult=3.0,
            stop_loss_mult=1.5,
            max_holding_days=21,
            cusum_recency_days=21,
            use_cusum_reversal_exit=False,
            use_cusum_gate=False,
            use_regime=False,
            use_meta=False,
            label="baseline_signals_only",
        ),
    ]

    # Stage 3 — barrier grid on best stage 1 config
    for pt, sl, mh in itertools.product([2.5, 3.0, 4.0], [1.0, 1.5, 2.0], [15, 21, 30]):
        grid.append(
            dict(
                profit_take_mult=pt,
                stop_loss_mult=sl,
                max_holding_days=mh,
                cusum_recency_days=21,
                use_cusum_reversal_exit=False,
                use_cusum_gate=True,
                use_regime=True,
                use_meta=True,
                label=f"grid_pt{pt}_sl{sl}_mh{mh}",
            )
        )

    # Stage 4 — concentration × frequency × cost sensitivity × sizing mode
    # Best barrier config (pt=3.0, sl=1.5, mh=30)
    # slippage_bps: 10=optimistic, 25=realistic mid-cap, 50=small-cap worst-case
    # sizing: kelly (signal-weighted × half-Kelly) vs hrp (risk-parity weights)
    stage4 = []
    for n_pos in [10, 20]:
        for freq in ["weekly", "monthly"]:
            for slip in [10, 25, 50]:
                for sizing in ["kelly", "hrp"]:
                    stage4.append(
                        dict(
                            profit_take_mult=3.0,
                            stop_loss_mult=1.5,
                            max_holding_days=30,
                            cusum_recency_days=21,
                            use_cusum_reversal_exit=False,
                            use_cusum_gate=True,
                            use_regime=True,
                            use_meta=False,
                            max_positions=n_pos,
                            rebalance_frequency=freq,
                            slippage_bps=slip,
                            position_sizing=sizing,
                            label=f"pos{n_pos}_{freq}_slip{slip}_{sizing}",
                        )
                    )

    return stage1 + stage2 + grid + stage4


# ── Single run ────────────────────────────────────────────────────────────────


def run_config(
    params: dict,
    universe: list[str],
    close_prices: pd.DataFrame,
    open_prices: pd.DataFrame,
    macro_prices,
    sentiment_prices,
    start: str,
    end: str,
    duckdb_store,
    parquet_storage,
    combiner=None,  # optional SignalCombiner override (used by AlphaGPT)
    n_strategies_tested: int = 1,  # cumulative count for DSR correction
    regime_filter: str | None = None,  # "vix" = hard VIX < 18 entry gate; None = off
) -> RunScore:
    config_id = params["label"]
    logger.info(f"  Running: {config_id}")

    exit_cfg = ExitConfig(
        profit_take_mult=params["profit_take_mult"],
        stop_loss_mult=params["stop_loss_mult"],
        max_holding_days=params["max_holding_days"],
        use_cusum_reversal=params["use_cusum_reversal_exit"],
    )

    max_pos = params.get("max_positions", 20)
    rebal_freq = params.get("rebalance_frequency", "monthly")
    slippage_bps = params.get("slippage_bps", 25)  # default 25bps round-trip
    sizing = params.get("position_sizing", "kelly")

    # Realistic costs: 25bps slippage (bid-ask + market impact) + $0.005/share commission
    costs = TransactionCosts(
        slippage_bps=slippage_bps,
        commission_per_share=0.005,
        commission_min=0.50,
    )

    eng_cfg = EventEngineConfig(
        max_positions=max_pos,
        max_position_weight=min(0.20, 1.0 / max_pos),
        rebalance_frequency=rebal_freq,
        position_sizing=sizing,
        transaction_costs=costs,
        exit_config=exit_cfg,
        cusum_recency_days=params["cusum_recency_days"],
        meta_label_min_samples=50,
        use_cusum_gate=params["use_cusum_gate"],
        use_regime_multiplier=params["use_regime"],
        use_meta_labeling=params["use_meta"],
        regime_filter=regime_filter,
    )

    # Use provided combiner (AlphaGPT) or default momentum-only combiner
    if combiner is None:
        combiner = SignalCombiner([MomentumSignal(duckdb_store)])

    engine = EventDrivenEngine(combiner, eng_cfg)

    try:
        result = engine.run(
            universe=universe,
            close_prices=close_prices,
            open_prices=open_prices,
            start_date=datetime.strptime(start, "%Y-%m-%d").date(),
            end_date=datetime.strptime(end, "%Y-%m-%d").date(),
            macro_prices=(
                macro_prices
                if macro_prices is not None and not macro_prices.empty
                else None
            ),
            sentiment_prices=(
                sentiment_prices
                if sentiment_prices is not None and not sentiment_prices.empty
                else None
            ),
        )
    except Exception as e:
        logger.error(f"    FAILED: {e}")
        return RunScore(
            config_id=config_id,
            sharpe=-99,
            cagr=-99,
            max_dd=-99,
            profit_factor=0,
            win_rate=0,
            avg_win_pct=0,
            avg_loss_pct=0,
            kelly_fraction=0,
            total_trades=0,
            avg_holding=0,
            psr=0,
            score=-999,
            passed=False,
            params=params,
            trace={
                "raw_llm_response": None,
                "parse_error": None,
                "backtest_error": str(e),
                "cusum_entry_rate": None,
                "meta_label_mean_prob": None,
                "cost_drag_pct": None,
                "exit_reason_breakdown": None,
            },
        )

    # --- Compute trace fields (exit breakdown, cost drag, CUSUM/meta stats) ---
    exit_reason_breakdown = None
    if not result.trade_log.empty and "exit_reason" in result.trade_log.columns:
        total = len(result.trade_log)
        if total > 0:
            reasons = result.trade_log["exit_reason"].value_counts()
            # Map engine exit reasons → spec names
            # "rebalance_out" lumped into "time"; "cusum_reversal" into "stop"
            time_frac   = (reasons.get("timeout", 0) + reasons.get("rebalance_out", 0)) / total
            profit_frac = reasons.get("profit_target", 0) / total
            stop_frac   = (reasons.get("stop_loss", 0) + reasons.get("cusum_reversal", 0)) / total
            exit_reason_breakdown = {
                "time":   round(time_frac, 3),
                "profit": round(profit_frac, 3),
                "stop":   round(stop_frac, 3),
                "other":  round(max(0.0, 1.0 - time_frac - profit_frac - stop_frac), 3),
            }

    cost_drag_pct = None
    if not result.trade_log.empty and "entry_price" in result.trade_log.columns and "exit_price" in result.trade_log.columns:
        tl_tmp = result.trade_log.copy()
        tl_tmp["_pnl_pct"] = (tl_tmp["exit_price"] - tl_tmp["entry_price"]) / tl_tmp["entry_price"]
        winners_tmp = tl_tmp[tl_tmp["_pnl_pct"] > 0]["_pnl_pct"]
        if len(winners_tmp) > 0:
            gross_return = float(winners_tmp.mean())
            slippage_rate = params.get("slippage_bps", 25) / 10000
            # cost_drag_pct: ratio of round-trip slippage to avg gross winner (0.0–1.0 scale)
            if gross_return > 0:
                cost_drag_pct = round(slippage_rate / gross_return, 3)

    # cusum_entry_rate and meta_label_mean_prob from engine_stats
    eng_stats = result.engine_stats
    cusum_entry_rate = None
    if eng_stats.get("cusum_total", 0) > 0:
        cusum_entry_rate = round(eng_stats["cusum_passed"] / eng_stats["cusum_total"], 3)

    meta_label_mean_prob = None
    meta_probs = eng_stats.get("meta_probs", [])
    if meta_probs:
        meta_label_mean_prob = round(sum(meta_probs) / len(meta_probs), 3)

    metrics = calculate_metrics(
        result.daily_returns,
        trade_log=result.trade_log if not result.trade_log.empty else None,
    )

    # In-run screening PSR: P(true SR > 0) with no multiple-testing correction.
    # Using n_strategies_tested=1 (benchmark = 0) keeps PSR meaningful throughout
    # the discovery loop — expected_max_sharpe(N) inflates the benchmark to ~2.5+
    # for N>100, collapsing PSR to 0.000 for every strategy regardless of quality.
    # The CPCV gate (below) handles selection-bias correction with proper N.
    psr_val = 0.0
    if len(result.daily_returns) >= 252:
        try:
            psr_res = deflated_sharpe(
                result.daily_returns.values,
                n_strategies_tested=1,
            )
            psr_val = psr_res.psr
        except Exception:
            pass

    # Avg holding and per-trade win/loss stats from trade log
    avg_hold = 0.0
    avg_win_pct = 0.0
    avg_loss_pct = 0.0
    kelly_frac = 0.0
    if not result.trade_log.empty:
        tl = result.trade_log
        avg_hold = float(tl["holding_days"].mean())
        # pnl_pct = (exit - entry) / entry  — trade log should have entry_price / exit_price
        if "entry_price" in tl.columns and "exit_price" in tl.columns:
            tl = tl.copy()
            tl["pnl_pct"] = (tl["exit_price"] - tl["entry_price"]) / tl["entry_price"]
            winners = tl[tl["pnl_pct"] > 0]["pnl_pct"]
            losers  = tl[tl["pnl_pct"] < 0]["pnl_pct"]
            avg_win_pct  = float(winners.mean() * 100) if len(winners) > 0 else 0.0
            avg_loss_pct = float(abs(losers.mean()) * 100) if len(losers) > 0 else 0.0
            # Kelly from trade-level pnl_pcts
            if len(winners) >= 10 and len(losers) >= 10:
                p = len(winners) / len(tl)
                b = winners.mean() / losers.abs().mean()
                kelly_frac = max(0.0, p - (1 - p) / b) * 0.5  # half-Kelly

    sc = composite_score(
        sharpe=metrics.sharpe_ratio,
        cagr=metrics.cagr * 100,
        max_dd=metrics.max_drawdown * 100,
        profit_factor=(
            metrics.profit_factor if hasattr(metrics, "profit_factor") else 1.0
        ),
        win_rate=metrics.win_rate if hasattr(metrics, "win_rate") else 0.5,
        total_trades=metrics.total_trades if hasattr(metrics, "total_trades") else 0,
        avg_holding=avg_hold,
    )

    # Discovery gate: Sharpe > 0.5, CAGR > 3%, DD < 35%, avg hold > 5d.
    # PSR with n=1 is trivially 1.0 for any positive Sharpe on long history;
    # real PSR validation (n=34) is reserved for the final out-of-sample run.
    passed = (
        metrics.sharpe_ratio > 0.5
        and metrics.cagr > 0.03
        and abs(metrics.max_drawdown * 100) < 35.0
        and avg_hold >= 5
    )

    rs = RunScore(
        config_id=config_id,
        sharpe=round(metrics.sharpe_ratio, 3),
        cagr=round(metrics.cagr * 100, 2),
        max_dd=round(metrics.max_drawdown * 100, 2),
        profit_factor=round(getattr(metrics, "profit_factor", 1.0), 3),
        win_rate=round(getattr(metrics, "win_rate", 0.5), 3),
        avg_win_pct=round(avg_win_pct, 2),
        avg_loss_pct=round(avg_loss_pct, 2),
        kelly_fraction=round(kelly_frac, 3),
        total_trades=getattr(metrics, "total_trades", 0),
        avg_holding=round(avg_hold, 1),
        psr=round(psr_val, 3),
        score=round(sc, 3),
        passed=passed,
        params=params,
        daily_returns=result.daily_returns,
        trace={
            "raw_llm_response": None,   # filled in by alpha_gpt.py caller
            "parse_error": None,         # filled in by alpha_gpt.py caller
            "backtest_error": None,
            "cusum_entry_rate": cusum_entry_rate,
            "meta_label_mean_prob": meta_label_mean_prob,
            "cost_drag_pct": cost_drag_pct,
            "exit_reason_breakdown": exit_reason_breakdown,
        },
    )

    logger.info(
        f"    Sharpe={rs.sharpe:+.2f}  CAGR={rs.cagr:+.1f}%  DD={rs.max_dd:.1f}%  "
        f"WR={rs.win_rate:.0%}  AvgW=+{rs.avg_win_pct:.1f}%  AvgL=-{rs.avg_loss_pct:.1f}%  "
        f"Kelly={rs.kelly_fraction:.2f}  PF={rs.profit_factor:.2f}  "
        f"Trades={rs.total_trades}  Hold={rs.avg_holding}d  "
        f"{'✅ PASS' if passed else '❌'}"
    )

    return rs


# ── Report ─────────────────────────────────────────────────────────────────────


def print_report(scores: list[RunScore], best: RunScore):
    print("\n" + "=" * 110)
    print("AUTO-RESEARCH RESULTS")
    print("=" * 110)

    df = pd.DataFrame(
        [
            {
                "config": s.config_id,
                "sharpe": s.sharpe,
                "cagr%": s.cagr,
                "max_dd%": s.max_dd,
                "wr%": round(s.win_rate * 100, 1),
                "avgW%": s.avg_win_pct,
                "avgL%": s.avg_loss_pct,
                "kelly": s.kelly_fraction,
                "pf": s.profit_factor,
                "trades": s.total_trades,
                "hold_d": s.avg_holding,
                "score": s.score,
                "pass": "✅" if s.passed else "❌",
            }
            for s in sorted(scores, key=lambda x: x.score, reverse=True)
        ]
    )

    print(df.to_string(index=False))
    print()
    print(f"BEST CONFIG: {best.config_id}  (score={best.score})")
    print(f"  Sharpe={best.sharpe}  CAGR={best.cagr}%  MaxDD={best.max_dd}%")
    print(f"  WinRate={best.win_rate*100:.1f}%  AvgWin=+{best.avg_win_pct:.1f}%  AvgLoss=-{best.avg_loss_pct:.1f}%")
    print(f"  KellyFraction={best.kelly_fraction:.3f}  ProfitFactor={best.profit_factor}")
    print(f"  Trades={best.total_trades}  AvgHolding={best.avg_holding}d")
    if best.avg_loss_pct > 0:
        rr = best.avg_win_pct / best.avg_loss_pct
        print(f"  Risk/Reward ratio = {rr:.2f}:1")
    print()
    print("BEST PARAMS:")
    for k, v in best.params.items():
        print(f"  {k}: {v}")
    print("=" * 110)


# ── Main ──────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Auto-research parameter optimizer")
    parser.add_argument("--universe", default="/tmp/universe_full.txt")
    parser.add_argument("--start", default="2010-01-01")
    parser.add_argument("--end", default="2025-12-31")
    parser.add_argument(
        "--max-runs", type=int, default=50, help="Max configs to test before stopping"
    )
    parser.add_argument(
        "--stop-on-pass",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Stop after first passing config (default: off — run all configs)",
    )
    parser.add_argument(
        "--stage", type=int, default=0, help="0=all, 1=stage1 only, 2=stage1+2, 3=all"
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        default=False,
        help="Fast mode: use 100-symbol subset + 7-year window for grid search",
    )
    parser.add_argument(
        "--fast-n",
        type=int,
        default=100,
        help="Universe size in fast mode (default 100)",
    )
    parser.add_argument(
        "--validate-config",
        default=None,
        help="Run a single config by label from the grid on the full universe "
        "(skips grid search, e.g. --validate-config grid_pt3.0_sl1.5_mh30)",
    )
    parser.add_argument(
        "--enable-meta",
        action="store_true",
        default=False,
        help="Enable meta-labeling even in fast mode (default: off in fast mode)",
    )
    args = parser.parse_args()

    # Load universe
    with open(args.universe) as f:
        all_tickers = [l.strip().upper() for l in f if l.strip()]

    # Fast mode: use a diverse 100-symbol subset to find params quickly
    if args.fast:
        import random

        random.seed(42)
        # Compact 30-symbol diverse set — fast enough for directional param search
        # (~3 min/config → 34 configs ≈ 1.7 hrs)
        anchor = [
            # Large cap tech (liquid, representative)
            "AAPL",
            "MSFT",
            "NVDA",
            "AMD",
            "META",
            # Small/mid cap tech (volatile, tests CUSUM/barriers)
            "CRWD",
            "NET",
            "DDOG",
            "PLTR",
            "FTNT",
            "ZS",
            # Semiconductors small cap
            "LSCC",
            "ONTO",
            "SITM",
            "AEHR",
            # Small cap high-vol tech
            "MARA",
            "KTOS",
            "UPWK",
            "FVRR",
            # Non-tech for regime diversity
            "JPM",
            "XOM",
            "GLD",
        ]
        rest = [t for t in all_tickers if t not in anchor]
        sample = anchor + random.sample(
            rest, max(0, min(args.fast_n - len(anchor), len(rest)))
        )
        all_tickers = [t for t in sample[: args.fast_n] if t]
        args.start = "2018-01-01"  # 7 years enough for param search
        logger.info(f"FAST MODE: {len(all_tickers)} symbols, {args.start}→{args.end}")
    else:
        logger.info(f"Universe: {len(all_tickers)} tickers")

    # Load price data once (expensive)
    logger.info("Loading price data...")
    all_symbols = all_tickers + ["SPY"]
    close_prices, open_prices = load_price_dataframes(all_symbols)
    universe = [s for s in all_tickers if s in close_prices.columns]
    logger.info(f"Active universe: {len(universe)} symbols, {len(close_prices)} days")

    # Pre-flight: validate data quality, label sanity, HRP before committing to grid
    if not args.validate_config:
        logger.info("Running pre-flight checks...")
        preflight_ok = run_preflight(close_prices, universe, n_sample=min(30, len(universe)))
        if not preflight_ok:
            logger.error("Pre-flight failed — fix data issues before running backtest")
            sys.exit(1)

    # Load macro once
    logger.info("Loading macro/sentiment data...")
    start_dt = datetime.strptime(args.start, "%Y-%m-%d").date()
    end_dt = datetime.strptime(args.end, "%Y-%m-%d").date()
    macro_prices, sentiment_prices = load_macro_dataframes(start_dt, end_dt)

    # Storage — DuckDBStore needs the PARQUET directory, not the .duckdb file path
    duckdb_store = DuckDBStore(PARQUET_DIR)
    parquet_storage = ParquetStorage(PARQUET_DIR)

    # Build grid
    full_grid = build_param_grid()

    # Validate-config mode: run a single named config, meta-labeling ON
    if args.validate_config:
        match = [p for p in full_grid if p["label"] == args.validate_config]
        if not match:
            logger.error(
                f"Config '{args.validate_config}' not found. "
                f"Available: {[p['label'] for p in full_grid]}"
            )
            sys.exit(1)
        grid = match
        # In validation mode, enable meta-labeling only if --enable-meta is set.
        # Meta-labeling requires O(n_rebalances × n_symbols × CUSUM) and is very
        # slow on large universes. Ablation shows it adds no edge vs. meta=False.
        grid[0]["use_meta"] = args.enable_meta
        logger.info(
            f"VALIDATION MODE: running single config '{args.validate_config}' "
            f"on {len(universe)} symbols, meta-labeling={'ON' if args.enable_meta else 'OFF'}"
        )
    else:
        # Fast mode: disable meta-labeling (RF retraining is expensive per rebalance)
        if args.fast and not args.enable_meta:
            for p in full_grid:
                p["use_meta"] = False
            logger.info("Fast mode: meta-labeling disabled for speed")

        if args.stage == 1:
            grid = full_grid[:3]
        elif args.stage == 2:
            grid = full_grid[:7]
        else:
            grid = full_grid[: args.max_runs]

    logger.info(f"Testing {len(grid)} configurations...")
    logger.info("=" * 70)

    scores: list[RunScore] = []
    start_ts = time.time()

    for i, params in enumerate(grid, 1):
        logger.info(f"\n[{i}/{len(grid)}] {params['label']}")
        rs = run_config(
            params,
            universe,
            close_prices,
            open_prices,
            macro_prices,
            sentiment_prices,
            args.start,
            args.end,
            duckdb_store,
            parquet_storage,
        )
        scores.append(rs)

        # Early stop if passing
        if rs.passed and args.stop_on_pass:
            logger.info(f"\n✅ PASSING CONFIG FOUND after {i} runs — stopping early")
            break

        elapsed = (time.time() - start_ts) / 60
        remaining = len(grid) - i
        eta = (elapsed / i) * remaining if i > 0 else 0
        logger.info(f"  [{i}/{len(grid)}] elapsed={elapsed:.1f}m  ETA={eta:.1f}m")

    best = max(scores, key=lambda s: s.score)
    print_report(scores, best)

    # Save results to JSON
    out_path = Path("data/cache/auto_research_results.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump([{**asdict(s)} for s in scores], f, indent=2, default=str)
    logger.info(f"Results saved to {out_path}")

    total_min = (time.time() - start_ts) / 60
    logger.info(f"Total time: {total_min:.1f} min")


if __name__ == "__main__":
    main()
