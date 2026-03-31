"""Metaculus prediction market data provider for Surprise Alpha strategy.

Fetches resolved questions from the Metaculus REST API.
No authentication required for read access.
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta

import requests

from data.providers.base import ProviderConfig
from data.providers.prediction_market import EventRecord

logger = logging.getLogger(__name__)


class MetaculusProvider:
    """Fetches resolved questions from Metaculus REST API.

    No authentication required. Rate limit: be conservative (1 req/2 sec).
    """

    BASE_URL = "https://www.metaculus.com/api2"

    def __init__(self, config: ProviderConfig | None = None) -> None:
        self._config = config or ProviderConfig(
            rate_limit_requests=30,
            rate_limit_period_seconds=60,
        )
        self._last_request_time: float = 0.0
        self._session: requests.Session = requests.Session()
        self._session.headers.update({"User-Agent": "hedge-fund-research/1.0"})

    def search_questions(
        self,
        keyword: str,
        start_date: date,
        end_date: date,
        max_results: int = 50,
    ) -> list[dict]:
        """Search for resolved questions matching a keyword.

        Returns list of raw question dicts from the API.
        """
        results: list[dict] = []
        offset = 0
        limit = 20  # Metaculus page size

        while len(results) < max_results:
            params = {
                "search": keyword,
                "status": "resolved",
                "resolve_time__gte": f"{start_date.isoformat()}T00:00:00Z",
                "resolve_time__lte": f"{end_date.isoformat()}T23:59:59Z",
                "format": "json",
                "limit": limit,
                "offset": offset,
            }
            response = self._get("/questions/", params)
            items = response.get("results", [])
            if not items:
                break
            results.extend(items)
            offset += limit
            if response.get("next") is None:
                break

        return results[:max_results]

    def get_question(self, question_id: int) -> dict | None:
        """Fetch a single question by ID. Returns None if not found."""
        try:
            return self._get(f"/questions/{question_id}/")
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                return None
            raise

    def questions_to_events(
        self,
        questions: list[dict],
        symbol: str,
        event_type: str = "prediction_market",
    ) -> list[EventRecord]:
        """Convert API question dicts to EventRecord objects.

        Skips questions where:
        - resolution is None (ambiguous/annulled)
        - community_prediction is None or missing q2
        - p_market_pre (q2) is not in (0, 1)

        Sets:
        - event_id = f"metaculus-{question['id']}"
        - source = "metaculus"
        - p_market_pre = q2 (median community prediction)
        - outcome = "bullish" if resolution == 1.0 else "bearish"
        - event_date = date portion of resolve_time
        - snapshot_datetime = resolve_time - 1 hour
        - outcome_confirmed = True (already resolved)
        - description = question["title"]
        """
        events: list[EventRecord] = []
        for q in questions:
            event = self._question_to_event(q, symbol, event_type)
            if event is not None:
                events.append(event)
        return events

    def _question_to_event(
        self,
        q: dict,
        symbol: str,
        event_type: str,
    ) -> EventRecord | None:
        """Convert a single question dict to an EventRecord, or None if invalid."""
        resolution = q.get("resolution")
        if resolution is None:
            return None

        community = q.get("community_prediction")
        if community is None:
            return None
        full = community.get("full")
        if full is None:
            return None
        q2 = full.get("q2")
        if q2 is None:
            return None

        p_market_pre = float(q2)
        if not (0.0 < p_market_pre < 1.0):
            return None

        outcome = "bullish" if float(resolution) == 1.0 else "bearish"

        try:
            resolve_time_str = q.get("resolve_time", "")
            if not resolve_time_str:
                return None
            resolve_dt = datetime.fromisoformat(resolve_time_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return None
        event_date = resolve_dt.date()
        snapshot_datetime = resolve_dt - timedelta(hours=1)

        return EventRecord(
            event_id=f"metaculus-{q['id']}",
            source="metaculus",
            symbol=symbol,
            event_date=event_date,
            snapshot_datetime=snapshot_datetime,
            resolved_at=resolve_dt,
            p_market_pre=p_market_pre,
            outcome=outcome,
            outcome_confirmed=True,
            event_type=event_type,
            description=str(q.get("title", "")),
        )

    def _get(self, path: str, params: dict | None = None) -> dict:
        """Make a rate-limited GET request with retry on transient errors."""
        import time

        url = f"{self.BASE_URL}{path}"
        last_error: Exception | None = None
        for attempt in range(self._config.max_retries):
            try:
                self._rate_limit()
                response = self._session.get(
                    url, params=params, timeout=self._config.timeout_seconds
                )
                response.raise_for_status()
                return response.json()  # type: ignore[no-any-return]
            except requests.HTTPError as e:
                if e.response.status_code == 404:
                    raise  # Don't retry 404s
                last_error = e
            except (requests.ConnectionError, requests.Timeout) as e:
                last_error = e
            if attempt < self._config.max_retries - 1:
                time.sleep(self._config.retry_delay_seconds * (attempt + 1))
        raise last_error  # type: ignore

    def _rate_limit(self) -> None:
        """Apply rate limiting between requests."""
        min_interval = (
            self._config.rate_limit_period_seconds / self._config.rate_limit_requests
        )
        elapsed = time.time() - self._last_request_time
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        self._last_request_time = time.time()
