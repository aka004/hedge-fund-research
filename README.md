# Hedge Fund Research System

A lean, cost-effective EOD (End-of-Day) equities backtesting system for strategy research.

## Strategy Overview

**Momentum + Value + Social Hype**

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

## Key Design Decisions

| Aspect | Choice | Rationale |
|--------|--------|-----------|
| Portfolio size | < $100K | Lean, cost-conscious design |
| Latency | EOD | Daily batch processing |
| Data storage | Parquet + DuckDB | Zero ops, fast analytics |
| Price data | Yahoo Finance | Free, sufficient for research |
| Social data | StockTwits | Free tier, pre-labeled sentiment |
| Framework | Custom Python | Full control, learning opportunity |

## Project Structure

```
hedge-fund-research/
├── data/
│   ├── providers/           # Data source implementations
│   │   ├── base.py          # Abstract interfaces
│   │   ├── yahoo_finance.py # Price/fundamental data
│   │   └── stocktwits.py    # Social sentiment data
│   └── storage/
│       ├── parquet/         # Raw cached data
│       └── cache/           # Query cache
├── strategy/
│   ├── signals/             # Signal generators
│   │   ├── momentum.py
│   │   ├── value.py
│   │   └── social.py
│   └── backtest/            # Backtesting engine
├── analysis/                # Performance analysis
├── notebooks/               # Research notebooks
├── docs/
│   └── plans/               # Design documents
├── scripts/                 # CLI scripts
├── tests/                   # Test suite
└── .claude/
    └── skills/              # Project-specific skills
```

## Getting Started

### Quick Setup

```bash
# Create virtual environment (if not already created)
python -m venv venv

# Install dependencies
pip install -r requirements.txt

# Activate environment (use the helper script)
source activate.sh

# Or manually:
source venv/bin/activate  # or `venv\Scripts\activate` on Windows
```

### Cursor/VSCode Integration

The project is configured to automatically use the correct Python environment in Cursor:

- **Python Interpreter**: Automatically set to `venv/bin/python3`
- **Terminal**: Auto-activates virtual environment when opening terminal
- **Testing**: Pytest configured and ready to use
- **Jupyter**: Uses the project's virtual environment

Just open the project in Cursor and it will automatically detect and use the `venv` environment.

### First Run

```bash
# Download initial data
python scripts/fetch_data.py --universe sp500 --years 5

# Run backtest
python scripts/run_backtest.py --strategy momentum_value_social
```

## Dependencies

- Python 3.11+
- pandas, numpy (data manipulation)
- yfinance (price data)
- duckdb (fast queries)
- pyarrow (parquet storage)
- requests (API calls)
- matplotlib, plotly (visualization)

## Data Sources

| Source | Data Type | Cost | Rate Limits |
|--------|-----------|------|-------------|
| Yahoo Finance | OHLCV, fundamentals | Free | Unofficial, be respectful |
| StockTwits | Sentiment, mentions | Free tier | 200 requests/hour |

## Backtest Safeguards

- **Survivorship bias**: Include delisted stocks in historical universe
- **Look-ahead bias**: Use point-in-time data only
- **Transaction costs**: Model slippage + commissions
- **Walk-forward validation**: Train/test splits with purging

## Roadmap

See [TODO.md](TODO.md) for implementation tasks.

### AFML Implementation Status

The system implements concepts from *Advances in Financial Machine Learning* (Lopez de Prado):

| Component | Status | Location |
|-----------|--------|----------|
| Triple-barrier labeling | Complete | `afml/labels.py` |
| Sample uniqueness weights | Complete | `afml/weights.py` |
| Purged K-Fold CV | Complete | `afml/cv.py` |
| HRP portfolio allocation | Partial | `afml/portfolio.py` |
| Regime detection | Partial | `afml/regime.py` |
| CPCV / Sequential bootstrap | Not started | - |
| Meta-labeling | Not started | - |

Full implementation roadmap: [docs/plans/2026-01-26-AFML-implementation-roadmap.md](docs/plans/2026-01-26-AFML-implementation-roadmap.md)

### Multi-Agent Research System (Planned)

A full orchestration system for automated stock research is planned:

| Phase | Description | Status |
|-------|-------------|--------|
| Manual prompts | Copy-paste agent sequence | Designed |
| Python orchestrator | Script-driven coordination | Planned |
| Full automation | Scheduled research + feedback | Planned |

See [TODO.md](TODO.md) Phase 3 for details.

## License

Private research project.
