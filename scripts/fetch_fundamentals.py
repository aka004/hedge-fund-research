#!/usr/bin/env python3
"""
Fetch quarterly fundamentals from SEC EDGAR Company Facts API.

Uses actual SEC filing dates (no look-ahead bias). Data goes back 10+ years.
No API key needed — just a User-Agent header (SEC requirement).

Output: parquet/fundamentals_quarterly/{symbol}.parquet
Columns: period_end, filed_date, total_revenue, net_income, total_expenses, ebitda

Usage:
    python scripts/fetch_fundamentals.py
    python scripts/fetch_fundamentals.py --symbols AAPL MSFT NVDA
"""

import argparse
import json
import logging
import sys
import time
import urllib.request
from pathlib import Path

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
FUND_DIR = PARQUET_DIR / "fundamentals_quarterly"
USER_AGENT = "HedgeFundResearch research@example.com"

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


def fetch_ticker_to_cik() -> dict[str, str]:
    """Download SEC ticker → CIK mapping."""
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
    """Extract quarterly values for the first matching tag.

    Filters to 10-Q and 10-K forms. Deduplicates by keeping only
    single-quarter periods (~90 days) to avoid cumulative YTD values.
    """
    usgaap = facts.get("facts", {}).get("us-gaap", {})

    for tag in tags:
        if tag not in usgaap:
            continue
        units = usgaap[tag].get("units", {})
        entries = units.get("USD", [])
        if not entries:
            continue

        results = []
        seen = set()
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

            # Deduplicate by (end_date, form)
            key = (end, form)
            if key in seen:
                continue
            seen.add(key)

            results.append({
                "period_end": end,
                "filed_date": filed,
                "form": form,
                "value": float(val),
            })

        if results:
            return results

    return []


def build_quarterly_df(facts: dict) -> pd.DataFrame | None:
    """Build a quarterly DataFrame from SEC EDGAR facts."""
    revenue = extract_quarterly(facts, REVENUE_TAGS)
    net_income = extract_quarterly(facts, NET_INCOME_TAGS)
    expenses = extract_quarterly(facts, EXPENSES_TAGS)
    ebitda = extract_quarterly(facts, EBITDA_TAGS)

    if not revenue and not net_income:
        return None

    # Build lookup dicts keyed by period_end
    def to_dict(entries):
        d = {}
        for e in entries:
            d[e["period_end"]] = {"value": e["value"], "filed_date": e["filed_date"]}
        return d

    rev_d = to_dict(revenue)
    ni_d = to_dict(net_income)
    exp_d = to_dict(expenses)
    ebitda_d = to_dict(ebitda)

    # Union of all period_end dates
    all_dates = sorted(set(list(rev_d) + list(ni_d)))
    if not all_dates:
        return None

    rows = []
    for dt in all_dates:
        # Use the latest filing date among available fields
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

        # Derive expenses from revenue - net_income if not available
        if row["total_expenses"] is None and row["total_revenue"] and row["net_income"]:
            row["total_expenses"] = row["total_revenue"] - row["net_income"]

        rows.append(row)

    df = pd.DataFrame(rows)
    df["period_end"] = pd.to_datetime(df["period_end"])
    df["filed_date"] = pd.to_datetime(df["filed_date"])
    return df.sort_values("period_end").reset_index(drop=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="Fetch fundamentals from SEC EDGAR")
    ap.add_argument("--symbols", nargs="*", default=None)
    ap.add_argument("--force", action="store_true", help="Re-fetch even if cached")
    args = ap.parse_args()

    if args.symbols:
        symbols = [s.upper() for s in args.symbols]
    else:
        prices_dir = PARQUET_DIR / "prices"
        symbols = sorted([p.stem for p in prices_dir.glob("*.parquet")])

    FUND_DIR.mkdir(parents=True, exist_ok=True)

    # Build ticker → CIK map
    logger.info("Fetching SEC ticker → CIK mapping...")
    ticker_to_cik = fetch_ticker_to_cik()
    logger.info(f"Mapped {len(ticker_to_cik)} tickers to CIKs")

    success = 0
    skipped = 0
    no_cik = 0
    no_data = 0

    logger.info(f"Fetching fundamentals for {len(symbols)} symbols from SEC EDGAR")

    for i, symbol in enumerate(symbols, 1):
        out_path = FUND_DIR / f"{symbol}.parquet"
        if out_path.exists() and not args.force:
            skipped += 1
            if i % 100 == 0:
                logger.info(f"  [{i}/{len(symbols)}] {success} ok, {skipped} cached, {no_cik} no CIK")
            continue

        # Handle ticker variants (e.g., BRK.B → BRK-B)
        cik = ticker_to_cik.get(symbol)
        if not cik:
            alt = symbol.replace(".", "-")
            cik = ticker_to_cik.get(alt)
        if not cik:
            alt = symbol.replace("-", ".")
            cik = ticker_to_cik.get(alt)
        if not cik:
            no_cik += 1
            continue

        facts = fetch_company_facts(cik)
        if not facts:
            no_data += 1
            time.sleep(0.1)
            continue

        df = build_quarterly_df(facts)
        if df is not None and len(df) >= 4:
            df.to_parquet(out_path, index=False)
            success += 1
        else:
            no_data += 1

        if i % 100 == 0:
            logger.info(
                f"  [{i}/{len(symbols)}] {success} ok, {skipped} cached, "
                f"{no_cik} no CIK, {no_data} no data"
            )

        time.sleep(0.1)  # 10 req/sec courtesy limit

    logger.info(
        f"Done: {success} fetched, {skipped} cached, "
        f"{no_cik} no CIK, {no_data} no data → {FUND_DIR}"
    )


if __name__ == "__main__":
    main()
