"""Module-level worker function for parallel AlphaGPT batch execution.

Must be a top-level importable module so the function can be pickled
by ProcessPoolExecutor with spawn context.
"""

import json
import logging
import random
import sys
import time
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
        new_soft = limit_bytes if hard == resource.RLIM_INFINITY else min(limit_bytes, hard)
        resource.setrlimit(resource.RLIMIT_AS, (new_soft, hard))
        logger.debug(f"Worker memory cap set to {memory_gb}GB ({new_soft:,} bytes)")
    except (ImportError, AttributeError, ValueError):
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
            system_prompt    — str | None, resolved system prompt (includes program.md)
            output_path      — str, path to write result JSON
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | worker | %(levelname)-8s | %(message)s",
        datefmt="%H:%M:%S",
    )

    _set_resource_limits(memory_gb=2)

    # Stagger startup to avoid parquet read race conditions when multiple
    # workers spawn simultaneously and all try to read the same files at once.
    jitter = random.uniform(0.0, 1.0)
    time.sleep(jitter)

    iteration = args["iteration"]
    output_path = args["output_path"]
    archetype = args.get("archetype")
    temperature = args.get("temperature", 1.0)
    logger.info(f"Worker {iteration} | archetype={archetype} | temperature={temperature:.1f}")

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
            system_prompt=args.get("system_prompt"),
            archetype=args.get("archetype"),
            temperature=args.get("temperature", 1.0),
            regime_filter=args.get("regime_filter"),
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
