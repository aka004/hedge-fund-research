#!/usr/bin/env python3
"""
Fetch Russell 2000 tech-sector universe with survivorship-bias mitigation.

Strategy:
  1. Download current IWM holdings CSV from iShares.
  2. Attempt to pull 4 historical IWM snapshots (2020-2023) from Wayback Machine.
  3. Union all tickers across all snapshots to include ever-members.
  4. Filter: sector in {Technology, Communication Services}.
  5. Filter: ADTV > $1M (last 252 days).
  6. Download full OHLCV history (2018-01-01 → today) via yfinance.
  7. Save parquets to data/cache/parquet/prices_russell2000/.
  8. Save ticker list to data/universes/russell2000_tech.txt.

Usage:
    python scripts/fetch_russell2000.py [--min-adtv 1_000_000] [--dry-run]
"""

import argparse
import io
import logging
import sys
import time
from pathlib import Path

import pandas as pd
import requests
import yfinance as yf

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

PARQUET_OUT_DIR = STORAGE_PATH / "parquet" / "prices_russell2000"
UNIVERSE_DIR = Path(__file__).parent.parent / "data" / "universes"
TICKER_LIST_PATH = UNIVERSE_DIR / "russell2000_tech.txt"

IWM_CSV_URL = (
    "https://www.ishares.com/us/products/239710/IWM/1467271812596.ajax"
    "?fileType=csv&fileName=IWM_holdings&dataType=fund"
)

TECH_SECTORS = {"Technology", "Communication Services"}

START_DATE = "2018-01-01"
END_DATE   = pd.Timestamp.today().strftime("%Y-%m-%d")


def fetch_iwm_current_tickers() -> set[str]:
    """Download current IWM holdings CSV from iShares and return ticker set."""
    logger.info("Fetching current IWM holdings...")
    headers = {"User-Agent": "Mozilla/5.0 (compatible; research-bot/1.0)"}
    try:
        resp = requests.get(IWM_CSV_URL, headers=headers, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        logger.warning(f"Failed to fetch IWM CSV: {e}")
        return set()

    # iShares CSV has preamble lines before the actual data; skip lines until
    # we find a row starting with "Ticker"
    lines = resp.text.splitlines()
    header_idx = next(
        (i for i, line in enumerate(lines) if line.startswith("Ticker")), None
    )
    if header_idx is None:
        logger.warning("Could not find 'Ticker' header in IWM CSV")
        return set()

    csv_body = "\n".join(lines[header_idx:])
    try:
        df = pd.read_csv(io.StringIO(csv_body))
    except Exception as e:
        logger.warning(f"Failed to parse IWM CSV: {e}")
        return set()

    tickers = set(
        str(t).strip().upper()
        for t in df["Ticker"].dropna()
        if str(t).strip() not in {"", "-", "CASH", "USD"}
    )
    logger.info(f"Current IWM: {len(tickers)} tickers")
    return tickers


def fetch_iwm_historical_snapshots() -> set[str]:
    """Attempt to pull ~4 yearly IWM snapshots from Wayback Machine CDX.

    Returns union of all tickers found. Falls back to empty set if Wayback
    is unreachable or returns no results.
    """
    all_tickers: set[str] = set()
    target_years = ["20200601", "20210601", "20220601", "20230601"]
    cdx_url = "http://web.archive.org/cdx/search/cdx"
    snapshot_base = "https://web.archive.org/web/{timestamp}/{url}"

    for year in target_years:
        try:
            # Find closest snapshot to June of each year
            params = {
                "url": IWM_CSV_URL,
                "output": "json",
                "limit": "1",
                "closest": year,
                "filter": "statuscode:200",
            }
            cdx_resp = requests.get(cdx_url, params=params, timeout=15)
            cdx_resp.raise_for_status()
            rows = cdx_resp.json()
            if len(rows) < 2:  # first row is header
                logger.warning(f"No Wayback snapshot found for {year}")
                continue

            timestamp = rows[1][1]
            snap_url = snapshot_base.format(timestamp=timestamp, url=IWM_CSV_URL)
            logger.info(f"Fetching {year} snapshot: {snap_url}")
            headers = {"User-Agent": "Mozilla/5.0"}
            snap_resp = requests.get(snap_url, headers=headers, timeout=30)
            snap_resp.raise_for_status()

            lines = snap_resp.text.splitlines()
            header_idx = next(
                (i for i, line in enumerate(lines) if line.startswith("Ticker")), None
            )
            if header_idx is None:
                continue
            csv_body = "\n".join(lines[header_idx:])
            df = pd.read_csv(io.StringIO(csv_body))
            tickers = set(
                str(t).strip().upper()
                for t in df["Ticker"].dropna()
                if str(t).strip() not in {"", "-", "CASH", "USD"}
            )
            logger.info(f"  {year}: {len(tickers)} tickers")
            all_tickers |= tickers
            time.sleep(1.5)  # be polite to Wayback

        except Exception as e:
            logger.warning(f"Wayback fetch for {year} failed: {e}")
            continue

    logger.info(f"Historical snapshots union: {len(all_tickers)} tickers")
    return all_tickers


def get_sector(ticker: str) -> str | None:
    """Return yfinance sector string, or None on failure."""
    try:
        info = yf.Ticker(ticker).info
        return info.get("sector")
    except Exception:
        return None


def filter_tech_and_adtv(
    tickers: list[str],
    min_adtv: float = 1_000_000.0,
) -> list[str]:
    """Download recent price data and filter to tech + ADTV > min_adtv.

    Returns list of tickers that pass both filters.
    """
    logger.info(f"Filtering {len(tickers)} tickers (sector + ADTV > ${min_adtv:,.0f})...")
    passed: list[str] = []

    for i, ticker in enumerate(sorted(tickers), 1):
        if i % 50 == 0:
            logger.info(f"  Progress: {i}/{len(tickers)}")
        try:
            df = yf.download(
                ticker,
                start="2024-01-01",
                auto_adjust=True,
                progress=False,
                multi_level_index=False,
            )
            if df.empty or len(df) < 50:
                continue

            # ADTV filter
            adtv = (df["Close"] * df["Volume"]).median()
            if adtv < min_adtv:
                continue

            # Sector filter (slow — yfinance info call)
            sector = get_sector(ticker)
            if sector not in TECH_SECTORS:
                continue

            passed.append(ticker)
            time.sleep(0.05)  # light rate limiting

        except Exception as e:
            logger.warning(f"  {ticker}: filter error — {e}")
            continue

    logger.info(f"Passed sector+ADTV filter: {len(passed)} tickers")
    return passed


def download_and_save(tickers: list[str], dry_run: bool = False) -> tuple[int, int]:
    """Download full OHLCV history for tickers and save parquets.

    Returns (n_saved, n_skipped).
    """
    PARQUET_OUT_DIR.mkdir(parents=True, exist_ok=True)
    n_saved = 0
    n_skipped = 0

    for i, ticker in enumerate(tickers, 1):
        if i % 25 == 0:
            logger.info(f"  Downloading {i}/{len(tickers)}...")

        out_path = PARQUET_OUT_DIR / f"{ticker}.parquet"
        if out_path.exists():
            logger.debug(f"  {ticker}: already exists, skipping")
            n_saved += 1
            continue

        if dry_run:
            logger.info(f"  [dry-run] Would save {ticker}")
            n_saved += 1
            continue

        try:
            df = yf.download(
                ticker,
                start=START_DATE,
                end=END_DATE,
                auto_adjust=True,
                progress=False,
                multi_level_index=False,
            )
            if df.empty:
                logger.warning(f"  {ticker}: empty data — skipping (may be delisted)")
                n_skipped += 1
                continue

            df = df.reset_index()
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]

            df = df.rename(columns={
                "Date": "date",
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Volume": "volume",
                "Adj Close": "adj_close",
            })

            # adj_close = Close when auto_adjust=True
            if "adj_close" not in df.columns:
                df["adj_close"] = df["close"]

            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date").sort_index()
            df = df[["adj_close", "open", "high", "low", "close", "volume"]]

            # Drop rows where adj_close is 0 or NaN (missing data, not actual zeros)
            df = df[df["adj_close"].notna() & (df["adj_close"] > 0)]

            if len(df) < 100:
                logger.warning(f"  {ticker}: only {len(df)} valid rows after cleaning — skipping")
                n_skipped += 1
                continue

            df.to_parquet(out_path)
            n_saved += 1
            time.sleep(0.05)

        except Exception as e:
            logger.warning(f"  {ticker}: download error — {e}")
            n_skipped += 1
            continue

    return n_saved, n_skipped


def main():
    ap = argparse.ArgumentParser(description="Fetch Russell 2000 tech universe")
    ap.add_argument("--min-adtv", type=float, default=1_000_000.0)
    ap.add_argument("--dry-run", action="store_true",
                    help="Skip actual downloads; just report what would be saved")
    ap.add_argument("--skip-historical", action="store_true",
                    help="Skip Wayback Machine historical snapshots (faster)")
    args = ap.parse_args()

    # 1. Get tickers
    current = fetch_iwm_current_tickers()
    if not args.skip_historical:
        historical = fetch_iwm_historical_snapshots()
    else:
        historical = set()
        logger.info("Skipping historical snapshots (--skip-historical)")

    all_tickers = sorted(current | historical)
    logger.info(f"Union of current + historical: {len(all_tickers)} tickers")

    if not all_tickers:
        logger.error("No tickers fetched — check network or use --skip-historical")
        sys.exit(1)

    # 2. Filter sector + ADTV
    tech_tickers = filter_tech_and_adtv(all_tickers, min_adtv=args.min_adtv)

    if not tech_tickers:
        logger.error("No tickers passed the filter — check sector/ADTV settings")
        sys.exit(1)

    # 3. Download OHLCV
    n_saved, n_skipped = download_and_save(tech_tickers, dry_run=args.dry_run)

    # 4. Save ticker list (only tickers with actual parquets)
    if not args.dry_run:
        final_tickers = sorted(
            p.stem for p in PARQUET_OUT_DIR.glob("*.parquet")
        )
    else:
        final_tickers = tech_tickers

    UNIVERSE_DIR.mkdir(parents=True, exist_ok=True)
    TICKER_LIST_PATH.write_text("\n".join(final_tickers) + "\n")

    logger.info(f"\n{'='*50}")
    logger.info(f"Russell 2000 Tech Universe — COMPLETE")
    logger.info(f"  Tickers with data:  {n_saved}")
    logger.info(f"  Skipped (no data):  {n_skipped}")
    logger.info(f"  Final universe:     {len(final_tickers)}")
    logger.info(f"  Ticker list saved:  {TICKER_LIST_PATH}")
    logger.info(f"  Parquets saved to:  {PARQUET_OUT_DIR}")
    logger.info(f"{'='*50}")


if __name__ == "__main__":
    main()
