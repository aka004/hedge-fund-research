"""Tests for per-universe benchmark_symbol in run_config."""

import inspect


def test_run_config_accepts_benchmark_symbol():
    """run_config must accept and forward benchmark_symbol to EventEngineConfig."""
    from scripts.auto_research import run_config

    sig = inspect.signature(run_config)
    assert "benchmark_symbol" in sig.parameters, \
        "run_config must accept benchmark_symbol parameter"
