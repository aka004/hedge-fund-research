"""Visualization tools for backtest analysis."""

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from analysis.metrics import PerformanceMetrics
from strategy.backtest.engine import BacktestResult


def plot_equity_curve(
    result: BacktestResult,
    benchmark: pd.Series | None = None,
    title: str = "Portfolio Equity Curve",
    save_path: Path | None = None,
) -> plt.Figure:
    """Plot portfolio equity curve.

    Args:
        result: Backtest result
        benchmark: Optional benchmark returns for comparison
        title: Chart title
        save_path: Optional path to save figure

    Returns:
        Matplotlib figure
    """
    fig, ax = plt.subplots(figsize=(12, 6))

    # Plot strategy equity
    equity = result.equity_curve.set_index("date")["equity"]
    normalized = equity / equity.iloc[0] * 100
    ax.plot(normalized.index, normalized.values, label="Strategy", linewidth=2)

    # Plot benchmark if provided
    if benchmark is not None:
        bench_normalized = (1 + benchmark).cumprod() * 100
        ax.plot(bench_normalized.index, bench_normalized.values, label="Benchmark", linewidth=1.5, alpha=0.7)

    ax.set_xlabel("Date")
    ax.set_ylabel("Value (Starting = 100)")
    ax.set_title(title)
    ax.legend()
    ax.grid(True, alpha=0.3)

    plt.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")

    return fig


def plot_drawdown(
    result: BacktestResult,
    title: str = "Drawdown Analysis",
    save_path: Path | None = None,
) -> plt.Figure:
    """Plot drawdown chart.

    Args:
        result: Backtest result
        title: Chart title
        save_path: Optional path to save figure

    Returns:
        Matplotlib figure
    """
    fig, ax = plt.subplots(figsize=(12, 4))

    # Calculate drawdown
    equity = result.equity_curve.set_index("date")["equity"]
    rolling_max = equity.expanding().max()
    drawdown = (equity / rolling_max - 1) * 100

    ax.fill_between(drawdown.index, 0, drawdown.values, color="red", alpha=0.3)
    ax.plot(drawdown.index, drawdown.values, color="red", linewidth=1)

    ax.set_xlabel("Date")
    ax.set_ylabel("Drawdown (%)")
    ax.set_title(title)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")

    return fig


def plot_monthly_returns(
    result: BacktestResult,
    title: str = "Monthly Returns Heatmap",
    save_path: Path | None = None,
) -> plt.Figure:
    """Plot monthly returns heatmap.

    Args:
        result: Backtest result
        title: Chart title
        save_path: Optional path to save figure

    Returns:
        Matplotlib figure
    """
    if result.daily_returns.empty:
        fig, ax = plt.subplots(figsize=(12, 8))
        ax.text(0.5, 0.5, "No data available", ha="center", va="center")
        return fig

    # Resample to monthly
    returns = result.daily_returns.copy()
    returns.index = pd.to_datetime(returns.index)
    monthly = returns.resample("ME").apply(lambda x: (1 + x).prod() - 1)

    # Create pivot table
    monthly_df = pd.DataFrame({
        "year": monthly.index.year,
        "month": monthly.index.month,
        "return": monthly.values * 100,
    })
    pivot = monthly_df.pivot(index="year", columns="month", values="return")

    fig, ax = plt.subplots(figsize=(12, 8))

    # Create heatmap
    im = ax.imshow(pivot.values, cmap="RdYlGn", aspect="auto", vmin=-10, vmax=10)

    # Labels
    ax.set_xticks(range(12))
    ax.set_xticklabels(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels(pivot.index)

    # Add colorbar
    cbar = plt.colorbar(im, ax=ax)
    cbar.set_label("Return (%)")

    # Add text annotations
    for i in range(len(pivot.index)):
        for j in range(12):
            val = pivot.iloc[i, j] if j < len(pivot.columns) and not pd.isna(pivot.iloc[i, j]) else None
            if val is not None:
                ax.text(j, i, f"{val:.1f}", ha="center", va="center", fontsize=8)

    ax.set_title(title)
    plt.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")

    return fig


def plot_position_weights(
    result: BacktestResult,
    title: str = "Position Weights Over Time",
    save_path: Path | None = None,
) -> plt.Figure:
    """Plot position weights as stacked area chart.

    Args:
        result: Backtest result
        title: Chart title
        save_path: Optional path to save figure

    Returns:
        Matplotlib figure
    """
    if not result.positions_history:
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.text(0.5, 0.5, "No position data available", ha="center", va="center")
        return fig

    # Convert to DataFrame
    dates = [ph["date"] for ph in result.positions_history]
    all_symbols = set()
    for ph in result.positions_history:
        all_symbols.update(ph["positions"].keys())

    data: dict[str, list[float]] = {symbol: [] for symbol in all_symbols}
    for ph in result.positions_history:
        for symbol in all_symbols:
            data[symbol].append(ph["positions"].get(symbol, 0))

    df = pd.DataFrame(data, index=dates)

    fig, ax = plt.subplots(figsize=(14, 6))

    # Stacked area chart
    ax.stackplot(df.index, df.T.values, labels=df.columns, alpha=0.8)

    ax.set_xlabel("Date")
    ax.set_ylabel("Portfolio Weight")
    ax.set_title(title)
    ax.legend(loc="upper left", bbox_to_anchor=(1, 1), ncol=2, fontsize=8)
    ax.set_ylim(0, 1)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")

    return fig


def create_tearsheet(
    result: BacktestResult,
    metrics: PerformanceMetrics,
    output_dir: Path,
    prefix: str = "backtest",
) -> None:
    """Create a full tearsheet with multiple plots.

    Args:
        result: Backtest result
        metrics: Performance metrics
        output_dir: Directory to save outputs
        prefix: Filename prefix
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate all plots
    plot_equity_curve(result, save_path=output_dir / f"{prefix}_equity.png")
    plot_drawdown(result, save_path=output_dir / f"{prefix}_drawdown.png")
    plot_monthly_returns(result, save_path=output_dir / f"{prefix}_monthly.png")
    plot_position_weights(result, save_path=output_dir / f"{prefix}_positions.png")

    # Close all figures to free memory
    plt.close("all")
