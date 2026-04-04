"""Tests for universe field in history entries and per-universe n_strategies_tested."""

from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_history_entry_has_universe_field():
    """Every history entry built by alpha_gpt must include a universe field."""
    from scripts.alpha_gpt import _build_error_entry_for_test

    entry = _build_error_entry_for_test(
        iteration=1,
        diag="test",
        spec={"expression": "cs_rank(returns)"},
        universe_name="russell2000_tech",
    )
    assert entry["universe"] == "russell2000_tech"


def test_history_entry_defaults_to_sp500():
    from scripts.alpha_gpt import _build_error_entry_for_test

    entry = _build_error_entry_for_test(
        iteration=1,
        diag="test",
        spec={"expression": "momentum(close, 20)"},
    )
    assert entry["universe"] == "sp500"
