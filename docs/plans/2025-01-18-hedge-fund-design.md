# Hedge Fund Research System Design

**Date**: 2025-01-18
**Status**: Approved
**Author**: Brainstorming session with multi-agent analysis

## Executive Summary

A lean EOD equities backtesting system for strategy research, combining momentum signals with value confirmation and social sentiment data from StockTwits.

## Requirements

| Requirement | Decision |
|-------------|----------|
| Asset class | US Equities |
| Latency | End-of-day (EOD) |
| Portfolio size | < $100K |
| Primary goal | Strategy research |
| Universe | S&P 500 → US Large/Mid Cap |
| Strategy | Momentum + Value + Social |
| Tech stack | Python (pandas/numpy) |
| Budget | $0/month (all free data) |

## Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                 LEAN EOD RESEARCH SYSTEM                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │ Data Layer   │───▶│ Strategy     │───▶│ Analysis     │      │
│  │              │    │ Layer        │    │ Layer        │      │
│  │ • Yahoo Fin  │    │ • Momentum   │    │ • Performance│      │
│  │ • StockTwits │    │ • Value      │    │ • Risk stats │      │
│  │ • Parquet    │    │ • Social     │    │ • Plots      │      │
│  │ • DuckDB     │    │ • Backtest   │    │              │      │
│  └──────────────┘    └──────────────┘    └──────────────┘      │
│                                                                 │
│  LOCAL MACHINE ONLY - No cloud, no subscriptions               │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Data Layer

#### Price/Fundamental Data (Yahoo Finance)

- OHLCV daily data
- Adjusted prices (split/dividend corrected)
- Basic fundamentals (P/E, revenue, earnings)
- Free, no API key required

#### Social Data (StockTwits)

Scalable provider pattern for future extension:

```python
class SocialDataProvider(ABC):
    """Abstract base - implement for each platform"""

    @abstractmethod
    def get_metrics(self, symbol: str, date: str) -> SocialMetrics:
        pass

    @abstractmethod
    def get_bulk_metrics(self, symbols: list[str], date: str) -> dict[str, SocialMetrics]:
        pass

@dataclass
class SocialMetrics:
    symbol: str
    date: str
    mention_count: int
    sentiment_score: float  # -1 (bearish) to +1 (bullish)
    volume_ratio: float     # vs 30-day average
    bullish_count: int
    bearish_count: int
```

**Implementations:**
- `StockTwitsProvider` (NOW)
- `RedditProvider` (LATER)
- `TwitterProvider` (LATER)

#### Storage

- **Parquet files**: Raw data, partitioned by year/month
- **DuckDB**: Fast analytical queries over Parquet
- **No database server**: Zero operational overhead

### Strategy Layer

#### Signal Flow

```
STEP 1: Universe (S&P 500)
    ~500 stocks
        │
        ▼
STEP 2: Momentum Screen
    • 12-month return > 0
    • Price > 200-day MA
    • Skip most recent month
    Output: ~150-200 stocks
        │
        ▼
STEP 3: Value Filter
    • P/E < 50
    • Positive earnings
    • Revenue growth > 0%
    Output: ~50-100 stocks
        │
        ▼
STEP 4: Social Signal
    • Attention: mention volume vs 30d avg
    • Sentiment: bullish % vs bearish %
    • Score: attention × sentiment
    Output: ~50-100 stocks with scores
        │
        ▼
STEP 5: Ranking & Selection
    Combined rank = momentum + value + social
    Select top 10-20 stocks
    Equal weight
        │
        ▼
STEP 6: Backtest / Paper Trade
```

#### Signal Combination

**Approach**: Sequential filtering (recommended for debugging)

1. Momentum filters universe first
2. Value confirms quality
3. Social ranks final candidates

### Backtesting Engine

#### Design Principles

- **Vectorized signals + Event-driven execution**: Best of both worlds
- **Same code for backtest and live**: Interface-based design
- **Proper cost modeling**: Slippage + commissions

#### Bias Prevention

| Bias | Mitigation |
|------|------------|
| Look-ahead | Point-in-time data only |
| Survivorship | Include delisted stocks |
| Overfitting | Walk-forward validation |
| Transaction costs | Model slippage + fees |

### Analysis Layer

#### Metrics to Track

- Total return, CAGR
- Sharpe ratio, Sortino ratio
- Max drawdown, drawdown duration
- Win rate, profit factor
- Turnover, transaction costs

## Agent Perspectives (Synthesis)

During brainstorming, four specialized agents provided analysis:

### Architecture Agent
- Recommended Parquet + DuckDB over time-series DB
- Emphasized unified backtest/live code via interfaces
- Suggested simple monolith over microservices

### Data Engineering Agent
- Identified survivorship bias as 1-2% annual impact
- Recommended hybrid refresh: incremental daily + full weekly
- Warned about timezone handling and corporate actions

### Quant Strategy Agent
- Recommended hybrid backtester (vectorized + event-driven)
- Emphasized walk-forward validation over simple train/test
- Suggested starting with sequential filtering

### Agent Analysis Agent
- Concluded LLM costs exceed value for <$100K portfolios
- Identified legitimate use: post-hoc analysis, not trading signals
- Recommended traditional pipeline with optional targeted LLM

## LLM/Agent Integration (Deferred)

Given budget constraints (<$100K), LLM agents are **not recommended** for core pipeline.

**If added later** (after scaling):
- Only for top 5-10 candidates after traditional filtering
- Earnings call sentiment analysis
- Anomaly explanation (why did X move?)
- Cost: ~$30-50/month for targeted use

## Implementation Phases

### Phase 1: Data Foundation
- [ ] Set up project structure
- [ ] Implement Yahoo Finance provider
- [ ] Implement Parquet storage
- [ ] Fetch S&P 500 historical data (5 years)

### Phase 2: Core Strategy
- [ ] Implement momentum signal
- [ ] Implement value filter
- [ ] Build basic backtester
- [ ] Add performance metrics

### Phase 3: Social Integration
- [ ] Implement StockTwits provider
- [ ] Add social metrics storage
- [ ] Integrate into strategy flow
- [ ] Backtest with social signals

### Phase 4: Research & Iteration
- [ ] Jupyter notebooks for exploration
- [ ] Parameter sensitivity analysis
- [ ] Walk-forward validation
- [ ] Document findings

### Phase 5: Expansion (Optional)
- [ ] Expand to US Large/Mid Cap
- [ ] Add Reddit provider
- [ ] Paper trading setup
- [ ] Live trading consideration

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Yahoo Finance API changes | Cache data locally, have backup source |
| StockTwits rate limits | Respect limits, cache aggressively |
| Overfitting to historical data | Walk-forward validation, out-of-sample testing |
| Strategy degradation | Monitor live performance vs backtest |

## Success Criteria

1. **Working backtest**: Can run momentum+value strategy on S&P 500
2. **Social integration**: StockTwits data incorporated
3. **Reproducibility**: Same inputs → same outputs
4. **Documentation**: Clear code, runnable notebooks
5. **Learning**: Understand every component
