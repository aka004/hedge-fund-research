"""
Pydantic models for API requests and responses.
"""

from datetime import date
from typing import Any

from pydantic import BaseModel, Field, field_validator

# Columns exposed by the `screener_summary` DuckDB view. The screener
# endpoint interpolates `Filter.field` / `SortConfig.field` directly into
# WHERE / ORDER BY clauses, so anything outside this set must be rejected
# at the request layer to prevent SQL injection.
ALLOWED_SCREENER_FIELDS = frozenset(
    {
        "ticker",
        "name",
        "sector",
        "industry",
        "exchange",
        "market_cap",
        "price",
        "price_date",
        "price_change",
        "price_change_pct",
        "volume",
        "pe_ratio",
        "forward_pe",
        "peg_ratio",
        "pb_ratio",
        "ps_ratio",
        "roe",
        "roa",
        "gross_margin",
        "operating_margin",
        "net_margin",
        "revenue_growth_yoy",
        "earnings_growth_yoy",
        "debt_equity",
        "current_ratio",
        "dividend_yield",
        "payout_ratio",
        "sma_20",
        "sma_50",
        "sma_200",
        "rsi_14",
        "macd",
        "beta",
        "atr_14",
        "relative_volume",
        "distance_52w_high",
        "distance_52w_low",
    }
)


# ============================================================
# Filter Models
# ============================================================


class FilterOperator:
    EQ = "eq"
    NE = "ne"
    LT = "lt"
    GT = "gt"
    LTE = "lte"
    GTE = "gte"
    BETWEEN = "between"
    IN = "in"
    CONTAINS = "contains"


class Filter(BaseModel):
    field: str
    operator: str
    value: Any

    @field_validator("field")
    @classmethod
    def _field_must_be_allowlisted(cls, v: str) -> str:
        if v not in ALLOWED_SCREENER_FIELDS:
            raise ValueError(f"field must be one of the screener columns; got {v!r}")
        return v


class SortConfig(BaseModel):
    field: str
    direction: str = Field(default="desc", pattern="^(asc|desc)$")

    @field_validator("field")
    @classmethod
    def _field_must_be_allowlisted(cls, v: str) -> str:
        if v not in ALLOWED_SCREENER_FIELDS:
            raise ValueError(
                f"sort field must be one of the screener columns; got {v!r}"
            )
        return v


# ============================================================
# Stock Models
# ============================================================


class StockSummary(BaseModel):
    ticker: str
    name: str
    sector: str | None = None
    industry: str | None = None
    exchange: str | None = None
    market_cap: float | None = None
    price: float | None = None
    price_date: date | None = None
    price_change: float | None = None
    price_change_pct: float | None = None
    volume: int | None = None
    pe_ratio: float | None = None
    forward_pe: float | None = None
    peg_ratio: float | None = None
    pb_ratio: float | None = None
    ps_ratio: float | None = None
    roe: float | None = None
    roa: float | None = None
    gross_margin: float | None = None
    operating_margin: float | None = None
    net_margin: float | None = None
    revenue_growth_yoy: float | None = None
    earnings_growth_yoy: float | None = None
    debt_equity: float | None = None
    current_ratio: float | None = None
    dividend_yield: float | None = None
    payout_ratio: float | None = None
    sma_20: float | None = None
    sma_50: float | None = None
    sma_200: float | None = None
    rsi_14: float | None = None
    macd: float | None = None
    beta: float | None = None
    atr_14: float | None = None
    relative_volume: float | None = None
    distance_52w_high: float | None = None
    distance_52w_low: float | None = None


class CompanyInfo(BaseModel):
    ticker: str
    name: str
    sector: str | None = None
    industry: str | None = None
    exchange: str | None = None
    market_cap: float | None = None
    country: str | None = None
    employees: int | None = None
    description: str | None = None
    website: str | None = None


class Fundamentals(BaseModel):
    pe_ratio: float | None = None
    forward_pe: float | None = None
    peg_ratio: float | None = None
    pb_ratio: float | None = None
    ps_ratio: float | None = None
    ev_ebitda: float | None = None
    roe: float | None = None
    roa: float | None = None
    roic: float | None = None
    gross_margin: float | None = None
    operating_margin: float | None = None
    net_margin: float | None = None
    revenue_growth_yoy: float | None = None
    revenue_growth_qoq: float | None = None
    earnings_growth_yoy: float | None = None
    debt_equity: float | None = None
    current_ratio: float | None = None
    quick_ratio: float | None = None
    dividend_yield: float | None = None
    payout_ratio: float | None = None


class Technicals(BaseModel):
    sma_20: float | None = None
    sma_50: float | None = None
    sma_200: float | None = None
    rsi_14: float | None = None
    macd: float | None = None
    beta: float | None = None
    atr_14: float | None = None
    distance_52w_high: float | None = None
    distance_52w_low: float | None = None


class PricePoint(BaseModel):
    date: date
    close: float
    volume: int


class StockDetail(BaseModel):
    company: CompanyInfo
    price: float | None = None
    price_change: float | None = None
    price_change_pct: float | None = None
    fundamentals: Fundamentals
    technicals: Technicals
    price_history: list[PricePoint] = []


# ============================================================
# Request/Response Models
# ============================================================


class ScreenerRequest(BaseModel):
    filters: list[Filter] = []
    sort: SortConfig | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    search: str | None = None


class ScreenerResponse(BaseModel):
    total: int
    page: int
    page_size: int
    data: list[StockSummary]


class HealthResponse(BaseModel):
    status: str
    version: str = "1.0.0"
