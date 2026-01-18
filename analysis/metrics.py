"""Performance metrics for strategy evaluation."""

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class PerformanceMetrics:
    """Comprehensive performance metrics for a strategy."""

    # Returns
    total_return: float
    cagr: float
    annualized_volatility: float

    # Risk-adjusted
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float

    # Drawdown
    max_drawdown: float
    max_drawdown_duration_days: int

    # Trade statistics
    total_trades: int
    win_rate: float
    profit_factor: float
    avg_win: float
    avg_loss: float

    # Other
    skewness: float
    kurtosis: float


def calculate_metrics(
    returns: pd.Series,
    trades: list | None = None,
    risk_free_rate: float = 0.02,
    periods_per_year: int = 252,
) -> PerformanceMetrics:
    """Calculate comprehensive performance metrics.

    Args:
        returns: Series of period returns
        trades: Optional list of Trade objects
        risk_free_rate: Annual risk-free rate
        periods_per_year: Trading periods per year (252 for daily)

    Returns:
        PerformanceMetrics object
    """
    if returns.empty or len(returns) < 2:
        return PerformanceMetrics(
            total_return=0.0,
            cagr=0.0,
            annualized_volatility=0.0,
            sharpe_ratio=0.0,
            sortino_ratio=0.0,
            calmar_ratio=0.0,
            max_drawdown=0.0,
            max_drawdown_duration_days=0,
            total_trades=0,
            win_rate=0.0,
            profit_factor=0.0,
            avg_win=0.0,
            avg_loss=0.0,
            skewness=0.0,
            kurtosis=0.0,
        )

    # Convert to numpy for calculations
    rets = returns.values

    # Total return
    total_return = (1 + rets).prod() - 1

    # Annualized return (CAGR)
    n_periods = len(rets)
    years = n_periods / periods_per_year
    cagr = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0.0

    # Volatility
    annualized_vol = rets.std() * np.sqrt(periods_per_year)

    # Sharpe ratio
    excess_returns = rets - risk_free_rate / periods_per_year
    sharpe = (excess_returns.mean() * periods_per_year) / annualized_vol if annualized_vol > 0 else 0.0

    # Sortino ratio (only downside deviation)
    downside_returns = rets[rets < 0]
    downside_std = downside_returns.std() * np.sqrt(periods_per_year) if len(downside_returns) > 0 else 0.0
    sortino = (excess_returns.mean() * periods_per_year) / downside_std if downside_std > 0 else 0.0

    # Drawdown analysis
    cum_returns = (1 + returns).cumprod()
    rolling_max = cum_returns.expanding().max()
    drawdowns = cum_returns / rolling_max - 1
    max_dd = drawdowns.min()

    # Max drawdown duration
    in_drawdown = drawdowns < 0
    dd_periods = []
    current_dd_length = 0
    for is_dd in in_drawdown:
        if is_dd:
            current_dd_length += 1
        else:
            if current_dd_length > 0:
                dd_periods.append(current_dd_length)
            current_dd_length = 0
    if current_dd_length > 0:
        dd_periods.append(current_dd_length)
    max_dd_duration = max(dd_periods) if dd_periods else 0

    # Calmar ratio
    calmar = cagr / abs(max_dd) if max_dd < 0 else 0.0

    # Trade statistics
    total_trades = len(trades) if trades else 0
    win_rate = 0.0
    profit_factor = 0.0
    avg_win = 0.0
    avg_loss = 0.0

    if trades:
        # Calculate PnL for each trade
        wins = []
        losses = []
        for trade in trades:
            # Simplified PnL calculation
            if trade.side == "sell":
                pnl = trade.gross_value - (trade.commission + trade.slippage)
            else:
                pnl = -(trade.gross_value + trade.commission + trade.slippage)

            if pnl > 0:
                wins.append(pnl)
            elif pnl < 0:
                losses.append(abs(pnl))

        total_trades = len(wins) + len(losses)
        if total_trades > 0:
            win_rate = len(wins) / total_trades

        if wins:
            avg_win = sum(wins) / len(wins)
        if losses:
            avg_loss = sum(losses) / len(losses)

        total_wins = sum(wins)
        total_losses = sum(losses)
        profit_factor = total_wins / total_losses if total_losses > 0 else float("inf")

    # Higher moments
    skewness = float(pd.Series(rets).skew()) if len(rets) > 2 else 0.0
    kurtosis = float(pd.Series(rets).kurtosis()) if len(rets) > 3 else 0.0

    return PerformanceMetrics(
        total_return=total_return,
        cagr=cagr,
        annualized_volatility=annualized_vol,
        sharpe_ratio=sharpe,
        sortino_ratio=sortino,
        calmar_ratio=calmar,
        max_drawdown=max_dd,
        max_drawdown_duration_days=max_dd_duration,
        total_trades=total_trades,
        win_rate=win_rate,
        profit_factor=profit_factor,
        avg_win=avg_win,
        avg_loss=avg_loss,
        skewness=skewness,
        kurtosis=kurtosis,
    )


def calculate_rolling_metrics(
    returns: pd.Series,
    window: int = 252,
    risk_free_rate: float = 0.02,
) -> pd.DataFrame:
    """Calculate rolling performance metrics.

    Args:
        returns: Series of period returns
        window: Rolling window size
        risk_free_rate: Annual risk-free rate

    Returns:
        DataFrame with rolling metrics
    """
    if len(returns) < window:
        return pd.DataFrame()

    results = []

    for i in range(window, len(returns) + 1):
        window_returns = returns.iloc[i - window : i]
        metrics = calculate_metrics(window_returns, risk_free_rate=risk_free_rate)
        results.append({
            "date": returns.index[i - 1] if hasattr(returns.index, "__getitem__") else i - 1,
            "rolling_sharpe": metrics.sharpe_ratio,
            "rolling_volatility": metrics.annualized_volatility,
            "rolling_return": metrics.total_return,
        })

    return pd.DataFrame(results)


def compare_to_benchmark(
    strategy_returns: pd.Series,
    benchmark_returns: pd.Series,
    risk_free_rate: float = 0.02,
) -> dict:
    """Compare strategy performance to a benchmark.

    Args:
        strategy_returns: Strategy return series
        benchmark_returns: Benchmark return series
        risk_free_rate: Annual risk-free rate

    Returns:
        Dictionary of comparison metrics
    """
    # Align dates
    aligned = pd.DataFrame({
        "strategy": strategy_returns,
        "benchmark": benchmark_returns,
    }).dropna()

    if aligned.empty:
        return {}

    strategy_metrics = calculate_metrics(aligned["strategy"], risk_free_rate=risk_free_rate)
    benchmark_metrics = calculate_metrics(aligned["benchmark"], risk_free_rate=risk_free_rate)

    # Alpha and Beta
    cov_matrix = aligned.cov()
    beta = cov_matrix.loc["strategy", "benchmark"] / cov_matrix.loc["benchmark", "benchmark"]

    excess_strategy = aligned["strategy"].mean() * 252
    excess_benchmark = aligned["benchmark"].mean() * 252
    alpha = excess_strategy - beta * excess_benchmark

    # Information ratio
    tracking_error = (aligned["strategy"] - aligned["benchmark"]).std() * np.sqrt(252)
    info_ratio = (strategy_metrics.cagr - benchmark_metrics.cagr) / tracking_error if tracking_error > 0 else 0.0

    return {
        "strategy_sharpe": strategy_metrics.sharpe_ratio,
        "benchmark_sharpe": benchmark_metrics.sharpe_ratio,
        "strategy_cagr": strategy_metrics.cagr,
        "benchmark_cagr": benchmark_metrics.cagr,
        "alpha": alpha,
        "beta": beta,
        "information_ratio": info_ratio,
        "tracking_error": tracking_error,
        "correlation": aligned["strategy"].corr(aligned["benchmark"]),
    }
