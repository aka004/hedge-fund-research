---
name: backtest-patterns
description: "Use when implementing backtesting code, signal generation, or performance analysis for trading strategies"
---

# Backtesting Patterns

## Core Principles

1. **No look-ahead bias**: Only use data available at decision time
2. **Realistic execution**: Model slippage, commissions, and market impact
3. **Survivorship awareness**: Include delisted stocks in historical universe
4. **Reproducibility**: Same inputs must produce same outputs

## Signal Generation Pattern

```python
def generate_signals(data: pd.DataFrame, as_of_date: date) -> pd.DataFrame:
    """
    CORRECT: Only use data up to as_of_date
    """
    # Filter to point-in-time data
    historical = data[data['date'] <= as_of_date]

    # Calculate signal using ONLY historical data
    signal = calculate_momentum(historical)

    return signal
```

## Backtest Loop Pattern

```python
for date in trading_dates:
    # 1. Get signals using ONLY data available at this date
    signals = strategy.generate_signals(data, as_of_date=date)

    # 2. Execute trades at NEXT day's open (realistic)
    next_open = get_next_open_prices(date)

    # 3. Apply transaction costs
    costs = calculate_costs(trades, next_open)

    # 4. Update portfolio
    portfolio.update(trades, next_open, costs)
```

## Transaction Cost Model

```python
@dataclass
class TransactionCosts:
    commission_per_share: float = 0.005  # $0.005/share
    slippage_bps: float = 5.0            # 5 basis points

    def calculate(self, shares: int, price: float) -> float:
        commission = shares * self.commission_per_share
        slippage = shares * price * (self.slippage_bps / 10000)
        return commission + slippage
```

## Adjusted Price Usage

```python
# CORRECT: Use adjusted prices for returns
returns = df['adj_close'].pct_change()

# WRONG: Raw prices ignore splits/dividends
# returns = df['close'].pct_change()  # DON'T DO THIS
```

## Walk-Forward Validation

```python
# Train on 2 years, test on 6 months, roll forward
for train_start, train_end, test_start, test_end in walk_forward_folds:
    # Fit parameters on training data
    params = optimize(train_data)

    # Evaluate on out-of-sample test data
    test_results = backtest(test_data, params)

    # This is more realistic than single train/test split
```

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Using future data | Filter data to `<= as_of_date` |
| Ignoring transaction costs | Add slippage + commission model |
| Single train/test split | Use walk-forward validation |
| Trading at close price | Execute at next day's open |
| Forgetting dividends | Use adjusted prices |
