"""Earnings surprise provider for Surprise Alpha backtest system.

Fetches historical EPS data from Yahoo Finance and converts earnings
consensus vs actuals into EventRecord proxy events. Uses z-score based
probability as a proxy for prediction market pre-event probability.
"""

from __future__ import annotations

import logging
import math
import time
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pandas as pd
import scipy.stats

from data.providers.base import ProviderConfig
from data.providers.prediction_market import EventRecord

logger = logging.getLogger(__name__)

_IN_LINE_THRESHOLD = 0.01  # Within 1% of estimate is treated as neutral


class EarningsSurpriseProvider:
    """Fetches earnings EPS data from Yahoo Finance and converts to EventRecord proxy events.

    Uses EPS estimate vs actual as a proxy for prediction market probability.
    z-score of the surprise is converted to a probability via the normal CDF.
    """

    def __init__(self, config: ProviderConfig | None = None) -> None:
        self._config = config or ProviderConfig()
        self._last_request_time: float = 0.0

    def get_events(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
        min_history_quarters: int = 8,
    ) -> list[EventRecord]:
        """Fetch earnings history and convert to EventRecord objects.

        Args:
            symbol: Ticker symbol
            start_date: Start of date range to return events for
            end_date: End of date range to return events for
            min_history_quarters: Minimum quarters needed to compute rolling std

        Returns:
            List of EventRecord objects, one per earnings announcement
        """
        raw = self._fetch_with_retry(lambda: self._fetch_earnings_history(symbol))

        if raw.empty:
            logger.warning("No earnings history for %s", symbol)
            return []

        probabilities = self._compute_probability(
            eps_actual=raw["eps_actual"],
            eps_estimate=raw["eps_estimate"],
            min_periods=min_history_quarters,
        )

        combined = raw.join(probabilities)
        combined = combined.sort_index()  # chronological order

        events: list[EventRecord] = []
        prior_confirmed_count = 0

        for idx, row in combined.iterrows():
            ann_dt: datetime = idx  # type: ignore[assignment]
            ann_date = ann_dt.date()

            if ann_date < start_date or ann_date > end_date:
                # Only count confirmed events (non-NaN actual) toward prior history
                if not pd.isna(row["eps_actual"]):
                    prior_confirmed_count += 1
                continue

            quarter_label = _quarter_label(ann_dt)
            record = self._make_event_record(
                symbol=symbol,
                row=row,
                quarter_label=quarter_label,
                ann_dt=ann_dt,
                n_historical_events=prior_confirmed_count,
            )
            if record is not None:
                events.append(record)

            # Only count confirmed events toward history (NaN actuals are unresolved)
            if not pd.isna(row["eps_actual"]):
                prior_confirmed_count += 1

        return events

    def _fetch_earnings_history(self, symbol: str) -> pd.DataFrame:
        """Fetch earnings history from Yahoo Finance.

        Returns DataFrame with columns: [eps_estimate, eps_actual]
        indexed by the announcement datetime (tz-aware).
        Rows where Reported EPS is NaN (not yet reported) are dropped.
        """
        import yfinance as yf

        ticker = yf.Ticker(symbol)
        earnings = ticker.earnings_dates

        if earnings is None or earnings.empty:
            return pd.DataFrame(columns=["eps_estimate", "eps_actual"])

        df = earnings[["EPS Estimate", "Reported EPS"]].copy()
        df.columns = ["eps_estimate", "eps_actual"]

        # Drop future (unreported) quarters — keep NaN in estimate but not actual
        df = df.dropna(subset=["eps_actual"])

        # Sort chronologically (yfinance returns newest first)
        df = df.sort_index()

        return df

    def _compute_probability(
        self,
        eps_actual: pd.Series,
        eps_estimate: pd.Series,
        min_periods: int = 8,
    ) -> pd.DataFrame:
        """Compute surprise z-score and convert to tail probability via normal CDF.

        Steps:
          1. surprise = eps_actual - eps_estimate
          2. rolling_std = surprise.rolling(min_periods, min_periods=min_periods).std()
             .shift(1)  — shift(1) prevents look-ahead: each row uses only prior history
          3. z_score = surprise / rolling_std  (NaN where std is NaN or 0)
          4. p_proxy = 1 - norm.cdf(|z_score|)  — tail probability of this magnitude
             (0.5 for z=0, ~0.0013 for |z|=3)

        p_proxy semantics: probability of seeing a surprise this large or larger.
        Small p_proxy = rare/surprising event = high information content.

        Returns DataFrame with columns: [surprise, rolling_std, z_score, p_proxy]
        """
        surprise = eps_actual - eps_estimate

        rolling_std = (
            surprise.rolling(window=min_periods, min_periods=min_periods).std().shift(1)
        )  # shift(1) = no look-ahead: use only prior obs for std

        # Avoid division by zero — set std=0 rows to NaN
        safe_std = rolling_std.where(rolling_std > 0)
        z_score = surprise / safe_std

        p_proxy = z_score.apply(
            lambda z: (
                1.0 - scipy.stats.norm.cdf(abs(z)) if not (z != z) else float("nan")
            )
        )

        return pd.DataFrame(
            {
                "surprise": surprise,
                "rolling_std": rolling_std,
                "z_score": z_score,
                "p_proxy": p_proxy,
            },
            index=eps_actual.index,
        )

    def _make_event_record(
        self,
        symbol: str,
        row: pd.Series,
        quarter_label: str,
        ann_dt: datetime,
        n_historical_events: int,
    ) -> EventRecord | None:
        """Convert one earnings row to an EventRecord.

        Returns None if:
        - p_proxy is NaN (not enough history for rolling std)
        - eps_actual is NaN

        Direction and outcome logic:
        - |surprise| < 1% of |estimate| → neutral, direction=0, p_market_pre=0.5
        - actual > estimate → bullish, p_market_pre=p_proxy, direction=+1
        - actual < estimate → bearish, p_market_pre=p_proxy, direction=-1

        p_market_pre = tail probability of seeing a surprise this large or larger.
        It is the same (p_proxy) for both beats and misses — it captures magnitude
        rarity, not directionality. Directionality is captured by `direction`.
        surprise_score = -log2(p_proxy): 0 bits for z=0, ~9.5 bits for |z|=3.
        """
        eps_actual = row["eps_actual"]
        eps_estimate = row["eps_estimate"]
        p_proxy = row["p_proxy"]

        if _is_nan(eps_actual) or _is_nan(p_proxy):
            return None

        surprise = eps_actual - eps_estimate

        # Determine in-line threshold
        reference = (
            abs(eps_estimate)
            if not _is_nan(eps_estimate) and eps_estimate != 0
            else 0.0
        )
        in_line = reference > 0 and abs(surprise) < _IN_LINE_THRESHOLD * reference

        if in_line:
            outcome = "neutral"
            direction = 0
            p_market_pre = 0.5
        elif surprise > 0:
            outcome = "bullish"
            direction = 1
            p_market_pre = float(p_proxy)
        else:
            outcome = "bearish"
            direction = -1
            p_market_pre = float(p_proxy)  # tail prob of this magnitude miss

        # Clamp to avoid log(0) issues — EventRecord.__post_init__ also does this
        p_market_pre = max(1e-9, min(1 - 1e-9, p_market_pre))

        surprise_score = -math.log2(p_market_pre)

        # Make snapshot_datetime tz-aware (UTC); subtract 1 hour as proxy for T-1h
        if ann_dt.tzinfo is None:
            ann_dt_utc = ann_dt.replace(tzinfo=UTC)
        else:
            ann_dt_utc = ann_dt.astimezone(UTC)

        snapshot_dt = ann_dt_utc - timedelta(hours=1)
        ann_date = ann_dt_utc.date()

        eps_actual_val = float(eps_actual)
        eps_estimate_val = (
            float(eps_estimate) if not _is_nan(eps_estimate) else float("nan")
        )

        description = (
            f"{symbol} {quarter_label} earnings: "
            f"actual={eps_actual_val:.2f}, estimate={eps_estimate_val:.2f}"
        )

        return EventRecord(
            event_id=f"earnings-{symbol}-{quarter_label}",
            source="earnings_proxy",
            symbol=symbol,
            event_date=ann_date,
            snapshot_datetime=snapshot_dt,
            resolved_at=ann_dt_utc,
            p_market_pre=p_market_pre,
            outcome=outcome,
            outcome_confirmed=not pd.isna(eps_actual),
            surprise_score=surprise_score,
            direction=direction,
            n_historical_events=n_historical_events,
            liquidity_ok=True,
            event_type="earnings",
            description=description,
            tags=["earnings_proxy"],
        )

    def _rate_limit(self) -> None:
        """Apply rate limiting between requests."""
        min_interval = (
            self._config.rate_limit_period_seconds / self._config.rate_limit_requests
        )
        elapsed = time.time() - self._last_request_time
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        self._last_request_time = time.time()

    def _fetch_with_retry(self, fetch_func: Callable[[], Any]) -> Any:
        """Execute a fetch function with retry logic and rate limiting."""
        last_error: Exception | None = None
        for attempt in range(self._config.max_retries):
            try:
                self._rate_limit()
                return fetch_func()
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Attempt %d/%d failed: %s",
                    attempt + 1,
                    self._config.max_retries,
                    exc,
                )
                if attempt < self._config.max_retries - 1:
                    time.sleep(self._config.retry_delay_seconds * (attempt + 1))
        raise last_error  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _quarter_label(dt: datetime) -> str:
    """Return a quarter label like '2024Q1' from a datetime."""
    quarter = (dt.month - 1) // 3 + 1
    return f"{dt.year}Q{quarter}"


def _is_nan(value: object) -> bool:
    """Return True if value is float NaN or non-numeric."""
    try:
        return math.isnan(float(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
