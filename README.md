# Hedge Fund Research System

EOD equities backtesting system for alpha factor discovery. Combines an LLM-driven expression engine with techniques from Lopez de Prado's *Advances in Financial Machine Learning* for rigorous statistical validation.

## How It Works

```
643-Symbol Universe (S&P 500 + NASDAQ Tech)
    │
    ├─ AlphaGPT Expression Engine ── LLM proposes math formulas over OHLCV + fundamentals
    │   ├─ 29 operators: ts_mean, ts_ema, vwap, ts_zscore, ts_argmax, cs_rank, ...
    │   ├─ 10 data columns: open, high, low, close, volume, returns,
    │   │   earnings_yield, revenue_growth, profit_margin, expense_ratio
    │   └─ Recursive descent parser → AST → matrix evaluator
    │
    ├─ Event-Driven Backtest Engine
    │   ├─ Daily entries at rebalance via open price
    │   ├─ Dynamic barrier exits (profit target / stop loss / timeout)
    │   ├─ HRP / equal / Kelly position sizing
    │   ├─ Regime filter (200-MA) + CUSUM entry gate
    │   └─ Transaction costs: slippage + commission modeled per trade
    │
    └─ AFML Validation Pipeline
        ├─ Purged K-Fold CV (no lookahead)
        ├─ Deflated Sharpe Ratio (PSR > 0.95 required)
        └─ Sample uniqueness weighting
```

## AlphaGPT — LLM-Driven Alpha Discovery

The expression engine is the core of the system. An LLM proposes mathematical formulas that get evaluated on a stock×time matrix and backtested. Results feed back to the LLM for iteration.

```bash
# Run AlphaGPT with full universe
python scripts/alpha_gpt.py --universe all --start 2018-01-01 --end 2024-12-31 --max-iter 20

# Run with default 22-ticker test universe
python scripts/alpha_gpt.py --max-iter 10

# Resume from previous run
python scripts/alpha_gpt.py --universe all --max-iter 15
```

### Expression Language

**Example expression:**
```
cs_rank(ts_zscore(returns, 7) * (-1)) * 0.40
+ cs_rank(ts_ema(close, 21) / ts_ema(close, 126) - 1) * 0.30
+ cs_rank(earnings_yield) * 0.20
+ cs_rank(ts_sum(volume, 5) / ts_mean(volume, 21) * (-1)) * 0.10
```

**Time-series operators** (per stock, rolling window):

| Operator | Description |
|----------|-------------|
| `ts_mean(x, d)` / `sma(x, d)` | Simple moving average |
| `ts_ema(x, d)` / `ema(x, d)` | Exponential moving average |
| `ts_std(x, d)` | Rolling standard deviation |
| `ts_delta(x, d)` | Price change: x[t] - x[t-d] |
| `ts_returns(x, d)` | Simple returns: x[t]/x[t-d] - 1 |
| `ts_zscore(x, d)` | (x - mean) / std over d days |
| `ts_rank(x, d)` | Percentile rank within last d days |
| `ts_argmax(x, d)` / `ts_argmin(x, d)` | Days since d-day high/low |
| `ts_skew(x, d)` / `ts_kurt(x, d)` | Rolling skewness / kurtosis |
| `ts_decay(x, d)` | Linearly decaying weighted average |
| `ts_vwap(price, vol, d)` / `vwap(...)` | Volume-weighted average price |
| `ts_corr(x, y, d)` / `ts_cov(x, y, d)` | Rolling correlation / covariance |
| `ts_sum(x, d)` / `ts_max(x, d)` / `ts_min(x, d)` / `ts_prod(x, d)` | Rolling aggregates |

**Cross-sectional operators** (across all stocks, per day):

| Operator | Description |
|----------|-------------|
| `cs_rank(x)` | Percentile rank across stocks (0 to 1) |
| `cs_zscore(x)` | Z-score across stocks |
| `cs_demean(x)` | Subtract cross-sectional mean |

**Element-wise:** `abs(x)`, `log(x)`, `sign(x)` — **Arithmetic:** `+`, `-`, `*`, `/` with parentheses

## Data Storage

```
data/cache/parquet/
├── prices/                          → symlink to /Volumes/Data_2026/hedge-fund-data/parquet/prices
│   ├── AAPL.parquet                 One file per symbol (643 total)
│   ├── MSFT.parquet                 Columns: open, high, low, close, volume, adj_close
│   └── ...                          History: 2011–2026 (varies by IPO date)
│
├── fundamentals_quarterly/          SEC EDGAR quarterly financials (620 files)
│   ├── AAPL.parquet                 Columns: period_end, filed_date, total_revenue,
│   └── ...                          net_income, total_expenses, ebitda
│                                    Uses actual SEC filing dates (no look-ahead bias)
│
├── fundamentals_daily/              Derived daily timeseries (forward-filled quarterly)
│   ├── earnings_yield.parquet       TTM net income / close price
│   ├── revenue_growth.parquet       YoY quarterly revenue growth
│   ├── profit_margin.parquet        Net income / revenue
│   ├── expense_ratio.parquet        Total expenses / revenue
│   └── ttm_net_income.parquet       Trailing 12-month net income
│
└── fundamentals/                    Legacy format (deprecated)

data/cache/
├── alpha_gpt_history.json           AlphaGPT iteration results
├── auto_research_results.json       Auto-research loop results
└── research.duckdb                  DuckDB analytics store
```

### Data Sources

| Source | Data | Cost | Coverage |
|--------|------|------|----------|
| Yahoo Finance | OHLCV prices, 10+ year history | Free | 643 symbols |
| SEC EDGAR | Quarterly financials with actual filing dates | Free | 620 symbols (96%) |
| FMP (fallback) | Quarterly income statements | Free tier (limited) | Mega-caps only |

**Missing fundamentals (23 symbols):** ETFs (QQQ, SPY) and foreign private issuers (ARM, ASML, AZN, PDD, CHKP, CYBR, etc.) that file 20-F instead of 10-K. These participate via price/volume factors but are excluded from `cs_rank(earnings_yield)`.

### Fetching Data

```bash
# Fetch S&P 500 prices
python scripts/fetch_data.py --universe sp500 --years 7

# Fetch fundamentals from SEC EDGAR (primary) + FMP (fallback)
python scripts/fetch_fundamentals.py

# Fill gaps only via FMP
python scripts/fetch_fundamentals.py --fmp-only

# Force re-fetch everything
python scripts/fetch_fundamentals.py --force

# Build daily fundamental timeseries
python scripts/build_fundamental_timeseries.py
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

## Project Structure

```
hedge-fund-research/
├── afml/                    # AFML techniques (12 modules)
├── strategy/
│   ├── signals/
│   │   ├── expression/      # Expression engine (parser, evaluator, operators)
│   │   ├── momentum.py      # Classic momentum signal
│   │   ├── combiner.py      # Signal ranking & combination
│   │   └── base.py          # Signal/SignalGenerator base classes
│   └── backtest/            # EventDrivenEngine + exit manager
├── data/
│   ├── providers/           # yahoo, stocktwits, sec, finnhub, etc.
│   └── storage/             # parquet, duckdb, universe definitions
├── analysis/                # metrics, visualization, reports
├── agents/                  # multi-agent alpha validation
├── scripts/
│   ├── alpha_gpt.py         # LLM-driven alpha discovery
│   ├── auto_research_loop.py # Batch orchestrator with human approval
│   ├── fetch_data.py        # Yahoo Finance price fetcher
│   ├── fetch_fundamentals.py # SEC EDGAR + FMP fundamentals
│   ├── build_fundamental_timeseries.py # Quarterly → daily timeseries
│   ├── run_event_engine.py  # Run backtests
│   └── auto_research.py     # Grid search configs
├── backend/                 # FastAPI API (screener, dashboard)
├── frontend/                # React + TypeScript + Tailwind
├── tests/                   # pytest suite (smoke + universe)
├── notebooks/               # Jupyter research notebooks
└── docs/plans/              # Architecture & design docs
```

## Getting Started

```bash
# Setup
pip install -r requirements.txt

# Set API keys in .env (copy from .env.example)
cp .env.example .env
# Required: ANTHROPIC_API_KEY (for AlphaGPT)
# Optional: FMP_API_KEY (for fundamental data fallback)

# Fetch price data
python scripts/fetch_data.py --universe sp500 --years 7

# Fetch fundamentals
python scripts/fetch_fundamentals.py
python scripts/build_fundamental_timeseries.py

# Run AlphaGPT
python scripts/alpha_gpt.py --universe all --max-iter 20 --start 2018-01-01 --end 2024-12-31

# Run event-driven backtest
python scripts/run_event_engine.py
```

## Tech Stack

**Backend:** Python 3.10+, FastAPI, DuckDB, pandas, numpy, scipy, scikit-learn, yfinance

**AI:** Anthropic Claude API (AlphaGPT expression discovery)

**Storage:** Parquet (columnar, one file per symbol), DuckDB (OLAP queries)

**Testing:** pytest, mypy, ruff

## Backtest Safeguards

- **No look-ahead bias**: purged cross-validation with embargo periods; SEC EDGAR actual filing dates for fundamentals
- **Transaction costs**: slippage + commissions on every trade
- **Walk-forward validation**: in-sample / out-of-sample split
- **Statistical validation**: deflated Sharpe ratio corrects for multiple testing
- **Zero-value caution**: 0s treated as missing data, never filled naively
- **Fundamental NaN handling**: missing data → NaN → excluded from cross-sectional ranking → stock not scored → never traded

## License

MIT
