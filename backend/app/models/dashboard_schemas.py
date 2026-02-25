"""
Pydantic response models for the AFML Research Dashboard.
"""

from pydantic import BaseModel

# ============================================================
# Dashboard Overview
# ============================================================


class DashboardOverview(BaseModel):
    run_id: str
    strategy_name: str
    nav: float
    total_pnl: float
    total_pnl_pct: float
    sharpe_raw: float
    psr: float
    deflated_sharpe: float
    max_drawdown: float
    current_drawdown: float
    win_rate: float
    regime: str  # "bull" | "bear" | "neutral"
    created_at: str
    is_mock: bool = False


# ============================================================
# Equity Curve
# ============================================================


class EquityPoint(BaseModel):
    date: str
    equity: float
    benchmark_equity: float
    drawdown: float
    daily_return: float


class EquityCurveResponse(BaseModel):
    run_id: str
    data: list[EquityPoint]
    is_mock: bool = False


# ============================================================
# Holdings
# ============================================================


class Holding(BaseModel):
    ticker: str
    weight: float
    hrp_weight: float
    kelly_fraction: float
    signal_source: str
    pnl: float | None = None
    pnl_pct: float | None = None
    meta_prob: float | None = None
    is_mock: bool = False


class HoldingsResponse(BaseModel):
    run_id: str
    date: str
    holdings: list[Holding]
    is_mock: bool = False


# ============================================================
# Discovered Factors (AlphaGPT - always mock)
# ============================================================


class DiscoveredFactor(BaseModel):
    id: int
    formula: str
    psr: float
    sharpe: float
    max_dd: float
    trades: int
    status: str  # "active" | "monitoring" | "rejected"
    is_mock: bool = True


class FactorsResponse(BaseModel):
    factors: list[DiscoveredFactor]
    is_mock: bool = True


# ============================================================
# Feature Importance
# ============================================================


class FeatureImportance(BaseModel):
    feature_name: str
    importance: float
    is_mock: bool = False


class FeatureImportanceResponse(BaseModel):
    run_id: str
    features: list[FeatureImportance]
    is_mock: bool = False


# ============================================================
# CV Paths (CPCV)
# ============================================================


class CVPath(BaseModel):
    path_id: int
    equity_curve: list[float]


class CVPathsResponse(BaseModel):
    run_id: str
    n_paths: int
    pbo: float
    paths: list[CVPath]
    is_mock: bool = False


# ============================================================
# Validation Checklist
# ============================================================


class ValidationCheck(BaseModel):
    check: str
    passed: bool
    detail: str | None = None


class ValidationChecklistResponse(BaseModel):
    run_id: str
    checks: list[ValidationCheck]
    is_mock: bool = False


# ============================================================
# Bootstrap Comparison
# ============================================================


class BootstrapComparison(BaseModel):
    method: str
    uniqueness: float


class BootstrapComparisonResponse(BaseModel):
    run_id: str
    comparisons: list[BootstrapComparison]
    is_mock: bool = False


# ============================================================
# Risk Metrics
# ============================================================


class RiskMetrics(BaseModel):
    run_id: str
    sharpe: float
    sortino: float
    max_drawdown: float
    current_drawdown: float
    beta: float
    alpha: float
    calmar: float
    profit_factor: float
    win_rate: float
    turnover: float
    is_mock: bool = False


# ============================================================
# HRP Weights
# ============================================================


class HRPWeightEntry(BaseModel):
    ticker: str
    hrp_weight: float
    actual_weight: float


class HRPWeightsResponse(BaseModel):
    run_id: str
    weights: list[HRPWeightEntry]
    is_mock: bool = False


# ============================================================
# Regime History
# ============================================================


class RegimePoint(BaseModel):
    date: str
    regime: str
    ma_200: float | None = None
    price: float | None = None
    distance_pct: float | None = None
    cusum_value: float | None = None
    days_in_regime: int | None = None


class RegimeHistoryResponse(BaseModel):
    data: list[RegimePoint]
    is_mock: bool = False


# ============================================================
# Kelly Pipeline
# ============================================================


class KellySizingStep(BaseModel):
    step: str
    value: float
    ticker: str


class KellyPipelineResponse(BaseModel):
    run_id: str
    ticker: str
    steps: list[KellySizingStep]
    is_mock: bool = False


# ============================================================
# Runs List
# ============================================================


class RunSummary(BaseModel):
    run_id: str
    strategy_name: str
    created_at: str
    sharpe_raw: float
    psr: float


class RunsResponse(BaseModel):
    runs: list[RunSummary]


# ============================================================
# Trade Log (Round-Trip Trades)
# ============================================================


class TradeLogEntry(BaseModel):
    symbol: str
    entry_date: str
    entry_price: float
    entry_reason: str
    exit_date: str
    exit_price: float
    exit_reason: str
    shares: float
    pnl: float
    return_pct: float
    holding_days: int
    max_favorable: float
    max_adverse: float


class TradeLogSummary(BaseModel):
    total_trades: int
    win_rate: float
    profit_factor: float
    avg_holding_days: float
    exit_breakdown: dict[str, float]


class TradeLogResponse(BaseModel):
    run_id: str
    trades: list[TradeLogEntry]
    summary: TradeLogSummary
    is_mock: bool = False
