"""Verify backend 500 responses don't leak internal error details.

Closes the HIGH finding from the 2026-05-13 code review: every handler
was doing `raise HTTPException(500, detail=str(e))`, which echoes raw
exception text — including potential API key fragments from
`get_anthropic_api_key()` failures, DuckDB schema details, or
filesystem paths — back to the caller.
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import HTTPException

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend"))

SECRET_LIKE_MESSAGE = (
    "leaked secret: sk-ant-api03-xyz123 in /Volumes/Data_2026/db.duckdb"
)


def _assert_no_leak(detail: str | None) -> None:
    text = str(detail or "").lower()
    for needle in ("secret", "sk-ant", "xyz123", "/volumes", "duckdb"):
        assert (
            needle not in text
        ), f"500 response detail leaks internal info ({needle!r} present): {detail!r}"


class TestMacroEndpointsHideInternalErrors:
    def test_get_indicators_500_is_generic(self):
        from app.api.macro import get_indicators

        with patch("app.api.macro.get_all_indicators_data") as mock_svc:
            mock_svc.side_effect = ValueError(SECRET_LIKE_MESSAGE)
            with pytest.raises(HTTPException) as exc_info:
                get_indicators()

        assert exc_info.value.status_code == 500
        _assert_no_leak(exc_info.value.detail)

    def test_get_history_500_is_generic(self):
        from app.api.macro import get_history

        with patch("app.api.macro.get_indicator_history") as mock_svc:
            mock_svc.side_effect = ValueError(SECRET_LIKE_MESSAGE)
            with pytest.raises(HTTPException) as exc_info:
                get_history(indicator_id="cpi", range="2Y")

        assert exc_info.value.status_code == 500
        _assert_no_leak(exc_info.value.detail)

    def test_get_verdict_500_is_generic(self):
        from app.api.macro import get_verdict

        with patch("app.api.macro.get_cached_verdict") as mock_svc:
            mock_svc.side_effect = ValueError(SECRET_LIKE_MESSAGE)
            with pytest.raises(HTTPException) as exc_info:
                get_verdict(refresh=False)

        assert exc_info.value.status_code == 500
        _assert_no_leak(exc_info.value.detail)


class TestScreenerEndpointHidesInternalErrors:
    def test_screen_stocks_500_is_generic(self):
        from app.api.screener import screen_stocks
        from app.models.schemas import ScreenerRequest

        with patch("app.api.screener.get_db") as mock_db:
            mock_db.side_effect = RuntimeError(SECRET_LIKE_MESSAGE)
            req = ScreenerRequest(filters=[], page=1, page_size=20)
            with pytest.raises(HTTPException) as exc_info:
                # screen_stocks is async; call its underlying sync body
                # by invoking via asyncio.run for a clean test.
                import asyncio

                asyncio.run(screen_stocks(req))

        assert exc_info.value.status_code == 500
        _assert_no_leak(exc_info.value.detail)


class TestStockEndpointHidesInternalErrors:
    def test_get_stock_detail_500_is_generic(self):
        from app.api.stock import get_stock_detail

        with patch("app.api.stock.get_db") as mock_db:
            mock_db.side_effect = RuntimeError(SECRET_LIKE_MESSAGE)
            import asyncio

            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(get_stock_detail(ticker="AAPL"))

        assert exc_info.value.status_code == 500
        _assert_no_leak(exc_info.value.detail)
