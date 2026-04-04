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
import statistics
import subprocess
import sys
import multiprocessing
import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed, TimeoutError as FutureTimeoutError
from datetime import date, datetime
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
import scripts.alpha_gpt as agpt
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
RESULTS_TSV_PATH = Path(__file__).parent.parent / "data" / "cache" / "results.tsv"

# Strategy archetypes cycled across workers to force expression diversity.
# Index into list with: WORKER_ARCHETYPES[iteration_index % len(WORKER_ARCHETYPES)]
WORKER_ARCHETYPES = [
    "momentum",
    "mean-reversion",
    "volatility",
    "volume-divergence",
    "value",
]


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


def ask_approval(proposal: dict, auto_approve: bool = False) -> bool:
    """Ask the user to approve a strategy shift."""
    print(f"\n{'='*60}")
    print(f"STRATEGY SHIFT PROPOSED: {proposal['type']}")
    print(f"{'='*60}")
    print(proposal["description"])
    print()
    if auto_approve:
        print("Auto-approving (--auto-approve flag set).")
        return True
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
    n_iters = analysis.get("n_iterations", 0)
    print(f"BATCH {batch_num} COMPLETE — {n_iters} total iterations")
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


# ── Keep/revert helpers ───────────────────────────────────────────────────────


def _get_batch_median_score(history: list[dict], last_n: int) -> float | None:
    """Compute median composite score from the last N scored iterations."""
    scored = [
        e["score"]["score"]
        for e in history[-last_n:]
        if e.get("score") and e["score"].get("score") is not None
    ]
    if not scored:
        return None
    return statistics.median(scored)


def _append_results_tsv(
    shift_type: str,
    pre_median: float | None,
    post_median: float | None,
    kept: bool,
    rationale: str,
    commit_hash: str = "none",
) -> None:
    """Append one result row to results.tsv, creating with header if needed."""
    RESULTS_TSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    write_header = not RESULTS_TSV_PATH.exists() or RESULTS_TSV_PATH.stat().st_size == 0
    with open(RESULTS_TSV_PATH, "a", encoding="utf-8") as f:
        if write_header:
            f.write("timestamp\tshift_type\tpre_median\tpost_median\tkept\trationale\tcommit_hash\n")
        ts = datetime.now().isoformat(timespec="seconds")
        pre_str = f"{pre_median:.4f}" if pre_median is not None else "null"
        post_str = f"{post_median:.4f}" if post_median is not None else "null"
        rationale_clean = rationale.replace("\t", " ").replace("\n", " ")[:120]
        f.write(
            f"{ts}\t{shift_type}\t{pre_str}\t{post_str}\t"
            f"{'yes' if kept else 'no'}\t{rationale_clean}\t{commit_hash}\n"
        )


def _write_system_prompt_to_disk(new_prompt: str, rationale: str = "") -> str | None:
    """Atomically rewrite the SYSTEM_PROMPT block in alpha_gpt.py between boundary markers.

    Uses write-to-temp + rename for atomicity. Returns short git commit hash or None.
    """
    alpha_gpt_path = Path(__file__).parent / "alpha_gpt.py"
    try:
        original = alpha_gpt_path.read_text(encoding="utf-8")
    except Exception as e:
        logger.error(f"Could not read alpha_gpt.py for SYSTEM_PROMPT update: {e}")
        return None

    start_marker = "# === META-AGENT EDITABLE BLOCK START ==="
    end_marker = "# === META-AGENT EDITABLE BLOCK END ==="

    start_idx = original.find(start_marker)
    end_idx = original.find(end_marker)

    if start_idx == -1 or end_idx == -1:
        logger.error(
            "Boundary markers not found in alpha_gpt.py — cannot update SYSTEM_PROMPT on disk"
        )
        return None

    # Build replacement block (preserve textwrap.dedent form)
    new_block = (
        f"{start_marker}\n"
        f"SYSTEM_PROMPT = textwrap.dedent(\"\"\"\n"
        f"{new_prompt}\n"
        f"\"\"\").strip()\n"
        f"{end_marker}"
    )

    updated = original[:start_idx] + new_block + original[end_idx + len(end_marker):]

    # Atomic write: temp file then rename
    tmp_path = alpha_gpt_path.with_suffix(".py.tmp")
    try:
        tmp_path.write_text(updated, encoding="utf-8")
        tmp_path.rename(alpha_gpt_path)
        logger.info(f"Updated SYSTEM_PROMPT on disk in {alpha_gpt_path.name}")
    except Exception as e:
        logger.error(f"Atomic write failed: {e}")
        tmp_path.unlink(missing_ok=True)
        return None

    # Git commit
    repo_root = alpha_gpt_path.parent.parent
    rel_path = str(alpha_gpt_path.relative_to(repo_root))
    commit_msg = f"meta: prompt_hint — {rationale[:60]}"
    try:
        subprocess.run(["git", "add", rel_path], cwd=repo_root, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", commit_msg],
            cwd=repo_root, check=True, capture_output=True,
        )
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_root, check=True, capture_output=True, text=True,
        )
        commit_hash = result.stdout.strip()
        logger.info(f"Committed SYSTEM_PROMPT update: {commit_hash}")
        return commit_hash
    except subprocess.CalledProcessError as e:
        logger.warning(f"Git commit failed: {e.stderr.decode() if e.stderr else e}")
        return None


# ── Main loop ─────────────────────────────────────────────────────────────────


def _run_batch_parallel(
    batch_iterations: list[int],
    history_snapshot: list[dict],
    universe: list[str],
    close_prices,
    open_prices,
    ohlcv: dict,
    macro_prices,
    sentiment_prices,
    start: str,
    end: str,
    model: str,
    workers: int,
    worker_timeout: int,
    system_prompt: str | None = None,
    global_iteration_offset: int = 0,
    regime_filter: str | None = None,
    universe_name: str = "sp500",
    benchmark_symbol: str = "SPY",
    atr_multiplier: float = 1.5,
) -> list[dict]:
    """Run a batch of AlphaGPT iterations in parallel using ProcessPoolExecutor.

    Each worker gets its own isolated copy of state (spawn, no fork), writes its
    result to a unique temp JSON file, and is abandoned if it exceeds worker_timeout.

    Results are sorted by iteration number before return. Crashed or timed-out
    workers produce an error entry — this function never raises.

    Returns:
        list[dict] — history entries, one per iteration, sorted by iteration.
    """
    from scripts.parallel_worker import worker_fn

    spawn_ctx = multiprocessing.get_context("spawn")

    # Create temp files — one per worker
    temp_files: list[str] = []
    for _ in batch_iterations:
        tf = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        tf.close()
        temp_files.append(tf.name)

    # Temperature ladder — more variation across workers encourages diverse proposals.
    WORKER_TEMPERATURES = [0.3, 0.7, 0.9, 1.1]

    worker_args = []
    for idx, (iteration, out_path) in enumerate(zip(batch_iterations, temp_files)):
        global_idx = global_iteration_offset + idx
        archetype = WORKER_ARCHETYPES[global_idx % len(WORKER_ARCHETYPES)]
        temperature = WORKER_TEMPERATURES[idx % len(WORKER_TEMPERATURES)]
        worker_args.append({
            "iteration": iteration,
            "history_snapshot": history_snapshot,
            "universe": universe,
            "close_prices": close_prices,
            "open_prices": open_prices,
            "ohlcv": ohlcv,
            "macro_prices": macro_prices,
            "sentiment_prices": sentiment_prices,
            "start": start,
            "end": end,
            "model": model,
            "n_strategies_tested": sum(
                1 for e in history_snapshot
                if e.get("universe", "sp500") == universe_name
            ),
            "output_path": out_path,
            "system_prompt": system_prompt,
            "archetype": archetype,
            "temperature": temperature,
            "regime_filter": regime_filter,
            "universe_name": universe_name,
            "benchmark_symbol": benchmark_symbol,
            "atr_multiplier": atr_multiplier,
        })

    results: list[dict] = []
    timeout_entries: list[dict] = []

    logger.info(
        f"Launching {len(batch_iterations)} parallel workers "
        f"(max_workers={workers}, timeout={worker_timeout}s)"
    )

    try:
        with ProcessPoolExecutor(max_workers=workers, mp_context=spawn_ctx) as executor:
            future_to_args = {
                executor.submit(worker_fn, wargs): wargs
                for wargs in worker_args
            }

            try:
                for future in as_completed(future_to_args, timeout=worker_timeout + 30):
                    wargs = future_to_args[future]
                    iteration = wargs["iteration"]
                    out_path = wargs["output_path"]

                    try:
                        future.result(timeout=worker_timeout)
                        raw = Path(out_path).read_text()
                        entry = json.loads(raw)
                        results.append(entry)
                        logger.info(
                            f"Worker {iteration} completed: "
                            f"score={entry.get('score', {}).get('score', '?')}"
                        )
                    except FutureTimeoutError:
                        logger.warning(
                            f"Worker {iteration} timed out after {worker_timeout}s — "
                            "recording timeout trace"
                        )
                        timeout_entries.append({
                            "iteration": iteration,
                            "spec": {},
                            "score": {},
                            "diagnosis": f"Worker timeout after {worker_timeout}s",
                            "timestamp": datetime.now().isoformat(),
                            "trace": {
                                "raw_llm_response": None,
                                "parse_error": None,
                                "backtest_error": f"timeout after {worker_timeout}s",
                                "cusum_entry_rate": None,
                                "meta_label_mean_prob": None,
                                "cost_drag_pct": None,
                                "exit_reason_breakdown": None,
                            },
                        })
                    except Exception as exc:
                        logger.error(f"Worker {iteration} raised: {exc}")
                        results.append({
                            "iteration": iteration,
                            "spec": {},
                            "score": {},
                            "diagnosis": f"Worker error: {exc}",
                            "timestamp": datetime.now().isoformat(),
                            "trace": {
                                "raw_llm_response": None,
                                "parse_error": None,
                                "backtest_error": str(exc),
                                "cusum_entry_rate": None,
                                "meta_label_mean_prob": None,
                                "cost_drag_pct": None,
                                "exit_reason_breakdown": None,
                            },
                        })
            except FutureTimeoutError:
                # Global deadline exceeded — record error entries for any futures that never completed
                logger.warning(
                    f"Global timeout ({worker_timeout + 30}s) exceeded — "
                    f"some workers did not complete"
                )
                for future, wargs in future_to_args.items():
                    if not future.done():
                        future.cancel()
                        timeout_entries.append({
                            "iteration": wargs["iteration"],
                            "spec": {},
                            "score": {},
                            "diagnosis": f"Global timeout: worker did not complete within {worker_timeout + 30}s",
                            "timestamp": datetime.now().isoformat(),
                            "trace": {
                                "raw_llm_response": None,
                                "parse_error": None,
                                "backtest_error": f"global timeout after {worker_timeout + 30}s",
                                "cusum_entry_rate": None,
                                "meta_label_mean_prob": None,
                                "cost_drag_pct": None,
                                "exit_reason_breakdown": None,
                            },
                        })
    finally:
        # Clean up temp files
        for out_path in temp_files:
            Path(out_path).unlink(missing_ok=True)

    return sorted(results + timeout_entries, key=lambda e: e["iteration"])


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
    ap.add_argument("--workers", type=int, default=4,
                    help="Parallel workers per batch (default: 4)")
    ap.add_argument("--worker-timeout", type=int, default=300,
                    help="Seconds before killing a worker (default: 300)")
    ap.add_argument("--no-parallel", action="store_true",
                    help="Disable parallelism, run sequentially (original behavior)")
    ap.add_argument("--auto-approve", action="store_true",
                    help="Auto-approve all meta-agent strategy shift proposals without prompting")
    ap.add_argument("--regime-filter", default=None, choices=["vix"],
                    help="Hard entry gate: 'vix' blocks entries when VIX >= 28 (default: off)")
    ap.add_argument("--atr-multiplier", type=float, default=1.5,
                    help="ATR multiplier for barrier width (default: 1.5). Set 0 to use vol-based barriers.")
    ap.add_argument(
        "--universe-name", default="sp500",
        choices=["sp500", "russell2000_tech"],
        help="Named universe for history isolation, benchmarks, and price paths (default: sp500)"
    )
    args = ap.parse_args()

    # ── Universe config ───────────────────────────────────────────────────
    from scripts.universe import get_universe_config
    universe_cfg = get_universe_config(args.universe_name)

    # Override HISTORY_PATH in alpha_gpt for this run
    agpt.HISTORY_PATH = universe_cfg.history_path

    # ── Universe symbols ──────────────────────────────────────────────────
    if args.universe == "all" or args.universe is None:
        universe = sorted([p.stem for p in universe_cfg.prices_dir.glob("*.parquet")])
    elif args.universe:
        universe = [t.strip() for t in Path(args.universe).read_text().splitlines() if t.strip()]

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
        close_prices, open_prices = load_price_dataframes(syms, prices_dir=universe_cfg.prices_dir)
        ohlcv = load_ohlcv_dataframes(syms, prices_dir=universe_cfg.prices_dir)
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
    if args.no_resume and universe_cfg.history_path.exists():
        universe_cfg.history_path.unlink()

    # ── Batch loop ────────────────────────────────────────────────────────
    total_spent = len(load_history())
    # global_iterations counts all iterations ever run, never resets on history_clear.
    # This ensures the budget is a hard cap regardless of how many times history is cleared.
    global_iterations = 0
    batch_num = 0

    while global_iterations < args.budget:
        batch_num += 1
        remaining = args.budget - global_iterations
        this_batch = min(args.batch_size, remaining)

        print(f"\n{'='*60}")
        print(f"BATCH {batch_num}: Running {this_batch} iterations "
              f"({global_iterations}/{args.budget} global | {total_spent} in current history)")
        print(f"Universe: {len(available)} symbols | Model: {config['model']}")
        print(f"{'='*60}\n")

        # ── Inject prompt hint if set ─────────────────────────────────────
        # We do this by temporarily patching alpha_gpt's SYSTEM_PROMPT
        hint = config.get("prompt_hint")
        if hint and hint in DIVERSITY_HINTS:
            agpt.SYSTEM_PROMPT = agpt.SYSTEM_PROMPT.rstrip() + DIVERSITY_HINTS[hint]
            logger.info(f"Injected prompt hint: {hint}")
        elif hint == "custom":
            custom_text = config.get("hint_text", "")
            if custom_text:
                agpt.SYSTEM_PROMPT = agpt.SYSTEM_PROMPT.rstrip() + "\n\nIMPORTANT: " + custom_text
                logger.info(f"Injected custom meta-agent hint: {custom_text[:80]}")

        # ── Run AlphaGPT batch ────────────────────────────────────────────
        if args.no_parallel:
            # ── Sequential mode (original behavior) ──────────────────────────
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
        else:
            # ── Parallel mode ─────────────────────────────────────────────────
            history_snapshot = load_history()
            start_iter = len(history_snapshot) + 1
            batch_iters = list(range(start_iter, start_iter + this_batch))

            entries = _run_batch_parallel(
                batch_iterations=batch_iters,
                history_snapshot=history_snapshot,
                universe=available,
                close_prices=close_prices,
                open_prices=open_prices,
                ohlcv=ohlcv,
                macro_prices=macro_prices,
                sentiment_prices=sentiment_prices,
                start=args.start,
                end=args.end,
                model=config["model"],
                workers=args.workers,
                worker_timeout=args.worker_timeout,
                system_prompt=agpt._load_system_prompt(),
                global_iteration_offset=global_iterations,
                regime_filter=args.regime_filter,
                universe_name=args.universe_name,
                benchmark_symbol=universe_cfg.benchmark,
                atr_multiplier=args.atr_multiplier,
            )

            # Main process owns the history file — workers never write to it
            history_snapshot.extend(entries)
            save_history(history_snapshot)

            # Check if any worker found a winner
            winner = None
            for entry in entries:
                score = entry.get("score", {})
                if score.get("psr", 0) >= PSR_TARGET and score.get("passed"):
                    from scripts.auto_research import RunScore
                    winner = RunScore(
                        config_id=entry.get("spec", {}).get("expression", "parallel_winner"),
                        sharpe=score.get("sharpe", 0),
                        cagr=score.get("cagr", 0),
                        max_dd=score.get("max_dd", 0),
                        profit_factor=score.get("profit_factor", 1),
                        win_rate=score.get("win_rate", 0),
                        avg_win_pct=score.get("avg_win_pct", 0),
                        avg_loss_pct=score.get("avg_loss_pct", 0),
                        kelly_fraction=0.0,
                        total_trades=score.get("total_trades", 0),
                        avg_holding=score.get("avg_holding", 0),
                        psr=score.get("psr", 0),
                        score=score.get("score", 0),
                        passed=True,
                        params={},
                        daily_returns=pd.Series(dtype=float),
                    )
                    logger.info(
                        f"Parallel winner at iteration {entry['iteration']}! "
                        f"PSR={score.get('psr', 0):.3f}"
                    )
                    break

        total_spent = len(load_history())

        # Don't count zero-trade iterations against budget — they wasted a worker
        # slot but produced no signal information. Expression goes into history so
        # the fingerprint exclusion list still sees it.
        zero_trade_count = 0
        if not args.no_parallel:
            zero_trade_count = sum(
                1 for e in entries
                if (e.get("trace") or {}).get("error") == "zero_trades"
            )
            if zero_trade_count:
                logger.info(
                    f"Batch had {zero_trade_count} zero-trade iteration(s) — "
                    f"not counted against budget"
                )
        global_iterations += this_batch - zero_trade_count

        # --- Post-shift keep/revert check (runs on batch after a shift was applied) ---
        pending = config.pop("_pending_revert_check", None)
        if pending:
            history_now = load_history()
            if not pending.get("is_history_clear"):
                actual_post_batch = total_spent - pending.get("shift_applied_at", total_spent)
                post_window = min(actual_post_batch, args.batch_size) if actual_post_batch > 0 else args.batch_size
                post_median = _get_batch_median_score(history_now, post_window)
                pre_median = pending["pre_median"]
                kept = (
                    post_median is not None
                    and pre_median is not None
                    and post_median > pre_median
                )
                if not kept:
                    logger.warning(
                        f"Post-shift median ({post_median}) <= pre-shift ({pre_median})"
                        " — reverting SYSTEM_PROMPT"
                    )
                    agpt.SYSTEM_PROMPT = pending["snapshot"]
                else:
                    logger.info(
                        f"Post-shift median improved ({pre_median:.4f} → {post_median:.4f})"
                        " — keeping change"
                    )
                # For kept prompt_hint shifts: write SYSTEM_PROMPT to disk and commit
                commit_hash = "none"
                if kept and pending["shift_type"] == "prompt_hint":
                    commit_hash = _write_system_prompt_to_disk(
                        agpt.SYSTEM_PROMPT, rationale=pending["rationale"]
                    ) or "none"

                _append_results_tsv(
                    shift_type=pending["shift_type"],
                    pre_median=pre_median,
                    post_median=post_median,
                    kept=kept,
                    rationale=pending["rationale"],
                    commit_hash=commit_hash,
                )
            else:
                # history_clear: no baseline to compare — always log as kept
                logger.info("history_clear shift: no revert possible, logging as kept")
                _append_results_tsv(
                    shift_type=pending["shift_type"],
                    pre_median=pending["pre_median"],
                    post_median=None,
                    kept=True,
                    rationale=pending["rationale"],
                )

        if winner:
            print(f"\n{'='*60}")
            print(f"ALPHA FOUND after {total_spent} iterations!")
            print(f"PSR={winner.psr:.3f}  Sharpe={winner.sharpe:.3f}  "
                  f"CAGR={winner.cagr:.1f}%")
            print(f"Continuing to exhaust full budget ({total_spent}/{args.budget})...")
            print(f"{'='*60}")

        # ── Analyze batch results ─────────────────────────────────────────
        history = load_history()
        analysis = analyze_batch(history)
        print_batch_summary(analysis, batch_num)

        # ── Check for strategy shift ──────────────────────────────────────
        proposal = propose_strategy_shift(analysis, config)
        if proposal:
            approved = ask_approval(proposal, auto_approve=args.auto_approve)
            if approved:
                changes = proposal.get("config_changes", {})
                logger.info(f"Applying: {changes}")

                # --- Snapshot before applying: for keep/revert comparison ---
                _shift_snapshot = agpt.SYSTEM_PROMPT
                _pre_median = _get_batch_median_score(history, args.batch_size)
                _is_history_clear = bool(changes.get("clear_history"))
                _shift_type = proposal.get("type", "unknown")
                _shift_rationale = proposal.get("meta_rationale", proposal.get("description", ""))

                if changes.get("universe") == "all":
                    universe = sorted([p.stem for p in universe_cfg.prices_dir.glob("*.parquet")])
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

                # Store pending revert check for next batch
                config["_pending_revert_check"] = {
                    "snapshot": _shift_snapshot,
                    "pre_median": _pre_median,
                    "shift_type": _shift_type,
                    "rationale": _shift_rationale,
                    "is_history_clear": _is_history_clear,
                    "shift_applied_at": total_spent,
                }
            else:
                logger.info("Shift rejected — continuing with current config")

    # ── Budget exhausted ──────────────────────────────────────────────────
    history = load_history()
    analysis = analyze_batch(history)
    print(f"\n{'='*60}")
    print(f"BUDGET EXHAUSTED ({global_iterations} global iterations, budget={args.budget})")
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

    print(f"\nFull history: {universe_cfg.history_path}")


if __name__ == "__main__":
    main()
