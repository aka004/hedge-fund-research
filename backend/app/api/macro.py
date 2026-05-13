"""Macro Intelligence Dashboard API endpoints."""

import logging

from fastapi import APIRouter, HTTPException, Query

from app.services.macro_service import (
    generate_ai_verdict,
    get_all_indicators_data,
    get_cached_verdict,
    get_indicator_history,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/macro", tags=["macro"])


# Handlers are intentionally `def`, not `async def`. The service layer
# uses synchronous FRED / yfinance HTTP calls, DuckDB I/O, and the
# Anthropic SDK — all blocking. Declaring them `async def` would freeze
# the FastAPI event loop for seconds at a time; with plain `def` FastAPI
# auto-routes the work onto its threadpool.


@router.get("/indicators")
def get_indicators():
    """Get all macro indicators with current values and signals."""
    try:
        return get_all_indicators_data()  # ensure_tables() called inside
    except Exception:
        logger.exception("Failed to fetch macro indicators")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/history/{indicator_id}")
def get_history(
    indicator_id: str,
    range: str = Query(default="2Y", regex="^(1Y|2Y|5Y|MAX)$"),
):
    """Get historical data for a specific indicator."""
    try:
        data = get_indicator_history(indicator_id, range)
        if data is None:
            raise HTTPException(
                status_code=404, detail=f"Indicator {indicator_id} not found"
            )
        return data
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to fetch history for %s", indicator_id)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/verdict")
def get_verdict(refresh: bool = Query(default=False)):
    """Get AI-generated macro verdict."""
    try:
        if not refresh:
            cached = get_cached_verdict()
            if cached:
                return cached
        indicators = get_all_indicators_data()
        return generate_ai_verdict(indicators)
    except Exception:
        logger.exception("Failed to generate verdict")
        raise HTTPException(status_code=500, detail="Internal server error")
