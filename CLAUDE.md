# Hedge Fund Research - Project Instructions

## Project Overview

EOD equities backtesting system for strategy research. Combines momentum signals with value confirmation and social sentiment (StockTwits).

## Key Design Decisions

- **Local only**: No cloud, no paid subscriptions
- **Free data**: Yahoo Finance + StockTwits free tier
- **Parquet + DuckDB**: Zero ops data storage
- **Python**: pandas/numpy, clean readable code

## Code Style

- **Readable over clever**: Avoid complex one-liners
- **Type hints**: Use dataclasses and type annotations
- **Docstrings**: Document public functions
- **Tests**: Write tests for core logic

## Data Handling Rules

- Always use **adjusted prices** for returns calculation
- Cache API responses to **Parquet** immediately
- Respect rate limits (StockTwits: 200 req/hour)
- Store dates in **ISO format** (YYYY-MM-DD)

## Backtest Safety

- **No look-ahead bias**: Only use data available at decision time
- **Include transaction costs**: Model slippage + commissions
- **Walk-forward validation**: Don't overfit to historical data

## File Organization

```
data/providers/     # API integrations
data/storage/       # Parquet files
strategy/signals/   # Signal generators
strategy/backtest/  # Backtesting engine
analysis/           # Performance metrics
notebooks/          # Research exploration
```

## Relevant Skills

When working on this project, consider using:

- `superpowers:test-driven-development` - Write tests before implementation
- `superpowers:systematic-debugging` - Debug data issues methodically
- `testing` - Test strategy components
- `review` - Review backtest code for bugs

## MCP Servers

This project may benefit from:

- `context7` - Look up pandas/numpy/yfinance documentation

## Commands

```bash
# Fetch data
python scripts/fetch_data.py --universe sp500 --years 5

# Run backtest
python scripts/run_backtest.py --strategy momentum_value_social

# Start Jupyter
jupyter notebook notebooks/
```
