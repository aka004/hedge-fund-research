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

## Multi-Agent Workflows

This project uses ralph-tui for multi-agent orchestration.

### Available Presets

| Preset | Command | Purpose |
|--------|---------|---------|
| `alpha-testing.yml` | `ralph run --preset presets/alpha-testing.yml` | Test alpha generation with data pipeline coordination |
| `afml-consensus.yml` | `ralph run --preset presets/afml-consensus.yml` | Multi-agent consensus meeting for architecture |

### Alpha Testing Workflow

```
┌─────────────────────┐
│ Momentum Researcher │ ─── tests alpha generation
└─────────┬───────────┘
          │ data.missing
          ▼
┌─────────────────────┐
│   Project Manager   │ ─── evaluates request
└─────────┬───────────┘
          │ pm.approved
          ▼
┌─────────────────────┐
│ Data Pipeline Agent │ ─── implements data fetch
└─────────┬───────────┘
          │ data.available
          ▼
┌─────────────────────┐
│ Momentum Researcher │ ─── retries with new data
└─────────────────────┘
```

**Agents:**
- **Momentum Researcher**: Generates alpha signals, reports missing data
- **Project Manager**: Evaluates if requests fit project scope, approves/rejects
- **Data Pipeline Agent**: Implements data fetching capabilities

**Agent Clearance (Data Pipeline):**
- CAN add methods to existing providers
- CAN add columns to Parquet files
- CANNOT change base provider interface
- CANNOT add dependencies without PM approval
- CANNOT modify the AFML module

---

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
