# Hedge Fund Research System

EOD equities backtesting system built on techniques from Lopez de Prado's *Advances in Financial Machine Learning*. Combines momentum, value, and social sentiment signals with rigorous statistical validation.

## How It Works

```
S&P 500 Universe
    │
    ├─ Momentum Signal ──── 12-1 month returns, price > 200 MA
    ├─ Value Signal ──────── P/E < 50, positive earnings, revenue growth
    ├─ Social Signal ─────── StockTwits attention + sentiment
    └─ Politician Signal ─── Congressional insider trades
            │
            ▼
    Signal Combiner (rank & select top 10-20)
            │
            ▼
    Event-Driven Backtest Engine
    ├─ Daily entries at rebalance via open price
    ├─ Dynamic barrier exits (profit target / stop loss / timeout)
    ├─ Rolling volatility adapts to regime
    └─ MFE/MAE tracking per trade
            │
            ▼
    AFML Validation Pipeline
    ├─ Purged K-Fold CV (no lookahead)
    ├─ Deflated Sharpe Ratio (PSR > 0.95 required)
    └─ Sample uniqueness weighting
```

## AFML Module

All cross-validation, labeling, and validation uses AFML techniques — never raw sklearn or naive Sharpe.

| Technique | File | Purpose |
|-----------|------|---------|
| Triple-Barrier Labeling | `afml/labels.py` | Profit target / stop loss / timeout labels |
| CUSUM Filter | `afml/cusum.py` | Event detection on cumulative returns |
| Purged K-Fold CV | `afml/cv.py` | Lookahead-free cross-validation |
| Combinatorial Purged CV | `afml/cpcv.py` | Exhaustive k-fold combinations |
| Sample Uniqueness | `afml/weights.py` | Overlap-aware sample weighting |
| Sequential Bootstrap | `afml/bootstrap.py` | Overlapping-label-aware bootstrap |
| Deflated Sharpe / PSR | `afml/metrics.py` | Multi-test-corrected Sharpe validation |
| Kelly Criterion | `afml/bet_sizing.py` | Optimal position sizing |
| Hierarchical Risk Parity | `afml/portfolio.py` | Correlation-aware portfolio allocation |
| Meta-Labeling | `afml/meta_labeling.py` | Secondary model for bet sizing |
| Regime Detection | `afml/regime.py` | 200-MA bull/bear classification |
| Stationarity Checks | `afml/checks.py` | ADF tests for feature validation |

**Validation gate:** PSR > 0.95 required for strategy approval (95% confidence the Sharpe ratio is positive after correcting for multiple testing).

## Event-Driven Backtest Engine

The `EventDrivenEngine` (`strategy/backtest/event_engine.py`) runs a daily-step simulation:

- **Entries** at monthly rebalance points using signal combiner rankings, filled at open price
- **Exits** via dynamic triple barriers (profit target, stop loss, max holding period) calibrated to rolling volatility
- **Position sizing**: max 10% per position, max 20 positions
- **Trade tracking**: round-trip trades with MFE (max favorable excursion) and MAE (max adverse excursion)
- **Benchmark**: SPY tracked alongside strategy equity curve
- **Transaction costs**: slippage + commission modeled on every trade

## Dashboard & Screener

A FastAPI + React frontend for interactive research.

**Screener** — filterable S&P 500 table with sorting, pagination, filter presets (Value, Growth, Momentum, Oversold), watchlist, and CSV export. Stock detail pages show fundamentals, price charts (SMA 20/50/200), and RSI.

**Dashboard** — five tabs for backtest analysis:

| Tab | Contents |
|-----|----------|
| Factor Lab | Signal factor attribution |
| Validation | PSR, Sharpe, stationarity results |
| Risk | Volatility, drawdown, tail risk |
| Portfolio | Holdings, weights, concentration |
| Trade Log | Round-trip trades with MFE/MAE |

## Multi-Agent Systems

### Alpha Validation Agents

Event-driven workflow (`agents/`) for automated strategy testing:

```
Momentum Researcher → alpha.ready
        ↓
Backtest Unit → purged k-fold validation
        ↓
Statistical Agent → PSR check (>= 0.95?)
  ├→ alpha.success → approved
  └→ alpha.rejected → feedback to researcher
```

### LLM Research Orchestrator

Multi-agent research pipeline (`research/`) with specialized agents: data fetcher, quant analyst, risk analyst, competitive analysis, qualitative review, synthesis, and claim verification. Integrates Yahoo Finance, SEC EDGAR, StockTwits, Reddit, and Finnhub.

## Data Providers

| Source | Data | Cost |
|--------|------|------|
| Yahoo Finance | OHLCV, fundamentals (P/E, revenue, earnings) | Free |
| StockTwits | Sentiment scores, message counts | Free (200 req/hr) |
| SEC EDGAR | Financial statement filings | Free |
| Finnhub | Company news & events | Free tier |
| House Clerk | Congressional stock trades | Free |
| Reddit | Subreddit activity | Free |

All responses cached to Parquet. Dates stored in ISO format. Adjusted prices used for returns.

## Project Structure

```
hedge-fund-research/
├── afml/                    # AFML techniques (12 modules)
├── strategy/
│   ├── signals/             # momentum, value, social, politician
│   └── backtest/            # EventDrivenEngine + exit manager
├── data/
│   ├── providers/           # yahoo, stocktwits, sec, finnhub, etc.
│   └── storage/             # parquet files + DuckDB
├── analysis/                # metrics, visualization, reports
├── agents/                  # multi-agent alpha validation
├── research/                # LLM research orchestrator
├── backend/                 # FastAPI API (screener, dashboard)
├── frontend/                # React + TypeScript + Tailwind
├── scripts/                 # CLI utilities
├── tests/                   # pytest suite (smoke + universe)
├── notebooks/               # Jupyter research notebooks
└── docs/plans/              # Architecture & design docs
```

## Getting Started

```bash
# Setup
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Fetch data
python scripts/fetch_data.py --universe sp500 --years 5

# Run event-driven backtest
python scripts/run_event_engine.py

# Start backend
cd backend && uvicorn app.main:app --reload

# Start frontend
cd frontend && npm install && npm run dev
```

## Tech Stack

**Backend:** Python 3.10+, FastAPI, DuckDB, pandas, numpy, scipy, scikit-learn, yfinance

**Frontend:** React 18, TypeScript, Vite, Tailwind CSS, Recharts

**Storage:** Parquet (columnar), DuckDB (OLAP queries)

**Testing:** pytest, mypy, ruff

## Backtest Safeguards

- **No look-ahead bias**: purged cross-validation with embargo periods
- **Transaction costs**: slippage + commissions on every trade
- **Walk-forward validation**: train/test splits with purging
- **Statistical validation**: deflated Sharpe ratio corrects for multiple testing
- **Zero-value caution**: 0s treated as missing data, never filled naively

## License

MIT
