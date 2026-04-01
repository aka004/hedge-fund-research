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


@router.get("/indicators")
async def get_indicators():
    """Get all macro indicators with current values and signals."""
    try:
        return get_all_indicators_data()  # ensure_tables() called inside
    except Exception as e:
        logger.error(f"Failed to fetch macro indicators: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history/{indicator_id}")
async def get_history(
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
    except Exception as e:
        logger.error(f"Failed to fetch history for {indicator_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/verdict")
async def get_verdict(refresh: bool = Query(default=False)):
    """Get AI-generated macro verdict."""
    try:
        if not refresh:
            cached = get_cached_verdict()
            if cached:
                return cached
        indicators = get_all_indicators_data()
        return generate_ai_verdict(indicators)
    except Exception as e:
        logger.error(f"Failed to generate verdict: {e}")
        raise HTTPException(status_code=500, detail=str(e))
