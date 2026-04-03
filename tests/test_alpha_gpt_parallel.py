"""Tests for run_single_iteration() — the parallel-safe single-pass function."""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import numpy as np
import pandas as pd
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
import pytest


def _make_prices(symbols=("AAPL", "MSFT"), n=60):
    dates = pd.bdate_range("2022-01-03", periods=n)
    data = {s: np.random.default_rng(0).uniform(100, 200, n) for s in symbols}
    df = pd.DataFrame(data, index=pd.to_datetime(dates))
    return df


def test_run_single_iteration_returns_dict():
    """run_single_iteration returns a dict with required keys."""
    from scripts.alpha_gpt import run_single_iteration

    close = _make_prices()
    ohlcv = {"close": close, "open": close * 0.99, "high": close * 1.01,
              "low": close * 0.98, "volume": close * 1000,
              "returns": close.pct_change().fillna(0)}

    # Mock the LLM call and backtest so no real API/data needed
    fake_spec = {
        "expression": "cs_rank(close)",
        "backtest": {
            "profit_take_mult": 2.0, "stop_loss_mult": 1.0,
            "max_holding_days": 20, "n_positions": 10,
            "rebalance_frequency": "monthly", "position_sizing": "equal",
            "use_cusum_gate": False, "use_regime": False, "slippage_bps": 25
        },
        "rationale": "test",
    }
    fake_response = MagicMock()
    fake_response.content = [MagicMock(text=json.dumps(fake_spec))]

    from scripts.auto_research import RunScore
    fake_score = RunScore(
        config_id="test", sharpe=0.3, cagr=5.0, max_dd=-10.0,
        profit_factor=1.3, win_rate=0.5, avg_win_pct=2.0, avg_loss_pct=1.5,
        kelly_fraction=0.2, total_trades=120, avg_holding=10.0,
        psr=0.6, score=1.5, passed=False, params={},
        daily_returns=pd.Series(dtype=float), trace={}
    )

    with patch("anthropic.Anthropic") as mock_client_cls, \
         patch("scripts.alpha_gpt.run_config", return_value=fake_score), \
         patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
        mock_client = MagicMock()
        mock_client.messages.create.return_value = fake_response
        mock_client_cls.return_value = mock_client

        result = run_single_iteration(
            iteration=1,
            history_snapshot=[],
            universe=["AAPL", "MSFT"],
            close_prices=close,
            open_prices=close * 0.99,
            ohlcv=ohlcv,
            macro_prices=None,
            sentiment_prices=None,
            start="2022-01-01",
            end="2022-12-31",
            model="claude-sonnet-4-6",
            n_strategies_tested=1,
        )

    assert isinstance(result, dict)
    assert result["iteration"] == 1
    assert "spec" in result
    assert "score" in result
    assert "diagnosis" in result
    assert "timestamp" in result
    assert "trace" in result
    # must not have called save_history (no disk writes)


def test_run_single_iteration_no_api_key_returns_error():
    """If ANTHROPIC_API_KEY is missing, returns error entry (no raise)."""
    from scripts.alpha_gpt import run_single_iteration
    import os

    close = _make_prices()
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}

    with patch.dict("os.environ", env, clear=True):
        result = run_single_iteration(
            iteration=5,
            history_snapshot=[],
            universe=["AAPL"],
            close_prices=close,
            open_prices=close,
            ohlcv={},
            macro_prices=None,
            sentiment_prices=None,
            start="2022-01-01",
            end="2022-12-31",
        )

    assert result["iteration"] == 5
    assert result["score"] == {}
    assert "api key" in result["diagnosis"].lower() or "ANTHROPIC_API_KEY" in result["diagnosis"]
