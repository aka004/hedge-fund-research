#!/usr/bin/env python3
"""Run Prediction Market Surprise Alpha backtest using earnings proxy data."""

import argparse
import logging
from datetime import date, timedelta

import pandas as pd


def _fetch_prices(
    symbols: list[str], start_date: date, end_date: date
) -> dict[str, pd.DataFrame]:
    """Fetch OHLCV data from Yahoo Finance.

    Args:
        symbols: List of ticker symbols
        start_date: Backtest start date
        end_date: Backtest end date

    Returns:
        Dict mapping symbol -> DataFrame with columns [date, open, close]
    """
    import yfinance as yf

    price_data: dict[str, pd.DataFrame] = {}
    for symbol in symbols:
        ticker = yf.Ticker(symbol)
        df = ticker.history(
            start=start_date.isoformat(),
            end=end_date.isoformat(),
            auto_adjust=True,
        ).reset_index()
        df.columns = df.columns.str.lower()
        if "datetime" in df.columns:
            df = df.rename(columns={"datetime": "date"})
        df["date"] = pd.to_datetime(df["date"]).dt.date
        price_data[symbol] = df[["date", "open", "close"]]
    return price_data


def main(symbols: list[str], start_date: date, end_date: date) -> None:
    """Run the surprise backtest pipeline end-to-end.

    Args:
        symbols: List of ticker symbols to backtest
        start_date: Backtest start date
        end_date: Backtest end date
    """
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    # Step 1: Fetch price data
    logger.info("Fetching price data for %d symbols...", len(symbols))
    price_data = _fetch_prices(symbols, start_date, end_date)
    logger.info("Fetched price data for %d symbols", len(price_data))

    # Step 2: Fetch earnings events
    logger.info("Fetching earnings events...")
    from data.providers.earnings_surprise import EarningsSurpriseProvider
    from data.storage.event_store import EventStore

    store = EventStore(storage_dir="data/storage")
    provider = EarningsSurpriseProvider()
    all_events = []
    for symbol in symbols:
        events = provider.get_events(symbol, start_date, end_date)
        if not events:
            logger.warning("No earnings events found for %s in date range", symbol)
        all_events.extend(events)

    if not all_events:
        logger.error(
            "No events found for any symbol — check date range and API availability"
        )
        return

    store.save_events(all_events)
    logger.info("Saved %d earnings events", len(all_events))

    # Step 3: Run backtest
    logger.info("Running backtest...")
    from strategy.backtest.event_backtest import (
        EventBacktestEngine,
        SurpriseBacktestConfig,
    )

    config = SurpriseBacktestConfig(initial_capital=100_000.0)
    engine = EventBacktestEngine(config=config, price_data=price_data)
    result = engine.run(all_events, start_date, end_date)
    logger.info(
        "Backtest complete: %d events traded out of %d",
        result.n_events_traded,
        result.n_events_total,
    )

    # Step 4: Run Masters diagnostics
    logger.info("Running Masters diagnostics...")
    mcpt_result = None
    statn_result = None
    entropy_result = None

    if len(result.event_returns) > 20:
        from afml import entropy_diagnostic, monte_carlo_permutation_test, rolling_statn

        mcpt_result = monte_carlo_permutation_test(result.event_returns)
        logger.info(
            "MCPT p_value=%.3f passes=%s", mcpt_result.p_value, mcpt_result.passes
        )

        daily = result.daily_returns.dropna()
        if len(daily) >= 60:
            statn_result = rolling_statn(daily)
            logger.info(
                "STATN fraction_stationary=%.2f passes=%s",
                statn_result.fraction_stationary,
                statn_result.passes,
            )

        tl = result.trade_log
        if not tl.empty and "surprise_score" in tl.columns:
            surprise_scores = tl["surprise_score"]
            labels = tl["return_pct"].apply(
                lambda r: 1 if r > 0 else (-1 if r < 0 else 0)
            )
            entropy_result = entropy_diagnostic(surprise_scores, labels)
            logger.info(
                "ENTROPY fraction_below_max=%.2f passes=%s",
                entropy_result.fraction_below_max,
                entropy_result.passes,
            )

    # Step 5: Print report
    from analysis.reports import generate_surprise_report

    print(generate_surprise_report(result, mcpt_result, statn_result, entropy_result))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Surprise Alpha backtest")
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=["AAPL", "MSFT", "GOOGL"],
        help="Ticker symbols to backtest",
    )
    parser.add_argument(
        "--years",
        type=int,
        default=5,
        help="Number of years of history (default: 5)",
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default=None,
        help="Start date in YYYY-MM-DD format",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default=None,
        help="End date in YYYY-MM-DD format",
    )
    args = parser.parse_args()

    end = date.today() if args.end_date is None else date.fromisoformat(args.end_date)
    start = (
        end - timedelta(days=args.years * 365)
        if args.start_date is None
        else date.fromisoformat(args.start_date)
    )

    main(args.symbols, start, end)
