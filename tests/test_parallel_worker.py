"""Tests for parallel_worker: temp-file result passing, resource limits, error handling."""
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
import sys
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


def _make_prices(symbols=("A", "B"), n_days=30):
    dates = pd.bdate_range("2023-01-01", periods=n_days)
    data = {s: np.random.default_rng(42).uniform(90, 110, n_days) for s in symbols}
    df = pd.DataFrame(data, index=pd.to_datetime(dates))
    return df


def test_worker_writes_valid_json():
    """worker_fn writes a JSON dict with 'iteration' key to output_path."""
    from scripts.parallel_worker import worker_fn

    close = _make_prices()
    ohlcv = {"close": close}

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
        out_path = tf.name

    fake_entry = {
        "iteration": 1,
        "spec": {"expression": "cs_rank(close)"},
        "score": {"sharpe": 0.5, "passed": False, "score": 0.1},
        "diagnosis": "test",
        "timestamp": "2026-01-01T00:00:00",
        "trace": {},
    }

    try:
        # Patch at the source module level — the worker imports fresh each call
        with patch("scripts.alpha_gpt.run_single_iteration", return_value=fake_entry):
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
        assert "score" in result
    finally:
        Path(out_path).unlink(missing_ok=True)


def test_worker_writes_error_on_exception():
    """If run_single_iteration raises, worker writes an error entry — never crashes."""
    from scripts.parallel_worker import worker_fn

    close = _make_prices()

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
        assert "boom" in result["diagnosis"] or "crash" in result["diagnosis"].lower()
        assert "backtest_error" in result["trace"]
    finally:
        Path(out_path).unlink(missing_ok=True)


def test_set_resource_limits_does_not_raise():
    """_set_resource_limits must never raise, even on unsupported platforms."""
    from scripts.parallel_worker import _set_resource_limits
    # Must not raise
    _set_resource_limits(memory_gb=2)


def test_worker_does_not_write_to_history(tmp_path):
    """worker_fn must only write to output_path, never to alpha_gpt_history.json."""
    from scripts.parallel_worker import worker_fn

    close = _make_prices()
    out_file = str(tmp_path / "result.json")

    fake_entry = {
        "iteration": 3,
        "spec": {},
        "score": {},
        "diagnosis": "ok",
        "timestamp": "2026-01-01",
        "trace": {},
    }

    with patch("scripts.alpha_gpt.run_single_iteration", return_value=fake_entry), \
         patch("scripts.alpha_gpt.save_history") as mock_save:
        worker_fn({
            "iteration": 3,
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
            "output_path": out_file,
        })

    # save_history must never be called by the worker
    mock_save.assert_not_called()
    # output file must exist
    assert Path(out_file).exists()
