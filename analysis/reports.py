"""Report generation for backtest results."""

from datetime import datetime
from pathlib import Path

import pandas as pd

from analysis.metrics import PerformanceMetrics
from analysis.obsidian_reports import (
    generate_backtest_report_obsidian,
    save_obsidian_note,
)
from strategy.backtest.engine import BacktestResult
from strategy.backtest.event_engine import EventEngineResult


def generate_summary_report(
    result: BacktestResult,
    metrics: PerformanceMetrics,
) -> str:
    """Generate a text summary report.

    Args:
        result: Backtest result
        metrics: Performance metrics

    Returns:
        Formatted text report
    """
    lines = [
        "=" * 60,
        "BACKTEST PERFORMANCE REPORT",
        "=" * 60,
        "",
        f"Period: {result.start_date} to {result.end_date}",
        f"Initial Capital: ${result.config.initial_capital:,.2f}",
        (
            f"Final Equity: ${result.equity_curve['equity'].iloc[-1]:,.2f}"
            if not result.equity_curve.empty
            else ""
        ),
        "",
        "-" * 40,
        "RETURNS",
        "-" * 40,
        f"Total Return: {metrics.total_return * 100:.2f}%",
        f"CAGR: {metrics.cagr * 100:.2f}%",
        f"Annualized Volatility: {metrics.annualized_volatility * 100:.2f}%",
        "",
        "-" * 40,
        "RISK-ADJUSTED METRICS",
        "-" * 40,
        f"Sharpe Ratio: {metrics.sharpe_ratio:.2f}",
        f"Sortino Ratio: {metrics.sortino_ratio:.2f}",
        f"Calmar Ratio: {metrics.calmar_ratio:.2f}",
        "",
        "-" * 40,
        "DRAWDOWN",
        "-" * 40,
        f"Max Drawdown: {metrics.max_drawdown * 100:.2f}%",
        f"Max Drawdown Duration: {metrics.max_drawdown_duration_days} days",
        "",
        "-" * 40,
        "TRADING STATISTICS",
        "-" * 40,
        f"Total Trades: {metrics.total_trades}",
        f"Win Rate: {metrics.win_rate * 100:.1f}%",
        f"Profit Factor: {metrics.profit_factor:.2f}",
        f"Average Win: ${metrics.avg_win:,.2f}",
        f"Average Loss: ${metrics.avg_loss:,.2f}",
        "",
        "-" * 40,
        "DISTRIBUTION",
        "-" * 40,
        f"Skewness: {metrics.skewness:.2f}",
        f"Kurtosis: {metrics.kurtosis:.2f}",
        "",
        "=" * 60,
    ]

    return "\n".join(lines)


def generate_trade_log(
    result: BacktestResult,
) -> pd.DataFrame:
    """Generate a trade log DataFrame.

    Args:
        result: Backtest result

    Returns:
        DataFrame with trade details
    """
    if not result.trades:
        return pd.DataFrame()

    trades_data = []
    for trade in result.trades:
        trades_data.append(
            {
                "date": trade.date,
                "symbol": trade.symbol,
                "side": trade.side,
                "shares": trade.shares,
                "price": trade.price,
                "gross_value": trade.gross_value,
                "commission": trade.commission,
                "slippage": trade.slippage,
                "net_value": trade.net_value,
            }
        )

    return pd.DataFrame(trades_data)


def generate_position_report(
    result: BacktestResult,
) -> pd.DataFrame:
    """Generate a report of position history.

    Args:
        result: Backtest result

    Returns:
        DataFrame with position weights over time
    """
    if not result.positions_history:
        return pd.DataFrame()

    rows = []
    for ph in result.positions_history:
        for symbol, weight in ph["positions"].items():
            rows.append(
                {
                    "date": ph["date"],
                    "symbol": symbol,
                    "weight": weight,
                }
            )

    return pd.DataFrame(rows)


def save_report_bundle(
    result: BacktestResult,
    metrics: PerformanceMetrics,
    output_dir: Path,
    prefix: str = "backtest",
) -> dict[str, Path]:
    """Save a complete report bundle.

    Args:
        result: Backtest result
        metrics: Performance metrics
        output_dir: Directory to save outputs
        prefix: Filename prefix

    Returns:
        Dictionary of saved file paths
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    saved_files = {}

    # Text summary
    summary_path = output_dir / f"{prefix}_summary.txt"
    summary_path.write_text(generate_summary_report(result, metrics))
    saved_files["summary"] = summary_path

    # Equity curve CSV
    if not result.equity_curve.empty:
        equity_path = output_dir / f"{prefix}_equity.csv"
        result.equity_curve.to_csv(equity_path, index=False)
        saved_files["equity"] = equity_path

    # Trade log CSV
    trade_log = generate_trade_log(result)
    if not trade_log.empty:
        trades_path = output_dir / f"{prefix}_trades.csv"
        trade_log.to_csv(trades_path, index=False)
        saved_files["trades"] = trades_path

    # Positions CSV
    positions = generate_position_report(result)
    if not positions.empty:
        positions_path = output_dir / f"{prefix}_positions.csv"
        positions.to_csv(positions_path, index=False)
        saved_files["positions"] = positions_path

    # Metrics JSON
    metrics_dict = {
        "total_return": metrics.total_return,
        "cagr": metrics.cagr,
        "annualized_volatility": metrics.annualized_volatility,
        "sharpe_ratio": metrics.sharpe_ratio,
        "sortino_ratio": metrics.sortino_ratio,
        "calmar_ratio": metrics.calmar_ratio,
        "max_drawdown": metrics.max_drawdown,
        "max_drawdown_duration_days": metrics.max_drawdown_duration_days,
        "total_trades": metrics.total_trades,
        "win_rate": metrics.win_rate,
        "profit_factor": metrics.profit_factor,
    }

    import json

    metrics_path = output_dir / f"{prefix}_metrics.json"
    metrics_path.write_text(json.dumps(metrics_dict, indent=2))
    saved_files["metrics"] = metrics_path

    return saved_files


def generate_summary_report_event(
    result: EventEngineResult,
    metrics: PerformanceMetrics,
) -> str:
    """Generate a text summary report for an event-driven backtest.

    Args:
        result: Event engine result (equity curve, trade log)
        metrics: Performance metrics (e.g. from calculate_metrics(result.daily_returns, trade_log=result.trade_log))

    Returns:
        Formatted text report
    """
    final_equity = (
        result.equity_curve["equity"].iloc[-1]
        if not result.equity_curve.empty and "equity" in result.equity_curve.columns
        else result.config.initial_capital
    )
    lines = [
        "=" * 60,
        "EVENT BACKTEST PERFORMANCE REPORT",
        "=" * 60,
        "",
        f"Period: {result.start_date} to {result.end_date}",
        f"Initial Capital: ${result.config.initial_capital:,.2f}",
        f"Final Equity: ${final_equity:,.2f}",
        "",
        "-" * 40,
        "RETURNS",
        "-" * 40,
        f"Total Return: {metrics.total_return * 100:.2f}%",
        f"CAGR: {metrics.cagr * 100:.2f}%",
        f"Annualized Volatility: {metrics.annualized_volatility * 100:.2f}%",
        "",
        "-" * 40,
        "RISK-ADJUSTED METRICS",
        "-" * 40,
        f"Sharpe Ratio: {metrics.sharpe_ratio:.2f}",
        f"Sortino Ratio: {metrics.sortino_ratio:.2f}",
        f"Calmar Ratio: {metrics.calmar_ratio:.2f}",
        "",
        "-" * 40,
        "DRAWDOWN",
        "-" * 40,
        f"Max Drawdown: {metrics.max_drawdown * 100:.2f}%",
        f"Max Drawdown Duration: {metrics.max_drawdown_duration_days} days",
        "",
        "-" * 40,
        "TRADING STATISTICS (from trade log)",
        "-" * 40,
        f"Total Trades: {metrics.total_trades}",
        f"Win Rate: {metrics.win_rate * 100:.1f}%",
        f"Profit Factor: {metrics.profit_factor:.2f}",
        f"Average Win: ${metrics.avg_win:,.2f}",
        f"Average Loss: ${metrics.avg_loss:,.2f}",
        "",
        "=" * 60,
    ]
    return "\n".join(lines)


def save_event_report(
    result: EventEngineResult,
    metrics: PerformanceMetrics,
    output_dir: Path,
    prefix: str = "event_backtest",
) -> dict[str, Path]:
    """Save event backtest report bundle (summary, equity, trade log, metrics).

    Args:
        result: Event engine result
        metrics: Performance metrics
        output_dir: Directory to save outputs
        prefix: Filename prefix

    Returns:
        Dictionary of saved file paths
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    saved_files = {}

    summary_path = output_dir / f"{prefix}_summary.txt"
    summary_path.write_text(generate_summary_report_event(result, metrics))
    saved_files["summary"] = summary_path

    if not result.equity_curve.empty:
        equity_path = output_dir / f"{prefix}_equity.csv"
        result.equity_curve.to_csv(equity_path, index=False)
        saved_files["equity"] = equity_path

    if not result.trade_log.empty:
        trades_path = output_dir / f"{prefix}_trades.csv"
        result.trade_log.to_csv(trades_path, index=False)
        saved_files["trades"] = trades_path

    import json

    metrics_dict = {
        "total_return": metrics.total_return,
        "cagr": metrics.cagr,
        "annualized_volatility": metrics.annualized_volatility,
        "sharpe_ratio": metrics.sharpe_ratio,
        "sortino_ratio": metrics.sortino_ratio,
        "calmar_ratio": metrics.calmar_ratio,
        "max_drawdown": metrics.max_drawdown,
        "max_drawdown_duration_days": metrics.max_drawdown_duration_days,
        "total_trades": metrics.total_trades,
        "win_rate": metrics.win_rate,
        "profit_factor": metrics.profit_factor,
    }
    metrics_path = output_dir / f"{prefix}_metrics.json"
    metrics_path.write_text(json.dumps(metrics_dict, indent=2))
    saved_files["metrics"] = metrics_path

    return saved_files


def generate_surprise_report(
    result: "SurpriseBacktestResult",
    mcpt_result: "McptResult | None" = None,
    statn_result: "RollingStationarityResult | None" = None,
    entropy_result: "EntropyDiagnosticResult | None" = None,
) -> str:
    """Generate a text report for Prediction Market Surprise Alpha backtest results.

    Args:
        result: SurpriseBacktestResult from EventBacktestEngine
        mcpt_result: Optional MCPT permutation test result
        statn_result: Optional rolling stationarity result
        entropy_result: Optional entropy diagnostic result

    Returns:
        Formatted string report with event stats, performance, diagnostics, top trades
    """
    lines = [
        "=== Prediction Market Surprise Alpha Backtest Report ===",
        "",
        "EVENT STATISTICS",
    ]

    n_total = result.n_events_total
    n_traded = result.n_events_traded
    n_filtered = result.n_events_filtered
    filter_pct = (n_filtered / n_total * 100) if n_total > 0 else 0.0
    lines += [
        f"  Total events considered: {n_total}",
        f"  Events traded: {n_traded}",
        f"  Events filtered: {n_filtered} ({filter_pct:.1f}% filtered out)",
        "",
        "PERFORMANCE",
    ]

    tl = result.trade_log
    if not tl.empty:
        total_return = (
            result.equity_curve["equity"].iloc[-1] / result.config.initial_capital - 1
            if not result.equity_curve.empty
            else 0.0
        )
        winners = tl[tl["pnl"] > 0]
        losers = tl[tl["pnl"] < 0]
        win_rate = len(winners) / len(tl) if len(tl) > 0 else 0.0
        gross_wins = float(winners["pnl"].sum()) if not winners.empty else 0.0
        gross_losses = abs(float(losers["pnl"].sum())) if not losers.empty else 0.0
        profit_factor = gross_wins / gross_losses if gross_losses > 0 else float("inf")

        dr = result.daily_returns.dropna()
        sharpe = 0.0
        if len(dr) > 1 and dr.std() > 0:
            sharpe = float(dr.mean() / dr.std() * (252**0.5))

        eq = result.equity_curve
        max_dd = 0.0
        if not eq.empty and "equity" in eq.columns:
            cum = eq["equity"]
            rolling_max = cum.expanding().max()
            drawdowns = cum / rolling_max - 1
            max_dd = float(drawdowns.min())

        lines += [
            f"  Total return: {total_return * 100:.1f}%",
            f"  Sharpe ratio: {sharpe:.2f}",
            f"  Max drawdown: {max_dd * 100:.1f}%",
            f"  Win rate: {win_rate * 100:.1f}%",
            f"  Profit factor: {profit_factor:.1f}",
        ]
    else:
        lines += ["  No trades to report."]

    lines.append("")

    # Masters diagnostic results
    has_diagnostics = any(
        r is not None for r in [statn_result, mcpt_result, entropy_result]
    )
    if has_diagnostics:
        lines.append("MASTERS DIAGNOSTIC RESULTS")
        if statn_result is not None:
            label = "PASS" if statn_result.passes else "FAIL"
            fs = statn_result.fraction_stationary
            lines.append(
                f"  STATN (Stationarity):    {label} (fraction_stationary={fs:.2f})"
            )
        if mcpt_result is not None:
            label = "PASS" if mcpt_result.passes else "FAIL"
            pv = mcpt_result.p_value
            np_ = mcpt_result.n_permutations
            lines.append(
                f"  MCPT (Permutation test): {label} (p_value={pv:.3f}, n_permutations={np_})"
            )
        if entropy_result is not None:
            label = "PASS" if entropy_result.passes else "FAIL"
            fbm = entropy_result.fraction_below_max
            lines.append(
                f"  ENTROPY:                 {label} (fraction_below_max={fbm:.2f})"
            )
        lines.append("")

    # Top 10 trades by return_pct
    if not tl.empty and "return_pct" in tl.columns:
        lines.append("TOP 10 TRADES BY RETURN")
        top10 = tl.nlargest(10, "return_pct")
        for _, row in top10.iterrows():
            symbol = row.get("symbol", "?")
            entry_date = row.get("entry_date", "?")
            exit_reason = row.get("exit_reason", "?")
            ret_pct = row.get("return_pct", 0.0) or 0.0
            surprise = row.get("surprise_score")
            sign = "+" if ret_pct >= 0 else ""
            surprise_str = (
                f"  (surprise: {surprise:.2f} bits)" if surprise is not None else ""
            )
            lines.append(
                f"  {symbol:<6} {entry_date}  {exit_reason:<14} {sign}{ret_pct * 100:.1f}%{surprise_str}"
            )

    return "\n".join(lines)


def save_obsidian_report(
    result: BacktestResult,
    metrics: PerformanceMetrics,
    backtest_id: str | None = None,
    obsidian: bool = True,
) -> Path:
    """Save an Obsidian-formatted backtest report.

    Args:
        result: Backtest result
        metrics: Performance metrics
        backtest_id: Optional backtest identifier
        obsidian: If True, save to Obsidian vault (default: True)

    Returns:
        Path to saved Obsidian note
    """
    if backtest_id is None:
        backtest_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Convert result and metrics to dictionaries
    result_dict = {
        "start_date": str(result.start_date),
        "end_date": str(result.end_date),
        "initial_capital": result.config.initial_capital,
        "final_equity": (
            result.equity_curve["equity"].iloc[-1]
            if not result.equity_curve.empty
            else result.config.initial_capital
        ),
    }

    metrics_dict = {
        "total_return": metrics.total_return,
        "cagr": metrics.cagr,
        "annualized_volatility": metrics.annualized_volatility,
        "sharpe_ratio": metrics.sharpe_ratio,
        "sortino_ratio": metrics.sortino_ratio,
        "calmar_ratio": metrics.calmar_ratio,
        "max_drawdown": metrics.max_drawdown,
        "max_drawdown_duration_days": metrics.max_drawdown_duration_days,
        "total_trades": metrics.total_trades,
        "win_rate": metrics.win_rate,
        "profit_factor": metrics.profit_factor,
        "avg_win": metrics.avg_win,
        "avg_loss": metrics.avg_loss,
        "skewness": metrics.skewness,
        "kurtosis": metrics.kurtosis,
    }

    # Generate Obsidian content
    obsidian_content = generate_backtest_report_obsidian(
        result_dict,
        metrics_dict,
        backtest_id=backtest_id,
    )

    # Save to Obsidian vault
    obsidian_path = save_obsidian_note(
        obsidian_content,
        f"{backtest_id}-backtest.md",
        subfolder="Research/Backtests",
    )

    return obsidian_path
