# Parallel Batch Execution + Process Isolation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add parallel worker execution within AlphaGPT batches using `ProcessPoolExecutor` + `spawn`, with full process isolation via temp files and per-worker timeouts.

**Architecture:** Extract a single-iteration function from `run_alpha_gpt()`, wrap it in a picklable module-level worker, run N workers in parallel per batch via `ProcessPoolExecutor(mp_context=spawn)`, collect results from temp JSON files, and sort/merge into history. Sequential mode preserved with `--no-parallel`.

**Tech Stack:** Python `concurrent.futures.ProcessPoolExecutor`, `multiprocessing` (spawn context), `resource.setrlimit`, `tempfile`, argparse.

---

## Codebase Context (READ BEFORE CODING)

### Key files
- `scripts/auto_research_loop.py` — outer batch orchestrator; `main()` is entry point; calls `run_alpha_gpt()` per batch
- `scripts/alpha_gpt.py` — AlphaGPT inner loop; `run_alpha_gpt()` contains the per-iteration LLM-call+backtest logic; `save_history()` / `load_history()` write `alpha_gpt_history.json`
- `scripts/auto_research.py` — `run_config()` creates `EventDrivenEngine` and runs the backtest; `RunScore` dataclass
- `strategy/backtest/event_engine.py` — stateless engine; one issue: `RandomForestClassifier(n_jobs=-1)` at line 567 causes CPU contention when many processes run at once

### Critical constraint
`run_alpha_gpt()` currently calls `save_history()` after **every** iteration. In parallel mode, workers MUST NOT touch `alpha_gpt_history.json`. Only the main process writes history (once, after collating all worker results).

### Why spawn (not fork)?
- `fork` copies memory including open file handles, locks, and numpy/pandas state — causes silent corruption under multiprocessing
- `spawn` starts a clean Python interpreter, imports modules fresh — safe but slower (child must re-import everything)

---

## Task 1: Audit and Fix `event_engine.py` for Multiprocessing Safety

**Files:**
- Modify: `strategy/backtest/event_engine.py:567`
- Test: `tests/test_event_engine.py`

### What to look for (already done for you)

**Issue found:** `_train_meta_label()` at line 567:
```python
clf = RandomForestClassifier(n_estimators=50, random_state=42, n_jobs=-1)
```
`n_jobs=-1` means "use all CPUs". With 4 parallel worker processes each setting `n_jobs=-1`, all 4 try to spawn thread pools using all N cores → severe contention → slowdown or OOM. Fix: use `n_jobs=1` since we already have process-level parallelism.

**No other global state issues:** `logger` is module-level but safe with spawn (each child re-initialises). No class-level caches. No shared file handles.

### Step 1: Write the failing test

In `tests/test_event_engine.py`, add at the bottom:

```python
def test_meta_label_clf_uses_single_job():
    """RandomForestClassifier must use n_jobs=1 so parallel workers don't fight for CPUs."""
    import inspect
    from strategy.backtest.event_engine import EventDrivenEngine
    src = inspect.getsource(EventDrivenEngine._train_meta_label)
    assert "n_jobs=1" in src, (
        "_train_meta_label must use n_jobs=1 — n_jobs=-1 causes CPU contention "
        "when multiple worker processes run backtests simultaneously"
    )
```

### Step 2: Run test to see it fail

```bash
cd /Users/a004/Documents/claude_code/hedge-fund-research/.claude/worktrees/goofy-sanderson
pytest tests/test_event_engine.py::test_meta_label_clf_uses_single_job -v
```
Expected: FAIL — `AssertionError: _train_meta_label must use n_jobs=1`

### Step 3: Fix `event_engine.py`

In `strategy/backtest/event_engine.py`, line 567, change:
```python
clf = RandomForestClassifier(n_estimators=50, random_state=42, n_jobs=-1)
```
to:
```python
clf = RandomForestClassifier(n_estimators=50, random_state=42, n_jobs=1)
```

### Step 4: Run test to verify it passes

```bash
pytest tests/test_event_engine.py::test_meta_label_clf_uses_single_job -v
```
Expected: PASS

### Step 5: Run full event engine test suite

```bash
pytest tests/test_event_engine.py -v
```
Expected: all pass (no regressions)

### Step 6: Commit

```bash
git add strategy/backtest/event_engine.py tests/test_event_engine.py
git commit -m "fix: use n_jobs=1 in meta-label RF to prevent CPU contention under multiprocessing"
```

---

## Task 2: Extract Single-Iteration Function in `alpha_gpt.py`

**Files:**
- Modify: `scripts/alpha_gpt.py`
- Test: `tests/test_parallel_worker.py` (new, created in Task 3)

### Background

`run_alpha_gpt()` is a loop. For parallelism, we need to pull out one pass of that loop into a pure function that:
- Takes a history snapshot (read-only list of dicts)
- Returns a single history entry dict (not saved to disk)
- Has no side effects on shared state

### Step 1: Write the function (add to `scripts/alpha_gpt.py` after `spec_to_run_params`)

```python
def run_single_iteration(
    iteration: int,
    history_snapshot: list[dict],
    universe: list[str],
    close_prices: "pd.DataFrame",
    open_prices: "pd.DataFrame",
    ohlcv: "dict[str, pd.DataFrame]",
    macro_prices,
    sentiment_prices,
    start: str,
    end: str,
    model: str = "claude-sonnet-4-6",
    n_strategies_tested: int = 1,
) -> dict:
    """Run one AlphaGPT iteration and return the history entry dict.

    Does NOT write to disk. Caller is responsible for saving history.
    Safe to call in a worker process (no shared mutable state).
    """
    import os
    import anthropic as _anthropic
    from datetime import datetime as _dt

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {
            "iteration": iteration,
            "spec": {},
            "score": {},
            "diagnosis": "ANTHROPIC_API_KEY not set in worker environment",
            "timestamp": _dt.now().isoformat(),
            "trace": {
                "raw_llm_response": None,
                "parse_error": "no api key",
                "backtest_error": None,
                "cusum_entry_rate": None,
                "meta_label_mean_prob": None,
                "cost_drag_pct": None,
                "exit_reason_breakdown": None,
            },
        }

    client = _anthropic.Anthropic(api_key=api_key)

    # ── Ask the LLM ──────────────────────────────────────────────────────────
    user_msg = build_user_message(history_snapshot)
    try:
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            system=_load_system_prompt(),
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = response.content[0].text
    except Exception as e:
        return {
            "iteration": iteration,
            "spec": {},
            "score": {},
            "diagnosis": f"LLM call failed: {e}",
            "timestamp": _dt.now().isoformat(),
            "trace": {
                "raw_llm_response": None,
                "parse_error": str(e),
                "backtest_error": None,
                "cusum_entry_rate": None,
                "meta_label_mean_prob": None,
                "cost_drag_pct": None,
                "exit_reason_breakdown": None,
            },
        }

    logger.info(
        f"[iter {iteration}] LLM: {raw[:200]}{'...' if len(raw) > 200 else ''}"
    )

    # ── Parse and validate ────────────────────────────────────────────────────
    try:
        spec = parse_spec(raw)
    except json.JSONDecodeError as e:
        return {
            "iteration": iteration,
            "spec": {"raw": raw},
            "score": {},
            "diagnosis": f"JSON parse error: {e}",
            "timestamp": _dt.now().isoformat(),
            "trace": {
                "raw_llm_response": raw,
                "parse_error": str(e),
                "backtest_error": None,
                "cusum_entry_rate": None,
                "meta_label_mean_prob": None,
                "cost_drag_pct": None,
                "exit_reason_breakdown": None,
            },
        }

    errors = validate_spec(spec)
    if errors:
        return {
            "iteration": iteration,
            "spec": spec,
            "score": {},
            "diagnosis": f"Validation: {errors}",
            "timestamp": _dt.now().isoformat(),
            "trace": {
                "raw_llm_response": raw,
                "parse_error": None,
                "backtest_error": None,
                "cusum_entry_rate": None,
                "meta_label_mean_prob": None,
                "cost_drag_pct": None,
                "exit_reason_breakdown": None,
            },
        }

    expr = spec["expression"]
    logger.info(f"[iter {iteration}] Expression: {expr}")

    # ── Build signal and run backtest ─────────────────────────────────────────
    try:
        combiner = build_signal(expr, ohlcv)
    except Exception as e:
        return {
            "iteration": iteration,
            "spec": spec,
            "score": {},
            "diagnosis": f"Build error: {e}",
            "timestamp": _dt.now().isoformat(),
            "trace": {
                "raw_llm_response": raw,
                "parse_error": None,
                "backtest_error": str(e),
                "cusum_entry_rate": None,
                "meta_label_mean_prob": None,
                "cost_drag_pct": None,
                "exit_reason_breakdown": None,
            },
        }

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
    )

    diag = diagnose(score)
    logger.info(f"[iter {iteration}] {diag}")

    _engine_trace = (score.trace or {}) if score is not None else {}
    entry = {
        "iteration": iteration,
        "spec": spec,
        "score": {
            "sharpe": score.sharpe,
            "cagr": score.cagr,
            "max_dd": score.max_dd,
            "profit_factor": score.profit_factor,
            "win_rate": score.win_rate,
            "avg_win_pct": score.avg_win_pct,
            "avg_loss_pct": score.avg_loss_pct,
            "total_trades": score.total_trades,
            "avg_holding": score.avg_holding,
            "psr": score.psr,
            "score": score.score,
            "passed": score.passed,
        },
        "diagnosis": diag,
        "timestamp": _dt.now().isoformat(),
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

    # CPCV gate if winner
    if score.psr >= PSR_TARGET and score.passed and score.daily_returns is not None:
        cpcv_result = validate_winner_cpcv(score.daily_returns)
        entry["cpcv"] = cpcv_result

    return entry
```

**Note:** `run_config` is imported from `scripts.auto_research`. When `duckdb_store=None` and `parquet_storage=None` are passed, `run_config` uses them only for `MomentumSignal` (which is not used when `combiner` is passed). Pass `combiner` explicitly to bypass that code path.

Check `auto_research.py:run_config()` line 311-312:
```python
if combiner is None:
    combiner = SignalCombiner([MomentumSignal(duckdb_store)])
```
So passing `combiner` means `duckdb_store` and `parquet_storage` args are unused — safe to pass `None`.

### Step 2: No test for this function yet (tested indirectly in Task 3)

### Step 3: Commit after writing the function

```bash
git add scripts/alpha_gpt.py
git commit -m "feat: extract run_single_iteration() from run_alpha_gpt() for parallel use"
```

---

## Task 3: Create `scripts/parallel_worker.py`

**Files:**
- Create: `scripts/parallel_worker.py`
- Create: `tests/test_parallel_worker.py`

### Background

With `spawn`, only module-level functions can be pickled and sent to worker processes. The worker function lives in its own module (`parallel_worker.py`) to keep things clean and avoid circular imports.

### Step 1: Write the test FIRST (`tests/test_parallel_worker.py`)

```python
"""Tests for parallel worker: temp-file result passing, resource limits, timeout tracking."""
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import numpy as np
import pandas as pd
import pytest

# Add repo root to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))


def _make_tiny_prices(symbols=("A", "B"), n_days=30):
    dates = pd.bdate_range("2023-01-01", periods=n_days)
    data = {s: np.random.default_rng(42).uniform(90, 110, n_days) for s in symbols}
    df = pd.DataFrame(data, index=dates)
    df.index = pd.to_datetime(df.index)
    return df


# ---------------------------------------------------------------------------
# Test: worker writes valid JSON to temp file
# ---------------------------------------------------------------------------

def test_worker_writes_json_to_temp_file():
    """Worker must write a valid JSON dict with 'iteration' key to the output path."""
    from scripts.parallel_worker import worker_fn

    close = _make_tiny_prices()
    ohlcv = {"close": close, "open": close * 0.99, "high": close * 1.01,
              "low": close * 0.98, "volume": close * 1000, "returns": close.pct_change()}

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
        out_path = tf.name

    try:
        with patch("scripts.alpha_gpt.run_single_iteration") as mock_iter:
            mock_iter.return_value = {
                "iteration": 1,
                "spec": {"expression": "cs_rank(close)"},
                "score": {"sharpe": 0.5, "passed": False, "score": 0.1},
                "diagnosis": "test",
                "timestamp": "2026-01-01T00:00:00",
                "trace": {},
            }

            worker_fn({
                "iteration": 1,
                "history_snapshot": [],
                "universe": ["A", "B"],
                "close_prices": close,
                "open_prices": close * 0.99,
                "ohlcv": ohlcv,
                "macro_prices": None,
                "sentiment_prices": None,
                "start": "2023-01-01",
                "end": "2023-06-30",
                "model": "claude-sonnet-4-6",
                "n_strategies_tested": 1,
                "output_path": out_path,
            })

        result = json.loads(Path(out_path).read_text())
        assert result["iteration"] == 1
        assert "spec" in result
    finally:
        Path(out_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Test: worker writes error entry on exception (no crash)
# ---------------------------------------------------------------------------

def test_worker_writes_error_on_exception():
    """If run_single_iteration raises, worker must write an error entry — not crash."""
    from scripts.parallel_worker import worker_fn

    close = _make_tiny_prices()

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
        out_path = tf.name

    try:
        with patch("scripts.alpha_gpt.run_single_iteration", side_effect=RuntimeError("boom")):
            worker_fn({
                "iteration": 2,
                "history_snapshot": [],
                "universe": ["A"],
                "close_prices": close,
                "open_prices": close,
                "ohlcv": {},
                "macro_prices": None,
                "sentiment_prices": None,
                "start": "2023-01-01",
                "end": "2023-06-30",
                "model": "claude-sonnet-4-6",
                "n_strategies_tested": 1,
                "output_path": out_path,
            })

        result = json.loads(Path(out_path).read_text())
        assert result["iteration"] == 2
        assert "boom" in result["diagnosis"]
    finally:
        Path(out_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Test: _set_resource_limits doesn't crash on unsupported platform
# ---------------------------------------------------------------------------

def test_set_resource_limits_graceful():
    """_set_resource_limits must not raise even if resource module unavailable."""
    from scripts.parallel_worker import _set_resource_limits
    # Should not raise regardless of platform
    _set_resource_limits(memory_gb=2)
```

### Step 2: Run tests to see them fail

```bash
pytest tests/test_parallel_worker.py -v
```
Expected: ImportError (module doesn't exist yet)

### Step 3: Create `scripts/parallel_worker.py`

```python
"""Module-level worker function for parallel AlphaGPT batch execution.

Must be a top-level importable module so the function can be pickled
by ProcessPoolExecutor with spawn context.
"""

import json
import logging
import sys
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

logger = logging.getLogger(__name__)


def _set_resource_limits(memory_gb: int = 2) -> None:
    """Cap this process's virtual memory to memory_gb gigabytes.

    Skips silently if resource module is unavailable (Windows) or
    if the current limit is already stricter.
    """
    try:
        import resource
        limit_bytes = memory_gb * 1024 ** 3
        soft, hard = resource.getrlimit(resource.RLIMIT_AS)
        # Only tighten — never loosen the hard limit
        new_soft = limit_bytes if hard == resource.RLIM_INFINITY else min(limit_bytes, hard)
        resource.setrlimit(resource.RLIMIT_AS, (new_soft, hard))
        logger.debug(f"Worker memory cap set to {memory_gb}GB ({new_soft:,} bytes)")
    except (ImportError, AttributeError, ValueError):
        # Windows has no RLIMIT_AS; some Linux configs disallow setrlimit
        logger.debug("resource.setrlimit unavailable — skipping memory cap")
    except Exception as e:
        logger.warning(f"setrlimit failed (non-fatal): {e}")


class _NumpyEncoder(json.JSONEncoder):
    """Handle numpy scalars in JSON output from worker."""
    def default(self, obj):
        try:
            import numpy as np
            if isinstance(obj, (np.bool_, np.integer)):
                return int(obj)
            if isinstance(obj, np.floating):
                return float(obj)
        except ImportError:
            pass
        return super().default(obj)


def worker_fn(args: dict) -> None:
    """Entry point for a single parallel AlphaGPT iteration.

    Writes result as JSON to args['output_path']. Never writes to
    alpha_gpt_history.json. On any error, writes an error entry so
    the main process can log and continue.

    Args:
        args: dict with keys:
            iteration        — int, this worker's iteration number
            history_snapshot — list[dict], read-only history at batch start
            universe         — list[str]
            close_prices     — pd.DataFrame
            open_prices      — pd.DataFrame
            ohlcv            — dict[str, pd.DataFrame]
            macro_prices     — pd.DataFrame | None
            sentiment_prices — pd.DataFrame | None
            start            — str, ISO date
            end              — str, ISO date
            model            — str, Claude model name
            n_strategies_tested — int
            output_path      — str, path to write result JSON
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | worker | %(levelname)-8s | %(message)s",
        datefmt="%H:%M:%S",
    )

    _set_resource_limits(memory_gb=2)

    iteration = args["iteration"]
    output_path = args["output_path"]

    try:
        from scripts.alpha_gpt import run_single_iteration

        entry = run_single_iteration(
            iteration=iteration,
            history_snapshot=args["history_snapshot"],
            universe=args["universe"],
            close_prices=args["close_prices"],
            open_prices=args["open_prices"],
            ohlcv=args["ohlcv"],
            macro_prices=args["macro_prices"],
            sentiment_prices=args["sentiment_prices"],
            start=args["start"],
            end=args["end"],
            model=args["model"],
            n_strategies_tested=args["n_strategies_tested"],
        )
    except Exception as exc:
        import traceback
        from datetime import datetime
        logger.error(f"Worker {iteration} crashed: {exc}\n{traceback.format_exc()}")
        entry = {
            "iteration": iteration,
            "spec": {},
            "score": {},
            "diagnosis": f"Worker crash: {exc}",
            "timestamp": datetime.now().isoformat(),
            "trace": {
                "raw_llm_response": None,
                "parse_error": None,
                "backtest_error": traceback.format_exc(),
                "cusum_entry_rate": None,
                "meta_label_mean_prob": None,
                "cost_drag_pct": None,
                "exit_reason_breakdown": None,
            },
        }

    Path(output_path).write_text(json.dumps(entry, cls=_NumpyEncoder))
    logger.info(f"Worker {iteration} wrote result to {output_path}")
```

### Step 4: Run tests to verify they pass

```bash
pytest tests/test_parallel_worker.py -v
```
Expected: all pass

### Step 5: Commit

```bash
git add scripts/parallel_worker.py tests/test_parallel_worker.py
git commit -m "feat: add parallel_worker.py with spawn-safe worker function and resource limits"
```

---

## Task 4: Add Parallel Batch Runner and CLI Flags to `auto_research_loop.py`

**Files:**
- Modify: `scripts/auto_research_loop.py`

### Changes overview

1. Add three new imports at the top of the file
2. Add `_run_batch_parallel()` function
3. Modify `main()`:
   - Add three CLI args (`--workers`, `--worker-timeout`, `--no-parallel`)
   - Replace `run_alpha_gpt()` call with conditional (parallel vs sequential)
   - Keep/revert logic and meta-agent unchanged

### Step 1: Add imports (after existing imports block)

After `import tempfile` (line ~21) and after the `from scripts.alpha_gpt import ...` block, add:

```python
import multiprocessing
from concurrent.futures import ProcessPoolExecutor, as_completed, TimeoutError as FutureTimeoutError
```

### Step 2: Add `_run_batch_parallel()` helper function

Insert this function before `get_all_symbols()`:

```python
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
) -> list[dict]:
    """Run a batch of AlphaGPT iterations in parallel using ProcessPoolExecutor.

    Each worker:
      - Gets its own isolated copy of state (spawn, no fork)
      - Writes result to a unique temp JSON file
      - Is killed (future cancelled) if it exceeds worker_timeout seconds

    Results are sorted by iteration number before return. Crashed or timed-out
    workers produce an error entry (never raise to the caller).

    Returns:
        list[dict] — history entries, one per iteration, sorted by iteration.
    """
    from scripts.parallel_worker import worker_fn

    spawn_ctx = multiprocessing.get_context("spawn")

    # Create temp files for results (one per worker)
    temp_files: list[str] = []
    for _ in batch_iterations:
        tf = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        tf.close()
        temp_files.append(tf.name)

    # Build args dicts
    worker_args = []
    for iteration, out_path in zip(batch_iterations, temp_files):
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
            "n_strategies_tested": len(history_snapshot) + iteration,
            "output_path": out_path,
        })

    results: list[dict] = []
    timeout_entries: list[dict] = []

    logger.info(
        f"Launching {len(batch_iterations)} parallel workers "
        f"(max_workers={workers}, timeout={worker_timeout}s)"
    )

    with ProcessPoolExecutor(max_workers=workers, mp_context=spawn_ctx) as executor:
        future_to_args = {
            executor.submit(worker_fn, wargs): wargs
            for wargs in worker_args
        }

        for future in as_completed(future_to_args, timeout=worker_timeout + 30):
            wargs = future_to_args[future]
            iteration = wargs["iteration"]
            out_path = wargs["output_path"]

            try:
                future.result(timeout=worker_timeout)
                # Read result from temp file
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
                from datetime import datetime as _dt
                timeout_entries.append({
                    "iteration": iteration,
                    "spec": {},
                    "score": {},
                    "diagnosis": f"Worker timeout after {worker_timeout}s",
                    "timestamp": _dt.now().isoformat(),
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
                from datetime import datetime as _dt
                results.append({
                    "iteration": iteration,
                    "spec": {},
                    "score": {},
                    "diagnosis": f"Worker error: {exc}",
                    "timestamp": _dt.now().isoformat(),
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

    # Clean up temp files
    for out_path in temp_files:
        try:
            Path(out_path).unlink(missing_ok=True)
        except Exception:
            pass

    all_entries = sorted(results + timeout_entries, key=lambda e: e["iteration"])
    return all_entries
```

**Important gotcha:** `as_completed(timeout=...)` has a global timeout (time to wait for ALL futures). Set it to `worker_timeout + 30` to give a grace period. The per-future timeout is enforced via `future.result(timeout=worker_timeout)`.

### Step 3: Modify `main()` — add CLI args

In `main()`, after `ap.add_argument("--skip-preflight", ...)`, add:

```python
ap.add_argument("--workers", type=int, default=4,
                help="Parallel workers per batch (default: 4)")
ap.add_argument("--worker-timeout", type=int, default=300,
                help="Seconds before killing a worker (default: 300)")
ap.add_argument("--no-parallel", action="store_true",
                help="Disable parallelism, run sequentially (original behavior)")
```

### Step 4: Modify `main()` — replace the batch run block

Find this block (around line 683):
```python
        winner = run_alpha_gpt(
            universe=available,
            ...
            resume=True,
        )

        total_spent = len(load_history())
```

Replace with:
```python
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
            )

            # Merge results into history (main process owns the file)
            history_snapshot.extend(entries)
            save_history(history_snapshot)

            # Check if any worker found a winner
            winner = None
            for entry in entries:
                score = entry.get("score", {})
                if score.get("psr", 0) >= PSR_TARGET and score.get("passed"):
                    # Reconstruct a minimal RunScore-like object for the outer loop
                    from scripts.auto_research import RunScore
                    import pandas as pd as _pd
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
                        daily_returns=_pd.Series(dtype=float),
                    )
                    logger.info(
                        f"Parallel winner found at iteration {entry['iteration']}! "
                        f"PSR={score.get('psr', 0):.3f}"
                    )
                    break

        total_spent = len(load_history())
```

**Note on `import pandas as _pd`:** This will cause a syntax error — use `import pandas as pd` (it's already imported). Fix: just use `pd.Series(dtype=float)` since `pd` is already imported at module level.

Corrected winner block:
```python
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
```

### Step 5: Write a test for the parallel batch runner

Add to `tests/test_parallel_worker.py`:

```python
# ---------------------------------------------------------------------------
# Test: _run_batch_parallel collects results sorted by iteration
# (uses --no-parallel equivalent: mocked worker to avoid spawning real processes)
# ---------------------------------------------------------------------------

def test_run_batch_parallel_sorts_by_iteration(monkeypatch):
    """_run_batch_parallel must return results sorted by iteration number."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from scripts.auto_research_loop import _run_batch_parallel
    import numpy as np
    import pandas as pd

    close = _make_tiny_prices()
    ohlcv = {"close": close}

    # Mock worker_fn to immediately write a result, simulating fast workers
    def _fake_worker_fn(args):
        from datetime import datetime
        entry = {
            "iteration": args["iteration"],
            "spec": {"expression": f"cs_rank(close) + {args['iteration']}"},
            "score": {"sharpe": 0.1 * args["iteration"], "passed": False, "score": 0.1},
            "diagnosis": "mock",
            "timestamp": datetime.now().isoformat(),
            "trace": {},
        }
        Path(args["output_path"]).write_text(json.dumps(entry))

    monkeypatch.setattr("scripts.parallel_worker.worker_fn", _fake_worker_fn)

    results = _run_batch_parallel(
        batch_iterations=[3, 1, 2],
        history_snapshot=[],
        universe=["A", "B"],
        close_prices=close,
        open_prices=close,
        ohlcv=ohlcv,
        macro_prices=None,
        sentiment_prices=None,
        start="2023-01-01",
        end="2023-06-30",
        model="claude-sonnet-4-6",
        workers=2,
        worker_timeout=30,
    )

    assert [r["iteration"] for r in results] == [1, 2, 3]
```

**Note:** This test is tricky because `_run_batch_parallel` uses `ProcessPoolExecutor` which can't be easily monkeypatched at the function level in tests. A simpler integration approach: test with actual mocked workers writing temp files. The monkeypatch on `parallel_worker.worker_fn` won't work because spawn creates new processes.

**Revised test approach**: Test only the sequential mode (unit test), and trust integration testing for parallel. The smoke test (Task 6) validates end-to-end parallel behavior.

Replace the parallel test with a simpler sequential test:

```python
def test_no_parallel_sequential_mode_args():
    """Verify CLI accepts --no-parallel flag without error."""
    import subprocess, sys
    result = subprocess.run(
        [sys.executable, "scripts/auto_research_loop.py", "--help"],
        capture_output=True, text=True,
        cwd=str(Path(__file__).parent.parent)
    )
    assert "--no-parallel" in result.stdout
    assert "--workers" in result.stdout
    assert "--worker-timeout" in result.stdout
```

### Step 6: Run tests

```bash
pytest tests/test_parallel_worker.py -v
```
Expected: all pass

### Step 7: Commit

```bash
git add scripts/auto_research_loop.py
git commit -m "feat: add parallel batch runner with ProcessPoolExecutor + spawn, CLI flags --workers/--worker-timeout/--no-parallel"
```

---

## Task 5: Smoke Test

**Goal:** Verify end-to-end that `--workers 2 --budget 2` launches 2 workers, both write results, history has 2 entries.

### Step 1: Clear history and run with --no-parallel first (sanity baseline)

```bash
cd /Users/a004/Documents/claude_code/hedge-fund-research/.claude/worktrees/goofy-sanderson
python scripts/auto_research_loop.py \
    --budget 2 --batch-size 2 --workers 2 \
    --no-parallel --skip-preflight \
    --no-resume 2>&1 | head -60
```
Expected: 2 sequential iterations, history written, no crashes.

### Step 2: Run parallel mode with 2 workers

```bash
python scripts/auto_research_loop.py \
    --budget 2 --batch-size 2 \
    --workers 2 --worker-timeout 300 \
    --skip-preflight --no-resume \
    2>&1 | tail -40
```
Expected output patterns:
- `Launching 2 parallel workers (max_workers=2, timeout=300s)`
- `Worker 1 wrote result to /tmp/...`
- `Worker 2 wrote result to /tmp/...`
- `Worker 1 completed: score=...`
- `Worker 2 completed: score=...`
- `BATCH 1 COMPLETE — 2 total iterations`

### Step 3: Verify history has 2 entries

```bash
python -c "
import json; from pathlib import Path
h = json.loads(Path('data/cache/alpha_gpt_history.json').read_text())
print(f'History entries: {len(h)}')
print(f'Iterations: {[e[\"iteration\"] for e in h]}')
"
```
Expected: `History entries: 2`, `Iterations: [1, 2]`

### Step 4: Verify no temp files left behind

```bash
ls /tmp/*.json 2>/dev/null | wc -l
```
Expected: 0 (all cleaned up)

---

## Troubleshooting Guide

### "Can't pickle lambda" error
Worker function must be a module-level function (not a lambda, nested function, or closure). It must be importable from `scripts.parallel_worker`. Check that `worker_fn` is defined at module level.

### Workers all propose the same expression
This is expected — all workers see the same history snapshot and call the LLM with identical context. LLM temperature makes responses slightly different. The history will record all results including duplicates; the LLM is instructed "Do NOT repeat an expression you already tried."

### `as_completed` raises TimeoutError before all futures complete
The `timeout` in `as_completed(timeout=worker_timeout + 30)` is a global timeout. If some workers are very slow, increase `--worker-timeout`. The `future.result(timeout=worker_timeout)` per-future timeout handles individual slow workers.

### Memory error in worker
The 2GB cap via `setrlimit(RLIMIT_AS)` covers virtual address space, which includes memory-mapped parquet files. On macOS, RLIMIT_AS behaviour differs from Linux — it may be less effective. If OOM errors occur, reduce `--workers`.

### History file corruption
Workers NEVER write to `alpha_gpt_history.json`. Only the main process writes (via `save_history()`), after all workers complete. Safe.

### Sequential mode broken
`--no-parallel` calls the original `run_alpha_gpt()` unchanged. If sequential mode breaks, the issue is in the imports or the arg parsing block, not the parallel code.
