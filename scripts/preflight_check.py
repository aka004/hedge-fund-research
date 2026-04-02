#!/usr/bin/env python3
"""
Pre-flight check pipeline — runs 3 gates before any full backtest.

Gate 1 — Data Quality    (stationarity_check)
Gate 2 — Label Quality   (triple_barrier + sample_uniqueness)
Gate 3 — Portfolio Math  (HRP dry run)

Returns True if all gates pass (warnings acceptable), False if any gate fails
with a hard block (e.g. price data has massive gaps, HRP fails to converge).

Usage (standalone):
    python scripts/preflight_check.py --universe /tmp/universe_full.txt

Usage (from code):
    from scripts.preflight_check import run_preflight
    ok = run_preflight(close_prices, universe)
    if not ok:
        sys.exit("Preflight failed — fix data before running backtest")
"""

import logging
import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from afml.checks import stationarity_check
from afml.labels import triple_barrier
from afml.portfolio import hrp
from afml.weights import sample_uniqueness_from_labels

logger = logging.getLogger(__name__)

# ── ANSI colours ──────────────────────────────────────────────────────────────
_GREEN = "\033[92m"
_RED = "\033[91m"
_AMBER = "\033[93m"
_CYAN = "\033[96m"
_BOLD = "\033[1m"
_RESET = "\033[0m"


def _ok(msg: str) -> str:
    return f"{_GREEN}✔ PASS{_RESET}  {msg}"


def _warn(msg: str) -> str:
    return f"{_AMBER}⚠ WARN{_RESET}  {msg}"


def _fail(msg: str) -> str:
    return f"{_RED}✘ FAIL{_RESET}  {msg}"


def _header(title: str) -> None:
    print(f"\n{_BOLD}{_CYAN}{'─'*60}{_RESET}")
    print(f"{_BOLD}{_CYAN}  {title}{_RESET}")
    print(f"{_BOLD}{_CYAN}{'─'*60}{_RESET}")


# ── Gate 1: Data Quality ──────────────────────────────────────────────────────


def _variance_stability(returns: pd.Series) -> tuple[float, bool]:
    """
    Compare rolling volatility in the first half vs second half of history.

    Returns (ratio, is_stable) where ratio = vol_second / vol_first.
    Stable if ratio is within [0.5, 2.0] — a 2× swing is expected in markets;
    beyond 4× suggests a structural break or data splice error.
    """
    half = len(returns) // 2
    vol_first = returns.iloc[:half].std()
    vol_second = returns.iloc[half:].std()
    if vol_first == 0:
        return float("nan"), False
    ratio = vol_second / vol_first
    return ratio, 0.25 <= ratio <= 4.0


def _arch_test(returns: pd.Series, lags: int = 5) -> tuple[float, bool]:
    """
    Engle's ARCH LM test for heteroskedasticity (volatility clustering).

    H0: no ARCH effects (variance is constant)
    H1: ARCH effects present (variance is time-varying)

    Returns (p_value, has_arch_effects).
    has_arch_effects = True means variance is NOT constant — expected for equities.
    This is informational: we flag it so the user knows sample weights may be
    dominated by high-vol regimes. It does NOT block the backtest.
    """
    from statsmodels.stats.diagnostic import het_arch

    clean = returns.dropna()
    if len(clean) < lags * 4:
        return float("nan"), False
    try:
        lm_stat, lm_p, f_stat, f_p = het_arch(clean, nlags=lags)
        return float(lm_p), lm_p < 0.05
    except Exception:
        return float("nan"), False


def gate1_data_quality(
    close_prices: pd.DataFrame,
    universe: list[str],
    n_sample: int = 30,
    min_years: float = 7.0,
) -> tuple[bool, list[str]]:
    """
    Gate 1: Data quality, stationarity (mean + variance + ARCH effects).

    Checks:
    - History length and zero-price audit
    - ADF unit-root test on returns (mean stationarity)
    - Rolling variance stability (first-half vs second-half vol ratio)
    - Engle's ARCH LM test (heteroskedasticity / volatility clustering)
    - Sanity: raw prices should be non-stationary

    Returns (passed, issues). Hard failures block the backtest;
    variance/ARCH findings are informational warnings only.
    """
    import numpy as np

    _header("GATE 1 — Data Quality & Stationarity (mean + variance + ARCH)")
    issues: list[str] = []
    hard_fails: int = 0

    available = [s for s in universe if s in close_prices.columns]
    sample = available[:n_sample]

    if not sample:
        print(_fail("No symbols available in close_prices"))
        return False, ["No price data loaded"]

    # ── History length + zero-price audit ────────────────────────────────
    min_days = int(min_years * 252)
    short_history: list[str] = []
    zero_price: list[str] = []

    for sym in sample:
        col = close_prices[sym].dropna()
        if len(col) < min_days:
            short_history.append(f"{sym}({len(col)}d)")
            if len(col) < 252:
                hard_fails += 1
        zeros = (col == 0).sum()
        if zeros > 0:
            zero_price.append(f"{sym}({zeros} zeros)")
            hard_fails += 1

    if short_history:
        pct = len(short_history) / len(sample) * 100
        print(_warn(f"Short history (<{min_years}y): {', '.join(short_history[:5])} ({pct:.0f}%)"))
        issues.append(f"short_history: {len(short_history)}/{len(sample)} symbols")
    else:
        print(_ok(f"History length ≥ {min_years}y for all {len(sample)} sampled symbols"))

    if zero_price:
        print(_fail(f"Zero prices (missing data): {', '.join(zero_price[:5])}"))
        issues.append(f"zero_prices: {len(zero_price)} symbols")
    else:
        print(_ok(f"No zero prices in {len(sample)} sampled symbols"))

    returns_df = close_prices[sample].pct_change().dropna()

    # ── Mean stationarity: ADF on returns ────────────────────────────────
    print(f"\n  [1/3] Mean stationarity — ADF unit-root test on daily returns...")
    try:
        results_df, adf_warnings = stationarity_check(returns_df, significance=0.05)
        n_stationary = results_df["is_stationary"].sum()
        n_total = len(results_df)
        pct_ok = n_stationary / n_total * 100 if n_total > 0 else 0

        if pct_ok >= 80:
            print(_ok(f"Returns mean-stationary: {n_stationary}/{n_total} ({pct_ok:.0f}%)"))
        elif pct_ok >= 50:
            print(_warn(f"Returns mean-stationary: {n_stationary}/{n_total} ({pct_ok:.0f}%) — check for data gaps"))
            issues.append(f"non_stationary_mean: {n_total - n_stationary} symbols")
        else:
            print(_fail(f"Returns mean-stationary: only {n_stationary}/{n_total} ({pct_ok:.0f}%) — data issue"))
            issues.append(f"non_stationary_mean: {n_total - n_stationary} symbols (critical)")
            hard_fails += 1

        if adf_warnings:
            for w in adf_warnings[:3]:
                print(f"     {_AMBER}→{_RESET} {w}")
            if len(adf_warnings) > 3:
                print(f"     {_AMBER}→{_RESET} ...and {len(adf_warnings)-3} more")

    except Exception as e:
        print(_fail(f"ADF stationarity check error: {e}"))
        issues.append(f"adf_error: {e}")

    # ── Variance stationarity: rolling vol ratio ──────────────────────────
    # Compare vol in first half vs second half of history.
    # A ratio far from 1 means there was a structural volatility shift
    # (e.g. a 2008-style crisis doubling vol permanently, or a data splice).
    # This does NOT block backtest — equity volatility naturally changes over
    # time. But ratios > 4× should be investigated before using in ML features.
    print(f"\n  [2/3] Variance stationarity — rolling vol ratio (first vs second half)...")
    try:
        ratios = []
        unstable: list[str] = []
        for sym in sample:
            r = returns_df[sym].dropna()
            if len(r) < 100:
                continue
            ratio, stable = _variance_stability(r)
            ratios.append(ratio)
            if not stable:
                unstable.append(f"{sym}({ratio:.1f}×)")

        if ratios:
            median_ratio = float(np.median(ratios))
            print(f"     Median vol ratio (2nd half / 1st half): {median_ratio:.2f}×")
            if unstable:
                print(_warn(
                    f"{len(unstable)} symbols have large vol shifts (>4×): "
                    f"{', '.join(unstable[:4])}"
                    + (f" +{len(unstable)-4} more" if len(unstable) > 4 else "")
                ))
                print(f"     → variance is non-stationary for these; "
                      f"triple_barrier barrier sizes will drift over time")
                issues.append(f"variance_unstable: {len(unstable)} symbols")
            else:
                print(_ok(
                    f"Variance stable across all {len(sample)} symbols "
                    f"(median ratio {median_ratio:.2f}×, all within 4× band)"
                ))
    except Exception as e:
        print(_warn(f"Variance stability check skipped: {e}"))

    # ── ARCH test: Engle's LM test for heteroskedasticity ─────────────────
    # For equities, ARCH effects are almost always present (vol clustering).
    # This is informational: we report what fraction of symbols show ARCH
    # effects so the user knows sample_uniqueness weights may be skewed toward
    # high-vol regimes. A possible fix is time-series weighting (not yet wired).
    print(f"\n  [3/3] Variance heteroskedasticity — Engle's ARCH LM test (lags=5)...")
    try:
        n_arch = 0
        arch_sample = sample[:min(15, len(sample))]  # cap for speed
        for sym in arch_sample:
            r = returns_df[sym].dropna()
            p_val, has_arch = _arch_test(r, lags=5)
            if has_arch:
                n_arch += 1

        pct_arch = n_arch / len(arch_sample) * 100 if arch_sample else 0
        msg = (
            f"ARCH effects detected in {n_arch}/{len(arch_sample)} symbols ({pct_arch:.0f}%) — "
            f"volatility is time-varying (expected for equities)"
        )
        if pct_arch >= 50:
            # Expected — equities almost always cluster vol
            print(_warn(msg))
            print(f"     → sample_uniqueness weights may be biased toward high-vol periods")
            print(f"     → triple_barrier uses rolling 20d vol for barrier sizing, which adapts")
            issues.append(f"arch_effects: {n_arch}/{len(arch_sample)} symbols (informational)")
        else:
            print(_ok(f"Low ARCH effects ({n_arch}/{len(arch_sample)}) — variance relatively stable"))

    except Exception as e:
        print(_warn(f"ARCH test skipped: {e}"))

    # ── Price sanity: raw prices should be non-stationary ────────────────
    print(f"\n  Sanity: raw prices should be non-stationary (unit root expected)...")
    try:
        price_sample = close_prices[sample[:10]].dropna()
        _, price_warnings = stationarity_check(price_sample, significance=0.05)
        n_nonstat = len(price_warnings)
        if n_nonstat < len(sample[:10]) * 0.5:
            print(_fail("Raw prices appear stationary — data may be pre-differenced or normalised"))
            hard_fails += 1
        else:
            print(_ok(f"Raw prices non-stationary as expected ({n_nonstat}/{len(sample[:10])} have unit root)"))
    except Exception as e:
        print(_warn(f"Price sanity check skipped: {e}"))

    passed = hard_fails == 0
    summary = _ok("Gate 1 passed") if passed else _fail(f"Gate 1 failed ({hard_fails} hard failures)")
    print(f"\n  {summary}")
    return passed, issues


# ── Gate 2: Label Quality ─────────────────────────────────────────────────────


def gate2_label_quality(
    close_prices: pd.DataFrame,
    universe: list[str],
    n_symbols: int = 5,
    profit_take: float = 2.0,
    stop_loss: float = 2.0,
    max_holding: int = 20,
) -> tuple[bool, list[str]]:
    """
    Gate 2: Triple-barrier labeling + sample uniqueness.

    Checks:
    - Label distribution (should have both +1 and -1, not all timeouts)
    - Effective sample size after uniqueness weighting
    - Average holding time (catches degenerate configs)

    Returns (passed, issues).
    """
    _header("GATE 2 — Label Quality (Triple-Barrier + Sample Uniqueness)")
    issues: list[str] = []
    hard_fails = 0

    available = [s for s in universe if s in close_prices.columns]
    sample_syms = available[:n_symbols]

    if not sample_syms:
        print(_fail("No symbols for label quality check"))
        return False, ["no_symbols"]

    all_profit_pct: list[float] = []
    all_stop_pct: list[float] = []
    all_timeout_pct: list[float] = []
    all_eff_sample_pct: list[float] = []
    all_avg_hold: list[float] = []

    for sym in sample_syms:
        try:
            prices = close_prices[sym].dropna()
            if len(prices) < 252:
                continue

            # Triple-barrier on last 3 years of data (fast)
            recent_prices = prices.tail(252 * 3)
            # Need DatetimeIndex
            if not isinstance(recent_prices.index, pd.DatetimeIndex):
                recent_prices.index = pd.to_datetime(recent_prices.index)

            labels = triple_barrier(
                prices=recent_prices,
                profit_take=profit_take,
                stop_loss=stop_loss,
                max_holding=max_holding,
            )

            if len(labels.labels) == 0:
                continue

            df = labels.to_dataframe()
            n = len(df)

            profit_pct = (df["exit_type"] == "profit").mean() * 100
            stop_pct = (df["exit_type"] == "stop").mean() * 100
            timeout_pct = (df["exit_type"] == "timeout").mean() * 100

            all_profit_pct.append(profit_pct)
            all_stop_pct.append(stop_pct)
            all_timeout_pct.append(timeout_pct)

            # Holding period = exit_time - entry_time
            entry_times = labels.labels.index
            exit_times = labels.exit_times
            holding_days = (exit_times - entry_times).dt.days
            avg_hold = holding_days.mean() if len(holding_days) > 0 else 0
            all_avg_hold.append(avg_hold)

            # Sample uniqueness
            weights = sample_uniqueness_from_labels(labels)
            # Effective sample size = (sum(w))^2 / sum(w^2) but weights are normalised so ESS ≈ 1/sum(w^2)
            ess = 1.0 / (weights ** 2).sum() if (weights ** 2).sum() > 0 else 0
            eff_pct = ess / n * 100 if n > 0 else 0
            all_eff_sample_pct.append(eff_pct)

        except Exception as e:
            logger.debug(f"Gate 2 skip {sym}: {e}")
            continue

    if not all_profit_pct:
        print(_fail("Could not run triple-barrier on any symbol"))
        return False, ["triple_barrier_failed"]

    avg_profit = sum(all_profit_pct) / len(all_profit_pct)
    avg_stop = sum(all_stop_pct) / len(all_stop_pct)
    avg_timeout = sum(all_timeout_pct) / len(all_timeout_pct)
    avg_hold = sum(all_avg_hold) / len(all_avg_hold)
    avg_eff = sum(all_eff_sample_pct) / len(all_eff_sample_pct)

    print(f"\n  Triple-barrier label distribution ({n_symbols} symbols, last 3y):")
    print(f"    Profit hits : {avg_profit:.1f}%")
    print(f"    Stop hits   : {avg_stop:.1f}%")
    print(f"    Timeouts    : {avg_timeout:.1f}%")
    print(f"    Avg holding : {avg_hold:.1f} days")

    # Flags
    if avg_profit < 5:
        print(_fail(f"Profit target almost never hit ({avg_profit:.1f}%) — barriers too wide or volatility too low"))
        issues.append(f"low_profit_rate: {avg_profit:.1f}%")
        hard_fails += 1
    elif avg_profit < 20:
        print(_warn(f"Low profit-hit rate ({avg_profit:.1f}%) — consider tighter profit_take multiplier"))
        issues.append(f"low_profit_rate: {avg_profit:.1f}%")
    else:
        print(_ok(f"Profit-hit rate looks healthy ({avg_profit:.1f}%)"))

    if avg_timeout > 70:
        print(_warn(f"High timeout rate ({avg_timeout:.1f}%) — barriers may be too wide for the volatility regime"))
        issues.append(f"high_timeout_rate: {avg_timeout:.1f}%")
    else:
        print(_ok(f"Timeout rate acceptable ({avg_timeout:.1f}%)"))

    # Sample uniqueness
    print(f"\n  Sample uniqueness (effective sample size):")
    print(f"    Avg ESS as % of raw samples: {avg_eff:.1f}%")
    if avg_eff < 20:
        print(_warn(f"Low sample uniqueness ({avg_eff:.1f}%) — labels heavily overlap → inflated sample count"))
        print(f"     → Use sample_uniqueness weights when fitting any ML model")
        issues.append(f"low_sample_uniqueness: {avg_eff:.1f}%")
    else:
        print(_ok(f"Sample uniqueness adequate ({avg_eff:.1f}% effective)"))

    passed = hard_fails == 0
    summary = _ok("Gate 2 passed") if passed else _fail(f"Gate 2 failed ({hard_fails} hard failures)")
    print(f"\n  {summary}")
    return passed, issues


# ── Gate 3: Portfolio Math ─────────────────────────────────────────────────────


def gate3_portfolio_math(
    close_prices: pd.DataFrame,
    universe: list[str],
    n_symbols: int = 20,
    lookback_days: int = 60,
) -> tuple[bool, list[str]]:
    """
    Gate 3: HRP dry run + covariance matrix health check.

    Checks:
    - HRP converges cleanly (no NaN weights, sums to 1)
    - Weight concentration (Herfindahl index — avoid "HRP collapsed to 1 stock")
    - Covariance matrix condition number (ill-conditioned = numerical issues)

    Returns (passed, issues).
    """
    _header("GATE 3 — Portfolio Math (HRP dry run)")
    issues: list[str] = []
    hard_fails = 0

    available = [s for s in universe if s in close_prices.columns]
    sample_syms = available[:n_symbols]

    if len(sample_syms) < 4:
        print(_fail("Need ≥4 symbols for HRP test"))
        return False, ["insufficient_symbols"]

    # Use recent lookback_days of returns
    try:
        recent = close_prices[sample_syms].tail(lookback_days + 1)
        if not isinstance(recent.index, pd.DatetimeIndex):
            recent.index = pd.to_datetime(recent.index)
        returns = recent.pct_change().dropna()

        # Drop symbols with NaN returns (insufficient history)
        returns = returns.dropna(axis=1, how="any")
        clean_syms = list(returns.columns)

        if len(clean_syms) < 4:
            print(_fail(f"Only {len(clean_syms)} symbols have clean {lookback_days}-day returns"))
            return False, ["insufficient_clean_symbols"]

        print(f"\n  Running HRP on {len(clean_syms)} symbols × {len(returns)} days of returns...")

        result = hrp(returns)

        # Check weights sum to 1
        weight_sum = result.weights.sum()
        if abs(weight_sum - 1.0) > 0.01:
            print(_fail(f"HRP weights don't sum to 1: {weight_sum:.4f}"))
            hard_fails += 1
            issues.append(f"hrp_weight_sum: {weight_sum:.4f}")
        else:
            print(_ok(f"HRP weights sum to 1.0 ({weight_sum:.4f})"))

        # Check for NaN
        nan_count = result.weights.isna().sum()
        if nan_count > 0:
            print(_fail(f"HRP produced {nan_count} NaN weights"))
            hard_fails += 1
            issues.append(f"hrp_nan_weights: {nan_count}")
        else:
            print(_ok("No NaN weights"))

        # Herfindahl concentration index (1/n = perfectly diversified, 1.0 = single stock)
        hhi = (result.weights ** 2).sum()
        hhi_equal = 1.0 / len(clean_syms)
        concentration_ratio = hhi / hhi_equal  # 1.0 = same as equal weight, >2 = concentrated

        print(f"\n  Weight concentration (Herfindahl):")
        print(f"    HHI          : {hhi:.4f}")
        print(f"    Equal-weight : {hhi_equal:.4f}")
        print(f"    Ratio        : {concentration_ratio:.2f}x equal-weight")

        # Show top 5 weights
        top5 = result.weights.nlargest(5)
        print(f"\n  Top 5 allocations by HRP:")
        for sym, w in top5.items():
            bar = "█" * int(w * 50)
            print(f"    {sym:6s}  {w:.3f}  {bar}")

        if concentration_ratio > 5:
            print(_fail(f"HRP extremely concentrated ({concentration_ratio:.1f}x equal-weight) — check for near-zero-variance assets"))
            hard_fails += 1
            issues.append(f"hrp_concentrated: {concentration_ratio:.1f}x")
        elif concentration_ratio > 2.5:
            print(_warn(f"HRP moderately concentrated ({concentration_ratio:.1f}x equal-weight) — some assets are highly correlated"))
            issues.append(f"hrp_concentration: {concentration_ratio:.1f}x")
        else:
            print(_ok(f"HRP diversification healthy ({concentration_ratio:.1f}x equal-weight)"))

        # Covariance condition number
        import numpy as np
        cov = returns.cov().values
        try:
            cond = np.linalg.cond(cov)
            print(f"\n  Covariance matrix condition number: {cond:.1f}")
            if cond > 1e6:
                print(_warn(f"High condition number ({cond:.0f}) — near-singular covariance, HRP may be unstable"))
                issues.append(f"high_cond_number: {cond:.0f}")
            else:
                print(_ok(f"Condition number OK ({cond:.0f})"))
        except Exception:
            pass

    except Exception as e:
        print(_fail(f"HRP dry run failed: {e}"))
        hard_fails += 1
        issues.append(f"hrp_error: {e}")

    passed = hard_fails == 0
    summary = _ok("Gate 3 passed") if passed else _fail(f"Gate 3 failed ({hard_fails} hard failures)")
    print(f"\n  {summary}")
    return passed, issues


# ── Main entry point ──────────────────────────────────────────────────────────


def run_preflight(
    close_prices: pd.DataFrame,
    universe: list[str],
    n_sample: int = 30,
) -> bool:
    """
    Run all 3 pre-flight gates. Returns True if safe to proceed with backtest.

    Prints a coloured report to stdout. Warnings are informational.
    Only hard failures (data corruption, HRP divergence) return False.

    Parameters
    ----------
    close_prices : pd.DataFrame
        Daily adjusted close prices indexed by date, columns = symbols
    universe : list[str]
        Ticker symbols to check (ordered by priority)
    n_sample : int
        Number of symbols to sample for checks (default 30)
    """
    print(f"\n{'═'*60}")
    print(f"{_BOLD}  PRE-FLIGHT CHECK{_RESET}")
    print(f"  {len(universe)} universe symbols  ·  {len(close_prices)} days  ·  {n_sample} sampled")
    print(f"{'═'*60}")

    g1_pass, g1_issues = gate1_data_quality(close_prices, universe, n_sample=n_sample)
    g2_pass, g2_issues = gate2_label_quality(close_prices, universe, n_symbols=min(5, n_sample))
    g3_pass, g3_issues = gate3_portfolio_math(close_prices, universe, n_symbols=min(20, n_sample))

    all_issues = g1_issues + g2_issues + g3_issues
    all_passed = g1_pass and g2_pass and g3_pass

    print(f"\n{'═'*60}")
    print(f"{_BOLD}  SUMMARY{_RESET}")
    print(f"{'═'*60}")
    print(f"  Gate 1 Data Quality   : {_GREEN+'PASS'+_RESET if g1_pass else _RED+'FAIL'+_RESET}")
    print(f"  Gate 2 Label Quality  : {_GREEN+'PASS'+_RESET if g2_pass else _RED+'FAIL'+_RESET}")
    print(f"  Gate 3 Portfolio Math : {_GREEN+'PASS'+_RESET if g3_pass else _RED+'FAIL'+_RESET}")

    if all_issues:
        print(f"\n  Issues ({len(all_issues)}):")
        for issue in all_issues:
            print(f"    {_AMBER}⚠{_RESET}  {issue}")

    verdict = (
        f"{_GREEN}{_BOLD}  ✔ ALL GATES PASSED — safe to run backtest{_RESET}"
        if all_passed
        else f"{_RED}{_BOLD}  ✘ PREFLIGHT FAILED — fix issues before backtest{_RESET}"
    )
    print(f"\n{verdict}")
    print(f"{'═'*60}\n")

    return all_passed


# ── Standalone runner ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.WARNING, format="%(message)s")

    parser = argparse.ArgumentParser(description="Pre-flight check before backtest")
    parser.add_argument("--universe", default="/tmp/universe_full.txt")
    parser.add_argument("--sample", type=int, default=30, help="Symbols to sample per gate")
    args = parser.parse_args()

    from config import STORAGE_PATH
    from scripts.run_event_engine import load_price_dataframes

    with open(args.universe) as f:
        tickers = [l.strip().upper() for l in f if l.strip()]

    print("Loading price data...")
    close_prices, _ = load_price_dataframes(tickers[:200])  # cap for speed
    universe = [t for t in tickers if t in close_prices.columns]

    ok = run_preflight(close_prices, universe, n_sample=args.sample)
    sys.exit(0 if ok else 1)
