# Alpha Research Program

## Current Focus
Momentum and value combination strategies using cross-sectional ranking.
Combine ts_* operators at multiple windows for multi-scale momentum.
Use cs_rank(earnings_yield) or cs_rank(revenue_growth) to add a value or growth tilt.

## Off-limits
- Windows > 252 days
- Raw price signals without normalization (always normalize with cs_rank or ts_zscore)
- Expressions that generate fewer than 100 trades over the backtest period
