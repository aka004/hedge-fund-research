"""EventStore: Parquet-based persistence for EventRecord objects.

One Parquet file per event source under data/storage/pm_events_{source}.parquet.
DuckDB is used in-memory to provide SQL query capabilities across all sources.
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd

from data.providers.prediction_market import EventRecord

logger = logging.getLogger(__name__)


class EventStore:
    """Read/write EventRecord objects to Parquet files, one file per source.

    Uses DuckDB in-memory for SQL queries across all event parquet files.
    """

    def __init__(self, storage_dir: str | Path = "data/storage") -> None:
        self._storage_dir = Path(storage_dir)
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        self._db = duckdb.connect(":memory:")
        self._setup_view()

    def _parquet_path(self, source: str) -> Path:
        """Return the parquet file path for a given source."""
        return self._storage_dir / f"pm_events_{source}.parquet"

    def _setup_view(self) -> None:
        """Create a DuckDB view over all pm_events_*.parquet files if any exist."""
        files = list(self._storage_dir.glob("pm_events_*.parquet"))
        if not files:
            return

        quoted = ", ".join(f"'{str(f)}'" for f in files)
        sql = f"CREATE OR REPLACE VIEW pm_events AS SELECT * FROM read_parquet([{quoted}])"
        self._db.execute(sql)
        logger.debug("DuckDB view pm_events created over %d file(s).", len(files))

    def save_events(self, events: list[EventRecord]) -> None:
        """Persist a list of EventRecords grouped by source.

        For each source:
        1. Load existing parquet if present.
        2. Append the new records.
        3. Deduplicate by (event_id, source) — keeping the newest row.
        4. Write back to parquet.
        """
        if not events:
            return

        # Group by source
        by_source: dict[str, list[dict]] = {}
        for evt in events:
            by_source.setdefault(evt.source, []).append(evt.to_dict())

        for source, new_rows in by_source.items():
            path = self._parquet_path(source)
            new_df = pd.DataFrame(new_rows)

            if path.exists():
                existing_df = pd.read_parquet(path)
                combined = pd.concat([existing_df, new_df], ignore_index=True)
            else:
                combined = new_df

            # Dedup: sort by snapshot_datetime so the most recent snapshot wins,
            # then keep last occurrence of each (event_id, source) pair.
            combined = combined.sort_values(
                "snapshot_datetime", ascending=True, na_position="first"
            )
            combined = combined.drop_duplicates(
                subset=["event_id", "source"], keep="last"
            )
            combined = combined.reset_index(drop=True)

            combined.to_parquet(path, index=False, compression="snappy")
            logger.info(
                "Saved %d events for source '%s' to %s.", len(new_rows), source, path
            )

        self._setup_view()

    def load_events(
        self,
        symbol: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        source: str | None = None,
    ) -> list[EventRecord]:
        """Load EventRecords from parquet with optional filters.

        Returns an empty list if no parquet files exist yet.
        """
        files = list(self._storage_dir.glob("pm_events_*.parquet"))
        if not files:
            return []

        if source is not None:
            path = self._parquet_path(source)
            if not path.exists():
                return []
            files = [path]

        dfs: list[pd.DataFrame] = []
        for f in files:
            df = pd.read_parquet(f)
            dfs.append(df)

        combined = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()
        if combined.empty:
            return []

        # Normalize event_date to date objects for type-safe comparison
        if "event_date" in combined.columns:
            combined["event_date"] = pd.to_datetime(combined["event_date"]).dt.date

        if symbol is not None:
            combined = combined[combined["symbol"] == symbol]

        if start_date is not None:
            combined = combined[combined["event_date"] >= start_date]

        if end_date is not None:
            combined = combined[combined["event_date"] <= end_date]

        if combined.empty:
            return []

        return [
            EventRecord.from_dict(row) for row in combined.to_dict(orient="records")
        ]

    def get_events_with_min_history(
        self,
        symbol: str,
        min_count: int = 20,
    ) -> list[EventRecord]:
        """Return events for a symbol only when confirmed event count >= min_count.

        Only outcome_confirmed=True events count toward the minimum threshold.
        """
        all_events = self.load_events(symbol=symbol)
        confirmed_count = sum(1 for e in all_events if e.outcome_confirmed)
        if confirmed_count < min_count:
            return []
        return [e for e in all_events if e.outcome_confirmed]

    def get_pre_event_snapshot(self, event_id: str) -> float | None:
        """Return p_market_pre for a specific event_id, or None if not found."""
        files = list(self._storage_dir.glob("pm_events_*.parquet"))
        for f in files:
            df = pd.read_parquet(f)
            match = df[df["event_id"] == event_id]
            if not match.empty:
                return float(match.iloc[0]["p_market_pre"])
        return None

    def query(self, sql: str) -> pd.DataFrame:
        """Execute arbitrary SQL against the pm_events DuckDB view.

        Raises RuntimeError if no events have been saved yet (view does not exist).
        """
        files = list(self._storage_dir.glob("pm_events_*.parquet"))
        if not files:
            raise RuntimeError(
                "No pm_events view available — save events before running queries."
            )
        return self._db.execute(sql).df()
