#!/usr/bin/env python3
"""
Fetch quarterly fundamentals from SEC EDGAR (primary) + FMP (fallback).

SEC EDGAR: Free, no API key, actual filing dates, 10+ year history.
FMP: Requires API key (FMP_API_KEY env var), fills coverage gaps.

Uses actual filing dates (no look-ahead bias).

Output: parquet/fundamentals_quarterly/{symbol}.parquet
Columns: period_end, filed_date, total_revenue, net_income, total_expenses, ebitda

Usage:
    python scripts/fetch_fundamentals.py
    python scripts/fetch_fundamentals.py --symbols AAPL MSFT NVDA
    python scripts/fetch_fundamentals.py --fmp-only       # skip EDGAR, only FMP gaps
    python scripts/fetch_fundamentals.py --force           # re-fetch everything
"""

import argparse
import json
import logging
import os
import sys
import time
import urllib.request
from pathlib import Path

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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

PARQUET_DIR = STORAGE_PATH / "parquet"
FUND_DIR = PARQUET_DIR / "fundamentals_quarterly"
USER_AGENT = "HedgeFundResearch research@example.com"

# ── SEC EDGAR config ─────────────────────────────────────────────────────────

# Revenue tags in priority order (companies use different ones)
REVENUE_TAGS = [
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "SalesRevenueNet",
    "SalesRevenueGoodsNet",
]
NET_INCOME_TAGS = ["NetIncomeLoss"]
EXPENSES_TAGS = ["CostsAndExpenses", "OperatingExpenses"]
EBITDA_TAGS = ["EBITDA"]


# ═══════════════════════════════════════════════════════════════════════════════
# SEC EDGAR — Primary source (free, no key)
# ═══════════════════════════════════════════════════════════════════════════════


def fetch_ticker_to_cik() -> dict[str, str]:
    """Download SEC ticker -> CIK mapping."""
    url = "https://www.sec.gov/files/company_tickers.json"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    data = json.loads(urllib.request.urlopen(req, timeout=30).read())
    mapping = {}
    for entry in data.values():
        ticker = entry["ticker"].upper()
        cik = str(entry["cik_str"]).zfill(10)
        mapping[ticker] = cik
    return mapping


def fetch_company_facts(cik: str) -> dict | None:
    """Fetch all XBRL facts for a company from SEC EDGAR."""
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=30).read())
    except Exception:
        return None


def extract_quarterly(facts: dict, tags: list[str]) -> list[dict]:
    """Extract quarterly values from ALL matching tags, merged by period_end.

    Companies switch XBRL tags over time (e.g. AAPL switched from
    SalesRevenueNet to RevenueFromContractWithCustomer in ~2018).
    We merge across all tags, preferring the first tag in priority order
    when multiple tags cover the same period.

    Filters to 10-Q and 10-K forms. Deduplicates by keeping only
    single-quarter periods (~90 days) to avoid cumulative YTD values.
    """
    usgaap = facts.get("facts", {}).get("us-gaap", {})

    # Collect from all tags, keyed by period_end
    merged: dict[str, dict] = {}

    for tag in tags:
        if tag not in usgaap:
            continue
        units = usgaap[tag].get("units", {})
        entries = units.get("USD", [])
        if not entries:
            continue

        for e in entries:
            form = e.get("form", "")
            if form not in ("10-Q", "10-K"):
                continue

            start = e.get("start")
            end = e.get("end")
            filed = e.get("filed")
            val = e.get("val")

            if not all([end, filed, val is not None]):
                continue

            # For 10-Q: keep only quarterly periods (~60-100 days)
            # For 10-K: keep only annual periods (~350-380 days)
            if start:
                days = (pd.Timestamp(end) - pd.Timestamp(start)).days
                if form == "10-Q" and days > 120:
                    continue  # skip cumulative YTD values
                if form == "10-K" and days < 300:
                    continue

            # Only add if this period_end not already covered by a higher-priority tag
            key = (end, form)
            if key not in merged:
                merged[key] = {
                    "period_end": end,
                    "filed_date": filed,
                    "form": form,
                    "value": float(val),
                }

    return sorted(merged.values(), key=lambda r: r["period_end"])


def build_quarterly_df_edgar(facts: dict) -> pd.DataFrame | None:
    """Build a quarterly DataFrame from SEC EDGAR facts."""
    revenue = extract_quarterly(facts, REVENUE_TAGS)
    net_income = extract_quarterly(facts, NET_INCOME_TAGS)
    expenses = extract_quarterly(facts, EXPENSES_TAGS)
    ebitda = extract_quarterly(facts, EBITDA_TAGS)

    if not revenue and not net_income:
        return None

    def to_dict(entries):
        d = {}
        for e in entries:
            d[e["period_end"]] = {"value": e["value"], "filed_date": e["filed_date"]}
        return d

    rev_d = to_dict(revenue)
    ni_d = to_dict(net_income)
    exp_d = to_dict(expenses)
    ebitda_d = to_dict(ebitda)

    all_dates = sorted(set(list(rev_d) + list(ni_d)))
    if not all_dates:
        return None

    rows = []
    for dt in all_dates:
        filed_dates = []
        if dt in rev_d:
            filed_dates.append(rev_d[dt]["filed_date"])
        if dt in ni_d:
            filed_dates.append(ni_d[dt]["filed_date"])
        filed = max(filed_dates) if filed_dates else None

        row = {
            "period_end": dt,
            "filed_date": filed,
            "total_revenue": rev_d.get(dt, {}).get("value"),
            "net_income": ni_d.get(dt, {}).get("value"),
            "total_expenses": exp_d.get(dt, {}).get("value"),
            "ebitda": ebitda_d.get(dt, {}).get("value"),
        }

        if row["total_expenses"] is None and row["total_revenue"] and row["net_income"]:
            row["total_expenses"] = row["total_revenue"] - row["net_income"]

        rows.append(row)

    df = pd.DataFrame(rows)
    df["period_end"] = pd.to_datetime(df["period_end"])
    df["filed_date"] = pd.to_datetime(df["filed_date"])
    return df.sort_values("period_end").reset_index(drop=True)


def fetch_edgar(symbol: str, ticker_to_cik: dict) -> pd.DataFrame | None:
    """Fetch quarterly fundamentals from SEC EDGAR for a single symbol."""
    cik = ticker_to_cik.get(symbol)
    if not cik:
        for alt in [symbol.replace(".", "-"), symbol.replace("-", ".")]:
            cik = ticker_to_cik.get(alt)
            if cik:
                break
    if not cik:
        return None

    facts = fetch_company_facts(cik)
    if not facts:
        return None

    df = build_quarterly_df_edgar(facts)
    if df is not None and len(df) >= 4:
        return df
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# FMP — Fallback source (API key required)
# ═══════════════════════════════════════════════════════════════════════════════


def fetch_fmp_income(symbol: str, api_key: str) -> pd.DataFrame | None:
    """Fetch quarterly income statement from FMP stable API.

    Returns DataFrame with same schema as EDGAR output:
    period_end, filed_date, total_revenue, net_income, total_expenses, ebitda
    """
    url = (
        f"https://financialmodelingprep.com/stable/income-statement"
        f"?symbol={symbol}&period=quarter&limit=80&apikey={api_key}"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        raw = json.loads(urllib.request.urlopen(req, timeout=20).read())
    except Exception as e:
        logger.debug(f"FMP request failed for {symbol}: {e}")
        return None

    if not isinstance(raw, list) or not raw:
        return None

    rows = []
    for r in raw:
        period_end = r.get("date")
        filed_date = r.get("filingDate")
        revenue = r.get("revenue")
        net_income = r.get("netIncome")
        expenses = r.get("costAndExpenses")
        ebitda = r.get("ebitda")

        if not period_end:
            continue
        # Need at least revenue or net_income
        if revenue is None and net_income is None:
            continue

        # Derive expenses if missing
        if expenses is None and revenue is not None and net_income is not None:
            expenses = revenue - net_income

        rows.append({
            "period_end": period_end,
            "filed_date": filed_date,
            "total_revenue": float(revenue) if revenue is not None else None,
            "net_income": float(net_income) if net_income is not None else None,
            "total_expenses": float(expenses) if expenses is not None else None,
            "ebitda": float(ebitda) if ebitda is not None else None,
        })

    if len(rows) < 4:
        return None

    df = pd.DataFrame(rows)
    df["period_end"] = pd.to_datetime(df["period_end"])
    df["filed_date"] = pd.to_datetime(df["filed_date"])
    return df.sort_values("period_end").reset_index(drop=True)


# ═══════════════════════════════════════════════════════════════════════════════
# Quality check — is the EDGAR data sufficient?
# ═══════════════════════════════════════════════════════════════════════════════


def needs_fmp_fill(out_path: Path) -> bool:
    """Check if an existing parquet has critical data gaps.

    Returns True if revenue or net_income has >30% missing values,
    meaning FMP might fill the gaps.
    """
    if not out_path.exists():
        return True
    try:
        df = pd.read_parquet(out_path)
        if len(df) < 4:
            return True
        rev_missing = df["total_revenue"].isna().mean()
        ni_missing = df["net_income"].isna().mean()
        return rev_missing > 0.3 or ni_missing > 0.3
    except Exception:
        return True


def merge_edgar_fmp(edgar_df: pd.DataFrame | None, fmp_df: pd.DataFrame | None) -> pd.DataFrame | None:
    """Merge EDGAR and FMP data, preferring EDGAR for overlapping periods.

    EDGAR is preferred because it has XBRL-validated data.
    FMP fills periods where EDGAR has no data.
    """
    if edgar_df is None and fmp_df is None:
        return None
    if edgar_df is None:
        return fmp_df
    if fmp_df is None:
        return edgar_df

    # Use EDGAR as base, fill missing periods from FMP
    edgar_dates = set(edgar_df["period_end"].dt.strftime("%Y-%m-%d"))
    fmp_new_rows = fmp_df[
        ~fmp_df["period_end"].dt.strftime("%Y-%m-%d").isin(edgar_dates)
    ]

    if fmp_new_rows.empty:
        # FMP adds no new periods — but check if it fills NaN columns
        merged = edgar_df.copy()
        for _, fmp_row in fmp_df.iterrows():
            fmp_date = fmp_row["period_end"].strftime("%Y-%m-%d")
            mask = merged["period_end"].dt.strftime("%Y-%m-%d") == fmp_date
            if not mask.any():
                continue
            idx = merged[mask].index[0]
            for col in ["total_revenue", "net_income", "total_expenses", "ebitda"]:
                if pd.isna(merged.at[idx, col]) and pd.notna(fmp_row.get(col)):
                    merged.at[idx, col] = fmp_row[col]
            # Fill missing filing date
            if pd.isna(merged.at[idx, "filed_date"]) and pd.notna(fmp_row.get("filed_date")):
                merged.at[idx, "filed_date"] = fmp_row["filed_date"]
        return merged.sort_values("period_end").reset_index(drop=True)

    combined = pd.concat([edgar_df, fmp_new_rows], ignore_index=True)
    combined = combined.sort_values("period_end").reset_index(drop=True)
    return combined


# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════


def main() -> None:
    ap = argparse.ArgumentParser(description="Fetch fundamentals from SEC EDGAR + FMP")
    ap.add_argument("--symbols", nargs="*", default=None)
    ap.add_argument("--force", action="store_true", help="Re-fetch everything")
    ap.add_argument("--fmp-only", action="store_true", help="Only fill gaps via FMP")
    ap.add_argument("--no-fmp", action="store_true", help="Skip FMP fallback")
    args = ap.parse_args()

    if args.symbols:
        symbols = [s.upper() for s in args.symbols]
    else:
        prices_dir = PARQUET_DIR / "prices"
        symbols = sorted([p.stem for p in prices_dir.glob("*.parquet")])

    FUND_DIR.mkdir(parents=True, exist_ok=True)

    fmp_key = os.environ.get("FMP_API_KEY", "")
    has_fmp = bool(fmp_key) and not args.no_fmp

    # ── Phase 1: SEC EDGAR (primary source) ──────────────────────────────────
    if not args.fmp_only:
        logger.info("Fetching SEC ticker -> CIK mapping...")
        ticker_to_cik = fetch_ticker_to_cik()
        logger.info(f"Mapped {len(ticker_to_cik)} tickers to CIKs")

        edgar_ok = 0
        edgar_skip = 0
        edgar_fail = 0

        logger.info(f"Phase 1: EDGAR — fetching {len(symbols)} symbols")
        for i, symbol in enumerate(symbols, 1):
            out_path = FUND_DIR / f"{symbol}.parquet"
            if out_path.exists() and not args.force:
                edgar_skip += 1
                if i % 100 == 0:
                    logger.info(f"  [{i}/{len(symbols)}] {edgar_ok} ok, {edgar_skip} cached")
                continue

            df = fetch_edgar(symbol, ticker_to_cik)
            if df is not None:
                df.to_parquet(out_path, index=False)
                edgar_ok += 1
            else:
                edgar_fail += 1

            if i % 100 == 0:
                logger.info(
                    f"  [{i}/{len(symbols)}] {edgar_ok} ok, {edgar_skip} cached, "
                    f"{edgar_fail} failed"
                )
            time.sleep(0.1)

        logger.info(
            f"EDGAR done: {edgar_ok} fetched, {edgar_skip} cached, {edgar_fail} failed"
        )

    # ── Phase 2: FMP fallback (fill gaps) ────────────────────────────────────
    if has_fmp:
        # Find symbols that need FMP
        gap_symbols = []
        for symbol in symbols:
            out_path = FUND_DIR / f"{symbol}.parquet"
            if needs_fmp_fill(out_path):
                gap_symbols.append(symbol)

        if not gap_symbols:
            logger.info("Phase 2: FMP — no gaps to fill")
        else:
            logger.info(f"Phase 2: FMP — filling {len(gap_symbols)} symbols with gaps")
            fmp_ok = 0
            fmp_fail = 0

            for i, symbol in enumerate(gap_symbols, 1):
                out_path = FUND_DIR / f"{symbol}.parquet"

                # Load existing EDGAR data if available
                edgar_df = None
                if out_path.exists():
                    try:
                        edgar_df = pd.read_parquet(out_path)
                    except Exception:
                        pass

                fmp_df = fetch_fmp_income(symbol, fmp_key)
                if fmp_df is None:
                    fmp_fail += 1
                    if i % 50 == 0:
                        logger.info(f"  [{i}/{len(gap_symbols)}] {fmp_ok} filled, {fmp_fail} failed")
                    time.sleep(0.2)
                    continue

                merged = merge_edgar_fmp(edgar_df, fmp_df)
                if merged is not None and len(merged) >= 4:
                    merged.to_parquet(out_path, index=False)
                    fmp_ok += 1
                else:
                    fmp_fail += 1

                if i % 50 == 0:
                    logger.info(f"  [{i}/{len(gap_symbols)}] {fmp_ok} filled, {fmp_fail} failed")
                time.sleep(0.2)  # FMP rate limit: ~5 req/sec on free tier

            logger.info(f"FMP done: {fmp_ok} filled, {fmp_fail} still missing")
    elif not args.no_fmp and not fmp_key:
        logger.info("Phase 2: FMP — skipped (no FMP_API_KEY in .env)")

    # ── Summary ──────────────────────────────────────────────────────────────
    total_cached = sum(1 for s in symbols if (FUND_DIR / f"{s}.parquet").exists())
    logger.info(f"Final coverage: {total_cached}/{len(symbols)} symbols have fundamentals")


if __name__ == "__main__":
    main()
