#!/usr/bin/env python3
"""
Integration runner for EventDrivenEngine.

Loads parquet data, builds signals, runs the event-driven backtest engine,
and persists results to DuckDB.

Usage:
    python scripts/run_event_engine.py --universe AAPL MSFT GOOGL AMZN NVDA \\
        --start 2022-01-01 --end 2025-12-31
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse
import logging
from datetime import date

import pandas as pd

from analysis.metrics import calculate_metrics
from config import STORAGE_PATH
from data.storage.duckdb_store import DuckDBStore
from data.storage.parquet import ParquetStorage
from strategy.backtest.event_engine import (
    EventDrivenEngine,
    EventEngineConfig,
)
from strategy.backtest.portfolio import TransactionCosts
from strategy.signals.combiner import SignalCombiner
from strategy.signals.momentum import MomentumSignal
from strategy.signals.value import ValueSignal

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

PARQUET_DIR = STORAGE_PATH / "parquet"

MACRO_TICKERS = ["^TNX", "^IRX", "HYG", "LQD"]
SENTIMENT_TICKERS = ["^VIX"]  # SPY is added automatically


def load_macro_dataframes(
    start_date: date,
    end_date: date,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load macro and sentiment tickers via yfinance for regime computation.

    Macro:     ^TNX (10Y yield), ^IRX (3M yield), HYG, LQD
    Sentiment: SPY (for 200MA), ^VIX
    """
    import yfinance as yf

    def _fetch(tickers: list[str]) -> pd.DataFrame:
        frames = {}
        for ticker in tickers:
            try:
                df = yf.download(
                    ticker,
                    start=start_date.isoformat(),
                    end=end_date.isoformat(),
                    auto_adjust=True,
                    progress=False,
                )
                if df.empty:
                    logger.warning(f"No data for macro ticker {ticker}")
                    continue
                # Handle MultiIndex columns from yfinance
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                col = "Close" if "Close" in df.columns else df.columns[0]
                frames[ticker] = df[col]
            except Exception as e:
                logger.warning(f"Failed to fetch {ticker}: {e}")
        return pd.DataFrame(frames)

    macro_df = _fetch(MACRO_TICKERS)
    sentiment_df = _fetch(SENTIMENT_TICKERS + ["SPY"])

    logger.info(f"Loaded macro tickers: {list(macro_df.columns)}")
    logger.info(f"Loaded sentiment tickers: {list(sentiment_df.columns)}")
    return macro_df, sentiment_df


def load_price_dataframes(
    symbols: list[str],
    price_col: str = "adj_close",
    prices_dir: Path | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load parquet files into wide close_prices and open_prices DataFrames."""
    if prices_dir is None:
        prices_dir = PARQUET_DIR / "prices"
    close_frames = {}
    open_frames = {}

    for symbol in symbols:
        path = prices_dir / f"{symbol}.parquet"
        if not path.exists():
            logger.warning(f"No parquet file for {symbol}, skipping")
            continue

        df = pd.read_parquet(path)
        # date may be the index (when saved with index=True) or a column
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date").sort_index()
        else:
            df.index = pd.to_datetime(df.index)
            df.index.name = "date"
            df = df.sort_index()

        if price_col in df.columns:
            close_frames[symbol] = df[price_col]
        elif "close" in df.columns:
            close_frames[symbol] = df["close"]

        if "open" in df.columns:
            open_frames[symbol] = df["open"]

    close_prices = pd.DataFrame(close_frames)
    open_prices = pd.DataFrame(open_frames)

    logger.info(
        f"Loaded {len(close_frames)} symbols, " f"{len(close_prices)} trading days"
    )
    return close_prices, open_prices


def load_ohlcv_dataframes(
    symbols: list[str],
    prices_dir: Path | None = None,
) -> dict[str, pd.DataFrame]:
    """Load full OHLCV into a dict of wide DataFrames.

    Returns:
        {"open": DataFrame, "high": DataFrame, "low": DataFrame,
         "close": DataFrame, "volume": DataFrame}
        Each DataFrame has shape (n_trading_days, n_symbols).
        Uses adj_close for the "close" key.
    """
    if prices_dir is None:
        prices_dir = PARQUET_DIR / "prices"
    frames: dict[str, dict[str, pd.Series]] = {
        col: {} for col in ("open", "high", "low", "close", "volume")
    }
    col_map = {"adj_close": "close", "open": "open", "high": "high", "low": "low", "volume": "volume"}

    for symbol in symbols:
        path = prices_dir / f"{symbol}.parquet"
        if not path.exists():
            continue
        df = pd.read_parquet(path)
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date").sort_index()
        else:
            df.index = pd.to_datetime(df.index)
            df = df.sort_index()

        for src_col, dest_col in col_map.items():
            if src_col in df.columns:
                frames[dest_col][symbol] = df[src_col]

    result = {col: pd.DataFrame(series_dict) for col, series_dict in frames.items()}
    n_symbols = len(result.get("close", pd.DataFrame()).columns)
    n_days = len(result.get("close", pd.DataFrame()))
    logger.info(f"OHLCV loaded: {n_symbols} symbols, {n_days} trading days")

    # Load fundamental daily DataFrames if available (45-day filing lag, forward-filled)
    fund_dir = PARQUET_DIR / "fundamentals_daily"
    fund_metrics = ("earnings_yield", "revenue_growth", "profit_margin", "expense_ratio")
    for metric in fund_metrics:
        path = fund_dir / f"{metric}.parquet"
        if path.exists():
            df = pd.read_parquet(path)
            df.index = pd.to_datetime(df.index)
            # Filter to requested symbols only
            available_cols = [s for s in symbols if s in df.columns]
            if available_cols:
                result[metric] = df[available_cols]

    n_fund = sum(1 for m in fund_metrics if m in result)
    if n_fund:
        logger.info(f"Fundamentals loaded: {n_fund} metrics")

    return result


def build_equity_df(result) -> pd.DataFrame:
    """Build the equity DataFrame for persistence."""
    eq = result.equity_curve.copy()

    # Compute benchmark equity from benchmark close prices
    if "benchmark" in eq.columns:
        first_bench = (
            eq["benchmark"].dropna().iloc[0]
            if not eq["benchmark"].dropna().empty
            else None
        )
        if first_bench and first_bench > 0:
            first_equity = eq["equity"].iloc[0]
            eq["benchmark_equity"] = eq["benchmark"] / first_bench * first_equity
        else:
            eq["benchmark_equity"] = 0.0
    else:
        eq["benchmark_equity"] = 0.0

    # Compute drawdown
    eq["peak"] = eq["equity"].expanding().max()
    eq["drawdown"] = (eq["equity"] - eq["peak"]) / eq["peak"] * 100

    # Daily return
    eq["daily_return"] = eq["equity"].pct_change()

    # Ensure date column
    if "date" not in eq.columns:
        eq = eq.reset_index()

    return eq[
        ["date", "equity", "benchmark_equity", "drawdown", "daily_return"]
    ].dropna(subset=["daily_return"])


def persist_results(result, metrics, universe: list[str], start_str: str, end_str: str):
    """Persist engine results to DuckDB via BacktestPersistence."""
    # Import here to use backend's database module
    sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))
    from app.services.persistence import BacktestPersistence

    persistence = BacktestPersistence()

    # Save run metadata
    run_data = {
        "n_assets": len(universe),
        "sharpe_raw": metrics.sharpe_ratio,
        "is_mock": False,
    }
    afml_data = {
        "psr": None,
        "deflated_sharpe": None,
        "pbo": None,
        "caveats": [],
    }
    run_id = persistence.save_run(
        result=run_data,
        strategy_name="EventDrivenEngine_momentum_value",
        afml_metrics=afml_data,
        universe=",".join(universe),
        start_date=start_str,
        end_date=end_str,
    )
    logger.info(f"Saved run: {run_id}")

    # Save equity curve
    equity_df = build_equity_df(result)
    persistence.save_equity_curve(run_id, equity_df)
    logger.info(f"Saved {len(equity_df)} equity curve rows")

    # Save round-trip trades
    if not result.trade_log.empty:
        persistence.save_round_trip_trades(run_id, result.trade_log)
        logger.info(f"Saved {len(result.trade_log)} round-trip trades")

    # Save final portfolio weights
    if result.open_positions:
        last_date = result.end_date
        total_value = sum(
            p.shares * (p.exit_price or p.entry_price) for p in result.open_positions
        )
        if total_value > 0:
            rows = []
            for pos in result.open_positions:
                value = pos.shares * (pos.exit_price or pos.entry_price)
                rows.append(
                    {
                        "date": last_date,
                        "ticker": pos.symbol,
                        "weight": value / total_value,
                        "hrp_weight": None,
                        "kelly_fraction": None,
                        "signal_source": "momentum+value",
                        "is_mock": False,
                    }
                )
            weights_df = pd.DataFrame(rows)
            persistence.save_portfolio_weights(run_id, weights_df)
            logger.info(f"Saved {len(rows)} portfolio weights")

    return run_id


def main():
    parser = argparse.ArgumentParser(description="Run EventDrivenEngine backtest")
    parser.add_argument(
        "--universe",
        nargs="+",
        required=True,
        help="Stock symbols to include",
    )
    parser.add_argument(
        "--start",
        default="2022-01-01",
        help="Start date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end",
        default="2025-12-31",
        help="End date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--max-positions",
        type=int,
        default=20,
        help="Maximum positions (default: 20)",
    )
    parser.add_argument(
        "--slippage-bps",
        type=float,
        default=10.0,
        help="Slippage in basis points (default: 10)",
    )
    args = parser.parse_args()

    universe = [s.upper() for s in args.universe]
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)

    logger.info(f"Universe: {universe}")
    logger.info(f"Period: {start} to {end}")

    # Load price data (include SPY for benchmark)
    all_symbols = list(set(universe + ["SPY"]))
    close_prices, open_prices = load_price_dataframes(all_symbols)

    if close_prices.empty:
        logger.error("No price data loaded. Run fetch_price_history.py first.")
        sys.exit(1)

    # Build signal generators
    duckdb_store = DuckDBStore(PARQUET_DIR)
    parquet_storage = ParquetStorage(PARQUET_DIR)

    momentum = MomentumSignal(duckdb_store)
    value = ValueSignal(parquet_storage)
    combiner = SignalCombiner([momentum, value])

    # Configure engine
    config = EventEngineConfig(
        initial_capital=100_000.0,
        max_positions=args.max_positions,
        max_position_weight=0.10,
        rebalance_frequency="monthly",
        position_sizing="equal",
        transaction_costs=TransactionCosts(slippage_bps=args.slippage_bps),
        benchmark_symbol="SPY",
    )

    # Load macro/sentiment data for 3-layer regime multiplier
    logger.info("Loading macro/sentiment data for regime computation...")
    macro_prices, sentiment_prices = load_macro_dataframes(start, end)

    # Run engine
    logger.info("Running EventDrivenEngine...")
    engine = EventDrivenEngine(combiner, config)
    result = engine.run(
        universe,
        close_prices,
        open_prices,
        macro_prices=macro_prices if not macro_prices.empty else None,
        sentiment_prices=sentiment_prices if not sentiment_prices.empty else None,
        start_date=start,
        end_date=end,
    )

    # Calculate metrics
    metrics = calculate_metrics(
        result.daily_returns,
        trade_log=result.trade_log,
    )

    # Print summary
    logger.info("=" * 50)
    logger.info("RESULTS")
    logger.info("=" * 50)
    logger.info(f"Sharpe Ratio:  {metrics.sharpe_ratio:.3f}")
    logger.info(f"Total Return:  {metrics.total_return:.1%}")
    logger.info(f"CAGR:          {metrics.cagr:.1%}")
    logger.info(f"Max Drawdown:  {metrics.max_drawdown:.1%}")
    logger.info(f"Total Trades:  {metrics.total_trades}")
    logger.info(f"Win Rate:      {metrics.win_rate:.1%}")
    logger.info(f"Profit Factor: {metrics.profit_factor:.2f}")
    logger.info(f"Avg Holding:   {getattr(metrics, 'avg_holding_days', 'N/A')}")
    logger.info("=" * 50)

    # PSR post-hoc validation (AFML Ch.14)
    from afml.metrics import deflated_sharpe

    if len(result.daily_returns) >= 252:
        psr_result = deflated_sharpe(
            result.daily_returns.values,
            n_strategies_tested=1,
        )
        verdict = "PASS ✓" if psr_result.passes_threshold else "FAIL — do not promote"
        logger.info(f"PSR: {psr_result.psr:.3f}  [{verdict}]")
        if not psr_result.passes_threshold:
            logger.warning(
                f"Strategy PSR {psr_result.psr:.3f} < 0.95. "
                "Insufficient statistical confidence. Do not promote to production."
            )
    else:
        logger.warning(
            f"Insufficient history for PSR ({len(result.daily_returns)} days < 252 required)"
        )

    # Persist to DuckDB
    run_id = persist_results(result, metrics, universe, args.start, args.end)
    logger.info(f"Results persisted. run_id={run_id}")


if __name__ == "__main__":
    main()
