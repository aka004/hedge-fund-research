"""Tests for afml/metrics.py — PSR benchmark and expected_max_sharpe."""

import numpy as np

from afml.metrics import deflated_sharpe


def test_psr_benchmark_not_deflated_by_annualization():
    """PSR benchmark should not divide by sqrt(annualization).

    With N=10 strategies and annualization=252, the current buggy code
    deflates the benchmark by sqrt(252) ≈ 15.87, making it ~0.09.
    The correct benchmark is ~1.4 (un-deflated).
    """
    rng = np.random.default_rng(42)
    # Strong strategy: will pass even against correct (higher) benchmark
    returns = rng.normal(0.001, 0.01, 252 * 3)

    result_n1 = deflated_sharpe(returns, n_strategies_tested=1)
    result_n10 = deflated_sharpe(returns, n_strategies_tested=10)

    # With more strategies tested, PSR should be LOWER (harder to pass)
    # Buggy code makes benchmark too easy, so PSR stays high with N=10
    # Correct code should show meaningful PSR reduction
    assert result_n10.psr < result_n1.psr, (
        f"PSR with N=10 ({result_n10.psr:.3f}) should be lower than "
        f"PSR with N=1 ({result_n1.psr:.3f}) — more strategies = harder to pass"
    )


def test_psr_in_run_screening():
    """In-run screening PSR (n_strategies=1) must be clearly between 0 and 1.

    Regression test: n_strategies_tested=100 inflates the DSR benchmark to
    ~2.53 via expected_max_sharpe(100), giving PSR=0.000 for any realistic
    strategy. The fix passes n_strategies=1 for screening so PSR = P(SR > 0).

    Spec: Sharpe=1.0, n_strategies=100, T=252, sr_std≈0.2 → PSR must be
    clearly > 0 when using n_strategies=1 (screening mode).
    """
    rng = np.random.default_rng(0)
    # Construct T=252 daily returns with annualized Sharpe ≈ 1.0
    # daily_mean = sr / sqrt(252) * daily_std; set daily_std = 0.02 (2%/day)
    daily_std = 0.02
    daily_mean = 1.0 / np.sqrt(252) * daily_std  # ≈ 0.00126
    returns = rng.normal(daily_mean, daily_std, 252)

    # --- Screening mode (n=1): PSR should be meaningful (clearly > 0, NOT 0.000) ---
    result_screen = deflated_sharpe(returns, n_strategies_tested=1)
    assert result_screen.psr > 0.5, (
        f"Screening PSR should be > 0.5 for Sharpe~1.0 strategy, got {result_screen.psr:.4f}. "
        f"If PSR=0.000 the n_strategies_tested inflation bug has returned."
    )

    # --- Legacy mode (n=100): DSR benchmark is high, PSR collapses toward 0 ---
    result_dsr = deflated_sharpe(returns, n_strategies_tested=100)
    assert result_dsr.psr < result_screen.psr, (
        f"DSR(n=100) PSR {result_dsr.psr:.4f} should be < screening PSR {result_screen.psr:.4f}"
    )

    # --- Confirm the root cause: expected_max_sharpe(100) >> Sharpe=1.0 ---
    from afml.metrics import expected_max_sharpe
    benchmark_100 = expected_max_sharpe(100)
    assert benchmark_100 > 2.0, (
        f"expected_max_sharpe(100) should exceed 2.0, got {benchmark_100:.4f}"
    )
    assert result_screen.sharpe < benchmark_100, (
        "Confirms Sharpe=1.0 cannot beat the DSR benchmark of 2.5+ with n=100"
    )


def test_expected_max_sharpe_standalone():
    """expected_max_sharpe() should exist as a standalone function."""
    from afml.metrics import expected_max_sharpe

    # N=1: no multiple testing, benchmark = 0
    assert expected_max_sharpe(1) == 0.0

    # N grows: expected max Sharpe increases (harder to beat)
    e10 = expected_max_sharpe(10)
    e100 = expected_max_sharpe(100)
    assert e100 > e10 > 0.0, "More trials = higher expected max Sharpe"

    # Typical range: for N=10, should be around 1.0-2.0
    assert 0.5 < e10 < 3.0, f"Unexpected value: {e10}"
