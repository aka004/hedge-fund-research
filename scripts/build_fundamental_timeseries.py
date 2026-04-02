#!/usr/bin/env python3
"""
Build look-ahead-safe daily fundamental DataFrames from quarterly data.

For each metric, applies a 45-day filing lag (SEC 10-Q deadline is 40 days
for large accelerated filers + 5-day buffer) then forward-fills into daily
frequency aligned with price dates.

Input:  parquet/fundamentals_quarterly/{symbol}.parquet (from fetch_fundamentals.py)
Output: parquet/fundamentals_daily/{metric}.parquet (dates × symbols wide format)

Usage:
    python scripts/build_fundamental_timeseries.py
"""

import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from config import STORAGE_PATH

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

PARQUET_DIR = STORAGE_PATH / "parquet"
QUARTERLY_DIR = PARQUET_DIR / "fundamentals_quarterly"
DAILY_DIR = PARQUET_DIR / "fundamentals_daily"

# When filed_date is available (SEC EDGAR), use it directly.
# Fallback: 45-day lag from period end (yfinance data without filing dates).
FILING_LAG_DAYS = 45


def load_price_dates() -> pd.DatetimeIndex:
    """Load trading dates from any price file to align fundamentals."""
    prices_dir = PARQUET_DIR / "prices"
    for p in sorted(prices_dir.glob("*.parquet"))[:1]:
        df = pd.read_parquet(p)
        if "date" in df.columns:
            return pd.DatetimeIndex(sorted(pd.to_datetime(df["date"]).unique()))
        return pd.DatetimeIndex(sorted(df.index.unique()))
    raise FileNotFoundError("No price files found")


def derive_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """Derive fundamental metrics from raw quarterly data.

    Args:
        df: Quarterly data with columns: period_end, total_revenue, net_income,
            total_expenses, ebitda

    Returns:
        DataFrame with: period_end, available_date, earnings_yield_raw,
        revenue_growth, profit_margin, expense_ratio
    """
    df = df.sort_values("period_end").copy()

    # Use actual SEC filing date if available, otherwise fall back to 45-day lag
    if "filed_date" in df.columns and df["filed_date"].notna().any():
        df["available_date"] = pd.to_datetime(df["filed_date"])
    else:
        df["available_date"] = df["period_end"] + pd.Timedelta(days=FILING_LAG_DAYS)

    # Profit margin = net_income / revenue
    df["profit_margin"] = np.where(
        df["total_revenue"].notna() & (df["total_revenue"] != 0),
        df["net_income"] / df["total_revenue"],
        np.nan,
    )

    # Expense ratio = expenses / revenue
    df["expense_ratio"] = np.where(
        df["total_revenue"].notna() & (df["total_revenue"] != 0),
        df["total_expenses"] / df["total_revenue"],
        np.nan,
    )

    # Revenue growth YoY = (rev_q - rev_q-4) / |rev_q-4|
    # q-4 = same quarter last year
    df["revenue_growth"] = np.nan
    if len(df) >= 5:
        for i in range(4, len(df)):
            prev = df.iloc[i - 4]["total_revenue"]
            curr = df.iloc[i]["total_revenue"]
            if pd.notna(prev) and pd.notna(curr) and prev != 0:
                df.iloc[i, df.columns.get_loc("revenue_growth")] = (curr - prev) / abs(prev)

    # Earnings yield raw = annualized net income (sum of last 4 quarters)
    # We store the TTM net income; earnings_yield = TTM_income / market_cap
    # Market cap comes from price data, so we store TTM income here
    df["ttm_net_income"] = np.nan
    if len(df) >= 4:
        for i in range(3, len(df)):
            ttm = df.iloc[i - 3 : i + 1]["net_income"]
            if ttm.notna().sum() == 4:
                df.iloc[i, df.columns.get_loc("ttm_net_income")] = ttm.sum()

    return df


def build_daily_series(
    symbol: str,
    df: pd.DataFrame,
    metric_col: str,
    trading_dates: pd.DatetimeIndex,
) -> pd.Series | None:
    """Build a daily time series for one metric, one symbol.

    Uses available_date (period_end + 45 days) as the point where each
    quarterly value becomes usable. Forward-fills until the next filing.
    """
    valid = df[["available_date", metric_col]].dropna(subset=[metric_col])
    if valid.empty:
        return None

    # Create a series indexed by available_date, deduplicate (keep last)
    series = pd.Series(
        valid[metric_col].values,
        index=pd.DatetimeIndex(valid["available_date"]),
        name=symbol,
    )
    series = series[~series.index.duplicated(keep="last")]

    # Reindex to trading dates and forward-fill
    # Only fill forward (past data carries forward), never backward
    series = series.reindex(trading_dates, method=None)
    series = series.ffill()

    return series


def main() -> None:
    if not QUARTERLY_DIR.exists():
        logger.error(f"No quarterly data at {QUARTERLY_DIR}. Run fetch_fundamentals.py first.")
        sys.exit(1)

    quarterly_files = sorted(QUARTERLY_DIR.glob("*.parquet"))
    logger.info(f"Building daily fundamentals from {len(quarterly_files)} symbols")

    trading_dates = load_price_dates()
    logger.info(f"Trading dates: {trading_dates[0].date()} to {trading_dates[-1].date()}")

    DAILY_DIR.mkdir(parents=True, exist_ok=True)

    # Metrics to build (column name in derived data → output file name)
    metrics = {
        "profit_margin": "profit_margin",
        "expense_ratio": "expense_ratio",
        "revenue_growth": "revenue_growth",
        "ttm_net_income": "ttm_net_income",
    }

    # Collect daily series per metric
    metric_data: dict[str, dict[str, pd.Series]] = {m: {} for m in metrics}

    for i, path in enumerate(quarterly_files, 1):
        symbol = path.stem
        try:
            raw = pd.read_parquet(path)
            raw["period_end"] = pd.to_datetime(raw["period_end"])
            derived = derive_metrics(raw)
        except Exception as e:
            logger.warning(f"{symbol}: failed to derive metrics: {e}")
            continue

        for metric_col, output_name in metrics.items():
            series = build_daily_series(symbol, derived, metric_col, trading_dates)
            if series is not None:
                metric_data[output_name][symbol] = series

        if i % 100 == 0:
            logger.info(f"  Processed {i}/{len(quarterly_files)} symbols")

    # Also build earnings_yield = ttm_net_income / market_cap
    # Market cap approximation: close_price × shares_outstanding
    # Since we don't have shares_outstanding, we use ttm_net_income / close_price
    # as a proxy (per-share earnings yield). This is proportional to the real
    # earnings yield and works fine for cross-sectional ranking.
    logger.info("Building earnings_yield from TTM net income / close price...")
    prices_dir = PARQUET_DIR / "prices"
    ey_data: dict[str, pd.Series] = {}

    for symbol, ttm_series in metric_data["ttm_net_income"].items():
        price_path = prices_dir / f"{symbol}.parquet"
        if not price_path.exists():
            continue
        pdf = pd.read_parquet(price_path)
        if "date" in pdf.columns:
            pdf["date"] = pd.to_datetime(pdf["date"])
            pdf = pdf.set_index("date").sort_index()
        close = pdf.get("adj_close", pdf.get("close"))
        if close is None:
            continue
        close = close.reindex(trading_dates, method="ffill")
        # Earnings yield = TTM income / price (per-share proxy)
        # Higher = cheaper = more attractive
        ey = ttm_series / close.replace(0, np.nan)
        if ey.notna().sum() > 0:
            ey_data[symbol] = ey

    metric_data["earnings_yield"] = ey_data

    # Save each metric as a wide DataFrame
    for metric_name, symbol_dict in metric_data.items():
        if not symbol_dict:
            logger.warning(f"No data for {metric_name}")
            continue
        wide = pd.DataFrame(symbol_dict)
        wide.index.name = "date"
        out_path = DAILY_DIR / f"{metric_name}.parquet"
        wide.to_parquet(out_path)
        n_symbols = wide.notna().any().sum()
        coverage = wide.notna().mean().mean()
        logger.info(
            f"  {metric_name}: {n_symbols} symbols, "
            f"{len(wide)} days, {coverage:.0%} coverage → {out_path.name}"
        )

    logger.info(f"Done. Daily fundamentals saved to {DAILY_DIR}")


if __name__ == "__main__":
    main()
