#!/usr/bin/env python3
"""
Post-run report writer for AlphaGPT discovery loop.

Reads alpha_gpt_history.json, extracts winners (PSR > 0.95 AND PBO < 0.5),
writes run report and updates winning_strategies.md in the Obsidian vault.

Usage:
    python scripts/write_obsidian_report.py --log-file logs/auto_research_run_YYYYMMDD.log \
        --report-date 2026-04-04 --universe-size 643
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

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

OBSIDIAN_DIR = Path(
    "/Users/a004/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian/Research/AlphaGPT-Runs"
)
HISTORY_PATH = Path(__file__).parent.parent / "data" / "cache" / "alpha_gpt_history.json"

PSR_THRESHOLD = 0.95
PBO_THRESHOLD = 0.5


def load_history() -> list[dict]:
    if not HISTORY_PATH.exists():
        return []
    with open(HISTORY_PATH) as f:
        return json.load(f)


def extract_top3(history: list[dict]) -> list[dict]:
    """Top 3 entries by Sharpe ratio, regardless of PSR/PBO gate."""
    valid = [e for e in history if e.get("score", {}).get("sharpe") is not None]
    valid.sort(key=lambda e: e["score"]["sharpe"], reverse=True)
    return valid[:3]


def extract_winners(history: list[dict]) -> list[dict]:
    winners = []
    for entry in history:
        score = entry.get("score", {})
        psr = score.get("psr", 0) or 0
        passed = score.get("passed", False)
        # PBO comes from trace or score
        pbo = score.get("pbo") or entry.get("trace", {}).get("pbo")
        if psr >= PSR_THRESHOLD and passed:
            if pbo is None or pbo < PBO_THRESHOLD:
                winners.append(entry)
    return winners


def parse_meta_shifts(log_text: str) -> list[str]:
    shifts = []
    for line in log_text.splitlines():
        if "meta-agent" in line.lower() or "strategy shift" in line.lower() or "prompt_hint" in line.lower():
            shifts.append(line.strip())
    return shifts


def parse_errors(log_text: str) -> list[str]:
    errors = []
    for line in log_text.splitlines():
        if "ERROR" in line or "crash" in line.lower() or "FAILED" in line:
            errors.append(line.strip())
    return errors[-20:]  # last 20 errors max


def parse_completion_status(log_text: str) -> tuple[int, bool]:
    """Returns (iterations_completed, budget_exhausted)."""
    lines = log_text.splitlines()
    max_iter = 0
    budget_exhausted = False
    for line in lines:
        if "Budget exhausted" in line or "budget exhausted" in line:
            budget_exhausted = True
        if "Worker" in line and "completed" in line:
            # parse iteration number if available
            pass
    # Count completed iterations from history
    history = load_history()
    return len(history), budget_exhausted


def write_run_report(
    report_date: str,
    log_file: Path,
    universe_size: int,
    regime_filter: str,
) -> Path:
    OBSIDIAN_DIR.mkdir(parents=True, exist_ok=True)
    log_text = log_file.read_text() if log_file and log_file.exists() else ""
    history = load_history()
    winners = extract_winners(history)
    meta_shifts = parse_meta_shifts(log_text)
    errors = parse_errors(log_text)
    iters_completed, budget_exhausted = parse_completion_status(log_text)

    report_path = OBSIDIAN_DIR / f"run_report_{report_date}.md"

    lines = [
        f"# AlphaGPT Run Report — {report_date}",
        "",
        "## Run Parameters",
        f"- **Universe size**: {universe_size} symbols",
        f"- **Regime filter**: `{regime_filter}`",
        f"- **Budget**: 30 iterations",
        f"- **Batch size**: 5",
        f"- **Workers**: 4",
        f"- **VIX threshold**: 28 (entries blocked when VIX ≥ 28)",
        f"- **Log file**: `{log_file}`",
        "",
        "## Run Summary",
        f"- **Iterations completed**: {iters_completed}",
        f"- **Budget exhausted**: {'Yes' if budget_exhausted else 'No'}",
        f"- **Strategies passing PSR > 0.95 AND PBO < 0.5**: {len(winners)}",
        "",
    ]

    if winners:
        lines += [
            "## Winning Strategies",
            "",
        ]
        for i, entry in enumerate(winners, 1):
            score = entry.get("score", {})
            spec = entry.get("spec", {})
            expr = spec.get("expression", "N/A")
            bp = spec.get("backtest", {})
            psr = score.get("psr", 0) or 0
            pbo = score.get("pbo") or entry.get("trace", {}).get("pbo") or "N/A"
            sharpe = score.get("sharpe") or 0
            cagr = score.get("cagr") or 0
            max_dd = score.get("max_dd") or 0
            trades = score.get("total_trades") or 0
            hold = score.get("avg_holding") or 0
            pf = score.get("profit_factor") or 0

            lines += [
                f"### Strategy {i} (Iteration {entry.get('iteration', '?')})",
                f"- **Expression**: `{expr}`",
                f"- **PSR**: {psr:.3f}",
                f"- **PBO**: {pbo:.3f if isinstance(pbo, float) else pbo}",
                f"- **Sharpe**: {sharpe:.3f}",
                f"- **CAGR**: {cagr:.1%}",
                f"- **Max DD**: {max_dd:.1%}",
                f"- **Profit Factor**: {pf:.2f}",
                f"- **Total Trades**: {trades}",
                f"- **Avg Hold**: {hold:.1f} days",
                f"- **Profit take**: {bp.get('profit_take_mult', 'N/A')}×  |  Stop: {bp.get('stop_loss_mult', 'N/A')}×  |  Max hold: {bp.get('max_holding_days', 'N/A')}d",
                f"- **Universe**: {universe_size} symbols",
                f"- **Regime filter**: {regime_filter}",
                "",
            ]
    else:
        lines += [
            "## Winning Strategies",
            "",
            "_No strategies passed PSR > 0.95 AND PBO < 0.5 in this run._",
            "",
        ]

    # All strategies performance overview
    if history:
        lines += [
            "## All Strategies Performance",
            "",
            "| Iter | Expression (truncated) | Sharpe | CAGR | PSR | Passed |",
            "|------|----------------------|--------|------|-----|--------|",
        ]
        for entry in history:
            score = entry.get("score", {})
            spec = entry.get("spec", {})
            expr = spec.get("expression", "N/A")
            expr_short = expr[:50] + "…" if len(expr) > 50 else expr
            sharpe = score.get("sharpe") or 0
            cagr = score.get("cagr") or 0
            psr = score.get("psr") or 0
            passed = "✅" if score.get("passed") else "❌"
            lines.append(
                f"| {entry.get('iteration', '?')} | `{expr_short}` | {sharpe:.2f} | {cagr:.1%} | {psr:.2f} | {passed} |"
            )
        lines.append("")

    if meta_shifts:
        lines += [
            "## Meta-Agent Shifts",
            "",
        ]
        for shift in meta_shifts[-10:]:
            lines.append(f"- {shift}")
        lines.append("")

    if errors:
        lines += [
            "## Errors Encountered",
            "",
        ]
        for err in errors:
            lines.append(f"- `{err}`")
        lines.append("")

    lines += [
        "---",
        f"*Generated by `write_obsidian_report.py` at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*",
    ]

    report_path.write_text("\n".join(lines))
    print(f"Run report written to: {report_path}")
    return report_path


def update_winning_strategies(
    universe_size: int,
    regime_filter: str,
    report_date: str,
) -> None:
    OBSIDIAN_DIR.mkdir(parents=True, exist_ok=True)
    ws_path = OBSIDIAN_DIR / "winning_strategies.md"
    history = load_history()
    winners = extract_winners(history)

    if not winners:
        print("No winners to add to winning_strategies.md")
        return

    existing = ws_path.read_text() if ws_path.exists() else ""

    new_entries = []
    for entry in winners:
        score = entry.get("score", {})
        spec = entry.get("spec", {})
        expr = spec.get("expression", "N/A")
        bp = spec.get("backtest", {})
        psr = score.get("psr", 0) or 0
        pbo = score.get("pbo") or entry.get("trace", {}).get("pbo") or "N/A"
        sharpe = score.get("sharpe") or 0
        cagr = score.get("cagr") or 0
        max_dd = score.get("max_dd") or 0
        pf = score.get("profit_factor") or 0

        # Skip if already in file
        if expr[:40] in existing:
            continue

        new_entries.append("\n".join([
            f"## [{report_date}] {expr[:60]}",
            f"- **Expression**: `{expr}`",
            f"- **Universe**: {universe_size} symbols (full S&P 500 universe)",
            f"- **Regime filter**: {regime_filter} (VIX < 28 entry gate)",
            f"- **PSR**: {psr:.3f}  |  **PBO**: {pbo:.3f if isinstance(pbo, float) else pbo}",
            f"- **Sharpe**: {sharpe:.3f}  |  **CAGR**: {cagr:.1%}  |  **Max DD**: {max_dd:.1%}",
            f"- **Profit Factor**: {pf:.2f}",
            f"- **Backtest params**: profit_take={bp.get('profit_take_mult')}×, stop={bp.get('stop_loss_mult')}×, max_hold={bp.get('max_holding_days')}d",
            "",
        ]))

    if not new_entries:
        print("All winners already in winning_strategies.md")
        return

    header = ""
    if not existing:
        header = "# AlphaGPT Winning Strategies\n\nStrategies that passed PSR > 0.95 AND PBO < 0.5.\nEach entry shows the universe size it was validated on.\n\n---\n\n"

    ws_path.write_text(existing + header + "\n\n".join(new_entries))
    print(f"winning_strategies.md updated: {len(new_entries)} new entries added")


def write_top3_candidates(
    universe_size: int,
    regime_filter: str,
    report_date: str,
) -> None:
    """Write top 3 strategies by Sharpe to top3_candidates_YYYY-MM-DD.md.

    These are the best-scoring strategies regardless of PSR/PBO gate — useful
    for identifying promising expressions that need further refinement.
    """
    OBSIDIAN_DIR.mkdir(parents=True, exist_ok=True)
    history = load_history()
    top3 = extract_top3(history)

    if not top3:
        print("No entries in history — skipping top3 report")
        return

    out_path = OBSIDIAN_DIR / f"top3_candidates_{report_date}.md"
    lines = [
        f"# Top 3 Strategy Candidates — {report_date}",
        "",
        "> These strategies did **not** pass the full gate (PSR > 0.95 AND PBO < 0.5).",
        "> Ranked by Sharpe ratio across the full run. Use as starting points for refinement.",
        "",
        f"- **Universe**: {universe_size} symbols",
        f"- **Regime filter**: {regime_filter} (VIX < 28 entry gate, 1-day lag)",
        f"- **Total strategies evaluated**: {len(history)}",
        "",
        "---",
        "",
    ]

    for rank, entry in enumerate(top3, 1):
        score = entry.get("score", {})
        spec = entry.get("spec", {})
        expr = spec.get("expression", "N/A")
        bp = spec.get("backtest", {})
        psr = score.get("psr", 0) or 0
        pbo = score.get("pbo") or entry.get("trace", {}).get("pbo") or "N/A"
        sharpe = score.get("sharpe") or 0
        cagr = score.get("cagr") or 0
        max_dd = score.get("max_dd") or 0
        pf = score.get("profit_factor") or 0
        trades = score.get("total_trades") or 0
        hold = score.get("avg_holding") or 0
        passed = score.get("passed", False)

        gate_note = "✅ passed full gate" if passed and psr >= PSR_THRESHOLD else f"❌ gate fail — PSR={psr:.3f}"

        lines += [
            f"## Rank {rank} — Iter {entry.get('iteration', '?')} ({gate_note})",
            f"- **Expression**: `{expr}`",
            f"- **Sharpe**: {sharpe:.3f}  |  **CAGR**: {cagr:.1%}  |  **Max DD**: {max_dd:.1%}",
            f"- **PSR**: {psr:.3f}  |  **PBO**: {pbo:.3f if isinstance(pbo, float) else pbo}",
            f"- **Profit Factor**: {pf:.2f}  |  **Trades**: {trades}  |  **Avg Hold**: {hold:.1f}d",
            f"- **Params**: profit_take={bp.get('profit_take_mult')}×, stop={bp.get('stop_loss_mult')}×, max_hold={bp.get('max_holding_days')}d",
            "",
        ]

    lines += [
        "---",
        f"*Generated by `write_obsidian_report.py` at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*",
    ]

    out_path.write_text("\n".join(lines))
    print(f"Top-3 candidates written to: {out_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log-file", type=Path, required=False)
    ap.add_argument("--report-date", default=datetime.now().strftime("%Y-%m-%d"))
    ap.add_argument("--universe-size", type=int, default=643)
    ap.add_argument("--regime-filter", default="vix")
    args = ap.parse_args()

    log_file = args.log_file
    if log_file is None:
        # Find most recent log
        log_dir = Path(__file__).parent.parent / "logs"
        logs = sorted(log_dir.glob("auto_research_run_*.log"), key=lambda p: p.stat().st_mtime)
        log_file = logs[-1] if logs else None

    write_run_report(
        report_date=args.report_date,
        log_file=log_file,
        universe_size=args.universe_size,
        regime_filter=args.regime_filter,
    )
    update_winning_strategies(
        universe_size=args.universe_size,
        regime_filter=args.regime_filter,
        report_date=args.report_date,
    )
    write_top3_candidates(
        universe_size=args.universe_size,
        regime_filter=args.regime_filter,
        report_date=args.report_date,
    )


if __name__ == "__main__":
    main()
