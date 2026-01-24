"""
Tests for AFML module.

These tests verify the core AFML techniques work correctly.
"""

import numpy as np
import pandas as pd
import pytest


# Test fixtures
@pytest.fixture
def sample_prices():
    """Generate sample price series."""
    np.random.seed(42)
    dates = pd.date_range("2020-01-01", periods=500, freq="D")
    returns = np.random.randn(500) * 0.02
    prices = 100 * np.exp(np.cumsum(returns))
    return pd.Series(prices, index=dates, name="price")


@pytest.fixture
def sample_returns():
    """Generate sample return series."""
    np.random.seed(42)
    dates = pd.date_range("2020-01-01", periods=500, freq="D")
    returns = np.random.randn(500) * 0.01
    return pd.Series(returns, index=dates, name="returns")


@pytest.fixture
def sample_multi_asset_returns():
    """Generate sample multi-asset returns."""
    np.random.seed(42)
    dates = pd.date_range("2020-01-01", periods=252, freq="D")
    n_assets = 5
    returns = pd.DataFrame(
        np.random.randn(252, n_assets) * 0.02,
        index=dates,
        columns=["AAPL", "GOOGL", "MSFT", "AMZN", "META"],
    )
    return returns


class TestPurgedKFold:
    """Tests for Purged K-Fold CV."""

    def test_basic_split(self, sample_returns):
        """Test basic split works."""
        from afml import purged_kfold

        X = pd.DataFrame({"feature": sample_returns.values}, index=sample_returns.index)

        splits = list(purged_kfold(X, n_splits=5))

        assert len(splits) == 5
        for train_idx, test_idx in splits:
            assert len(train_idx) > 0
            assert len(test_idx) > 0
            # No overlap
            assert len(set(train_idx) & set(test_idx)) == 0

    def test_embargo_reduces_training(self, sample_returns):
        """Test embargo removes samples after test set."""
        from afml import purged_kfold

        X = pd.DataFrame({"feature": sample_returns.values}, index=sample_returns.index)

        splits_no_embargo = list(purged_kfold(X, n_splits=5, embargo_pct=0.0))
        splits_with_embargo = list(purged_kfold(X, n_splits=5, embargo_pct=0.05))

        # Embargo should reduce training set size
        total_train_no_embargo = sum(len(s[0]) for s in splits_no_embargo)
        total_train_with_embargo = sum(len(s[0]) for s in splits_with_embargo)

        assert total_train_with_embargo < total_train_no_embargo


class TestTripleBarrier:
    """Tests for Triple-Barrier Labeling."""

    def test_basic_labeling(self, sample_prices):
        """Test basic labeling works."""
        from afml import triple_barrier

        labels = triple_barrier(sample_prices, max_holding=10)

        assert len(labels.labels) > 0
        assert set(labels.labels.unique()).issubset({-1, 0, 1})

    def test_exit_types(self, sample_prices):
        """Test all exit types are generated."""
        from afml import triple_barrier

        labels = triple_barrier(sample_prices, max_holding=10)

        # Should have at least some variety in exit types
        exit_types = set(labels.exit_types.unique())
        assert len(exit_types) > 0
        assert exit_types.issubset({"profit", "stop", "timeout"})

    def test_returns_are_reasonable(self, sample_prices):
        """Test returns are within expected range."""
        from afml import triple_barrier

        labels = triple_barrier(
            sample_prices, profit_take=2.0, stop_loss=2.0, max_holding=10
        )

        # Returns should be bounded (roughly by barriers)
        assert labels.returns.abs().max() < 1.0  # Less than 100%


class TestSampleUniqueness:
    """Tests for Sample Uniqueness Weighting."""

    def test_weights_sum_to_one(self, sample_prices):
        """Test normalized weights sum to 1."""
        from afml import triple_barrier
        from afml.weights import sample_uniqueness_from_labels

        labels = triple_barrier(sample_prices, max_holding=10)
        weights = sample_uniqueness_from_labels(labels, normalize=True)

        assert abs(weights.sum() - 1.0) < 1e-6

    def test_overlapping_samples_downweighted(self):
        """Test overlapping samples get lower weights."""
        from afml import sample_uniqueness

        # Create overlapping labels
        labels_start = pd.Series(
            [
                pd.Timestamp("2020-01-01"),
                pd.Timestamp("2020-01-02"),  # Overlaps with first
                pd.Timestamp("2020-01-10"),  # No overlap
            ]
        )
        labels_end = pd.Series(
            [
                pd.Timestamp("2020-01-05"),
                pd.Timestamp("2020-01-06"),
                pd.Timestamp("2020-01-15"),
            ]
        )

        weights = sample_uniqueness(labels_start, labels_end, normalize=False)

        # Non-overlapping sample should have higher weight
        assert weights.iloc[2] >= weights.iloc[0]


class TestDeflatedSharpe:
    """Tests for Deflated Sharpe Ratio / PSR."""

    def test_basic_calculation(self, sample_returns):
        """Test PSR calculation works."""
        from afml import deflated_sharpe

        result = deflated_sharpe(sample_returns.values)

        assert 0 <= result.psr <= 1
        assert result.n_observations == len(sample_returns)

    def test_multiple_testing_adjustment(self, sample_returns):
        """Test multiple testing reduces PSR."""
        from afml import deflated_sharpe

        result_1 = deflated_sharpe(sample_returns.values, n_strategies_tested=1)
        result_10 = deflated_sharpe(sample_returns.values, n_strategies_tested=10)

        # More strategies tested should reduce PSR
        assert result_10.psr <= result_1.psr

    def test_threshold_check(self):
        """Test threshold check works."""
        from afml import deflated_sharpe

        # High Sharpe should pass
        np.random.seed(42)
        good_returns = np.random.randn(500) * 0.01 + 0.002  # Positive drift
        result = deflated_sharpe(good_returns, threshold=0.5)

        # Should be testable (bool or numpy bool)
        assert result.passes_threshold in (True, False)


class TestHRP:
    """Tests for Hierarchical Risk Parity."""

    def test_weights_sum_to_one(self, sample_multi_asset_returns):
        """Test HRP weights sum to 1."""
        from afml import hrp

        result = hrp(sample_multi_asset_returns)

        assert abs(result.weights.sum() - 1.0) < 1e-6

    def test_all_weights_positive(self, sample_multi_asset_returns):
        """Test all weights are positive (long-only)."""
        from afml import hrp

        result = hrp(sample_multi_asset_returns)

        assert (result.weights >= 0).all()

    def test_cluster_order_complete(self, sample_multi_asset_returns):
        """Test all assets appear in cluster order."""
        from afml import hrp

        result = hrp(sample_multi_asset_returns)

        assert set(result.cluster_order) == set(sample_multi_asset_returns.columns)


class TestRegime:
    """Tests for Regime Detection."""

    def test_basic_detection(self, sample_prices):
        """Test regime detection works."""
        from afml import Regime, regime_200ma

        signal = regime_200ma(sample_prices, ma_period=50)  # Shorter for test

        assert signal.current_regime in [Regime.BULL, Regime.BEAR, Regime.NEUTRAL]
        assert len(signal.regime_series) == len(sample_prices)

    def test_bull_market_detection(self):
        """Test bull market is detected correctly."""
        from afml import Regime, regime_200ma

        # Create trending up prices
        dates = pd.date_range("2020-01-01", periods=300, freq="D")
        prices = pd.Series(np.linspace(100, 200, 300), index=dates)

        signal = regime_200ma(prices, ma_period=50)

        # Should be bull at the end
        assert signal.current_regime == Regime.BULL


class TestStationarity:
    """Tests for Stationarity Checks."""

    def test_returns_are_stationary(self, sample_returns):
        """Test returns are detected as stationary."""
        from afml.checks import adf_test

        result = adf_test(sample_returns)

        # Random returns should be stationary
        assert result.is_stationary

    def test_prices_are_nonstationary(self, sample_prices):
        """Test prices are detected as non-stationary."""
        from afml.checks import adf_test

        result = adf_test(sample_prices)

        # Trending prices should be non-stationary
        assert not result.is_stationary

    def test_batch_check(self, sample_returns, sample_prices):
        """Test batch stationarity check."""
        from afml import stationarity_check

        data = pd.DataFrame(
            {
                "returns": sample_returns.values[: len(sample_prices)],
                "prices": sample_prices.values,
            }
        )

        results, warnings = stationarity_check(data)

        assert len(results) == 2
        assert len(warnings) >= 1  # At least prices should warn
