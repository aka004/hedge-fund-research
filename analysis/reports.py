"""Report generation for backtest results."""

from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from analysis.metrics import PerformanceMetrics
from analysis.obsidian_reports import (
    generate_backtest_report_obsidian,
    save_obsidian_note,
)
from strategy.backtest.engine import BacktestResult


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
        f"Final Equity: ${result.equity_curve['equity'].iloc[-1]:,.2f}" if not result.equity_curve.empty else "",
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
        trades_data.append({
            "date": trade.date,
            "symbol": trade.symbol,
            "side": trade.side,
            "shares": trade.shares,
            "price": trade.price,
            "gross_value": trade.gross_value,
            "commission": trade.commission,
            "slippage": trade.slippage,
            "net_value": trade.net_value,
        })

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
            rows.append({
                "date": ph["date"],
                "symbol": symbol,
                "weight": weight,
            })

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


def save_obsidian_report(
    result: BacktestResult,
    metrics: PerformanceMetrics,
    backtest_id: Optional[str] = None,
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
        "final_equity": result.equity_curve["equity"].iloc[-1] if not result.equity_curve.empty else result.config.initial_capital,
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
