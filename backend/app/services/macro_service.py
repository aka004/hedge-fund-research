"""Macro Intelligence Dashboard service.

Fetches data from FRED/Yahoo, caches to DuckDB, computes signals,
and generates AI verdicts.
"""

import json
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import anthropic
import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from app.core.database import get_db, get_db_write
from app.services.macro_config import (
    INDICATOR_GROUPS,
    get_indicator_by_id,
)
from config import get_anthropic_api_key

logger = logging.getLogger(__name__)

CACHE_TTL_HOURS = 24
VERDICT_TTL_HOURS = 12

# ---------------------------------------------------------------------------
# Database setup
# ---------------------------------------------------------------------------


def ensure_tables() -> None:
    """Create macro tables if they don't exist."""
    with get_db_write() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS macro_indicators (
                series_id VARCHAR,
                date DATE,
                value DOUBLE,
                fetched_at TIMESTAMP,
                PRIMARY KEY (series_id, date)
            )
        """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS macro_ai_verdicts (
                id INTEGER PRIMARY KEY DEFAULT 1,
                verdict_json VARCHAR,
                created_at TIMESTAMP
            )
        """
        )


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------


def _get_fred_api_key() -> str | None:
    key = os.getenv("FRED_API_KEY")
    if not key:
        logger.warning("FRED_API_KEY not set -- FRED data unavailable")
    return key


def fetch_fred_series(series_id: str, api_key: str) -> pd.DataFrame:
    """Fetch a single FRED series. Returns DataFrame with date, value."""
    from fredapi import Fred

    fred = Fred(api_key=api_key)
    raw = fred.get_series(series_id)
    df = raw.reset_index()
    df.columns = ["date", "value"]
    df["date"] = pd.to_datetime(df["date"])
    df = df.dropna(subset=["value"])
    return df


def fetch_yahoo_data(ticker: str, period: str = "10y") -> pd.DataFrame:
    """Fetch Yahoo Finance data. Returns DataFrame with date, close, volume."""
    t = yf.Ticker(ticker)
    hist = t.history(period=period)
    if hist.empty:
        return pd.DataFrame(columns=["date", "close", "volume"])
    df = hist.reset_index()[["Date", "Close", "Volume"]]
    df.columns = ["date", "close", "volume"]
    df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
    return df


# ---------------------------------------------------------------------------
# Computations
# ---------------------------------------------------------------------------


def compute_yoy(df: pd.DataFrame) -> pd.DataFrame:
    """Add yoy_pct column (year-over-year percent change)."""
    df = df.sort_values("date").copy()
    df["yoy_pct"] = df["value"].pct_change(periods=12) * 100
    return df


def compute_mom_change(df: pd.DataFrame) -> pd.DataFrame:
    """Add mom_change column (month-over-month absolute change)."""
    df = df.sort_values("date").copy()
    df["mom_change"] = df["value"].diff()
    return df


def classify_signal(value: float, prev_value: float | None, config: dict) -> str:
    """Classify an indicator as hawkish, dovish, or neutral."""
    hawk = config.get("hawk_level")
    dove = config.get("dove_level")
    invert = config.get("invert_trend", False)

    if config.get("signal_type") == "ma200":
        return "neutral"

    if hawk is None or dove is None:
        return "neutral"

    # Level score: where does the value sit between dove and hawk?
    if hawk > dove:  # higher = more hawkish (e.g. CPI)
        if value >= hawk:
            level_score = 1.0
        elif value <= dove:
            level_score = -1.0
        else:
            level_score = (value - dove) / (hawk - dove) * 2 - 1
    else:  # lower = more hawkish (e.g. unemployment: hawk=3.5, dove=4.5)
        if value <= hawk:
            level_score = 1.0
        elif value >= dove:
            level_score = -1.0
        else:
            level_score = (dove - value) / (dove - hawk) * 2 - 1

    # Trend score
    trend_score = 0.0
    weight = config.get("trend_weight", 0.3)
    if prev_value is not None and prev_value != 0:
        change = (value - prev_value) / abs(prev_value)
        trend_score = max(-1.0, min(1.0, change * 10))
        if invert:
            trend_score = -trend_score

    combined = level_score * (1 - weight) + trend_score * weight

    if combined > 0.2:
        return "hawkish"
    elif combined < -0.2:
        return "dovish"
    return "neutral"


# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------


def get_cached_data(series_id: str) -> tuple[pd.DataFrame | None, datetime | None]:
    """Return cached data + last fetch time for a series."""
    try:
        with get_db() as conn:
            df = conn.execute(
                "SELECT date, value, fetched_at FROM macro_indicators "
                "WHERE series_id = ? ORDER BY date",
                [series_id],
            ).fetchdf()
        if df.empty:
            return None, None
        fetched_at = pd.to_datetime(df["fetched_at"].iloc[-1])
        return df[["date", "value"]], fetched_at
    except Exception:
        return None, None


def cache_data(series_id: str, df: pd.DataFrame) -> None:
    """Upsert indicator data to DuckDB."""
    if df.empty:
        return
    now = datetime.utcnow()
    with get_db_write() as conn:
        conn.execute("DELETE FROM macro_indicators WHERE series_id = ?", [series_id])
        records = df[["date", "value"]].copy()
        records["series_id"] = series_id
        records["fetched_at"] = now
        conn.execute(
            "INSERT INTO macro_indicators (series_id, date, value, fetched_at) "
            "SELECT series_id, date, value, fetched_at FROM records"
        )


def _is_cache_fresh(fetched_at: datetime | None) -> bool:
    if fetched_at is None:
        return False
    if fetched_at.tzinfo:
        fetched_at = fetched_at.replace(tzinfo=None)
    return datetime.utcnow() - fetched_at < timedelta(hours=CACHE_TTL_HOURS)


# ---------------------------------------------------------------------------
# Display formatting
# ---------------------------------------------------------------------------


def _format_display(
    value: float | None, fmt: str, prev_value: float | None = None
) -> str:
    if value is None:
        return "N/A"
    if fmt == "range":
        low = round(value - 0.125, 2)
        high = round(value + 0.125, 2)
        return f"{low:.2f}-{high:.2f}%"
    if fmt == "percent":
        return f"{value:.2f}%"
    if fmt == "currency_T":
        av = abs(value)
        if av >= 1_000_000:  # millions → show as trillions
            return f"${value / 1_000_000:.2f}T"
        elif av >= 1_000:  # thousands → show as billions
            return f"${value / 1_000:.0f}B"
        else:
            return f"${value:.1f}B"
    if fmt == "change_K":
        sign = "+" if value >= 0 else ""
        return f"{sign}{value:.0f}K"
    if fmt == "currency":
        return f"${value:,.2f}"
    if fmt == "number":
        return f"{value:,.2f}"
    return str(round(value, 2))


# ---------------------------------------------------------------------------
# Per-indicator refresh
# ---------------------------------------------------------------------------


def refresh_indicator(indicator_config: dict) -> dict:
    """Fetch, cache, and compute signal for one indicator."""
    ind_id = indicator_config["id"]
    source = indicator_config.get("source", "")
    series_id = indicator_config.get("series_id", ind_id)

    # AAII sentiment doesn't exist on FRED -- skip
    if series_id == "AAII":
        return {
            "id": ind_id,
            "name": indicator_config["name"],
            "value": None,
            "display": "N/A",
            "date": "",
            "trend": "flat",
            "trend_display": "—",
            "signal": "neutral",
            "sparkline": [],
            "series_id": "AAII",
            "available": False,
        }

    # Check cache first
    cached_df, fetched_at = get_cached_data(series_id)
    need_fetch = not _is_cache_fresh(fetched_at)

    df = None
    if source in ("fred", "fred_computed"):
        api_key = _get_fred_api_key()
        if need_fetch and api_key:
            try:
                if source == "fred_computed":
                    ids = indicator_config["series_ids"]
                    comp = indicator_config.get("computation")
                    df_a = fetch_fred_series(ids[0], api_key)
                    df_b = fetch_fred_series(ids[1], api_key)
                    # WRESBAL is in millions, RRPONTSYD is in billions
                    # Normalize RRPONTSYD to millions
                    if ids[1] == "RRPONTSYD":
                        df_b["value"] = df_b["value"] * 1000
                    merged = pd.merge(df_a, df_b, on="date", suffixes=("_a", "_b"))
                    if comp == "subtract":
                        merged["value"] = merged["value_a"] - merged["value_b"]
                    df = merged[["date", "value"]]
                    cache_data(series_id, df)
                else:
                    df = fetch_fred_series(series_id, api_key)
                    cache_data(series_id, df)
            except Exception as e:
                logger.error(f"FRED fetch failed for {series_id}: {e}")
        if df is None:
            df = cached_df

    elif source == "yahoo":
        ticker = indicator_config.get("ticker", "")
        cache_key = f"yahoo_{ticker}"
        cached_df, fetched_at = get_cached_data(cache_key)
        if need_fetch or not _is_cache_fresh(fetched_at):
            try:
                ydf = fetch_yahoo_data(ticker)
                if not ydf.empty:
                    df = ydf.rename(columns={"close": "value"})[["date", "value"]]
                    cache_data(cache_key, df)
            except Exception as e:
                logger.error(f"Yahoo fetch failed for {ticker}: {e}")
        if df is None:
            df = cached_df

    if df is None or df.empty:
        return {
            "id": ind_id,
            "name": indicator_config["name"],
            "value": None,
            "display": "N/A",
            "date": "",
            "trend": "flat",
            "trend_display": "—",
            "signal": "neutral",
            "sparkline": [],
            "series_id": indicator_config.get("series_id", ind_id),
            "available": False,
        }

    # Compute derived values
    unit = indicator_config.get("unit", "")
    if unit == "percent_yoy":
        df = compute_yoy(df)
        current = (
            df["yoy_pct"].dropna().iloc[-1]
            if not df["yoy_pct"].dropna().empty
            else None
        )
        prev = (
            df["yoy_pct"].dropna().iloc[-2] if len(df["yoy_pct"].dropna()) > 1 else None
        )
    elif unit == "mom_change_thousands":
        df = compute_mom_change(df)
        current = (
            df["mom_change"].dropna().iloc[-1]
            if not df["mom_change"].dropna().empty
            else None
        )
        prev = (
            df["mom_change"].dropna().iloc[-2]
            if len(df["mom_change"].dropna()) > 1
            else None
        )
    else:
        current = float(df["value"].iloc[-1])
        prev = float(df["value"].iloc[-2]) if len(df) > 1 else None

    signal = (
        classify_signal(current, prev, indicator_config)
        if current is not None
        else "neutral"
    )
    display = _format_display(
        current, indicator_config.get("display_format", "number"), prev
    )

    # Compute trend info
    if current is not None and prev is not None:
        diff = current - prev
        if abs(diff) < 0.001:
            trend = "flat"
            trend_display = "— 0.0"
        elif diff > 0:
            trend = "up"
            trend_display = f"▲ +{abs(diff):.1f}"
        else:
            trend = "down"
            trend_display = f"▼ {diff:.1f}"
    else:
        trend = "flat"
        trend_display = "—"

    # Extract date from last data point
    last_date = ""
    if not df.empty:
        last_dt = pd.to_datetime(df["date"].iloc[-1])
        last_date = (
            last_dt.strftime("%b %Y")
            if unit in ("percent_yoy", "mom_change_thousands", "percent")
            else last_dt.strftime("%b %d")
        )

    # Build sparkline from last 8 data points
    sparkline = []
    if unit == "percent_yoy" and "yoy_pct" in df.columns:
        vals = df["yoy_pct"].dropna().tail(8).tolist()
        sparkline = [round(v, 2) for v in vals]
    elif unit == "mom_change_thousands" and "mom_change" in df.columns:
        vals = df["mom_change"].dropna().tail(8).tolist()
        sparkline = [round(v, 2) for v in vals]
    else:
        vals = df["value"].tail(8).tolist()
        sparkline = [round(float(v), 2) for v in vals]

    return {
        "id": ind_id,
        "name": indicator_config["name"],
        "value": round(current, 4) if current is not None else None,
        "prev_value": round(prev, 4) if prev is not None else None,
        "display": display,
        "date": last_date,
        "trend": trend,
        "trend_display": trend_display,
        "signal": signal,
        "sparkline": sparkline,
        "series_id": indicator_config.get("series_id", ind_id),
        "available": True,
        "reference_lines": indicator_config.get("reference_lines", []),
    }


# ---------------------------------------------------------------------------
# Aggregate endpoints
# ---------------------------------------------------------------------------


def get_all_indicators_data() -> dict:
    """Return full dashboard payload with all groups and signal balance."""
    ensure_tables()
    groups = {}
    hawk_count = 0
    dove_count = 0
    neutral_count = 0

    for group_key, group_cfg in INDICATOR_GROUPS.items():
        items = []
        for ind_cfg in group_cfg["indicators"]:
            result = refresh_indicator(ind_cfg)
            items.append(result)
            if result.get("available"):
                if result["signal"] == "hawkish":
                    hawk_count += 1
                elif result["signal"] == "dovish":
                    dove_count += 1
                else:
                    neutral_count += 1
        groups[group_key] = {
            "label": group_cfg["label"],
            "color": group_cfg["color"],
            "indicators": items,
        }

    total = hawk_count + dove_count + neutral_count
    regime = (
        "HAWKISH"
        if hawk_count > dove_count
        else "DOVISH" if dove_count > hawk_count else "MIXED"
    )
    return {
        "indicators": groups,
        "signal_balance": {
            "hawkish": hawk_count,
            "dovish": dove_count,
            "neutral": neutral_count,
            "total": total,
            "regime": regime,
        },
        "last_updated": datetime.utcnow().isoformat(),
    }


def get_indicator_history(indicator_id: str, range: str = "2Y") -> dict | None:
    """Return historical data for charting a single indicator."""
    config = get_indicator_by_id(indicator_id)
    if config is None:
        return None

    range_map = {"1Y": 365, "2Y": 730, "5Y": 1825, "MAX": 36500}
    days = range_map.get(range, 730)
    cutoff = datetime.utcnow() - timedelta(days=days)

    source = config.get("source", "")
    series_id = config.get("series_id", indicator_id)

    if source == "yahoo":
        series_id = f"yahoo_{config.get('ticker', '')}"

    if series_id == "AAII":
        return {"id": indicator_id, "data": [], "available": False}

    # Try to refresh if needed, then read cache
    refresh_indicator(config)

    try:
        with get_db() as conn:
            df = conn.execute(
                "SELECT date, value FROM macro_indicators "
                "WHERE series_id = ? AND date >= ? ORDER BY date",
                [series_id, cutoff],
            ).fetchdf()
    except Exception:
        df = pd.DataFrame()

    if df.empty:
        return {"id": indicator_id, "data": [], "available": False}

    unit = config.get("unit", "")
    if unit == "percent_yoy":
        df = compute_yoy(df)
        records = [
            {"date": r["date"].isoformat()[:10], "value": round(r["yoy_pct"], 4)}
            for _, r in df.dropna(subset=["yoy_pct"]).iterrows()
        ]
    elif unit == "mom_change_thousands":
        df = compute_mom_change(df)
        records = [
            {"date": r["date"].isoformat()[:10], "value": round(r["mom_change"], 2)}
            for _, r in df.dropna(subset=["mom_change"]).iterrows()
        ]
    else:
        records = [
            {"date": r["date"].isoformat()[:10], "value": round(r["value"], 4)}
            for _, r in df.iterrows()
        ]

    return {
        "id": indicator_id,
        "name": config["name"],
        "data": records,
        "reference_lines": config.get("reference_lines", []),
        "available": True,
    }


# ---------------------------------------------------------------------------
# AI verdict
# ---------------------------------------------------------------------------


def get_cached_verdict() -> dict | None:
    """Return cached verdict if it's still fresh."""
    try:
        with get_db() as conn:
            row = conn.execute(
                "SELECT verdict_json, created_at FROM macro_ai_verdicts " "WHERE id = 1"
            ).fetchone()
        if row is None:
            return None
        created_at = pd.to_datetime(row[1])
        if created_at.tzinfo:
            created_at = created_at.replace(tzinfo=None)
        if datetime.utcnow() - created_at > timedelta(hours=VERDICT_TTL_HOURS):
            return None
        return json.loads(row[0])
    except Exception:
        return None


def generate_ai_verdict(indicators_data: dict) -> dict:
    """Call Claude to generate a macro verdict from indicator data."""
    try:
        api_key = get_anthropic_api_key()
    except ValueError:
        logger.warning("Anthropic API key not set -- skipping verdict")
        return {
            "narrative": "AI verdict unavailable — Anthropic API key not configured.",
            "regime": "MIXED",
            "signal_balance": indicators_data.get("signal_balance", {}),
            "generated_at": datetime.utcnow().isoformat(),
            "cached": False,
        }

    balance = indicators_data.get("signal_balance", {})
    groups = indicators_data.get("groups", {})

    summary_lines = []
    for gk, gv in groups.items():
        summary_lines.append(f"\n## {gv['label']}")
        for ind in gv["indicators"]:
            if ind.get("available"):
                summary_lines.append(
                    f"- {ind['name']}: {ind['display_value']} ({ind['signal']})"
                )

    prompt = (
        "You are a macro strategist at a top hedge fund. Analyze the following "
        "macro indicators and provide a concise verdict.\n\n"
        f"Signal balance: {balance.get('hawkish',0)} hawkish, "
        f"{balance.get('dovish',0)} dovish, {balance.get('neutral',0)} neutral\n"
        + "\n".join(summary_lines)
        + "\n\nProvide:\n1. One-line verdict (bullish/bearish/neutral + conviction)\n"
        "2. Key risks (2-3 bullets)\n3. Positioning suggestion (2-3 bullets)\n"
        "Keep it under 200 words. Be direct."
    )

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )

    verdict_text = response.content[0].text
    regime = (
        "HAWKISH"
        if balance.get("hawkish", 0) > balance.get("dovish", 0)
        else (
            "DOVISH"
            if balance.get("dovish", 0) > balance.get("hawkish", 0)
            else "MIXED"
        )
    )
    result = {
        "narrative": verdict_text,
        "regime": regime,
        "signal_balance": balance,
        "generated_at": datetime.utcnow().isoformat(),
        "cached": False,
    }

    # Cache the verdict
    try:
        verdict_json = json.dumps(result)
        with get_db_write() as conn:
            conn.execute("DELETE FROM macro_ai_verdicts WHERE id = 1")
            conn.execute(
                "INSERT INTO macro_ai_verdicts (id, verdict_json, created_at) "
                "VALUES (1, ?, ?)",
                [verdict_json, datetime.utcnow()],
            )
    except Exception as e:
        logger.error(f"Failed to cache verdict: {e}")

    return result
