#!/usr/bin/env python3
"""Regime detector comparison across the 3 confirmed winning AlphaGPT strategies.

Methodology
-----------
1. Run each of the 3 confirmed strategies as a full backtest (2015-01-01 → 2024-12-31)
   on a 20-symbol universe using default run_config settings.
2. Fit VIXRegimeDetector and HMMRegimeDetector on 2015-2020 data (train split).
3. Label each trading day in the daily_returns series with the detected regime.
4. Compute conditional performance statistics per regime (bull/sideways/bear).
5. Write results to data/cache/regime_comparison.md.

Usage
-----
    DATA_STORAGE_PATH=/path/to/data/cache \
        python scripts/regime_comparison.py
"""

import logging
import os
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

try:
    from dotenv import load_dotenv
    _d = Path(__file__).resolve().parent
    while _d != _d.parent:
        if (_d / ".env").exists():
            load_dotenv(_d / ".env", override=True)
            break
        _d = _d.parent
except ImportError:
    pass

from config import STORAGE_PATH
from scripts.auto_research import RunScore, run_config
from scripts.run_event_engine import (
    load_macro_dataframes,
    load_ohlcv_dataframes,
    load_price_dataframes,
)
from strategy.regime.hmm_detector import HMMRegimeDetector
from strategy.regime.vix_detector import VIXRegimeDetector

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

START = "2015-01-01"
END = "2024-12-31"
TRAIN_END = "2020-12-31"

# 20-symbol universe — large-cap liquid stocks well-covered by parquet files
UNIVERSE = [
    "AAPL", "MSFT", "NVDA", "AMD", "META",
    "GOOGL", "AMZN", "JPM", "XOM", "GLD",
    "JNJ", "PG", "KO", "WMT", "HD",
    "V", "MA", "UNH", "BAC", "CVX",
]

# The 3 confirmed passing strategy expressions (from winning_strategies.md)
STRATEGIES = [
    {
        "id": "strat1",
        "label": "Vol-Adj 21d Momentum",
        "expression": "cs_rank(ts_delta(close, 21) / ts_std(close, 21))",
        "use_regime": False,
        "use_cusum_gate": True,
        "profit_take_mult": 2.0,
        "stop_loss_mult": 1.0,
        "max_holding_days": 21,
        "max_positions": 20,
        "rebalance_frequency": "weekly",
        "position_sizing": "equal",
        "slippage_bps": 10,
    },
    {
        "id": "strat2",
        "label": "Multi-Scale Momentum + Vol Penalty",
        "expression": (
            "cs_rank(ts_returns(close, 126)) * 0.5 "
            "+ cs_rank(ts_returns(close, 21)) * 0.3 "
            "- cs_rank(ts_std(returns, 63)) * 0.2"
        ),
        "use_regime": True,
        "use_cusum_gate": True,
        "profit_take_mult": 3.0,
        "stop_loss_mult": 1.5,
        "max_holding_days": 30,
        "max_positions": 20,
        "rebalance_frequency": "weekly",
        "position_sizing": "equal",
        "slippage_bps": 10,
    },
    {
        "id": "strat3",
        "label": "Multi-Scale Momentum + Vol Penalty + Earnings Yield",
        "expression": (
            "cs_rank(ts_returns(close, 126)) * 0.5 "
            "+ cs_rank(ts_returns(close, 21)) * 0.3 "
            "- cs_rank(ts_std(returns, 63)) * 0.2 "
            "+ cs_rank(earnings_yield) * 0.2"
        ),
        "use_regime": False,
        "use_cusum_gate": True,
        "profit_take_mult": 3.0,
        "stop_loss_mult": 1.5,
        "max_holding_days": 30,
        "max_positions": 20,
        "rebalance_frequency": "weekly",
        "position_sizing": "equal",
        "slippage_bps": 10,
    },
]


# ── Data loading ───────────────────────────────────────────────────────────────

def load_data() -> tuple:
    """Load all price, OHLCV, and macro data.

    Returns
    -------
    tuple: (close_prices, open_prices, ohlcv, macro_prices, sentiment_prices, available_symbols)
    """
    from datetime import date
    start_date = datetime.strptime(START, "%Y-%m-%d").date()
    end_date = datetime.strptime(END, "%Y-%m-%d").date()

    logger.info(f"Loading price data for {len(UNIVERSE)} symbols...")
    all_syms = UNIVERSE + ["SPY"]
    close_prices, open_prices = load_price_dataframes(all_syms)
    available = [s for s in UNIVERSE if s in close_prices.columns]
    logger.info(f"Available: {len(available)}/{len(UNIVERSE)} symbols")

    logger.info("Loading OHLCV data...")
    ohlcv = load_ohlcv_dataframes(all_syms)

    logger.info("Loading macro/sentiment (VIX)...")
    macro_prices, sentiment_prices = load_macro_dataframes(start_date, end_date)

    return close_prices, open_prices, ohlcv, macro_prices, sentiment_prices, available


# ── Backtest each strategy ─────────────────────────────────────────────────────

def run_strategy(
    strat: dict,
    universe: list[str],
    close_prices: pd.DataFrame,
    open_prices: pd.DataFrame,
    ohlcv: dict,
    macro_prices,
    sentiment_prices,
    n_strategies_tested: int = 3,
) -> RunScore | None:
    """Run a single strategy backtest and return RunScore (with daily_returns)."""
    from strategy.signals.combiner import SignalCombiner
    from strategy.signals.expression import ExpressionSignal

    logger.info(f"Running backtest: {strat['label']}")
    combiner = SignalCombiner([ExpressionSignal(expression=strat["expression"], ohlcv=ohlcv)])

    params = {
        "label": f"regime_cmp_{strat['id']}",
        "profit_take_mult": strat["profit_take_mult"],
        "stop_loss_mult": strat["stop_loss_mult"],
        "max_holding_days": strat["max_holding_days"],
        "max_positions": strat["max_positions"],
        "rebalance_frequency": strat["rebalance_frequency"],
        "position_sizing": strat["position_sizing"],
        "use_cusum_gate": strat["use_cusum_gate"],
        "use_regime": strat["use_regime"],
        "slippage_bps": strat["slippage_bps"],
        "cusum_recency_days": 15,
        "use_cusum_reversal_exit": False,
        "use_meta": False,
    }

    try:
        score = run_config(
            params=params,
            universe=universe,
            close_prices=close_prices,
            open_prices=open_prices,
            macro_prices=macro_prices,
            sentiment_prices=sentiment_prices,
            start=START,
            end=END,
            duckdb_store=None,
            parquet_storage=None,
            combiner=combiner,
            n_strategies_tested=n_strategies_tested,
        )
        logger.info(
            f"  {strat['label']}: Sharpe={score.sharpe:.3f}  "
            f"CAGR={score.cagr:.1f}%  MaxDD={score.max_dd:.1f}%"
        )
        return score
    except Exception as e:
        logger.error(f"  FAILED: {e}")
        return None


# ── Regime fitting ─────────────────────────────────────────────────────────────

def fit_detectors(
    close_prices: pd.DataFrame,
    sentiment_prices: pd.DataFrame,
) -> tuple[VIXRegimeDetector, HMMRegimeDetector]:
    """Fit VIX and HMM detectors on 2015-2020 training data."""
    # Extract SPY returns
    if "SPY" not in close_prices.columns:
        raise RuntimeError("SPY not in close_prices — needed for HMM features")

    spy_close = close_prices["SPY"].dropna()
    spy_returns = spy_close.pct_change().dropna()

    # Extract VIX
    vix_col = "^VIX" if "^VIX" in sentiment_prices.columns else None
    if vix_col is None:
        logger.warning("^VIX not in sentiment_prices — attempting yfinance download")
        import yfinance as yf
        from datetime import date as dt_date
        vix_df = yf.download("^VIX", start=START, end=END, auto_adjust=True, progress=False)
        if isinstance(vix_df.columns, pd.MultiIndex):
            vix_df.columns = vix_df.columns.get_level_values(0)
        vix = vix_df["Close"].dropna()
        vix.index = pd.to_datetime(vix.index)
    else:
        vix = sentiment_prices[vix_col].dropna()

    # Slice to training period 2015-2020
    train_end = pd.Timestamp(TRAIN_END)
    spy_ret_train = spy_returns[spy_returns.index <= train_end]
    vix_train = vix[vix.index <= train_end]

    # Fit VIX detector
    logger.info("Fitting VIX regime detector...")
    vix_det = VIXRegimeDetector(bull_threshold=18.0, bear_threshold=28.0)
    vix_det.fit(returns=spy_ret_train, vix=vix)  # uses full VIX history for lookups

    # Fit HMM detector
    logger.info("Fitting HMM regime detector...")
    hmm_det = HMMRegimeDetector()
    hmm_det.fit(returns=spy_ret_train, vix=vix_train)

    return vix_det, hmm_det


# ── Conditional performance stats ─────────────────────────────────────────────

def conditional_stats(
    daily_returns: pd.Series,
    regime_series: pd.Series,
    regime_int: int,
) -> dict:
    """Compute performance stats for days where regime == regime_int.

    Parameters
    ----------
    daily_returns:
        Strategy daily return series.
    regime_series:
        Regime label series (0/1/2) indexed by the same dates.
    regime_int:
        Target regime to filter to.

    Returns
    -------
    dict with keys: n_days, sharpe, ann_return_pct, win_rate, max_dd_pct
    """
    # Align indices
    common = daily_returns.index.intersection(regime_series.index)
    if len(common) == 0:
        return {"n_days": 0, "sharpe": float("nan"), "ann_return_pct": float("nan"),
                "win_rate": float("nan"), "max_dd_pct": float("nan")}

    rets = daily_returns.reindex(common)
    mask = regime_series.reindex(common) == regime_int
    r = rets[mask]

    if len(r) < 10:
        return {"n_days": int(mask.sum()), "sharpe": float("nan"),
                "ann_return_pct": float("nan"), "win_rate": float("nan"),
                "max_dd_pct": float("nan")}

    ann_return = r.mean() * 252
    ann_vol = r.std() * np.sqrt(252)
    sharpe = (ann_return / ann_vol) if ann_vol > 1e-9 else float("nan")
    win_rate = (r > 0).mean()

    # Max drawdown on the conditional sub-series
    cumulative = (1 + r).cumprod()
    rolling_max = cumulative.cummax()
    drawdowns = (cumulative - rolling_max) / rolling_max
    max_dd = float(drawdowns.min()) * 100

    return {
        "n_days": int(mask.sum()),
        "sharpe": round(float(sharpe), 3),
        "ann_return_pct": round(float(ann_return * 100), 2),
        "win_rate": round(float(win_rate), 3),
        "max_dd_pct": round(max_dd, 2),
    }


# ── Markdown output ────────────────────────────────────────────────────────────

def build_markdown(
    results: list[dict],
    regime_distribution: dict,
) -> str:
    """Build the regime_comparison.md content."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        "# Regime Detector Comparison — AlphaGPT Winning Strategies",
        "",
        f"> Generated: {now}",
        f"> Universe: {len(UNIVERSE)} symbols | Period: {START} → {END}",
        f"> Train/test split for detectors: train {START} → {TRAIN_END}, test 2021-01-01 → {END}",
        "",
        "## Detector Descriptions",
        "",
        "| Detector | Method | Regimes |",
        "|----------|--------|---------|",
        "| **VIX** | Threshold: VIX<18=bull, 18–28=sideways, ≥28=bear | Deterministic |",
        "| **HMM** | 3-state GaussianHMM on SPY returns + 21d realized vol + VIX | Probabilistic |",
        "",
        "## Regime Distribution (full period 2015–2024)",
        "",
        "| Detector | Bear days (0) | Sideways days (1) | Bull days (2) | Total |",
        "|----------|--------------|-------------------|---------------|-------|",
    ]
    for det_name, dist in regime_distribution.items():
        total = sum(dist.values())
        lines.append(
            f"| {det_name} "
            f"| {dist.get(0, 0)} ({dist.get(0,0)/total*100:.0f}%) "
            f"| {dist.get(1, 0)} ({dist.get(1,0)/total*100:.0f}%) "
            f"| {dist.get(2, 0)} ({dist.get(2,0)/total*100:.0f}%) "
            f"| {total} |"
        )

    lines += [
        "",
        "## Conditional Performance by Regime",
        "",
        "_Sharpe and returns computed on days classified as each regime.",
        "Strategy full-period metrics shown for reference._",
        "",
    ]

    for res in results:
        strat = res["strategy"]
        full = res["full_period"]
        lines += [
            f"### {strat['label']}",
            "",
            f"**Expression:** `{strat['expression']}`",
            "",
            "**Full-period (2015–2024):**",
            "",
            f"| Sharpe | CAGR | Max DD | PSR | Passed |",
            f"|--------|------|--------|-----|--------|",
            f"| {full.get('sharpe', 'n/a')} "
            f"| {full.get('cagr', 'n/a')}% "
            f"| {full.get('max_dd', 'n/a')}% "
            f"| {full.get('psr', 'n/a')} "
            f"| {'✅' if full.get('passed') else '❌'} |",
            "",
            "**Conditional performance by regime:**",
            "",
            "| Detector | Regime | N Days | Sharpe | Ann Return | Win Rate | Max DD |",
            "|----------|--------|--------|--------|-----------|----------|--------|",
        ]
        for row in res["rows"]:
            lines.append(
                f"| {row['detector']} "
                f"| {row['regime_name']} "
                f"| {row['n_days']} "
                f"| {row['sharpe']:.3f} "
                f"| {row['ann_return_pct']:.2f}% "
                f"| {row['win_rate']:.1%} "
                f"| {row['max_dd_pct']:.2f}% |"
            )
        lines.append("")

    lines += [
        "## Key Findings",
        "",
        "> Auto-generated summary — review for accuracy.",
        "",
    ]

    # Auto-generate simple findings
    for res in results:
        label = res["strategy"]["label"]
        bear_rows = [r for r in res["rows"] if r["regime_name"] == "bear"]
        bull_rows = [r for r in res["rows"] if r["regime_name"] == "bull"]
        if bear_rows and bull_rows:
            bear_sharpe_avg = np.nanmean([r["sharpe"] for r in bear_rows])
            bull_sharpe_avg = np.nanmean([r["sharpe"] for r in bull_rows])
            lines.append(
                f"- **{label}**: avg bear Sharpe = {bear_sharpe_avg:.2f}, "
                f"avg bull Sharpe = {bull_sharpe_avg:.2f} "
                f"({'better in bull' if bull_sharpe_avg > bear_sharpe_avg else 'holds up in bear'})"
            )

    lines += ["", "---", f"_Source: `scripts/regime_comparison.py`_", ""]
    return "\n".join(lines)


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    logger.info("=== Regime Detector Comparison ===")
    logger.info(f"DATA_STORAGE_PATH: {STORAGE_PATH}")

    # 1. Load data
    close_prices, open_prices, ohlcv, macro_prices, sentiment_prices, available = load_data()
    universe = [s for s in UNIVERSE if s in available]
    logger.info(f"Universe for backtests: {universe}")

    # 2. Fit detectors
    vix_det, hmm_det = fit_detectors(close_prices, sentiment_prices)

    # Build regime series over the full price index
    price_index = close_prices.index
    vix_regimes = vix_det.predict_series(price_index)
    hmm_regimes = hmm_det.predict_series(price_index)

    # Regime distribution
    def regime_dist(series: pd.Series) -> dict:
        return {int(k): int(v) for k, v in series.value_counts().items()}

    regime_distribution = {
        "VIX": regime_dist(vix_regimes),
        "HMM": regime_dist(hmm_regimes),
    }
    logger.info(f"VIX regime distribution: {regime_distribution['VIX']}")
    logger.info(f"HMM regime distribution: {regime_distribution['HMM']}")

    # 3. Run backtests for each strategy
    all_results = []
    for strat in STRATEGIES:
        score = run_strategy(
            strat=strat,
            universe=universe,
            close_prices=close_prices,
            open_prices=open_prices,
            ohlcv=ohlcv,
            macro_prices=macro_prices,
            sentiment_prices=sentiment_prices,
        )
        if score is None or score.daily_returns is None:
            logger.warning(f"Skipping {strat['label']} — no daily_returns")
            continue

        daily_rets = score.daily_returns
        # Ensure datetime index for alignment
        if not isinstance(daily_rets.index, pd.DatetimeIndex):
            daily_rets.index = pd.to_datetime(daily_rets.index)

        rows = []
        for det_name, regime_series in [("VIX", vix_regimes), ("HMM", hmm_regimes)]:
            for regime_int, regime_name in [(0, "bear"), (1, "sideways"), (2, "bull")]:
                stats = conditional_stats(daily_rets, regime_series, regime_int)
                rows.append({
                    "detector": det_name,
                    "regime_name": regime_name,
                    **stats,
                })
                logger.info(
                    f"  {strat['id']} | {det_name} | {regime_name}: "
                    f"n={stats['n_days']}  Sharpe={stats['sharpe']:.3f}  "
                    f"AnnRet={stats['ann_return_pct']:.2f}%"
                )

        all_results.append({
            "strategy": strat,
            "full_period": {
                "sharpe": score.sharpe,
                "cagr": score.cagr,
                "max_dd": score.max_dd,
                "psr": score.psr,
                "passed": score.passed,
            },
            "rows": rows,
        })

    # 4. Write output
    md = build_markdown(all_results, regime_distribution)

    out_path = STORAGE_PATH / "regime_comparison.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md)
    logger.info(f"Written: {out_path}")

    # Obsidian copy
    obsidian_path = Path(
        "/Users/a004/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian"
        "/Research/AlphaGPT-Runs/regime_detector_comparison.md"
    )
    try:
        obsidian_path.parent.mkdir(parents=True, exist_ok=True)
        obsidian_path.write_text(md)
        logger.info(f"Written to Obsidian: {obsidian_path}")
    except Exception as e:
        logger.warning(f"Could not write Obsidian file: {e}")

    logger.info("=== Done ===")
    print(md)


if __name__ == "__main__":
    main()
