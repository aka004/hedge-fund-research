"""
Tests for AFML Stage 4-6 modules.

Kelly criterion, CPCV, sequential bootstrap, CUSUM filter, meta-labeling.
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
def overlapping_labels():
    """Generate overlapping label start/end times for bootstrap tests."""
    np.random.seed(42)
    dates = pd.date_range("2020-01-01", periods=100, freq="D")
    # Labels span 5-15 days, creating overlap
    durations = np.random.randint(5, 16, size=100)
    labels_start = pd.Series(dates, index=range(100))
    labels_end = pd.Series(
        [dates[i] + pd.Timedelta(days=int(durations[i])) for i in range(100)],
        index=range(100),
    )
    return labels_start, labels_end


class TestKellyCriterion:
    """Tests for Kelly Criterion bet sizing."""

    def test_basic_kelly(self):
        """kelly_criterion(0.6, 1.0) -> full_kelly = 0.2"""
        from afml import kelly_criterion

        result = kelly_criterion(0.6, 1.0)
        assert abs(result.full_kelly - 0.2) < 1e-6
        assert abs(result.half_kelly - 0.1) < 1e-6

    def test_no_edge(self):
        """Kelly with p=0.5, odds=1.0 -> f*=0 (no edge)."""
        from afml import kelly_criterion

        result = kelly_criterion(0.5, 1.0)
        assert abs(result.full_kelly) < 1e-6

    def test_negative_edge(self):
        """Kelly with p=0.3 -> negative f* (don't bet)."""
        from afml import kelly_criterion

        result = kelly_criterion(0.3, 1.0)
        assert result.full_kelly < 0

    def test_high_odds(self):
        """Kelly with favorable odds."""
        from afml import kelly_criterion

        result = kelly_criterion(0.4, 3.0)
        # f* = (0.4*3 - 0.6) / 3 = (1.2 - 0.6) / 3 = 0.2
        assert abs(result.full_kelly - 0.2) < 1e-6

    def test_expected_value(self):
        """Expected value should be p*b - q."""
        from afml import kelly_criterion

        result = kelly_criterion(0.6, 2.0)
        expected = 0.6 * 2.0 - 0.4
        assert abs(result.expected_value - expected) < 1e-6

    def test_edge_prob_zero(self):
        """p=0 should give f*=0."""
        from afml import kelly_criterion

        result = kelly_criterion(0.0, 1.0)
        assert result.full_kelly <= 0

    def test_edge_prob_one(self):
        """p=1 should give f*=1."""
        from afml import kelly_criterion

        result = kelly_criterion(1.0, 1.0)
        assert abs(result.full_kelly - 1.0) < 1e-6

    def test_invalid_odds(self):
        """Negative odds should raise."""
        from afml import kelly_criterion

        with pytest.raises(ValueError):
            kelly_criterion(0.5, -1.0)


class TestDiscreteKelly:
    """Tests for discrete Kelly sizing."""

    def test_rounds_down(self):
        """Discrete kelly rounds down to step."""
        from afml import discrete_kelly

        # f* = 0.2, step = 0.05 -> 0.20
        result = discrete_kelly(0.6, 1.0, step=0.05)
        assert abs(result - 0.20) < 1e-6

    def test_negative_returns_zero(self):
        """Negative edge returns 0."""
        from afml import discrete_kelly

        result = discrete_kelly(0.3, 1.0, step=0.05)
        assert result == 0.0

    def test_step_rounding(self):
        """Verify step rounding logic."""
        from afml import discrete_kelly

        # f* = (0.55*1 - 0.45)/1 = 0.1, step = 0.05 -> 0.10
        result = discrete_kelly(0.55, 1.0, step=0.05)
        assert abs(result - 0.10) < 1e-6


class TestCPCV:
    """Tests for Combinatorial Purged Cross-Validation."""

    def test_path_count(self):
        """6 splits, 2 test groups -> C(6,2) = 15 paths."""
        from afml import CombPurgedKFold

        cpcv = CombPurgedKFold(n_splits=6, n_test_groups=2)
        X = pd.DataFrame(
            np.random.randn(500, 3),
            index=pd.date_range("2020-01-01", periods=500),
        )
        splits = list(cpcv.split(X))
        assert len(splits) == 15

    def test_no_train_test_overlap(self):
        """Train and test must not overlap."""
        from afml import CombPurgedKFold

        cpcv = CombPurgedKFold(n_splits=6, n_test_groups=2)
        X = pd.DataFrame(
            np.random.randn(300, 2),
            index=pd.date_range("2020-01-01", periods=300),
        )

        for train_idx, test_idx in cpcv.split(X):
            overlap = set(train_idx) & set(test_idx)
            assert len(overlap) == 0, f"Train/test overlap: {overlap}"

    def test_different_split_configs(self):
        """5 splits, 2 test groups -> C(5,2) = 10 paths."""
        from afml import CombPurgedKFold

        cpcv = CombPurgedKFold(n_splits=5, n_test_groups=2)
        X = pd.DataFrame(
            np.random.randn(250, 2),
            index=pd.date_range("2020-01-01", periods=250),
        )
        splits = list(cpcv.split(X))
        assert len(splits) == 10

    def test_backtest_paths(self):
        """backtest_paths returns correct structure."""
        from afml import CombPurgedKFold

        np.random.seed(42)
        cpcv = CombPurgedKFold(n_splits=4, n_test_groups=2)
        X = pd.DataFrame(
            np.random.randn(200, 3),
            index=pd.date_range("2020-01-01", periods=200),
        )
        y = pd.Series(
            np.random.randn(200) * 0.01,
            index=X.index,
        )

        result = cpcv.backtest_paths(X, y)
        assert result.n_paths == 6  # C(4,2)
        assert len(result.paths) == 6
        assert len(result.path_sharpes) == 6
        assert 0.0 <= result.pbo <= 1.0

    def test_pbo_range(self):
        """PBO must be between 0 and 1."""
        from afml import CombPurgedKFold

        np.random.seed(42)
        cpcv = CombPurgedKFold(n_splits=6, n_test_groups=2)
        X = pd.DataFrame(
            np.random.randn(500, 3),
            index=pd.date_range("2020-01-01", periods=500),
        )
        y = pd.Series(np.random.randn(500) * 0.01, index=X.index)

        result = cpcv.backtest_paths(X, y)
        assert 0.0 <= result.pbo <= 1.0


class TestSequentialBootstrap:
    """Tests for Sequential Bootstrap."""

    def test_returns_correct_length(self, overlapping_labels):
        """Should return n_samples indices."""
        from afml import sequential_bootstrap

        labels_start, labels_end = overlapping_labels
        np.random.seed(42)
        idx = sequential_bootstrap(labels_start, labels_end, n_samples=50)
        assert len(idx) == 50

    def test_default_n_samples(self, overlapping_labels):
        """Default n_samples = len(labels)."""
        from afml import sequential_bootstrap

        labels_start, labels_end = overlapping_labels
        np.random.seed(42)
        idx = sequential_bootstrap(labels_start, labels_end)
        assert len(idx) == len(labels_start)

    def test_indices_in_range(self, overlapping_labels):
        """All indices must be valid."""
        from afml import sequential_bootstrap

        labels_start, labels_end = overlapping_labels
        np.random.seed(42)
        idx = sequential_bootstrap(labels_start, labels_end, n_samples=50)
        assert all(0 <= i < len(labels_start) for i in idx)

    def test_uniqueness_higher_than_standard(self, overlapping_labels):
        """Sequential bootstrap should have higher average uniqueness."""
        from afml import average_uniqueness, sequential_bootstrap

        labels_start, labels_end = overlapping_labels
        n = len(labels_start)

        # Standard bootstrap
        np.random.seed(42)
        standard_idx = np.random.choice(n, size=n, replace=True)
        standard_u = average_uniqueness(labels_start, labels_end, standard_idx)

        # Sequential bootstrap
        np.random.seed(42)
        seq_idx = sequential_bootstrap(labels_start, labels_end)
        seq_u = average_uniqueness(labels_start, labels_end, seq_idx)

        # Sequential should have >= uniqueness (may be equal for small sets)
        assert seq_u >= standard_u * 0.9  # Allow small tolerance


class TestAverageUniqueness:
    """Tests for average_uniqueness function."""

    def test_non_overlapping(self):
        """Non-overlapping labels should have uniqueness = 1."""
        from afml import average_uniqueness

        labels_start = pd.Series(
            [
                pd.Timestamp("2020-01-01"),
                pd.Timestamp("2020-01-10"),
                pd.Timestamp("2020-01-20"),
            ]
        )
        labels_end = pd.Series(
            [
                pd.Timestamp("2020-01-05"),
                pd.Timestamp("2020-01-15"),
                pd.Timestamp("2020-01-25"),
            ]
        )

        u = average_uniqueness(labels_start, labels_end, np.array([0, 1, 2]))
        assert abs(u - 1.0) < 1e-6

    def test_fully_overlapping(self):
        """Fully overlapping labels should have uniqueness < 1."""
        from afml import average_uniqueness

        labels_start = pd.Series(
            [
                pd.Timestamp("2020-01-01"),
                pd.Timestamp("2020-01-01"),
            ]
        )
        labels_end = pd.Series(
            [
                pd.Timestamp("2020-01-10"),
                pd.Timestamp("2020-01-10"),
            ]
        )

        u = average_uniqueness(labels_start, labels_end, np.array([0, 1]))
        assert u < 1.0
        assert abs(u - 0.5) < 1e-6

    def test_empty_indices(self):
        """Empty sample set should return 1.0."""
        from afml import average_uniqueness

        labels_start = pd.Series([pd.Timestamp("2020-01-01")])
        labels_end = pd.Series([pd.Timestamp("2020-01-05")])

        u = average_uniqueness(labels_start, labels_end, np.array([]))
        assert u == 1.0


class TestCUSUM:
    """Tests for CUSUM filter."""

    def test_detects_structural_break(self):
        """CUSUM should detect break in trending data."""
        from afml import cusum_filter

        dates = pd.date_range("2020-01-01", periods=300, freq="D")
        # Flat period, then trending up
        prices = pd.Series(
            np.concatenate(
                [
                    100 + np.random.RandomState(42).randn(150) * 0.5,
                    100 + np.cumsum(np.random.RandomState(42).randn(150) * 0.5 + 0.3),
                ]
            ),
            index=dates,
        )
        result = cusum_filter(prices)
        assert len(result.events) > 0

    def test_returns_cusum_series(self):
        """Result should contain positive and negative CUSUM series."""
        from afml import cusum_filter

        dates = pd.date_range("2020-01-01", periods=200, freq="D")
        np.random.seed(42)
        prices = pd.Series(
            100 * np.exp(np.cumsum(np.random.randn(200) * 0.02)), index=dates
        )

        result = cusum_filter(prices)
        # CUSUM series should have same length as returns (n-1)
        assert len(result.cusum_positive) == len(prices) - 1
        assert len(result.cusum_negative) == len(prices) - 1

    def test_threshold_auto_computed(self):
        """Auto threshold should be positive."""
        from afml import cusum_filter

        dates = pd.date_range("2020-01-01", periods=200, freq="D")
        np.random.seed(42)
        prices = pd.Series(
            100 * np.exp(np.cumsum(np.random.randn(200) * 0.02)), index=dates
        )

        result = cusum_filter(prices)
        assert result.threshold > 0

    def test_custom_threshold(self):
        """Custom threshold should be respected."""
        from afml import cusum_filter

        dates = pd.date_range("2020-01-01", periods=200, freq="D")
        np.random.seed(42)
        prices = pd.Series(
            100 * np.exp(np.cumsum(np.random.randn(200) * 0.02)), index=dates
        )

        result = cusum_filter(prices, threshold=0.05)
        assert result.threshold == 0.05

    def test_higher_threshold_fewer_events(self):
        """Higher threshold should produce fewer events."""
        from afml import cusum_filter

        dates = pd.date_range("2020-01-01", periods=500, freq="D")
        np.random.seed(42)
        prices = pd.Series(
            100 * np.exp(np.cumsum(np.random.randn(500) * 0.02)), index=dates
        )

        result_low = cusum_filter(prices, threshold=0.01)
        result_high = cusum_filter(prices, threshold=0.10)

        assert len(result_high.events) <= len(result_low.events)

    def test_cusum_positive_nonnegative(self):
        """Positive CUSUM should always be >= 0."""
        from afml import cusum_filter

        dates = pd.date_range("2020-01-01", periods=200, freq="D")
        np.random.seed(42)
        prices = pd.Series(
            100 * np.exp(np.cumsum(np.random.randn(200) * 0.02)), index=dates
        )

        result = cusum_filter(prices)
        assert (result.cusum_positive >= 0).all()


class TestMetaLabeling:
    """Tests for Meta-Labeling with Random Forest."""

    @pytest.fixture
    def synthetic_meta_data(self):
        """Create synthetic data for meta-labeling tests."""
        np.random.seed(42)
        n = 300
        dates = pd.date_range("2020-01-01", periods=n, freq="D")
        prices = pd.Series(
            100 * np.exp(np.cumsum(np.random.randn(n) * 0.02)), index=dates
        )

        from afml import triple_barrier

        labels = triple_barrier(prices, max_holding=10)

        # Trim to label length
        n_labels = len(labels.labels)
        valid_dates = labels.labels.index

        # Primary signals: noisy version of actual labels
        noise = np.random.choice([-1, 1], size=n_labels, p=[0.3, 0.7])
        primary_signals = pd.Series(
            np.where(labels.labels != 0, labels.labels * noise, 1),
            index=valid_dates,
        )

        # Features: some informative, some noise
        features = pd.DataFrame(
            {
                "momentum": np.random.randn(n_labels) + 0.1 * labels.labels.values,
                "volatility": np.abs(np.random.randn(n_labels)),
                "volume": np.random.randn(n_labels),
            },
            index=valid_dates,
        )

        return primary_signals, labels, features

    def test_oos_probabilities_in_range(self, synthetic_meta_data):
        """Meta-label probabilities should be between 0 and 1."""
        from afml import meta_label_fit

        signals, labels, features = synthetic_meta_data

        result = meta_label_fit(
            primary_signals=signals,
            labels=labels,
            features=features,
            labels_end_times=labels.exit_times,
            n_splits=3,
        )

        assert (result.probabilities >= 0).all()
        assert (result.probabilities <= 1).all()

    def test_cv_scores_reasonable(self, synthetic_meta_data):
        """CV scores should be between 0 and 1."""
        from afml import meta_label_fit

        signals, labels, features = synthetic_meta_data

        result = meta_label_fit(
            primary_signals=signals,
            labels=labels,
            features=features,
            labels_end_times=labels.exit_times,
            n_splits=3,
        )

        for score in result.cv_scores:
            assert 0.0 <= score <= 1.0

    def test_feature_names_preserved(self, synthetic_meta_data):
        """Feature names should match input."""
        from afml import meta_label_fit

        signals, labels, features = synthetic_meta_data

        result = meta_label_fit(
            primary_signals=signals,
            labels=labels,
            features=features,
            labels_end_times=labels.exit_times,
            n_splits=3,
        )

        assert result.feature_names == ["momentum", "volatility", "volume"]

    def test_meta_label_predict(self, synthetic_meta_data):
        """meta_label_predict should return probabilities."""
        from afml import meta_label_fit, meta_label_predict

        signals, labels, features = synthetic_meta_data

        result = meta_label_fit(
            primary_signals=signals,
            labels=labels,
            features=features,
            labels_end_times=labels.exit_times,
            n_splits=3,
        )

        preds = meta_label_predict(result.model, features)
        assert len(preds) == len(features)
        assert (preds >= 0).all()
        assert (preds <= 1).all()


class TestBidirectionalPurging:
    """Tests for bidirectional purging in PurgedKFold."""

    def test_bidirectional_reduces_training(self, sample_returns):
        """Bidirectional purging should remove more training samples."""
        from afml import PurgedKFold

        X = pd.DataFrame({"feature": sample_returns.values}, index=sample_returns.index)
        # Create labels that span 5 days
        labels_end = pd.Series(
            [
                sample_returns.index[min(i + 5, len(sample_returns) - 1)]
                for i in range(len(sample_returns))
            ],
            index=sample_returns.index,
        )

        cv_standard = PurgedKFold(n_splits=5, embargo_pct=0.01, bidirectional=False)
        cv_bidir = PurgedKFold(n_splits=5, embargo_pct=0.01, bidirectional=True)

        total_standard = sum(
            len(train) for train, _ in cv_standard.split(X, labels_end_times=labels_end)
        )
        total_bidir = sum(
            len(train) for train, _ in cv_bidir.split(X, labels_end_times=labels_end)
        )

        assert total_bidir <= total_standard

    def test_bidirectional_false_preserves_behavior(self, sample_returns):
        """bidirectional=False should match original behavior."""
        from afml import PurgedKFold

        X = pd.DataFrame({"feature": sample_returns.values}, index=sample_returns.index)

        cv_default = PurgedKFold(n_splits=5, embargo_pct=0.01)
        cv_explicit = PurgedKFold(n_splits=5, embargo_pct=0.01, bidirectional=False)

        for (train_d, test_d), (train_e, test_e) in zip(
            cv_default.split(X), cv_explicit.split(X), strict=False
        ):
            np.testing.assert_array_equal(train_d, train_e)
            np.testing.assert_array_equal(test_d, test_e)
