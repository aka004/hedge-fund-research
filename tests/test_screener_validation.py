"""Validation of screener request fields against an allowlist of column names.

These tests prevent SQL injection via the `field` parameter on `Filter` and
`SortConfig` (CVE-style finding from 2026-05-13 code review). Both fields are
interpolated directly into a DuckDB WHERE/ORDER BY clause inside
`backend/app/api/screener.py`, so unvalidated input would be a direct injection
vector.
"""

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend"))

from app.models.schemas import Filter, ScreenerRequest, SortConfig


class TestFilterFieldAllowlist:
    def test_valid_field_accepted(self):
        f = Filter(field="market_cap", operator="gt", value=1_000_000)
        assert f.field == "market_cap"

    def test_unknown_field_rejected(self):
        with pytest.raises(ValidationError):
            Filter(field="not_a_real_column", operator="eq", value=1)

    def test_sql_injection_rejected(self):
        with pytest.raises(ValidationError):
            Filter(field="ticker; DROP TABLE prices--", operator="eq", value="x")

    def test_subquery_injection_rejected(self):
        with pytest.raises(ValidationError):
            Filter(
                field="(SELECT password FROM users)",
                operator="eq",
                value="x",
            )


class TestSortFieldAllowlist:
    def test_valid_field_accepted(self):
        s = SortConfig(field="market_cap", direction="desc")
        assert s.field == "market_cap"

    def test_unknown_field_rejected(self):
        with pytest.raises(ValidationError):
            SortConfig(field="not_a_real_column", direction="asc")

    def test_sql_injection_in_field_rejected(self):
        with pytest.raises(ValidationError):
            SortConfig(field="market_cap; DROP TABLE--", direction="asc")

    def test_invalid_direction_rejected(self):
        with pytest.raises(ValidationError):
            SortConfig(field="market_cap", direction="asc; DROP TABLE--")


class TestScreenerRequestEndToEnd:
    def test_well_formed_request_accepted(self):
        r = ScreenerRequest(
            filters=[Filter(field="market_cap", operator="gt", value=1e9)],
            sort=SortConfig(field="market_cap", direction="desc"),
            page=1,
            page_size=20,
        )
        assert r.filters[0].field == "market_cap"
        assert r.sort.field == "market_cap"

    def test_injected_filter_field_rejected(self):
        with pytest.raises(ValidationError):
            ScreenerRequest(
                filters=[Filter(field="1=1 OR 1=1", operator="eq", value=1)],
            )
