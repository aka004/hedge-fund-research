# Task: Hedge Fund Research System

## Objective

Build a lean EOD equities backtesting system implementing a Momentum + Value + Social Hype strategy.

## Current Task

_Define your current task here_

## Setup Steps

- [ ] Create Python virtual environment
- [ ] Install dependencies from `requirements.txt`
- [ ] Verify project structure exists
- [ ] Run initial tests: `pytest tests/ -v`

## Implementation Phases

### Phase 1: Data Layer
- [ ] Implement Yahoo Finance data provider
- [ ] Implement data storage with Parquet + DuckDB
- [ ] Create S&P 500 universe management

### Phase 2: Signal Generators
- [ ] Implement momentum signal (12-1 month returns, price > 200 MA)
- [ ] Implement value filter (P/E < 50, positive earnings, revenue growth)
- [ ] Implement social signal (StockTwits attention + sentiment)

### Phase 3: Backtesting Engine
- [ ] Create portfolio management logic
- [ ] Implement transaction cost modeling
- [ ] Build walk-forward validation

### Phase 4: Analysis
- [ ] Performance metrics calculation
- [ ] Visualization tools
- [ ] Report generation

## Technical Specifications

### Data Storage
```
data/
├── storage/
│   ├── parquet/         # Raw cached data
│   └── cache/           # Query cache
```

### Key Metrics
- Sharpe ratio, Sortino ratio
- Max drawdown
- Win rate, profit factor
- Transaction costs impact

## Progress Tracking

**IMPORTANT:** Update `TODO.md` as you complete each task:
1. Mark tasks with `[x]` when complete
2. Add completion timestamp
3. Log any issues in the Notes section

---

When all requirements are complete and tests pass, output: LOOP_COMPLETE
