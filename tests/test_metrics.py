"""Tests for performance metrics."""

import numpy as np
import pandas as pd
import pytest

from analysis.metrics import (
    PerformanceMetrics,
    calculate_metrics,
    calculate_rolling_metrics,
    compare_to_benchmark,
)


class TestCalculateMetrics:
    """Tests for calculate_metrics function."""

    def test_empty_returns(self):
        returns = pd.Series([], dtype=float)
        metrics = calculate_metrics(returns)

        assert metrics.total_return == 0.0
        assert metrics.sharpe_ratio == 0.0

    def test_positive_returns(self):
        # 10% return each day for 252 days
        returns = pd.Series([0.0004] * 252)  # ~10% annualized
        metrics = calculate_metrics(returns)

        assert metrics.total_return > 0
        assert metrics.cagr > 0
        assert metrics.sharpe_ratio > 0

    def test_negative_returns(self):
        returns = pd.Series([-0.001] * 252)
        metrics = calculate_metrics(returns)

        assert metrics.total_return < 0
        assert metrics.sharpe_ratio < 0

    def test_drawdown_calculation(self):
        # Create returns that go up then down
        returns = pd.Series([0.1, 0.1, -0.15, -0.1, 0.05])
        metrics = calculate_metrics(returns)

        assert metrics.max_drawdown < 0

    def test_volatility(self):
        returns = pd.Series(np.random.normal(0.0005, 0.02, 252))
        metrics = calculate_metrics(returns)

        # Annualized vol should be roughly 2% * sqrt(252) ~ 32%
        assert 0.1 < metrics.annualized_volatility < 0.5

    def test_sortino_higher_than_sharpe_for_positive_skew(self):
        # Create returns with positive skew (more small losses, fewer big wins)
        np.random.seed(42)
        returns = pd.Series(np.random.exponential(0.01, 252) - 0.005)

        metrics = calculate_metrics(returns)

        # Sortino should be higher when there are fewer downside deviations
        if metrics.sharpe_ratio > 0:
            assert metrics.sortino_ratio >= metrics.sharpe_ratio


class TestRollingMetrics:
    """Tests for calculate_rolling_metrics function."""

    def test_insufficient_data(self):
        returns = pd.Series([0.01] * 100)
        df = calculate_rolling_metrics(returns, window=252)

        assert df.empty

    def test_rolling_window(self):
        returns = pd.Series([0.001] * 300)
        returns.index = pd.date_range("2024-01-01", periods=300)

        df = calculate_rolling_metrics(returns, window=100)

        assert not df.empty
        assert "rolling_sharpe" in df.columns
        assert len(df) == 201  # 300 - 100 + 1


class TestCompareToBenchmark:
    """Tests for compare_to_benchmark function."""

    def test_perfect_correlation(self):
        returns = pd.Series([0.01, -0.005, 0.02, -0.01, 0.015])
        benchmark = returns.copy()

        comparison = compare_to_benchmark(returns, benchmark)

        assert comparison["correlation"] == pytest.approx(1.0, rel=0.001)
        assert comparison["beta"] == pytest.approx(1.0, rel=0.001)

    def test_alpha_calculation(self):
        # Strategy beats benchmark consistently with some variance
        np.random.seed(42)
        benchmark = pd.Series(np.random.normal(0.001, 0.01, 252))
        strategy = pd.Series(np.random.normal(0.003, 0.01, 252))

        comparison = compare_to_benchmark(strategy, benchmark)

        # Strategy has higher returns
        assert comparison["strategy_cagr"] > comparison["benchmark_cagr"]

    def test_tracking_error(self):
        # Different returns should have tracking error
        np.random.seed(42)
        benchmark = pd.Series(np.random.normal(0.0005, 0.01, 252))
        strategy = pd.Series(np.random.normal(0.0006, 0.015, 252))

        comparison = compare_to_benchmark(strategy, benchmark)

        assert comparison["tracking_error"] > 0


class TestPerformanceMetrics:
    """Tests for PerformanceMetrics dataclass."""

    def test_metrics_dataclass(self):
        metrics = PerformanceMetrics(
            total_return=0.15,
            cagr=0.12,
            annualized_volatility=0.18,
            sharpe_ratio=0.67,
            sortino_ratio=0.89,
            calmar_ratio=0.8,
            max_drawdown=-0.15,
            max_drawdown_duration_days=45,
            total_trades=100,
            win_rate=0.55,
            profit_factor=1.5,
            avg_win=500.0,
            avg_loss=300.0,
            skewness=0.1,
            kurtosis=3.0,
        )

        assert metrics.total_return == 0.15
        assert metrics.sharpe_ratio == 0.67
        assert metrics.total_trades == 100
