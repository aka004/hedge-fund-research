#!/usr/bin/env python3
"""
AlphaGPT — LLM-driven alpha factor discovery via expression engine (Phase 1).

The LLM proposes mathematical expressions over OHLCV data (e.g.
"cs_rank(ts_corr(close, volume, 10)) - cs_rank(delta(close, 21))").
Each expression is parsed, evaluated on the stock matrix, backtested,
and the results feed back to the LLM for the next iteration.

Stops when PSR > 0.95 or --max-iter is reached.

Usage:
    python scripts/alpha_gpt.py \\
        --universe /tmp/universe_full.txt \\
        --start 2015-01-01 --end 2024-12-31 \\
        --max-iter 20
"""

import argparse
import json
import logging
import os
import sys
import textwrap
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

try:
    from dotenv import load_dotenv
    # Walk up from script dir until we find .env (handles worktrees)
    _d = Path(__file__).resolve().parent
    while _d != _d.parent:
        if (_d / ".env").exists():
            load_dotenv(_d / ".env", override=True)
            break
        _d = _d.parent
except ImportError:
    pass

import anthropic

from config import STORAGE_PATH
from data.storage.duckdb_store import DuckDBStore
from data.storage.parquet import ParquetStorage
from scripts.auto_research import RunScore, run_config
from scripts.preflight_check import run_preflight
from scripts.run_event_engine import (
    load_macro_dataframes,
    load_ohlcv_dataframes,
    load_price_dataframes,
)
from afml.cpcv import CombPurgedKFold
from strategy.signals.combiner import SignalCombiner
from strategy.signals.expression import ExpressionSignal, ParseError, parse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

PARQUET_DIR = STORAGE_PATH / "parquet"
HISTORY_PATH = Path(__file__).parent.parent / "data" / "cache" / "alpha_gpt_history.json"
PROGRAM_MD_PATH = Path(__file__).parent / "program.md"

PSR_TARGET = 0.95
SHARPE_MIN = 0.5
CAGR_MIN = 3.0
MAX_DD_LIMIT = 35.0


# ── System prompt ─────────────────────────────────────────────────────────────

# === META-AGENT EDITABLE BLOCK START ===
SYSTEM_PROMPT = textwrap.dedent("""
You are AlphaGPT, an expert quantitative researcher discovering alpha factors in US equities.

You propose alpha expressions — mathematical formulas over OHLCV data — that get evaluated
on a stock×time matrix and backtested. You receive performance feedback and iterate.

## Expression language

**Data columns** (all are DataFrames: dates × stocks):
  open, high, low, close, volume, returns (log returns from close)

**Fundamental columns** (quarterly data with actual SEC filing dates, forward-filled daily):
  earnings_yield   — TTM net income / price (higher = cheaper, like inverse PE)
  revenue_growth   — YoY quarterly revenue growth rate
  profit_margin    — net income / revenue
  expense_ratio    — total expenses / revenue
  NOTE: Some stocks lack data — NaN stocks are excluded automatically.
  These update quarterly so ts_* operators with windows < 60 days won't vary much.

**Time-series operators** (per stock, rolling window d in [1, 252]):
  ts_mean(x, d) / sma(x, d) — simple moving average (SMA)
  ts_ema(x, d) / ema(x, d)  — exponential moving average (EMA, span=d)
  ts_decay(x, d)    — linearly decaying weighted average (recent data gets more weight)
  ts_std(x, d)      — rolling standard deviation
  ts_sum(x, d)      — rolling sum
  ts_max(x, d)      — rolling max
  ts_min(x, d)      — rolling min
  ts_rank(x, d)     — percentile rank within last d days (0 to 1)
  ts_delta(x, d)    — x[t] - x[t-d]  (alias: delta)
  ts_returns(x, d)  — simple returns: x[t]/x[t-d] - 1
  ts_skew(x, d)     — rolling skewness (positive = right tail)
  ts_kurt(x, d)     — rolling kurtosis (high = fat tails)
  ts_zscore(x, d)   — time-series z-score: (x - mean_d) / std_d
  ts_argmax(x, d)   — days since d-day high (0 = at high today)
  ts_argmin(x, d)   — days since d-day low (0 = at low today)
  ts_prod(x, d)     — rolling product (compound returns)
  ts_corr(x, y, d)  — rolling correlation between two series
  ts_cov(x, y, d)   — rolling covariance between two series
  ts_vwap(price, volume, d) / vwap(price, volume, d) — volume-weighted avg price

**Cross-sectional operators** (across all stocks, per day):
  cs_rank(x)    — percentile rank across stocks (0 to 1)
  cs_zscore(x)  — z-score across stocks
  cs_demean(x)  — subtract cross-sectional mean (market-neutral)

**Element-wise**:
  abs(x), log(x), sign(x)

**Arithmetic**: +, -, *, / with parentheses

## Output format (strict JSON, no extra text)
```json
{
  "expression": "<alpha expression>",
  "backtest": {
    "profit_take_mult": <float 1.5-6.0>,
    "stop_loss_mult": <float 0.5-3.0>,
    "max_holding_days": <int 10-60>,
    "n_positions": <int 5-40>,
    "rebalance_frequency": "<weekly|monthly>",
    "position_sizing": "<equal|kelly|hrp>",
    "use_cusum_gate": <true|false>,
    "use_regime": <true|false>,
    "slippage_bps": <int 10-100>
  },
  "rationale": "<1-2 sentence hypothesis>"
}
```

## Hard constraints
- No look-ahead bias (the engine truncates data to as_of_date automatically).
- slippage_bps >= 10, n_positions >= 5.
- Window parameters d must be integers in [1, 252].
- Do NOT repeat an expression you already tried.

## Strategy targets
- PSR > 0.95, Sharpe > 0.5, CAGR > 3%, Max DD < 35%, Profit Factor > 1.2

## Diagnosis guide
- "too few trades" → more positions, weekly rebalance, broader expression
- "cost drag" → lower slippage, monthly rebalance, longer holding
- "short avg holding" → increase max_holding_days, raise profit_take_mult
- "deep drawdown" → use_regime=true, tighter stop, hrp sizing
- "low win rate" → add cross-sectional ranking (cs_rank), combine multiple signals
- "low profit factor" → wider profit targets, longer lookback windows
- "high correlation to market" → cross-sectional z-score removes beta exposure

## Expression design tips
- cs_rank() normalises to 0-1, making signals comparable across regimes
- Combining ts operators at different windows captures multi-scale momentum
- delta(close, d) / ts_std(close, d) is volatility-adjusted momentum
- Subtracting two cs_rank() terms creates a long-short signal
- cs_rank(earnings_yield) adds a value tilt (buy cheap momentum stocks)
- cs_rank(revenue_growth) * cs_rank(momentum) = growth-momentum combo
- Fundamentals change quarterly — use cs_rank() not ts_* for fundamentals
- Combining momentum with earnings_yield reduces momentum crash risk
- vwap(close, volume, 20) gives institutional fair-value reference
- close / vwap(close, volume, 20) - 1 = price vs VWAP deviation
- ts_ema(x, d) reacts faster to changes than ts_mean(x, d) (SMA)
- ts_argmax(close, 252) = days since 52-week high (momentum timing)
- ts_argmin(close, 252) = days since 52-week low (reversion timing)
- ts_skew(returns, 63) detects crash-prone vs lottery-ticket stocks
- ts_zscore(close, 63) = how extreme is today vs recent history
- cs_demean() removes market-level effects without ranking

IMPORTANT: Abandon short-window momentum (21-day returns) entirely. Instead, explore mean-reversion using ts_zscore(close, 20) negated (i.e., fade recent moves), or use volatility-adjusted signals like cs_rank(ts_returns(close, 126) / ts_std(close, 63)) to capture risk-adjusted momentum at medium horizons. Reduce trade frequency by using longer lookbacks (63-252 days only) and combine with cs_rank(earnings_yield) as a quality filter to avoid low-quality reversal traps.

IMPORTANT: Abandon short-window mean-reversion. Focus on longer-window trend signals: use ts_ema or ts_mean with windows 21-63 days for momentum, combine with cs_rank(earnings_yield) as a value filter multiplied (not subtracted) to concentrate on high-quality trend stocks. Try expressions like cs_rank(ts_ema(returns, 21)) * cs_rank(earnings_yield) or cs_rank(ts_mean(returns, 42) - ts_mean(returns, 5)) to capture pullback-within-trend. Avoid ts_zscore on close at windows < 20 days entirely — it generates excessive stop-outs.

IMPORTANT: Abandon multiplicative cs_rank combinations — they are producing directionally wrong signals. Instead, focus on pure mean-reversion: use ts_zscore(close, 20) or (close / ts_mean(close, 20) - 1) as the primary signal, going long on negative z-scores (oversold) and short on positive (overbought). Try a single clean signal like cs_rank(-ts_zscore(close, 20)) or cs_rank(-(close/ts_mean(close,5)-1)) without multiplying by value factors. Also consider that the current long/short direction may need to be flipped — test negating the final expression.

IMPORTANT: Abandon additive cs_rank combinations and instead build a single conditional signal: use ts_zscore(ts_mean(returns, 21), 63) as the core momentum signal, but gate it with a liquidity/volatility regime filter such as cs_rank(ts_std(returns, 21)) < 0.5 to only trade in low-volatility stocks. Try multiplicative interaction terms like cs_rank(ts_momentum(close, 21)) * cs_rank(-ts_std(returns, 21)) to explicitly favor low-volatility momentum rather than summing independent weak signals.

IMPORTANT: Abandon momentum combinations entirely. Focus on short-term mean-reversion: use ts_zscore(close, 20) or (close - ts_mean(close, 10)) / ts_std(close, 10) as the core signal, going long oversold stocks (negative zscore) and short overbought ones. Combine with a liquidity filter like cs_rank(volume) > 0.3 to reduce cost drag. Try: cs_rank(-ts_zscore(close, 15)) + 0.3 * cs_rank(ts_delta(volume, 5) / ts_mean(volume, 20)) to capture volume-confirmed reversals. Keep holding periods short (5-10 days) to reduce time exits and improve profit exit ratio.

IMPORTANT: Abandon momentum combination and focus purely on short-term mean-reversion: use ts_zscore(close, 5) or ts_zscore(close - ts_mean(close, 20), 10) to capture price deviations that snap back. Specifically try signals like cs_rank(-ts_zscore(close, 10)) to go long oversold stocks, or combine with a liquidity filter cs_rank(-ts_zscore(close, 5)) * (ts_mean(volume, 5) > ts_mean(volume, 20)) to avoid illiquid names. The high stop-loss rate suggests you need shorter holding periods and tighter reversion windows (5-15 days), not longer momentum windows.

IMPORTANT: Abandon additive cs_rank combinations and instead focus on conditional/interaction signals: use ts_zscore to filter only high-conviction setups, e.g. only rank stocks when ts_zscore(volume, 21) > 1.0 (volume confirmation), and target mean-reversion by using cs_rank(-ts_zscore(close, 5)) * (cs_rank(ts_zscore(close, 63)) > 0.7) to buy short-term oversold names within intermediate uptrends. Reduce turnover by using longer rebalance signals (63-126 day windows) and avoid high-frequency price/volume ratio signals that generate excessive cost drag.

IMPORTANT: Abandon momentum+value combinations entirely. Pivot to mean-reversion using short-term price dislocations: try cs_rank(-ts_zscore(close, 5)) or cs_rank(-(close / ts_min(close, 10) - 1)) to capture short-term oversold bounces. Combine with a liquidity filter like cs_rank(ts_mean(volume, 20)) to avoid illiquid names. Use holding periods of 3-10 days rather than the current longer-term signals that are generating excessive stop-outs.

IMPORTANT: Abandon additive momentum+value combinations. Instead, focus on mean-reversion signals using ts_zscore to identify short-term overextension: e.g., cs_rank(-ts_zscore(close, 5)) combined with cs_rank(ts_zscore(volume, 20) - ts_zscore(volume, 5)) to capture volume-confirmed reversals. Use short lookback windows (5-21 days) and avoid ts_decay which appears in every recent failing expression.

IMPORTANT: Abandon momentum-price combinations entirely. Focus on mean-reversion signals using ts_zscore of returns over short windows (5-10 days) combined with liquidity/volume confirmation: e.g., cs_rank(-ts_zscore(close, 10)) * cs_rank(ts_zscore(volume, 5)). Use short holding periods implied by 5-day windows to reduce stop-loss exposure. Try: cs_rank(-ts_zscore(ts_returns(close, 5), 20)) + cs_rank(ts_zscore(volume, 10) - ts_zscore(volume, 63)) as a short-term reversal with volume surge filter.

IMPORTANT: Pivot to mean-reversion: use ts_zscore(close, 20) - ts_zscore(close, 5) to capture short-term overextension relative to medium-term trend, combined with cs_rank(ts_zscore(volume, 10)) to filter for unusual volume confirmation. Avoid momentum-following operators; instead fade short-term extremes with expressions like -cs_rank(ts_zscore(returns, 5)) + cs_rank(ts_zscore(earnings_yield, 63)) to exploit reversion to fundamental value.

IMPORTANT: Abandon momentum combination entirely and focus on short-term mean-reversion: use ts_zscore(close, 5) or ts_zscore(returns, 10) to identify oversold stocks, combine with cs_rank(-ts_zscore(close, 20)) so you are buying recent underperformers relative to cross-section, and add a volatility filter like cs_rank(-ts_std(returns, 21)) to avoid high-vol names. Keep windows short (5-21 days) to reduce cost drag and target higher-conviction reversals.
""").strip()
# === META-AGENT EDITABLE BLOCK END ===


def _load_system_prompt() -> str:
    """Load base SYSTEM_PROMPT and append program.md research direction if it exists.

    program.md is loaded fresh each run so the meta-agent can update it between batches.
    """
    prompt = SYSTEM_PROMPT
    if PROGRAM_MD_PATH.exists():
        try:
            program_content = PROGRAM_MD_PATH.read_text(encoding="utf-8").strip()
            if program_content:
                prompt = prompt + "\n\n## Research Program\n" + program_content
        except Exception as e:
            logger.warning(f"Could not load program.md: {e}")
    return prompt


# ── Diagnosis helper ──────────────────────────────────────────────────────────


def diagnose(score: RunScore) -> str:
    """Generate a plain-English diagnosis from a RunScore."""
    issues = []

    if score.total_trades < 100:
        issues.append(f"too few trades ({score.total_trades})")
    if score.avg_holding < 5:
        issues.append(f"avg holding {score.avg_holding:.1f}d too short")
    if score.sharpe < SHARPE_MIN:
        issues.append(f"Sharpe {score.sharpe:.3f} < {SHARPE_MIN}")
    if score.cagr < CAGR_MIN:
        issues.append(f"CAGR {score.cagr:.1f}% < {CAGR_MIN}%")
    if abs(score.max_dd) > MAX_DD_LIMIT:
        issues.append(f"DD {score.max_dd:.1f}% > {MAX_DD_LIMIT}%")
    if score.profit_factor < 1.2:
        issues.append(f"PF {score.profit_factor:.3f} < 1.2")
    if score.win_rate < 0.40:
        issues.append(f"win rate {score.win_rate:.1%} < 40%")
    if score.avg_win_pct > 0 and score.avg_loss_pct > 0:
        slippage_bps = score.params.get("slippage_bps", 25)
        cost_pct = slippage_bps / 100
        if cost_pct > 0.3 * score.avg_win_pct:
            issues.append(f"cost drag: slip {cost_pct:.2f}% > 30% of avg win")

    if score.psr >= PSR_TARGET and score.passed:
        return "PASSED — PSR target met."

    return "; ".join(issues) if issues else "marginal — close but PSR not met"


def validate_winner_cpcv(
    daily_returns: pd.Series,
    pbo_threshold: float = 0.5,
) -> dict:
    """Run CPCV on a winning strategy's daily returns to check for overfitting.

    Returns dict with pbo, n_paths, median_sharpe, passed.
    """
    if len(daily_returns) < 252:
        return {"pbo": 1.0, "n_paths": 0, "median_sharpe": 0.0, "passed": False,
                "reason": "insufficient data for CPCV"}

    # Build a dummy DataFrame with DatetimeIndex for CPCV splitter
    X = pd.DataFrame({"ret": daily_returns.values}, index=daily_returns.index)
    y = daily_returns

    cpcv = CombPurgedKFold(n_splits=6, n_test_groups=2, embargo_pct=0.01)
    result = cpcv.backtest_paths(X, y)

    median_sharpe = float(np.median(result.path_sharpes)) if result.path_sharpes else 0.0
    passed = result.pbo < pbo_threshold and median_sharpe > 0

    return {
        "pbo": round(result.pbo, 3),
        "n_paths": result.n_paths,
        "median_sharpe": round(median_sharpe, 3),
        "passed": passed,
        "reason": (
            f"PBO={result.pbo:.1%}, median path Sharpe={median_sharpe:.3f}"
            + ("" if passed else " — likely overfit")
        ),
    }


# ── Build user message ────────────────────────────────────────────────────────


def _extract_fingerprints(history: list[dict]) -> list[str]:
    """Extract operator fingerprints from recent history for the exclusion list.

    A fingerprint is the set of top-level operator calls in an expression,
    e.g. "cs_rank(ts_returns(...))" → "cs_rank+ts_returns".
    Returns deduplicated fingerprints with their best Sharpe for context.
    """
    import re
    seen: dict[str, float] = {}  # fingerprint → best sharpe
    for entry in history[-20:]:
        expr = entry.get("spec", {}).get("expression", "")
        if not expr:
            continue
        # Extract ts_/cs_ operator names from the expression
        ops = re.findall(r'\b(ts_\w+|cs_\w+)\b', expr)
        if ops:
            fp = "+".join(sorted(set(ops)))
            sharpe = entry.get("score", {}).get("sharpe", 0) or 0
            if fp not in seen or sharpe > seen[fp]:
                seen[fp] = sharpe
    return [f"{fp} (best Sharpe={s:.3f})" for fp, s in seen.items()]


def build_user_message(history: list[dict], archetype: str | None = None) -> str:
    lines = []

    # ── Archetype directive ───────────────────────────────────────────────────
    if archetype:
        lines.append(
            f"STRATEGY ARCHETYPE FOR THIS ITERATION: {archetype.upper()}\n"
            f"You MUST propose an expression whose PRIMARY signal belongs to the "
            f"{archetype} family. Do not default to momentum unless that IS the assigned archetype.\n"
        )

    if not history:
        lines.append("No iterations yet. Propose the first alpha expression.")
        return "\n".join(lines)

    # ── Exclusion list ────────────────────────────────────────────────────────
    fingerprints = _extract_fingerprints(history)
    if fingerprints:
        lines.append(
            "EXPRESSIONS ALREADY TRIED — DO NOT REPEAT THESE OPERATOR PATTERNS:\n"
            + "\n".join(f"  • {fp}" for fp in fingerprints)
            + "\nPropose something STRUCTURALLY DIFFERENT — use different operators, "
            "different lookback windows, or entirely different signal logic.\n"
        )

    lines.append(f"=== ITERATION HISTORY ({len(history)} attempts) ===")
    for entry in history:
        i = entry["iteration"]
        spec = entry["spec"]
        score = entry.get("score", {})
        diag = entry["diagnosis"]
        expr = spec.get("expression", "?")
        bp = spec.get("backtest", {})

        if score:
            lines.append(
                f"\nIter {i}: {expr}"
                f" | sizing={bp.get('position_sizing')} rebal={bp.get('rebalance_frequency')}"
                f" slip={bp.get('slippage_bps')}bps"
            )
            lines.append(
                f"  Sharpe={score.get('sharpe', 0):.3f}"
                f" CAGR={score.get('cagr', 0):.1f}%"
                f" DD={score.get('max_dd', 0):.1f}%"
                f" WR={score.get('win_rate', 0):.1%}"
                f" Trades={score.get('total_trades', 0)}"
                f" Hold={score.get('avg_holding', 0):.1f}d"
                f" PSR={score.get('psr', 0):.3f}"
            )
        else:
            lines.append(f"\nIter {i}: {expr} — NO RESULT")

        lines.append(f"  Rationale: {spec.get('rationale', '')}")
        lines.append(f"  Diagnosis: {diag}")

    lines.append("\nPropose the NEXT alpha expression. Return ONLY the JSON.")
    return "\n".join(lines)


# ── Parse and validate ────────────────────────────────────────────────────────


def parse_spec(raw: str) -> dict:
    """Extract JSON from LLM response (handles markdown code fences)."""
    text = raw.strip()
    if "```" in text:
        start = text.find("{", text.find("```"))
        end = text.rfind("}") + 1
        text = text[start:end]
    return json.loads(text)


def validate_spec(spec: dict) -> list[str]:
    """Return list of validation errors (empty = valid)."""
    errors = []
    expr = spec.get("expression")
    if not expr:
        errors.append("'expression' field missing or empty")
    else:
        try:
            parse(expr)
        except ParseError as e:
            errors.append(f"Expression parse error: {e}")

    bp = spec.get("backtest")
    if not bp:
        errors.append("'backtest' dict missing")
    else:
        if bp.get("slippage_bps", 10) < 10:
            errors.append("slippage_bps must be >= 10")
        if bp.get("n_positions", 5) < 5:
            errors.append("n_positions must be >= 5")
    return errors


# ── Build signal from expression ──────────────────────────────────────────────


def build_signal(expression: str, ohlcv: dict[str, pd.DataFrame]) -> SignalCombiner:
    """Create a SignalCombiner wrapping a single ExpressionSignal."""
    gen = ExpressionSignal(expression=expression, ohlcv=ohlcv)
    return SignalCombiner([gen])


def spec_to_run_params(spec: dict, iteration: int) -> dict:
    """Convert AlphaGPT spec to run_config params dict."""
    bp = spec.get("backtest", {})
    return {
        "label": f"alphagpt_iter{iteration:03d}",
        "profit_take_mult": float(bp.get("profit_take_mult", 3.0)),
        "stop_loss_mult": float(bp.get("stop_loss_mult", 1.5)),
        "max_holding_days": int(bp.get("max_holding_days", 30)),
        "max_positions": int(bp.get("n_positions", 20)),
        "rebalance_frequency": bp.get("rebalance_frequency", "monthly"),
        "position_sizing": bp.get("position_sizing", "hrp"),
        "use_cusum_gate": bool(bp.get("use_cusum_gate", True)),
        "use_regime": bool(bp.get("use_regime", True)),
        "slippage_bps": int(bp.get("slippage_bps", 25)),
        "cusum_recency_days": 15,
        "use_cusum_reversal_exit": False,
        "use_meta": False,
    }


def run_single_iteration(
    iteration: int,
    history_snapshot: list[dict],
    universe: list[str],
    close_prices: pd.DataFrame,
    open_prices: pd.DataFrame,
    ohlcv: dict[str, pd.DataFrame],
    macro_prices,
    sentiment_prices,
    start: str,
    end: str,
    model: str = "claude-sonnet-4-6",
    n_strategies_tested: int = 1,
    system_prompt: str | None = None,
    archetype: str | None = None,
    temperature: float = 1.0,
    regime_filter: str | None = None,
) -> dict:
    """Run a single AlphaGPT iteration and return a history entry dict.

    Pure function — never writes to disk. Safe to call from a worker process.

    Parameters
    ----------
    iteration : int
        Iteration number (used in labels and entry dict).
    history_snapshot : list[dict]
        Read-only snapshot of prior history entries (used to build user message).
    universe : list[str]
        Ticker symbols to trade.
    close_prices : pd.DataFrame
        Close price matrix (dates x symbols).
    open_prices : pd.DataFrame
        Open price matrix (dates x symbols).
    ohlcv : dict[str, pd.DataFrame]
        Dict of OHLCV DataFrames keyed by column name.
    macro_prices : any
        Macro data passed through to run_config.
    sentiment_prices : any
        Sentiment data passed through to run_config.
    start : str
        Backtest start date (ISO format).
    end : str
        Backtest end date (ISO format).
    model : str
        Anthropic model name.
    n_strategies_tested : int
        Number of strategies tested so far (for DSR deflation).

    Returns
    -------
    dict
        History entry with keys: iteration, spec, score, diagnosis, timestamp, trace.
        Error paths return the same shape with empty score and diagnosis explaining the error.
    """
    def _error_entry(diag, *, spec=None, raw=None, parse_err=None, bt_err=None):
        return {
            "iteration": iteration,
            "spec": spec if spec is not None else {},
            "score": {},
            "diagnosis": diag,
            "timestamp": datetime.now().isoformat(),
            "trace": {
                "raw_llm_response": raw,
                "parse_error": parse_err,
                "backtest_error": bt_err,
                "cusum_entry_rate": None,
                "meta_label_mean_prob": None,
                "cost_drag_pct": None,
                "exit_reason_breakdown": None,
            },
        }

    # ── API key ──────────────────────────────────────────────────────────────
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return _error_entry("Missing ANTHROPIC_API_KEY — set it in the environment")

    client = anthropic.Anthropic(api_key=api_key)

    # ── Ask the LLM ──────────────────────────────────────────────────────────
    user_msg = build_user_message(history_snapshot, archetype=archetype)
    try:
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            temperature=min(temperature, 1.0),  # Anthropic API caps at 1.0
            system=system_prompt if system_prompt is not None else _load_system_prompt(),
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = response.content[0].text
        logger.info(f"[iter {iteration}] LLM: {raw[:200]}{'...' if len(raw) > 200 else ''}")
    except Exception as e:
        return _error_entry(f"LLM call failed: {e}")

    # ── Parse ─────────────────────────────────────────────────────────────────
    try:
        spec = parse_spec(raw)
    except json.JSONDecodeError as e:
        return _error_entry(
            f"JSON parse error: {e}",
            spec={"raw": raw},
            raw=raw,
            parse_err=str(e),
        )

    # ── Validate ──────────────────────────────────────────────────────────────
    errors = validate_spec(spec)
    if errors:
        return _error_entry(
            f"Validation: {errors}",
            spec=spec,
            raw=raw,
        )

    expr = spec["expression"]

    # ── Build signal ──────────────────────────────────────────────────────────
    try:
        combiner = build_signal(expr, ohlcv)
    except Exception as e:
        return _error_entry(
            f"Build error: {e}",
            spec=spec,
            raw=raw,
            bt_err=str(e),
        )

    # ── Run backtest ──────────────────────────────────────────────────────────
    params = spec_to_run_params(spec, iteration)
    score = run_config(
        params=params,
        universe=universe,
        close_prices=close_prices,
        open_prices=open_prices,
        macro_prices=macro_prices,
        sentiment_prices=sentiment_prices,
        start=start,
        end=end,
        duckdb_store=None,
        parquet_storage=None,
        combiner=combiner,
        n_strategies_tested=n_strategies_tested,
        regime_filter=regime_filter,
    )

    diag = diagnose(score)
    logger.info(f"[iter {iteration}] {diag}")

    # ── Build entry dict ──────────────────────────────────────────────────────
    _engine_trace = (score.trace or {}) if score is not None else {}
    entry = {
        "iteration": iteration,
        "spec": spec,
        "score": {
            "sharpe": score.sharpe, "cagr": score.cagr,
            "max_dd": score.max_dd, "profit_factor": score.profit_factor,
            "win_rate": score.win_rate, "avg_win_pct": score.avg_win_pct,
            "avg_loss_pct": score.avg_loss_pct, "total_trades": score.total_trades,
            "avg_holding": score.avg_holding, "psr": score.psr,
            "score": score.score, "passed": score.passed,
        },
        "diagnosis": diag,
        "timestamp": datetime.now().isoformat(),
        "trace": {
            "raw_llm_response": raw,
            "parse_error": None,
            "backtest_error": _engine_trace.get("backtest_error"),
            "cusum_entry_rate": _engine_trace.get("cusum_entry_rate"),
            "meta_label_mean_prob": _engine_trace.get("meta_label_mean_prob"),
            "cost_drag_pct": _engine_trace.get("cost_drag_pct"),
            "exit_reason_breakdown": _engine_trace.get("exit_reason_breakdown"),
        },
    }

    # ── CPCV gate for winners ─────────────────────────────────────────────────
    if score.psr >= PSR_TARGET and score.passed:
        if score.daily_returns is not None:
            cpcv_result = validate_winner_cpcv(score.daily_returns)
            entry["cpcv"] = cpcv_result

    return entry


# ── History I/O ───────────────────────────────────────────────────────────────


def load_history() -> list[dict]:
    if HISTORY_PATH.exists():
        try:
            return json.loads(HISTORY_PATH.read_text())
        except Exception:
            return []
    return []


class _NumpyEncoder(json.JSONEncoder):
    """Handle numpy types in JSON serialization."""
    def default(self, obj):
        import numpy as np
        if isinstance(obj, (np.bool_, np.integer)):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        return super().default(obj)


def save_history(history: list[dict]) -> None:
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_PATH.write_text(json.dumps(history, indent=2, cls=_NumpyEncoder))


# ── Main loop ─────────────────────────────────────────────────────────────────


def run_alpha_gpt(
    universe: list[str],
    close_prices: pd.DataFrame,
    open_prices: pd.DataFrame,
    ohlcv: dict[str, pd.DataFrame],
    macro_prices,
    sentiment_prices,
    start: str,
    end: str,
    duckdb_store,
    parquet_storage,
    max_iter: int = 20,
    model: str = "claude-sonnet-4-6",
    resume: bool = True,
) -> RunScore | None:
    """Run the AlphaGPT expression discovery loop."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY not set. Export it or add to .env")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    history: list[dict] = load_history() if resume else []
    start_iter = len(history) + 1
    logger.info(
        f"AlphaGPT starting at iteration {start_iter} "
        f"(model={model}, max_iter={max_iter})"
    )

    for iteration in range(start_iter, start_iter + max_iter):
        logger.info(f"\n{'='*60}")
        logger.info(f"AlphaGPT — Iteration {iteration}/{start_iter + max_iter - 1}")
        logger.info(f"{'='*60}")

        # ── Ask the LLM ──────────────────────────────────────────────────────
        user_msg = build_user_message(history)

        try:
            response = client.messages.create(
                model=model,
                max_tokens=1024,
                system=_load_system_prompt(),
                messages=[{"role": "user", "content": user_msg}],
            )
            raw = response.content[0].text
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            break

        logger.info(f"LLM response:\n{raw[:500]}{'...' if len(raw) > 500 else ''}")

        # ── Parse and validate ────────────────────────────────────────────────
        try:
            spec = parse_spec(raw)
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse failed: {e}")
            history.append({
                "iteration": iteration, "spec": {"raw": raw},
                "score": {}, "diagnosis": f"JSON parse error: {e}",
                "timestamp": datetime.now().isoformat(),
                "trace": {
                    "raw_llm_response": raw,
                    "parse_error": str(e),
                    "backtest_error": None,
                    "cusum_entry_rate": None,
                    "meta_label_mean_prob": None,
                    "cost_drag_pct": None,
                    "exit_reason_breakdown": None,
                },
            })
            save_history(history)
            continue

        errors = validate_spec(spec)
        if errors:
            logger.warning(f"Validation failed: {errors}")
            history.append({
                "iteration": iteration, "spec": spec,
                "score": {}, "diagnosis": f"Validation: {errors}",
                "timestamp": datetime.now().isoformat(),
                "trace": {
                    "raw_llm_response": raw,
                    "parse_error": None,
                    "backtest_error": None,
                    "cusum_entry_rate": None,
                    "meta_label_mean_prob": None,
                    "cost_drag_pct": None,
                    "exit_reason_breakdown": None,
                },
            })
            save_history(history)
            continue

        expr = spec["expression"]
        logger.info(f"Expression: {expr}")
        logger.info(f"Rationale: {spec.get('rationale', '')}")

        # ── Build signal and run backtest ─────────────────────────────────────
        try:
            combiner = build_signal(expr, ohlcv)
        except (ParseError, Exception) as e:
            logger.error(f"Signal build failed: {e}")
            history.append({
                "iteration": iteration, "spec": spec,
                "score": {}, "diagnosis": f"Build error: {e}",
                "timestamp": datetime.now().isoformat(),
                "trace": {
                    "raw_llm_response": raw,
                    "parse_error": None,
                    "backtest_error": str(e),
                    "cusum_entry_rate": None,
                    "meta_label_mean_prob": None,
                    "cost_drag_pct": None,
                    "exit_reason_breakdown": None,
                },
            })
            save_history(history)
            continue

        params = spec_to_run_params(spec, iteration)
        score = run_config(
            params=params,
            universe=universe,
            close_prices=close_prices,
            open_prices=open_prices,
            macro_prices=macro_prices,
            sentiment_prices=sentiment_prices,
            start=start,
            end=end,
            duckdb_store=duckdb_store,
            parquet_storage=parquet_storage,
            combiner=combiner,
            n_strategies_tested=len(history) + 1,
        )

        diag = diagnose(score)
        logger.info(
            f"Result: Sharpe={score.sharpe:.3f} CAGR={score.cagr:.1f}% "
            f"DD={score.max_dd:.1f}% PSR={score.psr:.3f} passed={score.passed}"
        )
        logger.info(f"Diagnosis: {diag}")

        # ── Record ────────────────────────────────────────────────────────────
        # Build trace by merging LLM-level data with engine trace from score
        _engine_trace = (score.trace or {}) if score is not None else {}
        history.append({
            "iteration": iteration,
            "spec": spec,
            "score": {
                "sharpe": score.sharpe, "cagr": score.cagr,
                "max_dd": score.max_dd, "profit_factor": score.profit_factor,
                "win_rate": score.win_rate, "avg_win_pct": score.avg_win_pct,
                "avg_loss_pct": score.avg_loss_pct, "total_trades": score.total_trades,
                "avg_holding": score.avg_holding, "psr": score.psr,
                "score": score.score, "passed": score.passed,
            },
            "diagnosis": diag,
            "timestamp": datetime.now().isoformat(),
            "trace": {
                "raw_llm_response": raw,
                "parse_error": None,
                "backtest_error": _engine_trace.get("backtest_error"),
                "cusum_entry_rate": _engine_trace.get("cusum_entry_rate"),
                "meta_label_mean_prob": _engine_trace.get("meta_label_mean_prob"),
                "cost_drag_pct": _engine_trace.get("cost_drag_pct"),
                "exit_reason_breakdown": _engine_trace.get("exit_reason_breakdown"),
            },
        })
        save_history(history)

        if score.psr >= PSR_TARGET and score.passed:
            logger.info(
                f"\n{'='*60}\n"
                f"ALPHA CANDIDATE at iteration {iteration}!\n"
                f"Expression: {expr}\n"
                f"PSR={score.psr:.3f}  Sharpe={score.sharpe:.3f}  "
                f"CAGR={score.cagr:.1f}%\n"
                f"{'='*60}"
            )

            # ── CPCV validation gate ─────────────────────────────────────
            if score.daily_returns is not None:
                cpcv_result = validate_winner_cpcv(score.daily_returns)
                logger.info(f"CPCV: {cpcv_result['reason']}")
                history[-1]["cpcv"] = cpcv_result
                save_history(history)

                if not cpcv_result["passed"]:
                    logger.warning(
                        f"CPCV FAILED (PBO={cpcv_result['pbo']:.1%}) — "
                        "likely overfit, continuing search"
                    )
                    continue
            else:
                logger.warning("No daily returns for CPCV — skipping validation")

            logger.info("CPCV PASSED — alpha confirmed")
            return score

    best = max(history, key=lambda h: h["score"].get("score", -999), default=None)
    if best:
        logger.info(
            f"\nMax iterations reached. Best: iter {best['iteration']} "
            f"(score={best['score'].get('score', -999):.3f})"
        )
    logger.info(f"History saved to {HISTORY_PATH}")
    return None


# ── CLI ───────────────────────────────────────────────────────────────────────


def main() -> None:
    ap = argparse.ArgumentParser(description="AlphaGPT: expression-based factor discovery")
    ap.add_argument("--universe", default=None, help="Universe file (one ticker/line) or 'all' for full parquet universe")
    ap.add_argument("--start", default="2015-01-01")
    ap.add_argument("--end", default="2024-12-31")
    ap.add_argument("--max-iter", type=int, default=20)
    ap.add_argument("--model", default="claude-sonnet-4-6")
    ap.add_argument("--no-resume", action="store_true", help="Start fresh")
    ap.add_argument("--skip-preflight", action="store_true")
    args = ap.parse_args()

    # ── Universe ──────────────────────────────────────────────────────────────
    if args.universe == "all":
        prices_dir = PARQUET_DIR / "prices"
        universe = sorted([p.stem for p in prices_dir.glob("*.parquet") if p.stem != "SPY"])
        logger.info(f"Using full parquet universe: {len(universe)} symbols")
    elif args.universe:
        universe = [t.strip() for t in Path(args.universe).read_text().splitlines() if t.strip()]
    else:
        universe = [
            "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA",
            "JPM", "GS", "BAC", "BRK-B", "JNJ", "UNH", "PFE",
            "XOM", "CVX", "COP", "NEE", "DUK", "SPY", "QQQ", "IWM",
        ]
        logger.info(f"Using default {len(universe)}-ticker universe")

    # ── Data ──────────────────────────────────────────────────────────────────
    duckdb_store = DuckDBStore(PARQUET_DIR)
    parquet_storage = ParquetStorage(PARQUET_DIR)

    logger.info(f"Loading data for {len(universe)} symbols...")
    close_prices, open_prices = load_price_dataframes(universe)
    ohlcv = load_ohlcv_dataframes(universe)

    if close_prices.empty:
        logger.error("No price data. Run fetch_data.py first.")
        sys.exit(1)

    available = [s for s in universe if s in close_prices.columns]
    logger.info(f"Data for {len(available)}/{len(universe)} symbols")

    from datetime import date as date_cls
    macro_prices, sentiment_prices = load_macro_dataframes(
        date_cls.fromisoformat(args.start), date_cls.fromisoformat(args.end)
    )

    # ── Preflight ─────────────────────────────────────────────────────────────
    if not args.skip_preflight:
        logger.info("Running pre-flight checks...")
        if not run_preflight(close_prices, available, n_sample=min(30, len(available))):
            logger.error("Pre-flight failed")
            sys.exit(1)
        logger.info("Pre-flight passed.")

    # ── Run ───────────────────────────────────────────────────────────────────
    winner = run_alpha_gpt(
        universe=available,
        close_prices=close_prices,
        open_prices=open_prices,
        ohlcv=ohlcv,
        macro_prices=macro_prices,
        sentiment_prices=sentiment_prices,
        start=args.start,
        end=args.end,
        duckdb_store=duckdb_store,
        parquet_storage=parquet_storage,
        max_iter=args.max_iter,
        model=args.model,
        resume=not args.no_resume,
    )

    if winner:
        print(f"\nAlpha found! PSR={winner.psr:.3f} Sharpe={winner.sharpe:.3f} CAGR={winner.cagr:.1f}%")
    else:
        print(f"\nMax iterations reached. No PSR > {PSR_TARGET} found.")
        print(f"Review: {HISTORY_PATH}")


if __name__ == "__main__":
    main()
