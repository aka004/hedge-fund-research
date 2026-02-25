"""
Dashboard API endpoints for AFML Research Dashboard.
"""

import json
import math

from fastapi import APIRouter, HTTPException, Query

from app.core.database import get_db
from app.models.dashboard_schemas import (
    BootstrapComparison,
    BootstrapComparisonResponse,
    CVPath,
    CVPathsResponse,
    DashboardOverview,
    EquityCurveResponse,
    EquityPoint,
    FactorsResponse,
    FeatureImportance,
    FeatureImportanceResponse,
    Holding,
    HoldingsResponse,
    HRPWeightEntry,
    HRPWeightsResponse,
    KellyPipelineResponse,
    KellySizingStep,
    RegimeHistoryResponse,
    RegimePoint,
    RiskMetrics,
    RunsResponse,
    RunSummary,
    TradeLogEntry,
    TradeLogResponse,
    TradeLogSummary,
    ValidationCheck,
    ValidationChecklistResponse,
)
from app.services.mock_data import get_mock_factors

router = APIRouter(prefix="/api", tags=["dashboard"])


def _clean(val):
    """Return None for NaN/Inf, otherwise the value."""
    if val is None:
        return None
    if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
        return None
    return val


def _resolve_run_id(run_id: str | None) -> str:
    """Get explicit run_id or latest."""
    if run_id:
        return run_id
    with get_db() as conn:
        row = conn.execute(
            "SELECT run_id FROM derived_backtest_runs "
            "ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="No backtest runs found")
    return row[0]


# ------------------------------------------------------------------
# GET /api/dashboard/overview
# ------------------------------------------------------------------


@router.get("/dashboard/overview", response_model=DashboardOverview)
async def dashboard_overview(run_id: str = Query(None)):
    rid = _resolve_run_id(run_id)

    with get_db() as conn:
        run = conn.execute(
            "SELECT * FROM derived_backtest_runs WHERE run_id = $1", [rid]
        ).fetchdf()
        if run.empty:
            raise HTTPException(status_code=404, detail=f"Run {rid} not found")
        r = run.to_dict("records")[0]

        # Max and current drawdown from equity curve
        eq = conn.execute(
            "SELECT drawdown, daily_return FROM derived_backtest_equity "
            "WHERE run_id = $1 ORDER BY date",
            [rid],
        ).fetchdf()

        max_dd = float(eq["drawdown"].min()) if not eq.empty else 0.0
        current_dd = float(eq["drawdown"].iloc[-1]) if not eq.empty else 0.0

        # Win rate from daily returns
        if not eq.empty:
            returns = eq["daily_return"].dropna()
            win_rate = (
                float((returns > 0).sum() / len(returns)) if len(returns) > 0 else 0.0
            )
        else:
            win_rate = 0.0

        # Current regime
        regime_row = conn.execute(
            "SELECT regime FROM derived_regime_history " "ORDER BY date DESC LIMIT 1"
        ).fetchone()
        regime = regime_row[0] if regime_row else "neutral"

        # NAV and PnL from equity curve
        if not eq.empty:
            eq_vals = conn.execute(
                "SELECT equity FROM derived_backtest_equity "
                "WHERE run_id = $1 ORDER BY date",
                [rid],
            ).fetchdf()
            nav = float(eq_vals["equity"].iloc[-1])
            initial = float(eq_vals["equity"].iloc[0])
            total_pnl = nav - initial
            total_pnl_pct = (total_pnl / initial * 100) if initial != 0 else 0.0
        else:
            nav, total_pnl, total_pnl_pct = 0.0, 0.0, 0.0

    return DashboardOverview(
        run_id=rid,
        strategy_name=r.get("strategy_name", ""),
        nav=nav,
        total_pnl=total_pnl,
        total_pnl_pct=total_pnl_pct,
        sharpe_raw=_clean(r.get("sharpe_raw")) or 0.0,
        psr=_clean(r.get("psr")) or 0.0,
        deflated_sharpe=_clean(r.get("deflated_sharpe")) or 0.0,
        max_drawdown=max_dd,
        current_drawdown=current_dd,
        win_rate=win_rate,
        regime=regime,
        created_at=str(r.get("created_at", "")),
        is_mock=bool(r.get("is_mock", False)),
    )


# ------------------------------------------------------------------
# GET /api/dashboard/equity-curve
# ------------------------------------------------------------------


@router.get("/dashboard/equity-curve", response_model=EquityCurveResponse)
async def equity_curve(run_id: str = Query(None)):
    rid = _resolve_run_id(run_id)
    with get_db() as conn:
        rows = conn.execute(
            "SELECT date, equity, benchmark_equity, drawdown, daily_return "
            "FROM derived_backtest_equity WHERE run_id = $1 ORDER BY date",
            [rid],
        ).fetchdf()
    if rows.empty:
        raise HTTPException(status_code=404, detail=f"No equity data for run {rid}")

    data = [
        EquityPoint(
            date=str(row["date"]),
            equity=float(row["equity"]),
            benchmark_equity=float(row["benchmark_equity"]),
            drawdown=float(row["drawdown"]),
            daily_return=float(row["daily_return"]),
        )
        for _, row in rows.iterrows()
    ]
    return EquityCurveResponse(run_id=rid, data=data)


# ------------------------------------------------------------------
# GET /api/dashboard/holdings
# ------------------------------------------------------------------


@router.get("/dashboard/holdings", response_model=HoldingsResponse)
async def holdings(run_id: str = Query(None)):
    rid = _resolve_run_id(run_id)
    with get_db() as conn:
        rows = conn.execute(
            "SELECT date, ticker, weight, hrp_weight, kelly_fraction, "
            "signal_source, is_mock "
            "FROM derived_portfolio_weights "
            "WHERE run_id = $1 AND date = ("
            "  SELECT MAX(date) FROM derived_portfolio_weights WHERE run_id = $1"
            ") ORDER BY weight DESC",
            [rid],
        ).fetchdf()
    if rows.empty:
        raise HTTPException(status_code=404, detail=f"No holdings for run {rid}")

    latest_date = str(rows["date"].iloc[0])
    items = [
        Holding(
            ticker=row["ticker"],
            weight=float(row["weight"]),
            hrp_weight=float(row.get("hrp_weight") or 0.0),
            kelly_fraction=float(row.get("kelly_fraction") or 0.0),
            signal_source=row.get("signal_source") or "",
            is_mock=bool(row.get("is_mock", False)),
        )
        for _, row in rows.iterrows()
    ]
    return HoldingsResponse(run_id=rid, date=latest_date, holdings=items)


# ------------------------------------------------------------------
# GET /api/dashboard/factors (mock - AlphaGPT deferred)
# ------------------------------------------------------------------


@router.get("/dashboard/factors", response_model=FactorsResponse)
async def factors():
    return get_mock_factors()


# ------------------------------------------------------------------
# GET /api/dashboard/feature-importance
# ------------------------------------------------------------------


@router.get("/dashboard/feature-importance", response_model=FeatureImportanceResponse)
async def feature_importance(run_id: str = Query(None)):
    rid = _resolve_run_id(run_id)
    with get_db() as conn:
        row = conn.execute(
            "SELECT metric_value, details, is_mock FROM derived_afml_metrics "
            "WHERE run_id = $1 AND metric_name = 'mda_importance'",
            [rid],
        ).fetchone()
    if not row:
        raise HTTPException(
            status_code=404, detail=f"No feature importance for run {rid}"
        )

    details_raw = row[1]
    is_mock = bool(row[2]) if row[2] is not None else False
    features = []
    if details_raw:
        details = (
            json.loads(details_raw) if isinstance(details_raw, str) else details_raw
        )
        if isinstance(details, dict):
            for name, imp in details.items():
                features.append(
                    FeatureImportance(
                        feature_name=name,
                        importance=float(imp),
                        is_mock=is_mock,
                    )
                )
    features.sort(key=lambda f: f.importance, reverse=True)
    return FeatureImportanceResponse(run_id=rid, features=features, is_mock=is_mock)


# ------------------------------------------------------------------
# GET /api/dashboard/cv-paths
# ------------------------------------------------------------------


@router.get("/dashboard/cv-paths", response_model=CVPathsResponse)
async def cv_paths(run_id: str = Query(None)):
    rid = _resolve_run_id(run_id)
    with get_db() as conn:
        rows = conn.execute(
            "SELECT path_id, day_index, equity "
            "FROM derived_cv_paths WHERE run_id = $1 "
            "ORDER BY path_id, day_index",
            [rid],
        ).fetchdf()
        run_row = conn.execute(
            "SELECT pbo, is_mock FROM derived_backtest_runs WHERE run_id = $1",
            [rid],
        ).fetchone()
    if rows.empty:
        raise HTTPException(status_code=404, detail=f"No CV paths for run {rid}")

    pbo = float(run_row[0]) if run_row and run_row[0] is not None else 0.0
    is_mock = bool(run_row[1]) if run_row and run_row[1] is not None else False

    paths_dict: dict[int, list[float]] = {}
    for _, row in rows.iterrows():
        pid = int(row["path_id"])
        paths_dict.setdefault(pid, []).append(float(row["equity"]))

    paths = [
        CVPath(path_id=pid, equity_curve=curve)
        for pid, curve in sorted(paths_dict.items())
    ]
    return CVPathsResponse(
        run_id=rid, n_paths=len(paths), pbo=pbo, paths=paths, is_mock=is_mock
    )


# ------------------------------------------------------------------
# GET /api/dashboard/validation-checklist
# ------------------------------------------------------------------


@router.get(
    "/dashboard/validation-checklist", response_model=ValidationChecklistResponse
)
async def validation_checklist(run_id: str = Query(None)):
    rid = _resolve_run_id(run_id)
    with get_db() as conn:
        run = conn.execute(
            "SELECT psr, deflated_sharpe, pbo, is_mock "
            "FROM derived_backtest_runs WHERE run_id = $1",
            [rid],
        ).fetchone()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {rid} not found")

    psr_val = _clean(run[0])
    ds_val = _clean(run[1])
    pbo_val = _clean(run[2])
    is_mock = bool(run[3]) if run[3] is not None else False

    checks = [
        ValidationCheck(
            check="PSR > 0.95",
            passed=psr_val is not None and psr_val > 0.95,
            detail=f"PSR = {psr_val:.4f}" if psr_val is not None else "Not computed",
        ),
        ValidationCheck(
            check="Deflated Sharpe > 0",
            passed=ds_val is not None and ds_val > 0,
            detail=f"DS = {ds_val:.4f}" if ds_val is not None else "Not computed",
        ),
        ValidationCheck(
            check="PBO < 0.5",
            passed=pbo_val is not None and pbo_val < 0.5,
            detail=f"PBO = {pbo_val:.4f}" if pbo_val is not None else "Not computed",
        ),
    ]
    return ValidationChecklistResponse(run_id=rid, checks=checks, is_mock=is_mock)


# ------------------------------------------------------------------
# GET /api/dashboard/bootstrap-comparison
# ------------------------------------------------------------------


@router.get(
    "/dashboard/bootstrap-comparison",
    response_model=BootstrapComparisonResponse,
)
async def bootstrap_comparison(run_id: str = Query(None)):
    rid = _resolve_run_id(run_id)
    with get_db() as conn:
        rows = conn.execute(
            "SELECT metric_name, metric_value, is_mock FROM derived_afml_metrics "
            "WHERE run_id = $1 AND metric_name LIKE 'bootstrap_%'",
            [rid],
        ).fetchdf()
    is_mock = False
    comparisons = []
    for _, row in rows.iterrows():
        method = str(row["metric_name"]).replace("bootstrap_", "")
        comparisons.append(
            BootstrapComparison(
                method=method, uniqueness=float(row["metric_value"] or 0)
            )
        )
        if row.get("is_mock"):
            is_mock = True
    return BootstrapComparisonResponse(
        run_id=rid, comparisons=comparisons, is_mock=is_mock
    )


# ------------------------------------------------------------------
# GET /api/dashboard/risk-metrics
# ------------------------------------------------------------------


@router.get("/dashboard/risk-metrics", response_model=RiskMetrics)
async def risk_metrics(run_id: str = Query(None)):
    rid = _resolve_run_id(run_id)
    with get_db() as conn:
        run = conn.execute(
            "SELECT sharpe_raw, is_mock FROM derived_backtest_runs WHERE run_id = $1",
            [rid],
        ).fetchone()
        if not run:
            raise HTTPException(status_code=404, detail=f"Run {rid} not found")

        eq = conn.execute(
            "SELECT equity, drawdown, daily_return FROM derived_backtest_equity "
            "WHERE run_id = $1 ORDER BY date",
            [rid],
        ).fetchdf()

        trades = conn.execute(
            "SELECT side, price, shares FROM derived_backtest_trades "
            "WHERE run_id = $1",
            [rid],
        ).fetchdf()

        weights = conn.execute(
            "SELECT ticker, weight FROM derived_portfolio_weights "
            "WHERE run_id = $1 AND date = ("
            "  SELECT MAX(date) FROM derived_portfolio_weights WHERE run_id = $1"
            ")",
            [rid],
        ).fetchdf()

    sharpe = _clean(run[0]) or 0.0
    is_mock = bool(run[1]) if run[1] is not None else False

    if not eq.empty:
        returns = eq["daily_return"].dropna()
        neg_returns = returns[returns < 0]
        downside_std = float(neg_returns.std()) if len(neg_returns) > 0 else 1.0
        sortino = (
            (float(returns.mean()) / downside_std * (252**0.5))
            if downside_std != 0
            else 0.0
        )
        max_dd = float(eq["drawdown"].min())
        current_dd = float(eq["drawdown"].iloc[-1])
        annual_return = float(returns.mean()) * 252
        calmar = (annual_return / abs(max_dd)) if max_dd != 0 else 0.0
        win_rate = (
            float((returns > 0).sum() / len(returns)) if len(returns) > 0 else 0.0
        )
    else:
        sortino, max_dd, current_dd, calmar, win_rate = 0.0, 0.0, 0.0, 0.0, 0.0

    # Profit factor from trades
    if not trades.empty:
        buy_trades = trades[trades["side"] == "buy"]
        sell_trades = trades[trades["side"] == "sell"]
        gross_profit = (
            float((sell_trades["price"] * sell_trades["shares"]).sum())
            if not sell_trades.empty
            else 0.0
        )
        gross_loss = (
            float((buy_trades["price"] * buy_trades["shares"]).sum())
            if not buy_trades.empty
            else 1.0
        )
        profit_factor = gross_profit / gross_loss if gross_loss != 0 else 0.0
    else:
        profit_factor = 0.0

    # Turnover from weights
    turnover = float(weights["weight"].sum()) if not weights.empty else 0.0

    return RiskMetrics(
        run_id=rid,
        sharpe=sharpe,
        sortino=sortino,
        max_drawdown=max_dd,
        current_drawdown=current_dd,
        beta=0.0,  # Requires benchmark correlation - computed if available
        alpha=0.0,  # Requires benchmark - computed if available
        calmar=calmar,
        profit_factor=profit_factor,
        win_rate=win_rate,
        turnover=turnover,
        is_mock=is_mock,
    )


# ------------------------------------------------------------------
# GET /api/dashboard/hrp-weights
# ------------------------------------------------------------------


@router.get("/dashboard/hrp-weights", response_model=HRPWeightsResponse)
async def hrp_weights(run_id: str = Query(None)):
    rid = _resolve_run_id(run_id)
    with get_db() as conn:
        rows = conn.execute(
            "SELECT ticker, hrp_weight, weight "
            "FROM derived_portfolio_weights "
            "WHERE run_id = $1 AND date = ("
            "  SELECT MAX(date) FROM derived_portfolio_weights WHERE run_id = $1"
            ") ORDER BY hrp_weight DESC",
            [rid],
        ).fetchdf()
    if rows.empty:
        raise HTTPException(status_code=404, detail=f"No HRP weights for run {rid}")

    weights = [
        HRPWeightEntry(
            ticker=row["ticker"],
            hrp_weight=float(row.get("hrp_weight") or 0.0),
            actual_weight=float(row["weight"]),
        )
        for _, row in rows.iterrows()
    ]
    return HRPWeightsResponse(run_id=rid, weights=weights)


# ------------------------------------------------------------------
# GET /api/dashboard/regime-history
# ------------------------------------------------------------------


@router.get("/dashboard/regime-history", response_model=RegimeHistoryResponse)
async def regime_history():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT date, regime, ma_200, price, distance_pct, "
            "cusum_value, days_in_regime "
            "FROM derived_regime_history ORDER BY date"
        ).fetchdf()
    data = [
        RegimePoint(
            date=str(row["date"]),
            regime=row["regime"],
            ma_200=_clean(row.get("ma_200")),
            price=_clean(row.get("price")),
            distance_pct=_clean(row.get("distance_pct")),
            cusum_value=_clean(row.get("cusum_value")),
            days_in_regime=(
                int(row["days_in_regime"])
                if row.get("days_in_regime") is not None
                else None
            ),
        )
        for _, row in rows.iterrows()
    ]
    return RegimeHistoryResponse(data=data)


# ------------------------------------------------------------------
# GET /api/dashboard/kelly-pipeline
# ------------------------------------------------------------------


@router.get("/dashboard/kelly-pipeline", response_model=KellyPipelineResponse)
async def kelly_pipeline(run_id: str = Query(None), ticker: str = Query(...)):
    rid = _resolve_run_id(run_id)
    with get_db() as conn:
        weight_row = conn.execute(
            "SELECT weight, hrp_weight, kelly_fraction "
            "FROM derived_portfolio_weights "
            "WHERE run_id = $1 AND ticker = $2 AND date = ("
            "  SELECT MAX(date) FROM derived_portfolio_weights "
            "  WHERE run_id = $1 AND ticker = $2"
            ")",
            [rid, ticker],
        ).fetchone()
        if not weight_row:
            raise HTTPException(
                status_code=404, detail=f"No weight data for {ticker} in run {rid}"
            )

    actual_weight = float(weight_row[0] or 0)
    hrp_weight = float(weight_row[1] or 0)
    kelly_fraction = float(weight_row[2] or 0)

    # Build the 6-step Kelly sizing pipeline
    steps = [
        KellySizingStep(
            step="1. Raw Kelly fraction", value=kelly_fraction, ticker=ticker
        ),
        KellySizingStep(
            step="2. Half-Kelly (conservative)",
            value=kelly_fraction * 0.5,
            ticker=ticker,
        ),
        KellySizingStep(step="3. HRP weight", value=hrp_weight, ticker=ticker),
        KellySizingStep(step="4. Signal-adjusted", value=actual_weight, ticker=ticker),
        KellySizingStep(
            step="5. Risk-budget cap", value=min(actual_weight, 0.10), ticker=ticker
        ),
        KellySizingStep(
            step="6. Final position size", value=actual_weight, ticker=ticker
        ),
    ]

    return KellyPipelineResponse(run_id=rid, ticker=ticker, steps=steps)


# ------------------------------------------------------------------
# GET /api/dashboard/runs
# ------------------------------------------------------------------


@router.get("/dashboard/runs", response_model=RunsResponse)
async def list_runs():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT run_id, strategy_name, created_at, sharpe_raw, psr "
            "FROM derived_backtest_runs ORDER BY created_at DESC"
        ).fetchdf()
    runs = [
        RunSummary(
            run_id=row["run_id"],
            strategy_name=row["strategy_name"],
            created_at=str(row["created_at"]),
            sharpe_raw=_clean(row.get("sharpe_raw")) or 0.0,
            psr=_clean(row.get("psr")) or 0.0,
        )
        for _, row in rows.iterrows()
    ]
    return RunsResponse(runs=runs)


# ------------------------------------------------------------------
# GET /api/dashboard/trade-log
# ------------------------------------------------------------------


@router.get("/dashboard/trade-log", response_model=TradeLogResponse)
async def trade_log(run_id: str = Query(None)):
    rid = _resolve_run_id(run_id)
    with get_db() as conn:
        rows = conn.execute(
            "SELECT symbol, entry_date, entry_price, entry_reason, "
            "exit_date, exit_price, exit_reason, shares, "
            "pnl, return_pct, holding_days, max_favorable, max_adverse "
            "FROM derived_round_trip_trades WHERE run_id = $1 "
            "ORDER BY exit_date DESC",
            [rid],
        ).fetchdf()

    if rows.empty:
        return TradeLogResponse(
            run_id=rid,
            trades=[],
            summary=TradeLogSummary(
                total_trades=0,
                win_rate=0.0,
                profit_factor=0.0,
                avg_holding_days=0.0,
                exit_breakdown={},
            ),
            is_mock=False,
        )

    trades = [
        TradeLogEntry(
            symbol=row["symbol"],
            entry_date=str(row["entry_date"]),
            entry_price=float(row["entry_price"]),
            entry_reason=row["entry_reason"],
            exit_date=str(row["exit_date"]),
            exit_price=float(row["exit_price"]),
            exit_reason=row["exit_reason"],
            shares=float(row["shares"]),
            pnl=float(row["pnl"]),
            return_pct=float(row["return_pct"]),
            holding_days=int(row["holding_days"]),
            max_favorable=float(row["max_favorable"]),
            max_adverse=float(row["max_adverse"]),
        )
        for _, row in rows.iterrows()
    ]

    # Build summary
    n = len(rows)
    winners = rows[rows["pnl"] > 0]
    losers = rows[rows["pnl"] < 0]

    win_rate = len(winners) / n if n > 0 else 0.0
    gross_wins = float(winners["pnl"].sum()) if len(winners) > 0 else 0.0
    gross_losses = abs(float(losers["pnl"].sum())) if len(losers) > 0 else 0.0
    profit_factor = gross_wins / gross_losses if gross_losses > 0 else 0.0

    avg_holding = float(rows["holding_days"].mean()) if n > 0 else 0.0

    exit_counts = rows["exit_reason"].value_counts()
    exit_breakdown = (exit_counts / n).to_dict() if n > 0 else {}

    summary = TradeLogSummary(
        total_trades=n,
        win_rate=win_rate,
        profit_factor=profit_factor,
        avg_holding_days=avg_holding,
        exit_breakdown=exit_breakdown,
    )

    return TradeLogResponse(run_id=rid, trades=trades, summary=summary, is_mock=False)
