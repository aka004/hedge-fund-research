# Quiver Quantitative Integration

## Overview

The system now uses **Quiver Quantitative API** for congressional trades and insider trading data, replacing the previous SEC EDGAR Form 4 implementation.

## Why Quiver?

- **Free tier available** - Get started without cost
- **Timely updates** - Daily updates as filings are submitted
- **No CIK needed** - Just politician names
- **Includes insider trading** - Corporate insider trades from SEC Form 4s
- **Easy API** - Simple Python library

## Setup

### 1. Get API Key

1. Go to https://api.quiverquant.com
2. Sign up for a free account
3. Get your API key from the dashboard

### 2. Configure

Add to your `.env` file:

```bash
QUIVER_API_KEY=your_api_key_here
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

This will install `quiverquant>=0.2.2`

## Usage

### Fetch Congressional Trades

```python
from data.providers.quiver import QuiverProvider

quiver = QuiverProvider()

# Get trades for specific politician
trades = quiver.get_congressional_trades(politician_name="Nancy Pelosi")

# Get trades for specific ticker
trades = quiver.get_congressional_trades(ticker="AAPL")

# Get all recent trades
trades = quiver.get_congressional_trades()
```

### Fetch Insider Trades

```python
# Get insider trades for specific ticker
insider_trades = quiver.get_insider_trades(ticker="AAPL")

# Get all recent insider trades
insider_trades = quiver.get_insider_trades()
```

### CLI Usage

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

## Data Format

### Congressional Trades

- `representative` or `senator`: Politician name
- `transaction_date`: Date of trade
- `ticker`: Stock symbol
- `type`: Purchase or Sale
- `amount`: Amount range (e.g., "$1,001 - $15,000")
- `filing_date`: When disclosure was filed

### Insider Trades

- `insider_name`: Name of corporate insider
- `transaction_date`: Date of trade
- `ticker`: Stock symbol
- `transaction_type`: Buy/Sell/Option Exercise, etc.
- `shares`: Number of shares
- `price`: Transaction price

## Integration with Existing System

The Quiver provider integrates seamlessly with existing components:

- **Storage**: Uses same `PoliticianTradeStorage` (Parquet)
- **Analysis**: `PoliticianTracker` works with Quiver data
- **Signals**: `PoliticianSignal` generator uses stored trades
- **Pipeline**: `DataPipelineAgent` fetches via Quiver

## Migration from SEC EDGAR

The SEC EDGAR provider (`data/providers/sec_edgar.py`) is no longer used but kept for reference. All politician tracking now uses Quiver.

## Limitations

- **45-day delay**: STOCK Act requires 45-day disclosure window
- **Amount ranges**: Congressional trades report ranges, not exact values
- **Free tier limits**: Check Quiver's free tier limits (may have rate limits)

## Resources

- Quiver API Docs: https://api.quiverquant.com/docs
- Python Package: https://github.com/Quiver-Quantitative/python-api
- Congress Dashboard: https://www.quiverquant.com/congresstrading/
