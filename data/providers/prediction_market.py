"""Prediction market data model for Surprise Alpha strategy.

Defines the EventRecord dataclass used to represent market prediction events
from sources like earnings proxies, Metaculus, Kalshi, and Polymarket.

MetaculusProvider lives in data.providers.metaculus and is re-exported here
for convenience.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from datetime import date, datetime

logger = logging.getLogger(__name__)

_VALID_OUTCOMES = {"bullish", "bearish", "neutral", "pending"}
_VALID_SOURCES = {"earnings_proxy", "metaculus", "kalshi", "polymarket"}


@dataclass
class EventRecord:
    """A single prediction market event record.

    Captures the pre-event market probability, resolution outcome, and
    computed surprise metrics for use in the Surprise Alpha strategy.
    """

    event_id: str
    source: str
    symbol: str
    event_date: date
    snapshot_datetime: datetime
    resolved_at: datetime | None
    p_market_pre: float
    outcome: str
    outcome_confirmed: bool
    surprise_score: float | None = None
    direction: int | None = None
    n_historical_events: int = 0
    liquidity_ok: bool = True
    event_type: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Validate fields after initialization."""
        self._validate_source()
        self._validate_outcome()
        self._clamp_probability()

    def _validate_source(self) -> None:
        if self.source not in _VALID_SOURCES:
            raise ValueError(
                f"Invalid source '{self.source}'. Must be one of {_VALID_SOURCES}"
            )

    def _validate_outcome(self) -> None:
        if self.outcome not in _VALID_OUTCOMES:
            raise ValueError(
                f"Invalid outcome '{self.outcome}'. Must be one of {_VALID_OUTCOMES}"
            )

    def _clamp_probability(self) -> None:
        """Clamp p_market_pre to (0, 1) range with a warning if out of bounds."""
        lo, hi = 1e-9, 1 - 1e-9
        if not (lo <= self.p_market_pre <= hi):
            logger.warning(
                "p_market_pre=%.6f is out of (0, 1) range for event '%s'. "
                "Clamping to [%.2e, %.2e].",
                self.p_market_pre,
                self.event_id,
                lo,
                hi,
            )
            self.p_market_pre = max(lo, min(hi, self.p_market_pre))

    def to_dict(self) -> dict:
        """Convert to a flat dict suitable for Parquet storage.

        - date/datetime fields are serialized as ISO strings
        - tags list is serialized as a JSON string
        - None floats become NaN; None ints become 0
        """
        return {
            "event_id": self.event_id,
            "source": self.source,
            "symbol": self.symbol,
            "event_date": self.event_date.isoformat(),
            "snapshot_datetime": self.snapshot_datetime.isoformat(),
            "resolved_at": (
                self.resolved_at.isoformat() if self.resolved_at is not None else None
            ),
            "p_market_pre": self.p_market_pre,
            "outcome": self.outcome,
            "outcome_confirmed": self.outcome_confirmed,
            "surprise_score": (
                self.surprise_score if self.surprise_score is not None else float("nan")
            ),
            "direction": (
                float(self.direction) if self.direction is not None else float("nan")
            ),
            "n_historical_events": self.n_historical_events,
            "liquidity_ok": self.liquidity_ok,
            "event_type": self.event_type,
            "description": self.description,
            "tags": json.dumps(self.tags),
        }

    @classmethod
    def from_dict(cls, d: dict) -> EventRecord:
        """Reconstruct an EventRecord from a flat dict (e.g. loaded from Parquet).

        Reverses the transformations applied by to_dict():
        - ISO strings → date/datetime objects
        - JSON string → list for tags
        - NaN → None for optional numeric fields
        """
        raw_resolved_at = d.get("resolved_at")
        resolved_at: datetime | None = None
        if raw_resolved_at is not None and not _is_nan(raw_resolved_at):
            resolved_at = datetime.fromisoformat(str(raw_resolved_at))

        raw_surprise = d.get("surprise_score")
        surprise_score: float | None = None
        if raw_surprise is not None and not _is_nan(raw_surprise):
            surprise_score = float(raw_surprise)

        raw_direction = d.get("direction")
        direction: int | None = None
        if raw_direction is not None and not _is_nan(raw_direction):
            direction = int(float(raw_direction))

        raw_tags = d.get("tags", "[]")
        tags: list[str] = (
            json.loads(raw_tags) if isinstance(raw_tags, str) else list(raw_tags or [])
        )

        raw_event_date = d["event_date"]
        if isinstance(raw_event_date, str):
            event_date = date.fromisoformat(raw_event_date)
        elif isinstance(raw_event_date, datetime):
            event_date = raw_event_date.date()
        else:
            event_date = raw_event_date

        raw_snapshot = d["snapshot_datetime"]
        if isinstance(raw_snapshot, str):
            snapshot_datetime = datetime.fromisoformat(raw_snapshot)
        elif isinstance(raw_snapshot, datetime):
            snapshot_datetime = raw_snapshot
        else:
            snapshot_datetime = datetime.fromisoformat(str(raw_snapshot))

        return cls(
            event_id=str(d["event_id"]),
            source=str(d["source"]),
            symbol=str(d["symbol"]),
            event_date=event_date,
            snapshot_datetime=snapshot_datetime,
            resolved_at=resolved_at,
            p_market_pre=float(d["p_market_pre"]),
            outcome=str(d["outcome"]),
            outcome_confirmed=bool(d["outcome_confirmed"]),
            surprise_score=surprise_score,
            direction=direction,
            n_historical_events=int(d.get("n_historical_events", 0)),
            liquidity_ok=bool(d.get("liquidity_ok", True)),
            event_type=str(d.get("event_type", "")),
            description=str(d.get("description", "")),
            tags=tags,
        )


def _is_nan(value: object) -> bool:
    """Return True if value is a float NaN."""
    try:
        return math.isnan(float(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
