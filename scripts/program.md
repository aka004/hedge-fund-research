# Alpha Research Program

## Objective
Discover alpha factors in US equities expressed as mathematical formulas over OHLCV data.
Each expression is evaluated on a stock×time matrix and backtested. The goal is an expression
with PSR > 0.95, Sharpe > 0.5, CAGR > 3%, Max DD < 35%, and Profit Factor > 1.2.

## Constraints
- No look-ahead bias (engine truncates to as_of_date automatically)
- slippage_bps >= 10, n_positions >= 5
- Window parameters d must be integers in [1, 252]
- Do NOT repeat an expression already tried

## Current Focus
Momentum and value combination strategies using cross-sectional ranking.
Combine ts_* operators at multiple windows for multi-scale momentum.
Use cs_rank(earnings_yield) or cs_rank(revenue_growth) to add a value or growth tilt.

## Off-limits
- Windows > 252 days
- Raw price signals without normalization (always normalize with cs_rank or ts_zscore)
- Expressions that generate fewer than 100 trades over the backtest period
