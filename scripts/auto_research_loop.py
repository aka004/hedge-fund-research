#!/usr/bin/env python3
"""
Auto-research loop — batch orchestrator for AlphaGPT expression discovery.

Runs AlphaGPT in batches, analyzes results with Python (no extra LLM calls),
and proposes strategy shifts that require human approval before proceeding.

Usage:
    python scripts/auto_research_loop.py \\
        --budget 50 --batch-size 10 \\
        --start 2018-01-01 --end 2024-12-31
"""

import argparse
import json
import logging
import os
import sys
from datetime import date
from pathlib import Path

import anthropic

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

try:
    from dotenv import load_dotenv
    _d = Path(__file__).resolve().parent
    while _d != _d.parent:
        if (_d / ".env").exists():
            load_dotenv(_d / ".env", override=True)
            break
        _d = _d.parent
except ImportError:
    pass

from config import STORAGE_PATH
from data.storage.duckdb_store import DuckDBStore
from data.storage.parquet import ParquetStorage
from scripts.alpha_gpt import (
    HISTORY_PATH,
    PSR_TARGET,
    load_history,
    run_alpha_gpt,
    save_history,
)
from scripts.preflight_check import run_preflight
from scripts.run_event_engine import (
    load_macro_dataframes,
    load_ohlcv_dataframes,
    load_price_dataframes,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

PARQUET_DIR = STORAGE_PATH / "parquet"


# ── Batch analysis (pure Python, no LLM) ─────────────────────────────────────


def analyze_batch(history: list[dict]) -> dict:
    """Analyze iteration history and return diagnostics + recommendations.

    All analysis is deterministic Python — no LLM tokens spent.
    """
    if not history:
        return {"status": "empty", "recommendations": []}

    scored = [e for e in history if e.get("score") and e["score"].get("sharpe") is not None]
    if not scored:
        return {"status": "no_results", "recommendations": ["All iterations failed to produce results"]}

    # Extract metrics
    sharpes = [e["score"]["sharpe"] for e in scored]
    cagrs = [e["score"]["cagr"] for e in scored]
    trades = [e["score"]["total_trades"] for e in scored]
    scores = [e["score"]["score"] for e in scored]
    win_rates = [e["score"]["win_rate"] for e in scored]
    holdings = [e["score"]["avg_holding"] for e in scored]
    expressions = [e["spec"].get("expression", "") for e in scored]

    best_idx = max(range(len(scores)), key=lambda i: scores[i])
    best = scored[best_idx]
    best_sharpe = sharpes[best_idx]
    best_score = scores[best_idx]

    recs = []
    issues = []

    # ── Check if any passed ──
    if any(e["score"].get("passed") for e in scored):
        return {
            "status": "alpha_found",
            "best": best,
            "recommendations": ["Run out-of-sample validation on the winning expression"],
        }

    # ── Convergence check: are recent iterations improving? ──
    if len(scores) >= 4:
        first_half = sum(scores[:len(scores)//2]) / (len(scores)//2)
        second_half = sum(scores[len(scores)//2:]) / (len(scores) - len(scores)//2)
        if second_half <= first_half * 1.05:
            issues.append("stagnant")
            recs.append("Scores not improving — LLM may be stuck in a local pattern")

    # ── Expression diversity check ──
    if len(expressions) >= 4:
        import re
        # Extract operator+args tokens (e.g. "ts_delta(close,5)") not just operator names,
        # so ts_delta(close,5) and ts_delta(returns,21) are treated as different signals.
        op_sets = []
        for expr in expressions:
            # Match function calls with their arguments: ts_mean(close, 20), cs_rank(x)
            calls = set(re.findall(r'((?:ts_|cs_)\w+\([^)]*\))', expr.replace(" ", "")))
            # Also include bare operator names as fallback for nested expressions
            bare = set(re.findall(r'\b(ts_\w+|cs_\w+)\b', expr))
            op_sets.append(calls | bare)
        # Jaccard similarity between consecutive expressions
        similarities = []
        for i in range(1, len(op_sets)):
            union = op_sets[i] | op_sets[i-1]
            inter = op_sets[i] & op_sets[i-1]
            if union:
                similarities.append(len(inter) / len(union))
        avg_sim = sum(similarities) / len(similarities) if similarities else 0
        if avg_sim > 0.75:
            issues.append("low_diversity")
            recs.append(
                f"Expression diversity low (avg Jaccard similarity {avg_sim:.0%}) "
                "— prompt needs to encourage different operator combinations"
            )

    # ── Universe size check ──
    # If cs_rank is used heavily but universe is small
    cs_rank_count = sum(expr.count("cs_rank") for expr in expressions)
    if cs_rank_count > len(expressions) * 1.5:
        # cs_rank used frequently — need enough stocks
        issues.append("cs_rank_heavy")
        recs.append(
            "Expressions rely heavily on cs_rank (cross-sectional ranking) "
            "— works best with 50+ stocks, consider expanding universe"
        )

    # ── Sharpe analysis ──
    if best_sharpe < 0.2:
        issues.append("very_low_sharpe")
        recs.append(f"Best Sharpe is {best_sharpe:.3f} — fundamental signal may be weak")
    elif best_sharpe < 0.5:
        issues.append("low_sharpe")
        recs.append(
            f"Best Sharpe is {best_sharpe:.3f} (target: 0.5) — "
            "getting close, more iterations may help"
        )

    # ── Cost drag check ──
    avg_trades_per_year = sum(trades) / len(trades) / 7  # ~7 years of backtest
    if avg_trades_per_year > 400:
        issues.append("high_turnover")
        recs.append(
            f"Avg {avg_trades_per_year:.0f} trades/year — "
            "high turnover eats returns. Consider monthly rebalance."
        )

    # ── Win rate check ──
    avg_wr = sum(win_rates) / len(win_rates)
    if avg_wr < 0.45:
        issues.append("low_win_rate")
        recs.append(f"Average win rate {avg_wr:.0%} — expressions may need ranking refinement")

    # ── Holding period check ──
    avg_hold = sum(holdings) / len(holdings)
    if avg_hold < 7:
        issues.append("short_holds")
        recs.append(f"Average holding {avg_hold:.1f}d — too short, increase max_holding_days")

    return {
        "status": "in_progress",
        "best": best,
        "best_sharpe": best_sharpe,
        "best_score": best_score,
        "n_iterations": len(scored),
        "issues": issues,
        "recommendations": recs,
    }


def _propose_strategy_shift_rules(analysis: dict, current_config: dict) -> dict | None:
    """Based on analysis, propose a config change that needs human approval.

    Returns None if no shift needed (just keep iterating).
    Returns a dict describing the proposed change.
    """
    issues = analysis.get("issues", [])
    if not issues:
        return None

    # Priority order of shifts
    if "stagnant" in issues and "low_diversity" in issues:
        return {
            "type": "prompt_diversity",
            "description": (
                "LLM is stuck — expressions are too similar and scores aren't improving.\n"
                "Proposal: Add diversity hints to the system prompt (encourage mean-reversion, "
                "volatility, intraday range expressions instead of momentum-volume)."
            ),
            "config_changes": {"prompt_hint": "diverse"},
        }

    if "cs_rank_heavy" in issues and current_config.get("universe_size", 20) < 50:
        return {
            "type": "expand_universe",
            "description": (
                f"Expressions use cs_rank heavily but universe is only "
                f"{current_config.get('universe_size', 20)} stocks.\n"
                "Proposal: Expand to all available symbols (~100) for better "
                "cross-sectional differentiation."
            ),
            "config_changes": {"universe": "all"},
        }

    if "high_turnover" in issues:
        return {
            "type": "reduce_turnover",
            "description": (
                "High turnover is dragging returns.\n"
                "Proposal: Force monthly rebalance and increase max_holding_days to 45."
            ),
            "config_changes": {"force_monthly": True, "max_holding_days": 45},
        }

    if "very_low_sharpe" in issues:
        return {
            "type": "reset_direction",
            "description": (
                "Sharpe is very low across all iterations — current direction isn't working.\n"
                "Proposal: Clear history and restart with different expression templates "
                "(mean-reversion, volatility breakout, price structure)."
            ),
            "config_changes": {"clear_history": True, "prompt_hint": "mean_reversion"},
        }

    return None


_META_AGENT_SYSTEM_PROMPT = (
    "You are a research director reviewing alpha expression discovery attempts.\n"
    "You receive batch history with expressions tried, scores, and execution traces.\n"
    "Your job: identify the root cause of stagnation and propose ONE concrete strategy change.\n\n"
    "Respond ONLY with valid JSON:\n"
    "{\n"
    '  "type": "prompt_hint" | "universe_expand" | "rebalance_frequency" | "history_clear" | "no_action",\n'
    '  "rationale": "1-3 sentences explaining the root cause",\n'
    '  "change": {\n'
    "    // For prompt_hint: {\"hint\": \"focus on mean-reversion using ts_zscore operators\"}\n"
    "    // For universe_expand: {\"target_symbols\": 600}\n"
    "    // For rebalance_frequency: {\"frequency\": \"monthly\"}\n"
    "    // For history_clear: {}\n"
    "    // For no_action: {}\n"
    "  }\n"
    "}"
)


def _build_meta_agent_message(history: list[dict], program_md_path: Path, n_batch: int) -> str:
    """Build the user message for the meta-agent from recent batch history."""
    program_content = ""
    if program_md_path.exists():
        try:
            program_content = program_md_path.read_text(encoding="utf-8").strip()
        except Exception:
            pass

    lines = []
    if program_content:
        lines.append("## Current Research Program\n" + program_content + "\n")

    lines.append(f"## Last {n_batch} Iterations\n")
    for entry in history[-n_batch:]:
        i = entry.get("iteration", "?")
        expr = entry.get("spec", {}).get("expression", "?")
        score = entry.get("score", {})
        diag = entry.get("diagnosis", "")
        trace = entry.get("trace") or {}

        lines.append(f"Iter {i}: {expr}")
        if score:
            lines.append(
                f"  Sharpe={score.get('sharpe', 0):.3f} CAGR={score.get('cagr', 0):.1f}% "
                f"PSR={score.get('psr', 0):.3f} Trades={score.get('total_trades', 0)}"
            )
        lines.append(
            f"  cusum_entry_rate={trace.get('cusum_entry_rate')} "
            f"meta_prob={trace.get('meta_label_mean_prob')} "
            f"cost_drag={trace.get('cost_drag_pct')} "
            f"exits={trace.get('exit_reason_breakdown')}"
        )
        if diag:
            lines.append(f"  Diagnosis: {diag}")

    lines.append("\nAnalyze the pattern of failures and propose ONE concrete strategy change.")
    return "\n".join(lines)


def propose_strategy_shift(analysis: dict, current_config: dict) -> dict | None:
    """Call Claude meta-agent to propose a strategy shift. Falls back to rule-based on error.

    Returns None for no_action or if no issues detected.
    Returns a proposal dict compatible with ask_approval() and the apply logic below it.
    """
    issues = analysis.get("issues", [])
    if not issues:
        return None

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning("No ANTHROPIC_API_KEY — using rule-based strategy shift")
        return _propose_strategy_shift_rules(analysis, current_config)

    history = load_history()
    batch_size = current_config.get("batch_size", 10)
    program_md_path = Path(__file__).parent / "program.md"

    try:
        client = anthropic.Anthropic(api_key=api_key)
        user_msg = _build_meta_agent_message(history, program_md_path, n_batch=batch_size)
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=512,
            temperature=0.3,
            system=_META_AGENT_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = response.content[0].text.strip()
        logger.info(f"Meta-agent response: {raw[:300]}")

        # Parse JSON — handle markdown code fences
        text = raw
        if "```" in text:
            start = text.find("{", text.find("```"))
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                text = text[start:end]
        proposal_json = json.loads(text)

        if "type" not in proposal_json or "rationale" not in proposal_json:
            raise ValueError(f"Meta-agent response missing required fields: {proposal_json}")

        shift_type = proposal_json["type"]
        change = proposal_json.get("change", {})
        rationale = proposal_json["rationale"]

        if shift_type == "no_action":
            logger.info(f"Meta-agent: no action needed — {rationale}")
            return None

        # Convert meta-agent JSON → internal proposal format (same shape as _propose_strategy_shift_rules)
        if shift_type == "prompt_hint":
            hint_text = change.get("hint", "Try different operator combinations")
            return {
                "type": "prompt_hint",
                "description": f"Meta-agent: {rationale}\nHint: {hint_text}",
                "config_changes": {"prompt_hint": "custom", "hint_text": hint_text},
                "meta_rationale": rationale,
            }
        if shift_type == "universe_expand":
            return {
                "type": "expand_universe",
                "description": f"Meta-agent: {rationale}\nProposal: Expand universe.",
                "config_changes": {"universe": "all"},
                "meta_rationale": rationale,
            }
        if shift_type == "rebalance_frequency":
            freq = change.get("frequency", "monthly")
            return {
                "type": "reduce_turnover",
                "description": f"Meta-agent: {rationale}\nProposal: Switch to {freq} rebalance.",
                "config_changes": {"force_monthly": freq == "monthly"},
                "meta_rationale": rationale,
            }
        if shift_type == "history_clear":
            return {
                "type": "reset_direction",
                "description": f"Meta-agent: {rationale}\nProposal: Clear history.",
                "config_changes": {"clear_history": True},
                "meta_rationale": rationale,
            }

        raise ValueError(f"Unknown shift type from meta-agent: {shift_type}")

    except Exception as e:
        logger.warning(f"Meta-agent call failed ({e}) — falling back to rule-based shift")
        return _propose_strategy_shift_rules(analysis, current_config)


# ── Prompt hint injection ─────────────────────────────────────────────────────

DIVERSITY_HINTS = {
    "diverse": (
        "\n\nIMPORTANT: Your recent expressions have been too similar. "
        "Try COMPLETELY DIFFERENT approaches:\n"
        "- Mean-reversion: buy stocks that dropped and are reverting (negative delta + high ts_rank)\n"
        "- Volatility breakout: ts_std expanding while price breaks ts_max\n"
        "- Price structure: (close - low) / (high - low) captures intraday position\n"
        "- Volume divergence: price making new highs but volume declining\n"
        "Do NOT reuse ts_delta(close, 5)/ts_std(close, 20) — try new combinations."
    ),
    "mean_reversion": (
        "\n\nFocus on MEAN-REVERSION strategies:\n"
        "- Stocks that have fallen relative to their rolling mean (close / ts_mean - 1)\n"
        "- Oversold conditions: ts_rank(close, 60) near 0 (stock at 60-day lows)\n"
        "- Volume spike on decline: delta(close, 5) < 0 AND delta(volume, 5) > 0\n"
        "- Bollinger band reversion: (close - ts_mean(close, 20)) / ts_std(close, 20)"
    ),
}


# ── Human interaction ─────────────────────────────────────────────────────────


def ask_approval(proposal: dict) -> bool:
    """Ask the user to approve a strategy shift."""
    print(f"\n{'='*60}")
    print(f"STRATEGY SHIFT PROPOSED: {proposal['type']}")
    print(f"{'='*60}")
    print(proposal["description"])
    print()
    while True:
        answer = input("Approve this change? [y/n/q(uit)]: ").strip().lower()
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        if answer in ("q", "quit"):
            print("Stopping auto-research loop.")
            sys.exit(0)


def print_batch_summary(analysis: dict, batch_num: int) -> None:
    """Print a human-readable summary after each batch."""
    print(f"\n{'─'*60}")
    print(f"BATCH {batch_num} COMPLETE — {analysis['n_iterations']} total iterations")
    print(f"{'─'*60}")

    best = analysis.get("best", {})
    bs = best.get("score", {})
    print(f"Best so far: Sharpe={bs.get('sharpe', 0):.3f}  "
          f"CAGR={bs.get('cagr', 0):.1f}%  "
          f"DD={bs.get('max_dd', 0):.1f}%  "
          f"Score={bs.get('score', 0):.3f}")
    print(f"Expression: {best.get('spec', {}).get('expression', '?')}")

    if analysis.get("recommendations"):
        print("\nDiagnostics:")
        for r in analysis["recommendations"]:
            print(f"  - {r}")


# ── Main loop ─────────────────────────────────────────────────────────────────


def get_all_symbols() -> list[str]:
    """Get all symbols with parquet price data."""
    prices_dir = PARQUET_DIR / "prices"
    return sorted([p.stem for p in prices_dir.glob("*.parquet")])


def main() -> None:
    ap = argparse.ArgumentParser(description="Auto-research loop for AlphaGPT")
    ap.add_argument("--budget", type=int, default=50, help="Max total AlphaGPT iterations")
    ap.add_argument("--batch-size", type=int, default=10, help="Iterations per batch")
    ap.add_argument("--start", default="2018-01-01")
    ap.add_argument("--end", default="2024-12-31")
    ap.add_argument("--model", default="claude-sonnet-4-6")
    ap.add_argument("--universe", default=None, help="Universe file or 'all' for all symbols")
    ap.add_argument("--no-resume", action="store_true")
    ap.add_argument("--skip-preflight", action="store_true")
    args = ap.parse_args()

    # ── Universe ──────────────────────────────────────────────────────────
    if args.universe == "all":
        universe = get_all_symbols()
    elif args.universe:
        universe = [t.strip() for t in Path(args.universe).read_text().splitlines() if t.strip()]
    else:
        universe = [
            "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA",
            "JPM", "GS", "BAC", "JNJ", "UNH", "PFE",
            "XOM", "CVX", "COP", "NEE", "DUK", "SPY", "QQQ",
        ]

    config = {
        "universe_size": len(universe),
        "batch_size": args.batch_size,
        "model": args.model,
        "prompt_hint": None,
    }

    logger.info(f"Auto-research: budget={args.budget}, batch={args.batch_size}, "
                f"universe={len(universe)} symbols")

    # ── Load data ─────────────────────────────────────────────────────────
    duckdb_store = DuckDBStore(PARQUET_DIR)
    parquet_storage = ParquetStorage(PARQUET_DIR)

    def load_all_data(syms):
        close_prices, open_prices = load_price_dataframes(syms)
        ohlcv = load_ohlcv_dataframes(syms)
        available = [s for s in syms if s in close_prices.columns]
        macro_prices, sentiment_prices = load_macro_dataframes(
            date.fromisoformat(args.start), date.fromisoformat(args.end)
        )
        return close_prices, open_prices, ohlcv, macro_prices, sentiment_prices, available

    logger.info(f"Loading data for {len(universe)} symbols...")
    close_prices, open_prices, ohlcv, macro_prices, sentiment_prices, available = \
        load_all_data(universe)

    if not available:
        logger.error("No price data available.")
        sys.exit(1)

    logger.info(f"Data for {len(available)}/{len(universe)} symbols")

    # ── Preflight ─────────────────────────────────────────────────────────
    if not args.skip_preflight:
        logger.info("Running pre-flight checks...")
        if not run_preflight(close_prices, available, n_sample=min(30, len(available))):
            logger.error("Pre-flight failed")
            sys.exit(1)

    # ── Clear history if requested ────────────────────────────────────────
    if args.no_resume and HISTORY_PATH.exists():
        HISTORY_PATH.unlink()

    # ── Batch loop ────────────────────────────────────────────────────────
    total_spent = len(load_history())
    batch_num = 0

    while total_spent < args.budget:
        batch_num += 1
        remaining = args.budget - total_spent
        this_batch = min(args.batch_size, remaining)

        print(f"\n{'='*60}")
        print(f"BATCH {batch_num}: Running {this_batch} iterations "
              f"({total_spent}/{args.budget} spent)")
        print(f"Universe: {len(available)} symbols | Model: {config['model']}")
        print(f"{'='*60}\n")

        # ── Inject prompt hint if set ─────────────────────────────────────
        # We do this by temporarily patching alpha_gpt's SYSTEM_PROMPT
        hint = config.get("prompt_hint")
        if hint and hint in DIVERSITY_HINTS:
            import scripts.alpha_gpt as agpt
            agpt.SYSTEM_PROMPT = agpt.SYSTEM_PROMPT.rstrip() + DIVERSITY_HINTS[hint]
            logger.info(f"Injected prompt hint: {hint}")
        elif hint == "custom":
            custom_text = config.get("hint_text", "")
            if custom_text:
                import scripts.alpha_gpt as agpt
                agpt.SYSTEM_PROMPT = agpt.SYSTEM_PROMPT.rstrip() + "\n\nIMPORTANT: " + custom_text
                logger.info(f"Injected custom meta-agent hint: {custom_text[:80]}")

        # ── Run AlphaGPT batch ────────────────────────────────────────────
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
            max_iter=this_batch,
            model=config["model"],
            resume=True,
        )

        total_spent = len(load_history())

        if winner:
            print(f"\n{'='*60}")
            print(f"ALPHA FOUND after {total_spent} iterations!")
            print(f"PSR={winner.psr:.3f}  Sharpe={winner.sharpe:.3f}  "
                  f"CAGR={winner.cagr:.1f}%")
            print(f"{'='*60}")
            return

        # ── Analyze batch results ─────────────────────────────────────────
        history = load_history()
        analysis = analyze_batch(history)
        print_batch_summary(analysis, batch_num)

        # ── Check for strategy shift ──────────────────────────────────────
        proposal = propose_strategy_shift(analysis, config)
        if proposal:
            approved = ask_approval(proposal)
            if approved:
                changes = proposal.get("config_changes", {})
                logger.info(f"Applying: {changes}")

                if changes.get("universe") == "all":
                    universe = get_all_symbols()
                    logger.info(f"Expanding universe to {len(universe)} symbols...")
                    close_prices, open_prices, ohlcv, macro_prices, sentiment_prices, available = \
                        load_all_data(universe)
                    config["universe_size"] = len(available)
                    logger.info(f"Loaded {len(available)} symbols")

                if changes.get("prompt_hint"):
                    config["prompt_hint"] = changes["prompt_hint"]

                if changes.get("hint_text"):
                    config["hint_text"] = changes["hint_text"]

                if changes.get("clear_history"):
                    logger.info("Clearing iteration history for fresh start")
                    save_history([])
                    total_spent = 0

                if changes.get("force_monthly"):
                    import scripts.alpha_gpt as agpt
                    # Patch spec_to_run_params to enforce monthly rebalance
                    _orig_spec_to_run = agpt.spec_to_run_params
                    def _forced_monthly_params(spec, iteration, _orig=_orig_spec_to_run):
                        params = _orig(spec, iteration)
                        params["rebalance_frequency"] = "monthly"
                        params["max_holding_days"] = max(
                            params["max_holding_days"],
                            changes.get("max_holding_days", 45),
                        )
                        return params
                    agpt.spec_to_run_params = _forced_monthly_params
                    logger.info("Forced monthly rebalance + max_holding >= 45d")
            else:
                logger.info("Shift rejected — continuing with current config")

    # ── Budget exhausted ──────────────────────────────────────────────────
    history = load_history()
    analysis = analyze_batch(history)
    print(f"\n{'='*60}")
    print(f"BUDGET EXHAUSTED ({args.budget} iterations)")
    print(f"{'='*60}")
    print_batch_summary(analysis, "FINAL")

    best = analysis.get("best", {})
    bs = best.get("score", {})
    if bs.get("sharpe", 0) > 0.3:
        print("\nBest expression showed promise — consider:")
        print("  1. Running more iterations with --budget 100")
        print("  2. Expanding universe with --universe all")
        print("  3. Testing on out-of-sample period")
    else:
        print("\nNo strong signal found. Consider:")
        print("  1. Different expression templates (mean-reversion, volatility)")
        print("  2. Longer backtest period")
        print("  3. More granular data (intraday if available)")

    print(f"\nFull history: {HISTORY_PATH}")


if __name__ == "__main__":
    main()
