"""
Pydantic models for API requests and responses.
"""

from typing import Optional, List, Any
from pydantic import BaseModel, Field
from datetime import date


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


class SortConfig(BaseModel):
    field: str
    direction: str = Field(default="desc", pattern="^(asc|desc)$")


# ============================================================
# Stock Models
# ============================================================

class StockSummary(BaseModel):
    ticker: str
    name: str
    sector: Optional[str] = None
    industry: Optional[str] = None
    exchange: Optional[str] = None
    market_cap: Optional[float] = None
    price: Optional[float] = None
    price_date: Optional[date] = None
    price_change: Optional[float] = None
    price_change_pct: Optional[float] = None
    volume: Optional[int] = None
    pe_ratio: Optional[float] = None
    forward_pe: Optional[float] = None
    peg_ratio: Optional[float] = None
    pb_ratio: Optional[float] = None
    ps_ratio: Optional[float] = None
    roe: Optional[float] = None
    roa: Optional[float] = None
    gross_margin: Optional[float] = None
    operating_margin: Optional[float] = None
    net_margin: Optional[float] = None
    revenue_growth_yoy: Optional[float] = None
    earnings_growth_yoy: Optional[float] = None
    debt_equity: Optional[float] = None
    current_ratio: Optional[float] = None
    dividend_yield: Optional[float] = None
    payout_ratio: Optional[float] = None
    rsi_14: Optional[float] = None
    beta: Optional[float] = None
    sma_20: Optional[float] = None
    sma_50: Optional[float] = None
    sma_200: Optional[float] = None
    distance_52w_high: Optional[float] = None
    distance_52w_low: Optional[float] = None


class CompanyInfo(BaseModel):
    ticker: str
    name: str
    sector: Optional[str] = None
    industry: Optional[str] = None
    exchange: Optional[str] = None
    market_cap: Optional[float] = None
    country: Optional[str] = None
    employees: Optional[int] = None
    description: Optional[str] = None
    website: Optional[str] = None


class Fundamentals(BaseModel):
    pe_ratio: Optional[float] = None
    forward_pe: Optional[float] = None
    peg_ratio: Optional[float] = None
    pb_ratio: Optional[float] = None
    ps_ratio: Optional[float] = None
    ev_ebitda: Optional[float] = None
    roe: Optional[float] = None
    roa: Optional[float] = None
    roic: Optional[float] = None
    gross_margin: Optional[float] = None
    operating_margin: Optional[float] = None
    net_margin: Optional[float] = None
    revenue_growth_yoy: Optional[float] = None
    revenue_growth_qoq: Optional[float] = None
    earnings_growth_yoy: Optional[float] = None
    debt_equity: Optional[float] = None
    current_ratio: Optional[float] = None
    quick_ratio: Optional[float] = None
    dividend_yield: Optional[float] = None
    payout_ratio: Optional[float] = None


class Technicals(BaseModel):
    sma_20: Optional[float] = None
    sma_50: Optional[float] = None
    sma_200: Optional[float] = None
    rsi_14: Optional[float] = None
    macd: Optional[float] = None
    beta: Optional[float] = None
    atr_14: Optional[float] = None
    distance_52w_high: Optional[float] = None
    distance_52w_low: Optional[float] = None


class PricePoint(BaseModel):
    date: date
    close: float
    volume: int


class StockDetail(BaseModel):
    company: CompanyInfo
    price: Optional[float] = None
    price_change: Optional[float] = None
    price_change_pct: Optional[float] = None
    fundamentals: Fundamentals
    technicals: Technicals
    price_history: List[PricePoint] = []


# ============================================================
# Request/Response Models
# ============================================================

class ScreenerRequest(BaseModel):
    filters: List[Filter] = []
    sort: Optional[SortConfig] = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    search: Optional[str] = None


class ScreenerResponse(BaseModel):
    total: int
    page: int
    page_size: int
    data: List[StockSummary]


class HealthResponse(BaseModel):
    status: str
    version: str = "1.0.0"
