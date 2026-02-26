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
| Insider/Congressional | OpenBB (SEC, Gov) | Free, no API key needed |
| Macro data | OpenBB (FRED) | Free with API key registration |
| Framework | Custom Python | Full control, learning opportunity |

## Project Structure

```
hedge-fund-research/
├── data/
│   ├── providers/           # Data source implementations
│   │   ├── base.py          # Abstract interfaces
│   │   ├── yahoo.py         # Price/fundamental data
│   │   ├── stocktwits.py    # Social sentiment data
│   │   ├── house_clerk.py   # Congressional trades (free)
│   │   └── openbb_provider.py  # SEC insider, gov trades, FRED macro
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
- openbb (SEC insider, gov trades, FRED macro, news)
- duckdb (fast queries)
- pyarrow (parquet storage)
- requests (API calls)
- matplotlib, plotly (visualization)

## Data Sources

| Source | Data Type | Cost | Rate Limits |
|--------|-----------|------|-------------|
| Yahoo Finance | OHLCV, fundamentals | Free | Unofficial, be respectful |
| StockTwits | Sentiment, mentions | Free tier | 200 requests/hour |
| OpenBB (SEC) | Insider trading (Form 4) | Free, no key | SEC EDGAR rate limits |
| OpenBB (Gov) | Congressional trades | Free, no key | Government data |
| OpenBB (FRED) | Macro series (GDP, CPI, rates) | Free key required | Unlimited |
| House Stock Watcher | Congressional trades | Free, no key | Public GitHub data |

## Backtest Safeguards

- **Survivorship bias**: Include delisted stocks in historical universe
- **Look-ahead bias**: Use point-in-time data only
- **Transaction costs**: Model slippage + commissions
- **Walk-forward validation**: Train/test splits with purging

## Roadmap

See [TODO.md](TODO.md) for implementation tasks.

### AFML Module

The system implements techniques from *Advances in Financial Machine Learning* (Lopez de Prado):

| Component | File | Status |
|-----------|------|--------|
| Triple-barrier labeling | `afml/labels.py` | Complete |
| CUSUM filter | `afml/cusum.py` | Complete |
| Purged K-Fold CV | `afml/cv.py` | Complete |
| Combinatorial Purged CV | `afml/cpcv.py` | Complete |
| Sample uniqueness weights | `afml/weights.py` | Complete |
| Sequential bootstrap | `afml/bootstrap.py` | Complete |
| Deflated Sharpe / PSR | `afml/metrics.py` | Complete |
| Kelly criterion | `afml/bet_sizing.py` | Complete |
| HRP portfolio | `afml/portfolio.py` | Complete |
| Meta-labeling (RF) | `afml/meta_labeling.py` | Complete |
| Regime detection (200MA) | `afml/regime.py` | Complete |
| ADF stationarity | `afml/checks.py` | Complete |

Full roadmap: [docs/plans/2026-02-18-unified-backtest-roadmap.md](docs/plans/2026-02-18-unified-backtest-roadmap.md)

### Multi-Agent Systems

| System | Status | Entry Point |
|--------|--------|-------------|
| Alpha validation (event-driven) | Working | `agents/orchestrator.py` |
| LLM research orchestrator | Working | `research/orchestrator.py` |
| Dashboard backtest runner | Working | `backend/app/services/backtest_runner.py` |

## License

Private research project.
