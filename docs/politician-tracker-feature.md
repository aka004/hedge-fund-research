# Politician Portfolio Tracker Feature

## Overview

Automatic tracking of politician stock trades using **House Stock Watcher** free JSON endpoint (congressional trades from STOCK Act disclosures). Calculates performance metrics including **filing delay analysis** and generates copy-trading signals for backtesting.

## Components

### 1. Configuration

- **`config/politicians.yaml`**: Watchlist of politicians to track (name, role, party)
- **`config.py`**: Added settings:
  - `POLITICIAN_WATCHLIST_PATH`: Path to politicians.yaml
  - `POLITICIAN_SIGNAL_LOOKBACK_DAYS`: Days to look back for trades (default: 45)
  - **No API key needed** - completely free!

### 2. Data Provider

**`data/providers/house_clerk.py`**: House Stock Watcher provider
- Fetches congressional trades from free JSON endpoint
- Data source: `https://house-stock-watcher-data.s3-us-west-2.amazonaws.com/data/all_transactions.json`
- No CIK needed - just politician names
- **100% free** - no API key or subscription required
- Community-maintained, updated regularly

### 3. Storage

**`data/storage/politician_trades.py`**: Parquet-based storage for politician trades
- Stores transactions by politician and symbol
- Supports date filtering and deduplication
- Tracks portfolio snapshots over time

### 4. Analysis

**`analysis/politician_tracker.py`**: Performance analysis module
- Calculates win rate, average return, holding period
- Computes Sharpe ratio (if sufficient trades)
- Tracks best/worst trades
- **Filing delay tracking**:
  - Average delay between trade and disclosure
  - Maximum delay (flags >45 days as suspicious)
  - Late filing count and percentage
  - Identifies STOCK Act compliance violations

### 5. Signal Generator

**`strategy/signals/politician.py`**: Copy-trading signal generator
- Generates buy signals when politicians buy
- Generates sell signals when politicians sell
- Signal strength based on:
  - Politician's historical win rate
  - Trade size (larger = more conviction)
  - Time decay (older trades = weaker)

### 6. Data Pipeline Integration

**`agents/data_pipeline.py`**: Added `fetch_politician_trades()` method
- Fetches trades from House Stock Watcher JSON
- Caches to Parquet storage
- Supports filtering by politician, ticker, date range
- Tracks filing delays for compliance analysis

### 7. CLI Script

**`scripts/fetch_politician_trades.py`**: Command-line tool
- List politicians in watchlist
- Fetch trades for specific politician or all
- Supports date range filtering

## Usage

### Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Configure politicians in `config/politicians.yaml`:
   - Just add politician names (no CIK or API key needed)
   - Use exact names as they appear in House Stock Watcher database
   - Check https://housestockwatcher.com for name formatting

**That's it!** No API keys, no authentication, completely free.

### Fetching Trades

```bash
# List politicians in watchlist
python scripts/fetch_politician_trades.py list

# Fetch trades for specific politician
python scripts/fetch_politician_trades.py fetch --politician "Nancy Pelosi"

# Fetch all politicians (last 90 days)
python scripts/fetch_politician_trades.py fetch --all

# Fetch with custom date range
python scripts/fetch_politician_trades.py fetch --all --start-date 2024-01-01 --end-date 2024-12-31
```

### Using in Backtests

```python
from data.storage.parquet import ParquetStorage
from data.storage.politician_trades import PoliticianTradeStorage
from strategy.signals.politician import PoliticianSignal
from config import STORAGE_PATH

# Initialize storage
price_storage = ParquetStorage(STORAGE_PATH)
trade_storage = PoliticianTradeStorage(STORAGE_PATH)

# Create signal generator
politician_signal = PoliticianSignal(trade_storage, price_storage)

# Generate signals
signals = politician_signal.generate(
    symbols=["AAPL", "MSFT", "GOOGL"],
    as_of_date=date.today()
)

# Use in signal combiner
from strategy.signals.combiner import SignalCombiner
combiner = SignalCombiner([politician_signal, ...])
```

### Performance Analysis

```python
from analysis.politician_tracker import PoliticianTracker

tracker = PoliticianTracker(trade_storage, price_storage)
performance = tracker.calculate_performance("Nancy Pelosi")

print(f"Win Rate: {performance.win_rate:.1f}%")
print(f"Avg Return: {performance.avg_return:.2f}%")
print(f"Sharpe Ratio: {performance.sharpe_ratio}")

# Filing delay analysis
print(f"\nSTOCK Act Compliance:")
print(f"Avg Filing Delay: {performance.avg_filing_delay_days:.1f} days")
print(f"Max Delay: {performance.max_filing_delay_days} days")
print(f"Late Filings (>45d): {performance.late_filings_count} ({performance.late_filings_pct:.1f}%)")

# Get suspicious trades (filed late)
suspicious = tracker.get_suspicious_trades(
    politician_name="Nancy Pelosi",
    delay_threshold_days=45
)
print(f"\nSuspicious trades with delays >45 days:")
print(suspicious[["transaction_date", "disclosure_date", "ticker", "filing_delay_days"]])
```

## Data Schema

### Congressional Trade (from House Stock Watcher)

- `representative`: Name of House representative
- `transaction_date`: Date transaction occurred (YYYY-MM-DD)
- `disclosure_date`: Date disclosure was filed (MM/DD/YYYY)
- `disclosure_year`: Year of disclosure
- `ticker`: Stock ticker symbol
- `type`: Transaction type (purchase, sale_full, sale_partial, exchange)
- `amount`: Amount range (e.g., "$1,001 - $15,000")
- `owner`: Who owns the asset (self, joint, dependent)
- `district`, `state`, `party`: Politician metadata
- `sector`, `industry`: Stock classification
- `ptr_link`: Link to original PDF disclosure
- `cap_gains_over_200_usd`: Whether capital gains exceeded $200

### Filing Delay Fields (Calculated)

- `filing_delay_days`: Days between transaction_date and disclosure_date
- **STOCK Act Compliance**: Required to file within 30-45 days
- **Suspicious threshold**: >45 days delay

## Notes

- **100% Free**: No API keys, no subscriptions, no rate limits
- **No CIK Needed**: Works with politician names only
- **Filing Delays**: 
  - STOCK Act requires disclosure within 30-45 days
  - Real-world delays: 5-64+ days
  - System tracks and flags late filings
  - Can't front-run trades, but patterns still valuable
- **Amount Ranges**: Congressional trades report ranges, not exact values
- **Historical Data**: Coverage from at least 2020 to present
- **Update Frequency**: Community updates regularly as new filings appear
- **Data Quality**: Hand-transcribed by volunteers, generally accurate

## Filing Delay Analysis Use Cases

1. **Compliance Tracking**: Identify politicians who consistently file late
2. **Suspicious Pattern Detection**: Trades with unusually long delays (>60 days)
3. **Timing Analysis**: Compare returns for quickly-filed vs late-filed trades
4. **Signal Quality**: Weight recent filings more heavily than delayed ones
5. **Penalty Risk**: Politicians with chronic late filings may face scrutiny

## Future Enhancements

- Policy event correlation (flag trades near major announcements)
- Multi-politician consensus signals
- Real-time alerts for new filings (poll JSON endpoint)
- Portfolio visualization dashboard
- Integration with policy event database
- Filing delay alerts (notify when suspicious patterns emerge)
- Cross-reference with committee assignments (trade stocks they regulate?)
