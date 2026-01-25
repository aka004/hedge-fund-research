---
title: Hedge Fund Research System - Project Overview
project: hedge-fund-research
type: project
created: 2026-01-25 14:55:43
tags:
  - project/hedge-fund-research
  - type/project
  - status/active
version: 1.0
last_updated: 2026-01-25
---

# Hedge Fund Research System - Project Overview

**Last Updated:** 2026-01-25 14:55:43

## Project Description

A lean, cost-effective EOD (End-of-Day) equities backtesting system for strategy research.
The system focuses on momentum + value + social sentiment strategies for the S&P 500 universe.

## Strategy Overview

```
Universe (S&P 500)
    |
    v
Momentum Screen (12-1 month returns, price > 200 MA)
    |
    v
Value Filter (P/E < 50, positive earnings, revenue growth)
    |
    v
Social Signal (StockTwits attention + sentiment)
    |
    v
Ranking & Selection (top 10-20 stocks)
```

## Current Status

### Data Storage
- **Location**: `/Volumes/Data_2026/hedge-fund-research-data`
- **Price Data**: 0 symbols cached
- **Fundamental Data**: 0 symbols
- **Sentiment Data**: 0 symbols

### Configuration
- **Database**: External drive (Data_2026)
- **Obsidian Notes**: iCloud Drive (syncs across devices)

## Key Features

### 1. Data Pipeline
- **Yahoo Finance**: Free price and fundamental data
- **StockTwits**: Social sentiment data
- **Parquet Storage**: Efficient columnar format
- **DuckDB**: Fast SQL queries over Parquet

### 2. Strategy Signals
- **Momentum Signal**: 12-1 month returns with moving average filter
- **Value Signal**: P/E ratios, earnings quality
- **Social Signal**: StockTwits sentiment and attention
- **Signal Combiner**: Weighted combination of signals

### 3. Backtesting Engine
- **Walk-Forward Validation**: Train/test splits with purging
- **Transaction Costs**: Models slippage and commissions
- **Performance Metrics**: Sharpe, Sortino, Calmar ratios, drawdowns

### 4. Alpha Research Loop
- **Parameter Sweeps**: Automated exploration of strategy space
- **Results Logging**: CSV and Obsidian reports
- **Resume Capability**: Skip already-tested configurations

### 5. Obsidian Integration
- **Research Summaries**: Auto-generated from alpha research
- **Backtest Reports**: Performance analysis in Obsidian format
- **Daily Notes**: Track research progress
- **iCloud Sync**: Access reports on all devices

## Project Structure

```
hedge-fund-research/
├── data/
│   ├── providers/       # Data source implementations
│   └── storage/         # Parquet + DuckDB storage
├── strategy/
│   ├── signals/         # Signal generators
│   └── backtest/        # Backtesting engine
├── analysis/            # Performance analysis & reports
├── scripts/             # CLI tools
└── docs/               # Documentation
```

## Configuration

### Data Storage (Hard Drive)
- **Path**: `/Volumes/Data_2026/hedge-fund-research-data`
- **Format**: Parquet files + DuckDB
- **Purpose**: Market data, prices, fundamentals, sentiment

### Obsidian Notes (iCloud Drive)
- **Vault**: iCloud Drive
- **Project Folder**: `obsidian-vault`
- **Purpose**: Research reports, summaries, daily notes

## Usage Examples

### Fetch Data
```bash
python scripts/fetch_data.py --universe sp500 --years 7
```

### Run Alpha Research
```bash
# Quick test
python scripts/alpha_research.py --quick --obsidian

# Full parameter sweep
python scripts/alpha_research.py --full --obsidian
```

### Generate Reports
```bash
# Generate Obsidian report from existing results
python scripts/generate_obsidian_report.py --type research

# Generate daily note
python scripts/generate_obsidian_report.py --type daily
```

## Design Decisions

| Aspect | Choice | Rationale |
|---------|--------|-----------|
| Portfolio size | < $100K | Lean, cost-conscious design |
| Latency | EOD | Daily batch processing |
| Data storage | Parquet + DuckDB | Zero ops, fast analytics |
| Price data | Yahoo Finance | Free, sufficient for research |
| Social data | StockTwits | Free tier, pre-labeled sentiment |
| Framework | Custom Python | Full control, learning opportunity |

## Backtest Safeguards

- **Survivorship bias**: Include delisted stocks in historical universe
- **Look-ahead bias**: Use point-in-time data only
- **Transaction costs**: Model slippage + commissions
- **Walk-forward validation**: Train/test splits with purging

## Next Steps

- [ ] Run full parameter sweep
- [ ] Analyze top-performing configurations
- [ ] Implement additional signals
- [ ] Expand universe beyond S&P 500
- [ ] Add real-time monitoring

## Related Documents

- [[_Index|Project Index]]
- [[Research/Alpha-Research/|Alpha Research Reports]]
- [[Research/Backtests/|Backtest Reports]]
- [[Daily-Notes/|Daily Notes]]

## Technical Stack

- **Python 3.11+**
- **pandas, numpy**: Data manipulation
- **yfinance**: Price data
- **duckdb**: Fast queries
- **pyarrow**: Parquet storage
- **matplotlib, plotly**: Visualization
