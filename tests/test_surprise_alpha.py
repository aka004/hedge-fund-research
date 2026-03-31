"""Tests for the Prediction Market Surprise Alpha system.

Phase 1: TestEventStore — CRUD operations for EventStore.
Phase 2: TestEarningsSurpriseProvider — EPS proxy event generation.
"""

from __future__ import annotations

import math
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from afml import (
    cscv_symmetric,
    entropy_diagnostic,
    monte_carlo_permutation_test,
    parameter_chooser,
    rolling_statn,
)
from data.providers.prediction_market import EventRecord
from data.storage.event_store import EventStore
from strategy.signals.surprise_signal import SurpriseSignal, SurpriseSignalConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_event(
    event_id: str = "evt-001",
    symbol: str = "AAPL",
    source: str = "earnings_proxy",
    outcome: str = "bullish",
    confirmed: bool = True,
    event_date: date | None = None,
    p_market_pre: float = 0.7,
) -> EventRecord:
    """Create a minimal valid EventRecord for testing."""
    return EventRecord(
        event_id=event_id,
        source=source,
        symbol=symbol,
        event_date=event_date or date(2024, 1, 15),
        snapshot_datetime=datetime(2024, 1, 15, 8, 0, 0, tzinfo=UTC),
        resolved_at=(
            datetime(2024, 1, 15, 22, 0, 0, tzinfo=UTC) if confirmed else None
        ),
        p_market_pre=p_market_pre,
        outcome=outcome,
        outcome_confirmed=confirmed,
        event_type="earnings",
        description="Q4 2023 earnings",
        tags=["sp500", "tech"],
    )


# ---------------------------------------------------------------------------
# TestEventStore
# ---------------------------------------------------------------------------


class TestEventStore:
    """Tests for EventStore CRUD operations."""

    def test_save_and_load_roundtrip(self, tmp_path: Path) -> None:
        """Save events and load them back with identical data."""
        store = EventStore(storage_dir=tmp_path)
        evt = _make_event()
        store.save_events([evt])

        loaded = store.load_events()
        assert len(loaded) == 1

        rec = loaded[0]
        assert rec.event_id == evt.event_id
        assert rec.symbol == evt.symbol
        assert rec.source == evt.source
        assert rec.outcome == evt.outcome
        assert rec.outcome_confirmed == evt.outcome_confirmed
        assert rec.event_date == evt.event_date
        assert math.isclose(rec.p_market_pre, evt.p_market_pre)
        assert rec.tags == evt.tags

    def test_deduplication_by_event_id_and_source(self, tmp_path: Path) -> None:
        """Saving same event_id+source twice keeps only the newest."""
        store = EventStore(storage_dir=tmp_path)

        evt_v1 = _make_event(outcome="pending", confirmed=False)
        store.save_events([evt_v1])

        # Save updated version of the same event
        evt_v2 = _make_event(outcome="bullish", confirmed=True)
        store.save_events([evt_v2])

        loaded = store.load_events()
        assert len(loaded) == 1
        assert loaded[0].outcome == "bullish"
        assert loaded[0].outcome_confirmed is True

    def test_load_filters_by_symbol(self, tmp_path: Path) -> None:
        """load_events with symbol filter returns only matching events."""
        store = EventStore(storage_dir=tmp_path)
        store.save_events(
            [
                _make_event(event_id="evt-aapl", symbol="AAPL"),
                _make_event(event_id="evt-goog", symbol="GOOG"),
                _make_event(event_id="evt-msft", symbol="MSFT"),
            ]
        )

        result = store.load_events(symbol="GOOG")
        assert len(result) == 1
        assert result[0].symbol == "GOOG"
        assert result[0].event_id == "evt-goog"

    def test_load_filters_by_date_range(self, tmp_path: Path) -> None:
        """load_events with date range returns only events in range."""
        store = EventStore(storage_dir=tmp_path)
        store.save_events(
            [
                _make_event(event_id="evt-jan", event_date=date(2024, 1, 10)),
                _make_event(event_id="evt-feb", event_date=date(2024, 2, 10)),
                _make_event(event_id="evt-mar", event_date=date(2024, 3, 10)),
            ]
        )

        result = store.load_events(
            start_date=date(2024, 2, 1),
            end_date=date(2024, 2, 28),
        )
        assert len(result) == 1
        assert result[0].event_id == "evt-feb"

    def test_load_empty_store_returns_empty_list(self, tmp_path: Path) -> None:
        """load_events returns [] when no parquet files exist."""
        store = EventStore(storage_dir=tmp_path)
        result = store.load_events()
        assert result == []

    def test_get_events_with_min_history_passes(self, tmp_path: Path) -> None:
        """Returns events when confirmed count >= min_count."""
        store = EventStore(storage_dir=tmp_path)

        # Create 5 confirmed events for AAPL
        events = [
            _make_event(event_id=f"evt-{i:03d}", confirmed=True) for i in range(5)
        ]
        store.save_events(events)

        result = store.get_events_with_min_history(symbol="AAPL", min_count=5)
        assert len(result) == 5

    def test_get_events_with_min_history_fails(self, tmp_path: Path) -> None:
        """Returns empty list when confirmed count < min_count."""
        store = EventStore(storage_dir=tmp_path)

        # Only 3 confirmed events, but require 10
        events = [
            _make_event(event_id=f"evt-{i:03d}", confirmed=True) for i in range(3)
        ]
        store.save_events(events)

        result = store.get_events_with_min_history(symbol="AAPL", min_count=10)
        assert result == []

    def test_get_pre_event_snapshot(self, tmp_path: Path) -> None:
        """Returns p_market_pre for a specific event_id."""
        store = EventStore(storage_dir=tmp_path)
        evt = _make_event(event_id="evt-snap", p_market_pre=0.83)
        store.save_events([evt])

        p = store.get_pre_event_snapshot("evt-snap")
        assert p is not None
        assert math.isclose(p, 0.83)

    def test_get_pre_event_snapshot_missing_returns_none(self, tmp_path: Path) -> None:
        """Returns None when event_id is not found."""
        store = EventStore(storage_dir=tmp_path)
        store.save_events([_make_event()])

        p = store.get_pre_event_snapshot("nonexistent-id")
        assert p is None

    def test_multiple_sources_stored_separately(self, tmp_path: Path) -> None:
        """Events from different sources go to different parquet files."""
        store = EventStore(storage_dir=tmp_path)
        store.save_events(
            [
                _make_event(event_id="evt-ep", source="earnings_proxy"),
                _make_event(event_id="evt-mc", source="metaculus"),
            ]
        )

        ep_file = tmp_path / "pm_events_earnings_proxy.parquet"
        mc_file = tmp_path / "pm_events_metaculus.parquet"
        assert ep_file.exists(), "earnings_proxy parquet not created"
        assert mc_file.exists(), "metaculus parquet not created"

        # Each file should contain only its own source

        ep_df = pd.read_parquet(ep_file)
        mc_df = pd.read_parquet(mc_file)
        assert list(ep_df["source"].unique()) == ["earnings_proxy"]
        assert list(mc_df["source"].unique()) == ["metaculus"]

    def test_load_filters_by_source(self, tmp_path: Path) -> None:
        """load_events with source filter returns only that source's events."""
        store = EventStore(storage_dir=tmp_path)
        store.save_events(
            [
                _make_event(event_id="evt-ep", source="earnings_proxy"),
                _make_event(event_id="evt-mc", source="metaculus"),
            ]
        )

        result = store.load_events(source="metaculus")
        assert len(result) == 1
        assert result[0].event_id == "evt-mc"

    def test_min_history_unconfirmed_not_counted(self, tmp_path: Path) -> None:
        """Unconfirmed events do not count toward min_count threshold."""
        store = EventStore(storage_dir=tmp_path)

        # 3 confirmed + 10 unconfirmed = 13 total, but only 3 confirmed
        confirmed = [_make_event(event_id=f"c-{i}", confirmed=True) for i in range(3)]
        unconfirmed = [
            _make_event(event_id=f"u-{i}", confirmed=False, outcome="pending")
            for i in range(10)
        ]
        store.save_events(confirmed + unconfirmed)

        # Should fail: 3 confirmed < 5 required
        result = store.get_events_with_min_history(symbol="AAPL", min_count=5)
        assert result == []

    def test_get_events_with_min_history_excludes_unconfirmed(
        self, tmp_path: Path
    ) -> None:
        """When threshold is met, only confirmed events are returned."""
        store = EventStore(storage_dir=tmp_path)

        # 5 confirmed + 3 unconfirmed — threshold met, but unconfirmed must be excluded
        confirmed = [_make_event(event_id=f"c-{i}", confirmed=True) for i in range(5)]
        unconfirmed = [
            _make_event(event_id=f"u-{i}", confirmed=False, outcome="pending")
            for i in range(3)
        ]
        store.save_events(confirmed + unconfirmed)

        result = store.get_events_with_min_history(symbol="AAPL", min_count=5)
        assert len(result) == 5
        assert all(e.outcome_confirmed for e in result)

    def test_query_sql_against_view(self, tmp_path: Path) -> None:
        """query() runs SQL against the pm_events view."""
        store = EventStore(storage_dir=tmp_path)
        store.save_events(
            [
                _make_event(event_id="evt-a", symbol="AAPL"),
                _make_event(event_id="evt-b", symbol="GOOG"),
            ]
        )

        df = store.query("SELECT COUNT(*) AS cnt FROM pm_events")
        assert df.iloc[0]["cnt"] == 2

    def test_query_raises_when_no_events(self, tmp_path: Path) -> None:
        """query() raises RuntimeError when no events exist yet."""
        store = EventStore(storage_dir=tmp_path)
        with pytest.raises(RuntimeError, match="No pm_events view"):
            store.query("SELECT * FROM pm_events")


# ---------------------------------------------------------------------------
# Helpers for TestSurpriseSignal
# ---------------------------------------------------------------------------

# "Yesterday" is where the interesting event lands; "today" is as_of_date.
_EVENT_DATE = date(2024, 6, 14)
_AS_OF = date(2024, 6, 15)  # lookback_days=1 → event_date must be < _AS_OF


def _make_signal_events(
    symbol: str = "AAPL",
    n: int = 25,
    event_date: date = _EVENT_DATE,
    p_market_pre: float = 0.02,
    outcome: str = "bullish",
    confirmed: bool = True,
    liquidity_ok: bool = True,
) -> list[EventRecord]:
    """Create n confirmed EventRecords for SurpriseSignal tests.

    The first record sits on event_date with the supplied parameters.
    The remaining n-1 are historical padding (same symbol, earlier date)
    so that get_events_with_min_history passes the threshold.
    """
    base_ts = datetime(2024, 6, 14, 22, 0, 0, tzinfo=UTC)

    primary = EventRecord(
        event_id=f"signal-evt-primary-{symbol.lower()}",
        source="earnings_proxy",
        symbol=symbol,
        event_date=event_date,
        snapshot_datetime=base_ts,
        resolved_at=base_ts,
        p_market_pre=p_market_pre,
        outcome=outcome,
        outcome_confirmed=confirmed,
        liquidity_ok=liquidity_ok,
        event_type="earnings",
        n_historical_events=n - 1,
    )

    padding = [
        EventRecord(
            event_id=f"signal-evt-hist-{symbol.lower()}-{i}",
            source="earnings_proxy",
            symbol=symbol,
            event_date=date(2024, 1, 1),
            snapshot_datetime=base_ts,
            resolved_at=base_ts,
            p_market_pre=0.5,
            outcome="bullish",
            outcome_confirmed=True,
            liquidity_ok=True,
            event_type="earnings",
        )
        for i in range(n - 1)
    ]

    return [primary] + padding


# ---------------------------------------------------------------------------
# TestSurpriseSignal
# ---------------------------------------------------------------------------


class TestSurpriseSignal:
    """Tests for SurpriseSignal generation logic (Phase 3)."""

    def _store_with(self, tmp_path: Path, events: list[EventRecord]) -> EventStore:
        store = EventStore(storage_dir=str(tmp_path))
        store.save_events(events)
        return store

    # ------------------------------------------------------------------
    # Static method: compute_surprise
    # ------------------------------------------------------------------

    def test_compute_surprise_bullish_50pct(self) -> None:
        """p=0.5, bullish → bits=1.0, direction=+1."""
        bits, direction = SurpriseSignal.compute_surprise(0.5, "bullish")
        assert math.isclose(bits, 1.0, rel_tol=1e-6)
        assert direction == +1

    def test_compute_surprise_bullish_low_prob(self) -> None:
        """p=0.0625, bullish → bits=4.0 (exactly -log2(0.0625))."""
        bits, direction = SurpriseSignal.compute_surprise(0.0625, "bullish")
        assert math.isclose(bits, 4.0, rel_tol=1e-6)
        assert direction == +1

    def test_compute_surprise_bearish_high_prob(self) -> None:
        """p=0.98, bearish → bits=-log2(0.02), direction=-1."""
        bits, direction = SurpriseSignal.compute_surprise(0.98, "bearish")
        expected = -math.log2(0.02)
        assert math.isclose(bits, expected, rel_tol=1e-6)
        assert direction == -1

    def test_compute_surprise_neutral(self) -> None:
        """Neutral outcome → bits=0.0, direction=0."""
        bits, direction = SurpriseSignal.compute_surprise(0.5, "neutral")
        assert bits == 0.0
        assert direction == 0

    def test_compute_surprise_pending(self) -> None:
        """Pending outcome → bits=0.0, direction=0."""
        bits, direction = SurpriseSignal.compute_surprise(0.5, "pending")
        assert bits == 0.0
        assert direction == 0

    # ------------------------------------------------------------------
    # generate(): filters
    # ------------------------------------------------------------------

    def test_min_bits_filter_excludes_low_surprise(self, tmp_path: Path) -> None:
        """Events with surprise < min_surprise_bits are excluded."""
        events = _make_signal_events(p_market_pre=0.5, outcome="bullish")
        store = self._store_with(tmp_path, events)
        sig = SurpriseSignal(store)
        assert sig.generate(["AAPL"], _AS_OF) == []

    def test_min_history_filter_excludes_symbol(self, tmp_path: Path) -> None:
        """Symbols with fewer than min_history confirmed events get no signal."""
        events = _make_signal_events(n=5, p_market_pre=0.02)
        store = self._store_with(tmp_path, events)
        sig = SurpriseSignal(store)
        assert sig.generate(["AAPL"], _AS_OF) == []

    def test_look_ahead_bias_prevention(self, tmp_path: Path) -> None:
        """Events on exactly cutoff date (as_of - lookback) are included; as_of_date events excluded."""
        from datetime import timedelta

        as_of = date(2024, 6, 15)
        lookback = 1
        cutoff = as_of - timedelta(days=lookback)  # June 14

        # AAPL: primary event on cutoff (June 14) + historical padding — should produce signal
        events_old = _make_signal_events("AAPL", n=25, event_date=cutoff)

        # GOOG: primary event on as_of_date (June 15) — should NOT produce signal.
        # Padding events are also placed on as_of so no GOOG events pass the date filter.
        from datetime import UTC

        from data.providers.prediction_market import EventRecord as _ER

        base_ts = datetime(2024, 6, 15, 22, 0, 0, tzinfo=UTC)
        events_future = [
            _ER(
                event_id=f"goog-evt-{i}",
                source="earnings_proxy",
                symbol="GOOG",
                event_date=as_of,  # all on as_of — future-dated, none should pass
                snapshot_datetime=base_ts,
                resolved_at=base_ts,
                p_market_pre=0.02,
                outcome="bullish",
                outcome_confirmed=True,
                liquidity_ok=True,
                event_type="earnings",
                n_historical_events=24,
            )
            for i in range(25)
        ]

        store = EventStore(storage_dir=str(tmp_path))
        store.save_events(events_old + events_future)

        signal_gen = SurpriseSignal(
            store, SurpriseSignalConfig(min_history=20, min_surprise_bits=0.0)
        )
        signals = signal_gen.generate(["AAPL", "GOOG"], as_of)

        symbols_with_signals = {s.symbol for s in signals}
        assert (
            "AAPL" in symbols_with_signals
        ), "Event on cutoff date should produce signal"
        assert (
            "GOOG" not in symbols_with_signals
        ), "Event on as_of_date should NOT produce signal"

    def test_bullish_surprise_positive_score(self, tmp_path: Path) -> None:
        """Bullish surprise → score > 0."""
        events = _make_signal_events(p_market_pre=0.02, outcome="bullish")
        store = self._store_with(tmp_path, events)
        sig = SurpriseSignal(store)

        result = sig.generate(["AAPL"], _AS_OF)
        assert len(result) == 1
        assert result[0].score > 0
        assert result[0].metadata["direction"] == +1

    def test_bearish_surprise_negative_score(self, tmp_path: Path) -> None:
        """Bearish surprise → score < 0."""
        events = _make_signal_events(p_market_pre=0.98, outcome="bearish")
        store = self._store_with(tmp_path, events)
        sig = SurpriseSignal(store)

        result = sig.generate(["AAPL"], _AS_OF)
        assert len(result) == 1
        assert result[0].score < 0
        assert result[0].metadata["direction"] == -1

    def test_neutral_outcome_excluded(self, tmp_path: Path) -> None:
        """Neutral outcome is excluded even when surprise bits would be high."""
        events = _make_signal_events(p_market_pre=0.02, outcome="neutral")
        store = self._store_with(tmp_path, events)
        sig = SurpriseSignal(store)
        assert sig.generate(["AAPL"], _AS_OF) == []

    def test_liquidity_filter_excludes_event(self, tmp_path: Path) -> None:
        """Events with liquidity_ok=False are excluded."""
        events = _make_signal_events(
            p_market_pre=0.02, outcome="bullish", liquidity_ok=False
        )
        store = self._store_with(tmp_path, events)
        sig = SurpriseSignal(store)
        assert sig.generate(["AAPL"], _AS_OF) == []

    def test_signals_sorted_by_abs_score_descending(self, tmp_path: Path) -> None:
        """Most surprising events appear first in returned list."""
        aapl_events = _make_signal_events(
            symbol="AAPL", p_market_pre=0.02, outcome="bullish"
        )
        msft_events = _make_signal_events(
            symbol="MSFT", p_market_pre=0.0625, outcome="bullish"
        )
        store = self._store_with(tmp_path, aapl_events + msft_events)
        sig = SurpriseSignal(store)

        result = sig.generate(["AAPL", "MSFT"], _AS_OF)
        assert len(result) == 2
        assert result[0].symbol == "AAPL"
        assert abs(result[0].score) > abs(result[1].score)

    def test_signal_metadata_populated(self, tmp_path: Path) -> None:
        """Signal metadata contains expected keys."""
        events = _make_signal_events(p_market_pre=0.02, outcome="bullish")
        store = self._store_with(tmp_path, events)
        sig = SurpriseSignal(store)

        result = sig.generate(["AAPL"], _AS_OF)
        assert len(result) == 1
        meta = result[0].metadata
        assert meta is not None
        for key in (
            "event_id",
            "p_market_pre",
            "outcome",
            "direction",
            "surprise_bits",
            "n_historical_events",
            "event_type",
        ):
            assert key in meta, f"metadata missing key: {key}"

    def test_signal_name_is_surprise_alpha(self, tmp_path: Path) -> None:
        """Signal.signal_name equals 'surprise_alpha'."""
        events = _make_signal_events(p_market_pre=0.02, outcome="bullish")
        store = self._store_with(tmp_path, events)
        sig = SurpriseSignal(store)

        result = sig.generate(["AAPL"], _AS_OF)
        assert len(result) == 1
        assert result[0].signal_name == "surprise_alpha"

    def test_empty_symbols_returns_empty(self, tmp_path: Path) -> None:
        """generate() with empty symbols list returns []."""
        store = EventStore(storage_dir=str(tmp_path))
        sig = SurpriseSignal(store)
        assert sig.generate([], _AS_OF) == []

    def test_custom_config_lower_threshold(self, tmp_path: Path) -> None:
        """Custom min_surprise_bits=0.5 allows lower-surprise events through."""
        events = _make_signal_events(p_market_pre=0.5, outcome="bullish")
        store = self._store_with(tmp_path, events)
        config = SurpriseSignalConfig(min_surprise_bits=0.5, min_history=25)
        sig = SurpriseSignal(store, config=config)

        result = sig.generate(["AAPL"], _AS_OF)
        assert len(result) >= 1

    def test_signals_have_ranks_assigned(self, tmp_path: Path) -> None:
        """All returned signals must have a non-None rank."""
        aapl_events = _make_signal_events(
            symbol="AAPL", p_market_pre=0.02, outcome="bullish"
        )
        msft_events = _make_signal_events(
            symbol="MSFT", p_market_pre=0.03, outcome="bullish"
        )
        store = self._store_with(tmp_path, aapl_events + msft_events)
        sig = SurpriseSignal(store)

        result = sig.generate(["AAPL", "MSFT"], _AS_OF)
        assert all(s.rank is not None for s in result)


# ---------------------------------------------------------------------------
# TestMastersDiagnostics (Phase 5)
# ---------------------------------------------------------------------------


class TestMastersDiagnostics:
    """Tests for the Masters Diagnostic Pipeline (STATN, ENTROPY, MCPT, CHOOSER, CSCV)."""

    # ------------------------------------------------------------------
    # rolling_statn
    # ------------------------------------------------------------------

    def test_rolling_statn_stationary_series(self) -> None:
        """White noise → high fraction_stationary."""
        rng = np.random.default_rng(42)
        returns = pd.Series(rng.standard_normal(200))
        result = rolling_statn(returns, window=60)
        assert result.fraction_stationary > 0.5

    def test_rolling_statn_nonstationary_series(self) -> None:
        """Random walk → low fraction_stationary."""
        rng = np.random.default_rng(42)
        random_walk = pd.Series(np.cumsum(rng.standard_normal(200)))
        result = rolling_statn(random_walk, window=60)
        assert result.fraction_stationary < 0.5
        assert (
            not result.passes
        )  # Mostly non-stationary → should not pass the 80% threshold

    def test_rolling_statn_passes_field(self) -> None:
        """passes=True when fraction_stationary >= threshold."""
        rng = np.random.default_rng(42)
        returns = pd.Series(rng.standard_normal(200))
        result = rolling_statn(returns, window=60, threshold_fraction=0.0)
        assert result.passes is True

    def test_rolling_statn_result_type(self) -> None:
        """Result has rolling_pvalues Series and float fraction."""
        rng = np.random.default_rng(42)
        returns = pd.Series(rng.standard_normal(150))
        result = rolling_statn(returns, window=60)
        assert isinstance(result.rolling_pvalues, pd.Series)
        assert isinstance(result.fraction_stationary, float)
        assert 0.0 <= result.fraction_stationary <= 1.0

    # ------------------------------------------------------------------
    # entropy_diagnostic
    # ------------------------------------------------------------------

    def test_entropy_uniform_labels(self) -> None:
        """Perfectly uniform labels → H ≈ H_max → passes=False."""
        scores = pd.Series(np.linspace(0, 10, 100))
        labels = pd.Series(([+1, -1, 0] * 34)[:100])
        result = entropy_diagnostic(scores, labels)
        assert not result.passes

    def test_entropy_concentrated_labels(self) -> None:
        """All labels same → H=0 → passes=True."""
        scores = pd.Series(np.linspace(0, 10, 30))
        labels = pd.Series([+1] * 30)
        result = entropy_diagnostic(scores, labels)
        assert result.passes

    def test_entropy_result_has_bucket_stats(self) -> None:
        """bucket_stats DataFrame has required columns."""
        scores = pd.Series(np.linspace(0, 10, 50))
        labels = pd.Series([+1, -1] * 25)
        result = entropy_diagnostic(scores, labels)
        assert "bucket_label" in result.bucket_stats.columns
        assert "count" in result.bucket_stats.columns
        assert "entropy" in result.bucket_stats.columns

    def test_entropy_h_max_value(self) -> None:
        """H_max = log2(n_unique_classes)."""
        scores = pd.Series(np.linspace(0, 10, 60))
        labels = pd.Series([+1, -1] * 30)
        result = entropy_diagnostic(scores, labels)
        assert math.isclose(result.h_max, math.log2(2), rel_tol=1e-6)

    # ------------------------------------------------------------------
    # monte_carlo_permutation_test
    # ------------------------------------------------------------------

    def test_mcpt_random_returns_high_pvalue(self) -> None:
        """Random returns (no signal) → high p-value → does not pass."""
        rng = np.random.default_rng(42)
        returns = pd.Series(rng.standard_normal(100))
        result = monte_carlo_permutation_test(
            returns, n_permutations=200, random_seed=42
        )
        assert result.p_value > 0.05

    def test_mcpt_strong_positive_returns_low_pvalue(self) -> None:
        """Strong positive signal → low p-value → passes."""
        rng = np.random.default_rng(42)
        # Strong positive drift with some noise — permuting destroys the signal
        returns = pd.Series(
            rng.standard_normal(200) * 0.002 + 0.01
        )  # 1% daily return, low vol
        result = monte_carlo_permutation_test(
            returns, n_permutations=500, random_seed=42
        )
        assert result.p_value < 0.05
        assert result.passes

    def test_mcpt_result_fields(self) -> None:
        """McptResult has required numeric fields."""
        returns = pd.Series([0.01] * 50)
        result = monte_carlo_permutation_test(
            returns, n_permutations=100, random_seed=0
        )
        assert isinstance(result.observed_sharpe, float)
        assert len(result.permutation_sharpes) == 100
        assert 0.0 <= result.p_value <= 1.0
        assert result.n_permutations == 100

    # ------------------------------------------------------------------
    # parameter_chooser
    # ------------------------------------------------------------------

    def test_parameter_chooser_selects_best_psr(self) -> None:
        """Variant with highest PSR is selected."""
        rng = np.random.default_rng(42)
        good_returns = pd.Series(rng.standard_normal(100) * 0.01 + 0.002)
        bad_returns = pd.Series(rng.standard_normal(100) * 0.05)
        variants = [
            {"params": {"min_bits": 4.0}, "returns": good_returns},
            {"params": {"min_bits": 3.0}, "returns": bad_returns},
        ]
        result = parameter_chooser(variants)
        assert result.best_params == {"min_bits": 4.0}

    def test_parameter_chooser_result_shape(self) -> None:
        """param_scores has one row per variant."""
        rng = np.random.default_rng(42)
        variants = [
            {"params": {"k": i}, "returns": pd.Series(rng.standard_normal(60) * 0.01)}
            for i in range(3)
        ]
        result = parameter_chooser(variants)
        assert result.n_variants == 3
        assert len(result.param_scores) == 3
        assert "psr" in result.param_scores.columns

    # ------------------------------------------------------------------
    # cscv_symmetric
    # ------------------------------------------------------------------

    def test_cscv_constant_returns_low_pbo_rank(self) -> None:
        """Constant positive returns → IS and OOS equally good → low pbo_rank."""
        returns = pd.Series(
            [0.01] * 100, index=pd.date_range("2020-01-01", periods=100)
        )
        result = cscv_symmetric(returns)
        assert result.pbo_rank <= 0.5

    def test_cscv_result_has_both_is_and_oos_sharpes(self) -> None:
        """Result includes IS and OOS Sharpe lists of equal length."""
        rng = np.random.default_rng(42)
        returns = pd.Series(
            rng.standard_normal(120) * 0.01,
            index=pd.date_range("2020-01-01", periods=120),
        )
        result = cscv_symmetric(returns)
        assert len(result.path_sharpes_is) == len(result.path_sharpes_oos)
        assert result.n_paths > 0

    def test_cscv_passes_field(self) -> None:
        """passes=True when pbo_rank < threshold."""
        returns = pd.Series(
            [0.01] * 100, index=pd.date_range("2020-01-01", periods=100)
        )
        result = cscv_symmetric(returns, pbo_rank_threshold=1.0)
        assert result.passes is True

    def test_cscv_pbo_rank_in_range(self) -> None:
        """pbo_rank is always in [0, 1]."""
        rng = np.random.default_rng(7)
        returns = pd.Series(
            rng.standard_normal(90) * 0.01,
            index=pd.date_range("2021-01-01", periods=90),
        )
        result = cscv_symmetric(returns)
        assert 0.0 <= result.pbo_rank <= 1.0


# ---------------------------------------------------------------------------
# Helpers for TestEarningsSurpriseProvider
# ---------------------------------------------------------------------------


def _make_earnings_df(n_quarters: int = 12) -> pd.DataFrame:
    """Create a synthetic earnings_dates DataFrame like yfinance returns.

    Alternates beat / miss / in-line so we have a mix to test.
    Index is DatetimeIndex of quarterly announcement datetimes (UTC-aware).
    yfinance returns newest-first, so the DataFrame is reversed at the end.
    """
    from datetime import timedelta

    base = datetime(2022, 1, 15, 16, 0, 0, tzinfo=UTC)
    dates = [base + timedelta(days=91 * i) for i in range(n_quarters)]

    estimates = [1.00 + 0.05 * i for i in range(n_quarters)]
    actuals = []
    for i, est in enumerate(estimates):
        if i % 3 == 0:
            actuals.append(est * 1.10)  # beat
        elif i % 3 == 1:
            actuals.append(est * 0.90)  # miss
        else:
            actuals.append(est * 1.005)  # in-line (< 1% threshold)

    df = pd.DataFrame(
        {
            "EPS Estimate": estimates,
            "Reported EPS": actuals,
            "Surprise(%)": [
                ((a - e) / abs(e) * 100) if e != 0 else 0.0
                for a, e in zip(actuals, estimates, strict=False)
            ],
        },
        index=pd.DatetimeIndex(dates, name="Earnings Date"),
    )
    return df.iloc[::-1]  # newest-first, matching yfinance behaviour


def _raw_earnings(df: pd.DataFrame) -> pd.DataFrame:
    """Convert yfinance-style DataFrame to internal (eps_estimate, eps_actual) format."""
    return (
        df[["EPS Estimate", "Reported EPS"]]
        .rename(columns={"EPS Estimate": "eps_estimate", "Reported EPS": "eps_actual"})
        .sort_index()
    )


# ---------------------------------------------------------------------------
# TestEarningsSurpriseProvider
# ---------------------------------------------------------------------------


class TestEarningsSurpriseProvider:
    """Tests for EarningsSurpriseProvider -- all use mocked yfinance data."""

    # ------------------------------------------------------------------
    # _compute_probability
    # ------------------------------------------------------------------

    def test_compute_probability_z_sign(self) -> None:
        """Non-zero z implies p<0.5; z=0 implies p=0.5 (tail probability semantics).

        p_proxy = 1 - norm.cdf(|z|): larger |z| → smaller p_proxy (rarer event).
        For any non-zero z, p < 0.5. For z=0, p = 0.5 (50% chance of this magnitude).
        """
        from data.providers.earnings_surprise import EarningsSurpriseProvider

        provider = EarningsSurpriseProvider()
        n = 12
        eps_estimate = pd.Series([1.0] * n)
        actuals = [1.1 if i % 2 == 0 else 0.9 for i in range(n)]
        eps_actual = pd.Series(actuals)

        result = provider._compute_probability(
            eps_estimate=eps_estimate, eps_actual=eps_actual
        )

        valid = result.dropna(subset=["p_proxy"])
        assert len(valid) > 0, "Expected at least some valid rows after warmup"

        for _, row_data in valid.iterrows():
            z = row_data["z_score"]
            p = row_data["p_proxy"]
            # Tail probability: any non-zero |z| gives p < 0.5
            assert 0.0 <= p <= 0.5, f"z={z:.3f} should give 0 <= p <= 0.5, got {p:.3f}"

    def test_compute_probability_constant_surprise_gives_nan(self) -> None:
        """All surprises == 0 implies rolling_std == 0 implies p_proxy = NaN."""
        from data.providers.earnings_surprise import EarningsSurpriseProvider

        provider = EarningsSurpriseProvider()
        n = 10
        eps_estimate = pd.Series([1.0] * n)
        eps_actual = pd.Series([1.0] * n)
        result = provider._compute_probability(
            eps_estimate=eps_estimate, eps_actual=eps_actual
        )
        assert result["p_proxy"].isna().all()

    def test_compute_probability_returns_expected_columns(self) -> None:
        """Result DataFrame has: surprise, rolling_std, z_score, p_proxy."""
        from data.providers.earnings_surprise import EarningsSurpriseProvider

        provider = EarningsSurpriseProvider()
        eps = pd.Series([1.0, 1.1, 0.9] * 4)
        result = provider._compute_probability(eps_estimate=eps, eps_actual=eps * 1.05)
        assert set(result.columns) == {"surprise", "rolling_std", "z_score", "p_proxy"}

    def test_compute_probability_zero_zscore_gives_half(self) -> None:
        """When surprise=0 and rolling_std>0, z_score=0 → p_proxy=0.5."""
        from data.providers.earnings_surprise import EarningsSurpriseProvider

        provider = EarningsSurpriseProvider()
        # Mix of surprises then rows with surprise=0: rolling_std will be > 0
        eps_actual = pd.Series([1.1, 0.9, 1.05, 0.95, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0])
        eps_estimate = pd.Series([1.0] * 10)
        result = provider._compute_probability(eps_actual, eps_estimate, min_periods=4)
        # Find rows where surprise==0 and z_score is not NaN
        zero_surprise_rows = result[
            (result["surprise"] == 0.0) & result["z_score"].notna()
        ]
        if not zero_surprise_rows.empty:
            assert (
                abs(zero_surprise_rows["z_score"]) < 1e-10
            ).all(), f"Expected z_score=0 for zero surprise, got {zero_surprise_rows['z_score'].tolist()}"
            assert (
                abs(zero_surprise_rows["p_proxy"] - 0.5) < 1e-10
            ).all(), f"Expected p_proxy=0.5 for z_score=0, got {zero_surprise_rows['p_proxy'].tolist()}"

    # ------------------------------------------------------------------
    # _make_event_record
    # ------------------------------------------------------------------

    def test_make_event_record_beat(self) -> None:
        """Beat: outcome=bullish, p_market_pre=p_proxy, direction=+1."""
        from datetime import timedelta

        from data.providers.earnings_surprise import EarningsSurpriseProvider

        provider = EarningsSurpriseProvider()
        ann_dt = datetime(2024, 2, 1, 16, 0, 0, tzinfo=UTC)

        row = pd.Series(
            {
                "eps_estimate": 1.00,
                "eps_actual": 1.20,
                "surprise": 0.20,
                "rolling_std": 0.10,
                "z_score": 2.0,
                "p_proxy": 0.75,
            }
        )

        record = provider._make_event_record(
            symbol="AAPL",
            row=row,
            quarter_label="2024Q1",
            ann_dt=ann_dt,
            n_historical_events=5,
        )

        assert record is not None
        assert record.outcome == "bullish"
        assert record.direction == 1
        assert math.isclose(record.p_market_pre, 0.75, rel_tol=1e-6)
        assert record.source == "earnings_proxy"
        assert record.event_type == "earnings"
        assert record.n_historical_events == 5
        assert record.outcome_confirmed is True
        assert record.resolved_at is not None
        assert record.resolved_at - record.snapshot_datetime == timedelta(hours=1)

    def test_make_event_record_miss(self) -> None:
        """Miss: outcome=bearish, p_market_pre=p_proxy (tail prob of magnitude), direction=-1."""

        from data.providers.earnings_surprise import EarningsSurpriseProvider

        provider = EarningsSurpriseProvider()
        ann_dt = datetime(2024, 5, 1, 16, 0, 0, tzinfo=UTC)

        row = pd.Series(
            {
                "eps_estimate": 1.00,
                "eps_actual": 0.70,
                "surprise": -0.30,
                "rolling_std": 0.10,
                "z_score": -3.0,
                "p_proxy": 0.20,
            }
        )

        record = provider._make_event_record(
            symbol="MSFT",
            row=row,
            quarter_label="2024Q2",
            ann_dt=ann_dt,
            n_historical_events=8,
        )

        assert record is not None
        assert record.outcome == "bearish"
        assert record.direction == -1
        assert math.isclose(record.p_market_pre, 0.20, rel_tol=1e-6)

    def test_make_event_record_in_line(self) -> None:
        """Surprise < 1% of estimate: outcome=neutral, direction=0, p=0.5."""

        from data.providers.earnings_surprise import EarningsSurpriseProvider

        provider = EarningsSurpriseProvider()
        ann_dt = datetime(2024, 8, 1, 16, 0, 0, tzinfo=UTC)

        row = pd.Series(
            {
                "eps_estimate": 2.00,
                "eps_actual": 2.01,  # 0.5% beat -- within 1% in-line threshold
                "surprise": 0.01,
                "rolling_std": 0.10,
                "z_score": 0.1,
                "p_proxy": 0.54,
            }
        )

        record = provider._make_event_record(
            symbol="GOOG",
            row=row,
            quarter_label="2024Q3",
            ann_dt=ann_dt,
            n_historical_events=3,
        )

        assert record is not None
        assert record.outcome == "neutral"
        assert record.direction == 0
        assert math.isclose(record.p_market_pre, 0.5, rel_tol=1e-6)

    def test_make_event_record_returns_none_when_p_proxy_nan(self) -> None:
        """Returns None when p_proxy is NaN (insufficient rolling history)."""

        from data.providers.earnings_surprise import EarningsSurpriseProvider

        provider = EarningsSurpriseProvider()
        ann_dt = datetime(2023, 1, 15, 16, 0, 0, tzinfo=UTC)

        row = pd.Series(
            {
                "eps_estimate": 1.00,
                "eps_actual": 1.20,
                "surprise": 0.20,
                "rolling_std": float("nan"),
                "z_score": float("nan"),
                "p_proxy": float("nan"),
            }
        )

        record = provider._make_event_record(
            symbol="AAPL",
            row=row,
            quarter_label="2023Q1",
            ann_dt=ann_dt,
            n_historical_events=0,
        )

        assert record is None

    def test_make_event_record_returns_none_when_eps_actual_nan(self) -> None:
        """Returns None when eps_actual is NaN (unreported quarter)."""

        from data.providers.earnings_surprise import EarningsSurpriseProvider

        provider = EarningsSurpriseProvider()
        ann_dt = datetime(2024, 11, 1, 16, 0, 0, tzinfo=UTC)

        row = pd.Series(
            {
                "eps_estimate": 1.00,
                "eps_actual": float("nan"),
                "surprise": float("nan"),
                "rolling_std": 0.10,
                "z_score": float("nan"),
                "p_proxy": float("nan"),
            }
        )

        record = provider._make_event_record(
            symbol="AAPL",
            row=row,
            quarter_label="2024Q4",
            ann_dt=ann_dt,
            n_historical_events=10,
        )

        assert record is None

    def test_event_id_format(self) -> None:
        """event_id = 'earnings-{symbol}-{quarter_label}'."""

        from data.providers.earnings_surprise import EarningsSurpriseProvider

        provider = EarningsSurpriseProvider()
        ann_dt = datetime(2024, 4, 25, 16, 0, 0, tzinfo=UTC)

        row = pd.Series(
            {
                "eps_estimate": 1.00,
                "eps_actual": 1.20,
                "surprise": 0.20,
                "rolling_std": 0.10,
                "z_score": 2.0,
                "p_proxy": 0.75,
            }
        )

        record = provider._make_event_record(
            symbol="AAPL",
            row=row,
            quarter_label="2024Q2",
            ann_dt=ann_dt,
            n_historical_events=0,
        )

        assert record is not None
        assert record.event_id == "earnings-AAPL-2024Q2"

    # ------------------------------------------------------------------
    # get_events (full pipeline with mocked _fetch_earnings_history)
    # ------------------------------------------------------------------

    def test_get_events_mocked(self) -> None:
        """Full get_events() with mocked fetch returns valid EventRecord list."""
        from unittest.mock import patch

        from data.providers.earnings_surprise import EarningsSurpriseProvider

        raw = _raw_earnings(_make_earnings_df(n_quarters=12))

        with patch(
            "data.providers.earnings_surprise.EarningsSurpriseProvider"
            "._fetch_earnings_history",
            return_value=raw,
        ):
            provider = EarningsSurpriseProvider()
            events = provider.get_events(
                symbol="TEST",
                start_date=date(2022, 1, 1),
                end_date=date(2025, 12, 31),
                min_history_quarters=8,
            )

        assert len(events) > 0
        for evt in events:
            assert evt.source == "earnings_proxy"
            assert evt.event_type == "earnings"
            assert evt.symbol == "TEST"
            assert evt.outcome_confirmed is True
            assert evt.outcome in {"bullish", "bearish", "neutral"}
            assert 0.0 < evt.p_market_pre < 1.0
            assert evt.liquidity_ok is True

    def test_get_events_n_historical_events_increments(self) -> None:
        """n_historical_events is non-decreasing across returned events."""
        from unittest.mock import patch

        from data.providers.earnings_surprise import EarningsSurpriseProvider

        raw = _raw_earnings(_make_earnings_df(n_quarters=12))

        with patch(
            "data.providers.earnings_surprise.EarningsSurpriseProvider"
            "._fetch_earnings_history",
            return_value=raw,
        ):
            provider = EarningsSurpriseProvider()
            events = provider.get_events(
                symbol="TEST",
                start_date=date(2022, 1, 1),
                end_date=date(2025, 12, 31),
                min_history_quarters=8,
            )

        counts = [e.n_historical_events for e in events]
        assert all(
            a < b for a, b in zip(counts, counts[1:], strict=False)
        ), f"Expected strict increase: {counts}"

    def test_get_events_returns_empty_for_empty_history(self) -> None:
        """Returns empty list when no earnings history is available."""
        from unittest.mock import patch

        from data.providers.earnings_surprise import EarningsSurpriseProvider

        with patch(
            "data.providers.earnings_surprise.EarningsSurpriseProvider"
            "._fetch_earnings_history",
            return_value=pd.DataFrame(columns=["eps_estimate", "eps_actual"]),
        ):
            provider = EarningsSurpriseProvider()
            events = provider.get_events(
                symbol="UNKNOWN",
                start_date=date(2023, 1, 1),
                end_date=date(2024, 12, 31),
            )

        assert events == []

    def test_get_events_filters_by_date_range(self) -> None:
        """Events outside start_date/end_date are excluded from results."""
        from unittest.mock import patch

        from data.providers.earnings_surprise import EarningsSurpriseProvider

        raw = _raw_earnings(_make_earnings_df(n_quarters=12))

        with patch(
            "data.providers.earnings_surprise.EarningsSurpriseProvider"
            "._fetch_earnings_history",
            return_value=raw,
        ):
            provider = EarningsSurpriseProvider()
            events_narrow = provider.get_events(
                symbol="TEST",
                start_date=date(2024, 1, 1),
                end_date=date(2024, 6, 30),
                min_history_quarters=8,
            )
            events_wide = provider.get_events(
                symbol="TEST",
                start_date=date(2022, 1, 1),
                end_date=date(2025, 12, 31),
                min_history_quarters=8,
            )

        assert len(events_narrow) <= len(events_wide)
        for evt in events_narrow:
            assert date(2024, 1, 1) <= evt.event_date <= date(2024, 6, 30)

    # ------------------------------------------------------------------
    # _quarter_label helper
    # ------------------------------------------------------------------

    def test_quarter_label_helper(self) -> None:
        """_quarter_label returns correct quarter strings for all quarters."""
        from data.providers.earnings_surprise import _quarter_label

        cases = [
            (datetime(2024, 1, 15), "2024Q1"),
            (datetime(2024, 4, 25), "2024Q2"),
            (datetime(2024, 7, 31), "2024Q3"),
            (datetime(2024, 10, 30), "2024Q4"),
            (datetime(2023, 12, 31), "2023Q4"),
        ]
        for dt, expected in cases:
            assert _quarter_label(dt) == expected, f"dt={dt}, expected={expected}"


# ---------------------------------------------------------------------------
# Helpers for TestEventBacktest
# ---------------------------------------------------------------------------


def _make_price_data(
    symbol: str,
    start: date,
    n_days: int,
    open_prices: list[float] | None = None,
    close_prices: list[float] | None = None,
) -> pd.DataFrame:
    """Create synthetic price DataFrame for testing (weekdays only)."""
    from datetime import timedelta

    weekdays = [
        start + timedelta(days=i)
        for i in range(n_days)
        if (start + timedelta(days=i)).weekday() < 5
    ]
    if open_prices is not None:
        assert len(open_prices) >= len(
            weekdays
        ), f"open_prices too short: {len(open_prices)} < {len(weekdays)}"
    if close_prices is not None:
        assert len(close_prices) >= len(
            weekdays
        ), f"close_prices too short: {len(close_prices)} < {len(weekdays)}"
    opens = open_prices or [100.0] * len(weekdays)
    closes = close_prices or [100.0] * len(weekdays)
    return pd.DataFrame(
        {
            "date": weekdays[: len(closes)],
            "open": opens[: len(closes)],
            "close": closes[: len(closes)],
        }
    )


def _make_backtest_event(
    symbol: str = "AAPL",
    event_date: date = date(2024, 1, 2),
    direction: int = 1,
    surprise_score: float = 5.0,
    event_id: str | None = None,
) -> EventRecord:
    """Create a confirmed bullish EventRecord with high surprise score."""
    from datetime import UTC

    eid = event_id or f"bt-evt-{symbol.lower()}-{event_date.isoformat()}"
    return EventRecord(
        event_id=eid,
        source="earnings_proxy",
        symbol=symbol,
        event_date=event_date,
        snapshot_datetime=datetime(
            event_date.year, event_date.month, event_date.day, 22, 0, 0, tzinfo=UTC
        ),
        resolved_at=datetime(
            event_date.year, event_date.month, event_date.day, 22, 0, 0, tzinfo=UTC
        ),
        p_market_pre=0.05,
        outcome="bullish" if direction == 1 else "bearish",
        outcome_confirmed=True,
        surprise_score=surprise_score,
        direction=direction,
        liquidity_ok=True,
        event_type="earnings",
    )


# ---------------------------------------------------------------------------
# TestEventBacktest
# ---------------------------------------------------------------------------


class TestEventBacktest:
    """Tests for EventBacktestEngine (Phase 4)."""

    def test_profit_target_exit(self) -> None:
        """Position exits at profit target (+2%) before T+5."""
        from strategy.backtest.event_backtest import (
            EventBacktestEngine,
            SurpriseBacktestConfig,
        )

        start = date(2024, 1, 2)  # Tuesday
        event_date = start  # event resolves day 0
        entry_date = date(2024, 1, 3)  # T+1 open

        opens = [100.0] * 10
        closes = [100.0, 100.0, 102.5] + [102.5] * 7  # day 2 close hits +2%

        price_data = {"AAPL": _make_price_data("AAPL", start, 14, opens, closes)}
        config = SurpriseBacktestConfig(min_surprise_bits=4.0)
        engine = EventBacktestEngine(config, price_data)

        event = _make_backtest_event("AAPL", event_date)
        result = engine.run([event], start, date(2024, 1, 12))

        assert result.n_events_traded == 1
        assert len(result.trade_log) == 1
        row = result.trade_log.iloc[0]
        assert row["exit_reason"] == "profit_target"
        assert row["return_pct"] is not None
        assert row["return_pct"] > 0.019  # approx +2%

    def test_stop_loss_exit(self) -> None:
        """Position exits at stop loss (-1%) before T+5."""
        from strategy.backtest.event_backtest import (
            EventBacktestEngine,
            SurpriseBacktestConfig,
        )

        start = date(2024, 1, 2)
        event_date = start
        opens = [100.0] * 10
        closes = [100.0, 100.0, 98.5] + [98.5] * 7  # hits -1% stop

        price_data = {"AAPL": _make_price_data("AAPL", start, 14, opens, closes)}
        config = SurpriseBacktestConfig(min_surprise_bits=4.0)
        engine = EventBacktestEngine(config, price_data)

        event = _make_backtest_event("AAPL", event_date)
        result = engine.run([event], start, date(2024, 1, 12))

        assert result.n_events_traded == 1
        row = result.trade_log.iloc[0]
        assert row["exit_reason"] == "stop_loss"
        assert row["return_pct"] < -0.009  # approx -1%

    def test_timeout_exit(self) -> None:
        """Position exits at T+5 if no barrier hit."""
        from strategy.backtest.event_backtest import (
            EventBacktestEngine,
            SurpriseBacktestConfig,
        )

        start = date(2024, 1, 2)
        event_date = start
        opens = [100.0] * 10
        closes = [100.5] * 10  # never hits +2% or -1% — n_days=14 gives 10 weekdays

        price_data = {"AAPL": _make_price_data("AAPL", start, 14, opens, closes)}
        config = SurpriseBacktestConfig(min_surprise_bits=4.0, max_holding_days=5)
        engine = EventBacktestEngine(config, price_data)

        event = _make_backtest_event("AAPL", event_date)
        result = engine.run([event], start, date(2024, 1, 16))

        assert result.n_events_traded == 1
        row = result.trade_log.iloc[0]
        assert row["exit_reason"] == "timeout"
        assert (
            row["return_pct"] is not None
        )  # Just verify it was computed, not its sign

    def test_no_look_ahead_entry_at_t_plus_1_open(self) -> None:
        """Entry must use T+1 OPEN price, not T+0 close."""
        from strategy.backtest.event_backtest import (
            EventBacktestEngine,
            SurpriseBacktestConfig,
        )

        start = date(2024, 1, 2)
        event_date = start
        # Day 0 open=95, close=95 — should NOT be used
        # Day 1 open=102, close=103 — entry must be at open=102
        # n_days=14 spans 10 weekdays (2024-01-02 is a Tuesday)
        opens = [95.0, 102.0] + [103.0] * 8
        closes = [95.0, 103.0] + [103.0] * 8

        price_data = {"AAPL": _make_price_data("AAPL", start, 14, opens, closes)}
        config = SurpriseBacktestConfig(min_surprise_bits=4.0)
        engine = EventBacktestEngine(config, price_data)

        event = _make_backtest_event("AAPL", event_date)
        result = engine.run([event], start, date(2024, 1, 16))

        assert result.n_events_traded == 1
        row = result.trade_log.iloc[0]
        assert abs(row["entry_price"] - 102.0) < 0.01

    def test_max_concurrent_positions_cap(self) -> None:
        """Engine respects max_concurrent_positions limit."""
        from strategy.backtest.event_backtest import (
            EventBacktestEngine,
            SurpriseBacktestConfig,
        )

        start = date(2024, 1, 2)
        event_date = start
        n_events = 15
        max_pos = 5

        symbols = [f"SYM{i:02d}" for i in range(n_events)]
        price_data = {sym: _make_price_data(sym, start, 14) for sym in symbols}

        config = SurpriseBacktestConfig(
            min_surprise_bits=4.0,
            max_concurrent_positions=max_pos,
        )
        engine = EventBacktestEngine(config, price_data)

        events = [
            _make_backtest_event(sym, event_date, event_id=f"evt-{sym}")
            for sym in symbols
        ]
        result = engine.run(events, start, date(2024, 1, 16))

        assert result.n_events_traded <= max_pos
        assert result.n_events_filtered >= n_events - max_pos

    def test_low_surprise_filtered(self) -> None:
        """Events with surprise_score < min_surprise_bits are filtered."""
        from strategy.backtest.event_backtest import (
            EventBacktestEngine,
            SurpriseBacktestConfig,
        )

        start = date(2024, 1, 2)
        price_data = {"AAPL": _make_price_data("AAPL", start, 14)}

        config = SurpriseBacktestConfig(min_surprise_bits=4.0)
        engine = EventBacktestEngine(config, price_data)

        event = _make_backtest_event("AAPL", start, surprise_score=2.0)
        result = engine.run([event], start, date(2024, 1, 12))

        assert result.n_events_traded == 0
        assert result.n_events_filtered >= 1
        assert len(result.trade_log) == 0

    def test_trade_log_has_event_id_and_surprise_score(self) -> None:
        """trade_log DataFrame has event_id and surprise_score columns."""
        from strategy.backtest.event_backtest import (
            EventBacktestEngine,
            SurpriseBacktestConfig,
        )

        start = date(2024, 1, 2)
        opens = [100.0] * 10
        closes = [102.5] * 10  # hits profit target — n_days=14 gives 10 weekdays

        price_data = {"AAPL": _make_price_data("AAPL", start, 14, opens, closes)}
        config = SurpriseBacktestConfig(min_surprise_bits=4.0)
        engine = EventBacktestEngine(config, price_data)

        event = _make_backtest_event("AAPL", start, event_id="my-evt-001")
        result = engine.run([event], start, date(2024, 1, 12))

        assert "event_id" in result.trade_log.columns
        assert "surprise_score" in result.trade_log.columns
        if len(result.trade_log) > 0:
            assert result.trade_log.iloc[0]["event_id"] == "my-evt-001"

    def test_equity_curve_columns(self) -> None:
        """equity_curve has date, equity, n_active_positions columns."""
        from strategy.backtest.event_backtest import (
            EventBacktestEngine,
            SurpriseBacktestConfig,
        )

        start = date(2024, 1, 2)
        price_data = {"AAPL": _make_price_data("AAPL", start, 14)}
        config = SurpriseBacktestConfig(min_surprise_bits=4.0)
        engine = EventBacktestEngine(config, price_data)

        event = _make_backtest_event("AAPL", start)
        result = engine.run([event], start, date(2024, 1, 12))

        assert "date" in result.equity_curve.columns
        assert "equity" in result.equity_curve.columns
        assert "n_active_positions" in result.equity_curve.columns

    def test_bearish_event_not_traded(self) -> None:
        """Events with direction=-1 (bearish) are skipped — no short selling."""
        from strategy.backtest.event_backtest import (
            EventBacktestEngine,
            SurpriseBacktestConfig,
        )

        start = date(2024, 1, 2)
        price_data = {"AAPL": _make_price_data("AAPL", start, 14)}
        config = SurpriseBacktestConfig(min_surprise_bits=4.0)
        engine = EventBacktestEngine(config, price_data)

        event = _make_backtest_event("AAPL", start, direction=-1, surprise_score=6.0)
        result = engine.run([event], start, date(2024, 1, 12))

        assert result.n_events_traded == 0
        assert len(result.trade_log) == 0


# ---------------------------------------------------------------------------
# Phase 7: TestMetaculusProvider
# ---------------------------------------------------------------------------


class TestMetaculusProvider:
    """Tests for MetaculusProvider — all mocked, no network calls."""

    def _make_question(
        self,
        qid: int = 1,
        resolution: float | None = 1.0,
        q2: float | None = 0.3,
        title: str = "Test question",
    ) -> dict:
        """Helper: create a mock question dict like Metaculus API returns."""
        return {
            "id": qid,
            "title": title,
            "resolve_time": "2024-03-15T18:00:00Z",
            "resolution": resolution,
            "community_prediction": {"full": {"q2": q2}},
            "categories": ["finance"],
        }

    def test_questions_to_events_bullish_outcome(self) -> None:
        """resolution=1.0 -> outcome='bullish', p_market_pre=q2."""
        from data.providers.metaculus import MetaculusProvider

        provider = MetaculusProvider()
        questions = [self._make_question(qid=1, resolution=1.0, q2=0.3)]
        events = provider.questions_to_events(questions, symbol="SPY")

        assert len(events) == 1
        assert events[0].outcome == "bullish"
        assert events[0].p_market_pre == pytest.approx(0.3)

    def test_questions_to_events_bearish_outcome(self) -> None:
        """resolution=0.0 -> outcome='bearish', p_market_pre=q2."""
        from data.providers.metaculus import MetaculusProvider

        provider = MetaculusProvider()
        questions = [self._make_question(qid=2, resolution=0.0, q2=0.7)]
        events = provider.questions_to_events(questions, symbol="SPY")

        assert len(events) == 1
        assert events[0].outcome == "bearish"
        assert events[0].p_market_pre == pytest.approx(0.7)

    def test_questions_to_events_skips_null_resolution(self) -> None:
        """resolution=None -> skipped."""
        from data.providers.metaculus import MetaculusProvider

        provider = MetaculusProvider()
        questions = [self._make_question(qid=3, resolution=None, q2=0.5)]
        events = provider.questions_to_events(questions, symbol="SPY")

        assert len(events) == 0

    def test_questions_to_events_skips_missing_q2(self) -> None:
        """community_prediction missing -> skipped."""
        from data.providers.metaculus import MetaculusProvider

        provider = MetaculusProvider()
        q = {
            "id": 4,
            "title": "No prediction",
            "resolve_time": "2024-03-15T18:00:00Z",
            "resolution": 1.0,
            "community_prediction": None,
            "categories": [],
        }
        events = provider.questions_to_events([q], symbol="SPY")

        assert len(events) == 0

    def test_questions_to_events_event_id_format(self) -> None:
        """event_id must be f'metaculus-{id}'."""
        from data.providers.metaculus import MetaculusProvider

        provider = MetaculusProvider()
        questions = [self._make_question(qid=999, resolution=1.0, q2=0.4)]
        events = provider.questions_to_events(questions, symbol="SPY")

        assert len(events) == 1
        assert events[0].event_id == "metaculus-999"

    def test_questions_to_events_source_is_metaculus(self) -> None:
        """source must be 'metaculus'."""
        from data.providers.metaculus import MetaculusProvider

        provider = MetaculusProvider()
        questions = [self._make_question(qid=5, resolution=1.0, q2=0.6)]
        events = provider.questions_to_events(questions, symbol="AAPL")

        assert len(events) == 1
        assert events[0].source == "metaculus"

    def test_search_questions_mocked(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """search_questions makes correct API call with pagination."""
        from data.providers.metaculus import MetaculusProvider

        provider = MetaculusProvider()
        page1 = {
            "results": [
                self._make_question(qid=10),
                self._make_question(qid=11),
            ],
            "next": "https://www.metaculus.com/api2/questions/?offset=20",
        }
        page2: dict = {"results": [], "next": None}
        call_count = 0

        def mock_get(path: str, params: dict | None = None) -> dict:
            nonlocal call_count
            result = page1 if call_count == 0 else page2
            call_count += 1
            return result

        monkeypatch.setattr(provider, "_get", mock_get)

        results = provider.search_questions(
            keyword="inflation",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            max_results=50,
        )

        assert len(results) == 2
        assert call_count == 2  # two pages fetched

    def test_questions_to_events_snapshot_is_one_hour_before_resolve(self) -> None:
        """snapshot_datetime must be resolve_time - 1 hour."""
        from data.providers.metaculus import MetaculusProvider

        provider = MetaculusProvider()
        questions = [self._make_question(qid=6, resolution=1.0, q2=0.5)]
        events = provider.questions_to_events(questions, symbol="SPY")

        assert len(events) == 1
        resolve_dt = events[0].resolved_at
        assert resolve_dt is not None
        diff = resolve_dt - events[0].snapshot_datetime
        assert diff.total_seconds() == pytest.approx(3600)

    def test_questions_to_events_outcome_confirmed_true(self) -> None:
        """outcome_confirmed must be True for all resolved questions."""
        from data.providers.metaculus import MetaculusProvider

        provider = MetaculusProvider()
        questions = [self._make_question(qid=7, resolution=0.0, q2=0.2)]
        events = provider.questions_to_events(questions, symbol="SPY")

        assert len(events) == 1
        assert events[0].outcome_confirmed is True

    def test_get_question_returns_none_on_404(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """get_question returns None when the API returns 404."""
        import requests as req

        from data.providers.metaculus import MetaculusProvider

        provider = MetaculusProvider()

        def mock_get(path: str, params: dict | None = None) -> dict:
            mock_resp = req.Response()
            mock_resp.status_code = 404
            raise req.HTTPError(response=mock_resp)

        monkeypatch.setattr(provider, "_get", mock_get)
        result = provider.get_question(99999)

        assert result is None
