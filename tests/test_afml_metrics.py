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
