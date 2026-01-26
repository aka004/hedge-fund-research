# Hedge Fund Research - Project Instructions

## Project Overview

EOD equities backtesting system for strategy research. Combines momentum signals with value confirmation and social sentiment (StockTwits).

## AFML Module (MANDATORY)

All agents MUST use functions from `afml/` for these operations. These techniques are from López de Prado's "Advances in Financial Machine Learning".

| Operation | Required Function | DO NOT |
|-----------|------------------|--------|
| Cross-validation | `afml.purged_kfold()` | Use sklearn's KFold |
| Labeling | `afml.triple_barrier()` | Use fixed-time returns |
| Sharpe validation | `afml.deflated_sharpe()` | Use raw Sharpe ratio |
| Portfolio weights | `afml.hrp()` | Use mean-variance optimization |
| Sample weights | `afml.sample_uniqueness()` | Use equal weights |
| Regime check | `afml.regime_200ma()` | Skip regime context |
| Feature check | `afml.stationarity_check()` | Use non-stationary features |

### Validation Gates

- **PSR > 0.95** required for strategy approval (95% confidence)
- **Stationarity check** required before using any feature in models
- **Purged K-Fold** required for all cross-validation (no sklearn KFold)

### Example Usage

```python
from afml import (
    purged_kfold,
    triple_barrier,
    sample_uniqueness,
    deflated_sharpe,
    hrp,
    regime_200ma,
    stationarity_check,
)

# Labeling
labels = triple_barrier(prices, profit_take=2.0, stop_loss=2.0, max_holding=10)

# Cross-validation (NOT sklearn)
for train_idx, test_idx in purged_kfold(X, n_splits=5, embargo_pct=0.01):
    model.fit(X.iloc[train_idx], y.iloc[train_idx])

# Validation
result = deflated_sharpe(returns, n_strategies_tested=10)
if not result.passes_threshold:
    raise ValueError(f"PSR {result.psr:.2f} < 0.95 threshold")

# Portfolio construction
weights = hrp(returns_df).weights
```

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

### CRITICAL: Zero Values as Missing Data

**Be CAUTIOUS of 0 values** - they often represent MISSING data, not actual zeros:

| Field | 0 Means | Action |
|-------|---------|--------|
| Price | Missing data | Flag as NaN, investigate |
| Volume | Trading halt OR missing | Check if market was open |
| P/E Ratio | Missing OR division error | Use NaN, never 0 |
| Returns | Suspicious if many | Check for data gaps |
| Volatility | Impossible value | Must be > 0, flag as NaN |
| Sentiment | No data OR neutral | Distinguish explicitly |

**Never do this:**
```python
df.fillna(0)  # BAD: Hides missing data
```

**Do this instead:**
```python
if df.isna().any().any():
    logger.warning(f"Missing data: {df.isna().sum()}")
# Keep NaN, handle explicitly in analysis
```

## Backtest Safety

- **No look-ahead bias**: Only use data available at decision time
- **Include transaction costs**: Model slippage + commissions
- **Walk-forward validation**: Don't overfit to historical data

## File Organization

```
afml/               # AFML techniques (MANDATORY - see above)
data/providers/     # API integrations
data/storage/       # Parquet files
strategy/signals/   # Signal generators
strategy/backtest/  # Backtesting engine
analysis/           # Performance metrics
notebooks/          # Research exploration
```

## Multi-Agent Alpha Testing Workflow

Event-driven multi-agent workflow for testing alpha generation strategies.

### Agents and AFML Responsibilities

| Agent | AFML Techniques | Role |
|-------|-----------------|------|
| **Momentum Researcher** | `triple_barrier()`, `regime_200ma()` | Generate alpha signals |
| **Backtest Unit** | `purged_kfold()` | Validate with CV |
| **Statistical Agent** | `deflated_sharpe()`, `sample_uniqueness()` | Compute PSR, approve/reject |
| **Project Manager** | - | Evaluate data requests, coordinate |
| **Data Pipeline Agent** | - | Implement data fetching |
| **Scribe** | - | Record all events |

### Complete Event Flow

#### Main Flow (Alpha Validation)
```
Momentum Researcher
  │ alpha.ready
  ▼
Backtest Unit ───────── purged k-fold validation
  │ backtest.passed
  ▼
Statistical Agent ────── PSR check (>= 0.95?)
  ├── alpha.success ──→ ✅ DONE
  └── alpha.rejected ──→ Momentum Researcher (adjust strategy)
```

#### Side Flow: Data Requests (When data.missing)
```
Any Agent
  │ data.missing
  ▼
Project Manager ──────── evaluates request
  ├── pm.approved ──→ Data Pipeline Agent → data.available → retry
  │
  └── pm.rejected ──→ Momentum Researcher
                        │ alternative.proposed
                        ▼
                     HUMAN REVIEW (you decide)
                        │ alternative.approved
                        ▼
                     Momentum Researcher (implement alternative)
```

### Agent Clearance Levels

| Clearance | Agents | Can Do | Cannot Do |
|-----------|--------|--------|-----------|
| **Research** | Momentum Researcher | Read data, compute signals, propose alphas | Modify data pipeline |
| **Validation** | Backtest Unit, Statistical Agent | Read data/signals, run validation | Change thresholds, modify pipeline |
| **Infrastructure** | Project Manager, Scribe | Coordinate, log events | Modify data pipeline |
| **Pipeline** | Data Pipeline Agent | Add provider methods, add Parquet columns | Change base interface, modify AFML |
| **Admin** | Human (you) | Approve alternatives, final decisions | - |

### Human Approval Gates

| Event | What You Decide | When It Triggers |
|-------|-----------------|------------------|
| `alternative.proposed` | Approve/reject workaround approach | After PM rejects data request |

### Zero Value Warnings

**All agents MUST be cautious of 0 values:**
- Price = 0 → Missing data
- Volume = 0 → Trading halt or missing
- Volatility = 0 → Impossible, missing data
- Returns = 0 → Suspicious if widespread

**Never use `fillna(0)` - keep NaN and log warnings.**

---

## Relevant Skills

When working on this project, consider using:

- `test-driven-development` - Write tests before implementation (RED-GREEN-REFACTOR)
- `systematic-debugging` - Debug data issues methodically (4-phase root cause process)
- `brainstorming` - Interactive design refinement before coding
- `writing-plans` - Create detailed implementation plans
- `executing-plans` - Execute plans in batches with checkpoints
- `requesting-code-review` - Review code against plan before completion
- `testing` - Test strategy components
- `review` - Review backtest code for bugs

## MCP Servers

This project may benefit from:

- `context7` - Look up pandas/numpy/yfinance documentation

## Testing Workflow

### Simplified Alpha Testing

Two-phase testing separates data validation from alpha logic:

#### Phase 1: Data Fetch Tests (No Alpha Required)
Validates that agents can get all required data before implementing strategies.

```bash
# Quick smoke test (5 key symbols)
pytest tests/test_data_fetch.py -v -m smoke

# Full universe coverage test
pytest tests/test_data_fetch.py -v -m universe

# Generate data availability report
pytest tests/test_data_fetch.py::TestDataReport -v -s
```

**What it validates:**
- Yahoo Finance API is reachable
- Required columns exist (date, OHLCV, adj_close)
- Sufficient history (7+ years for momentum)
- Data quality (no zeros, no negatives, proper OHLC ordering)
- Momentum calculation feasibility (12-1 month returns)
- 200-day MA calculation feasibility

#### Phase 2: Alpha Tests (Strategy Logic)
After Phase 1 passes, test the actual alpha generation.

```bash
# Run signal generation tests
pytest tests/test_signals.py -v

# Run backtest tests
pytest tests/test_backtest.py -v
```

### Test Markers

| Marker | Purpose | Speed |
|--------|---------|-------|
| `smoke` | Quick validation (5 symbols) | Fast |
| `universe` | Full S&P 500 coverage | Slow |

## Commands

```bash
# Fetch data
python scripts/fetch_data.py --universe sp500 --years 5

# Run backtest
python scripts/run_backtest.py --strategy momentum_value_social

# Start Jupyter
jupyter notebook notebooks/
```
