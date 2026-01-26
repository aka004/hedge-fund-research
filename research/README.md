# Alpha Research

This folder contains results from the alpha-seeking research loop. The research engine systematically tests parameter combinations for momentum-based trading strategies.

## Quick Start

```bash
# Quick test (reduced parameter space, ~1 year of data)
python scripts/alpha_research.py --quick

# Full exhaustive search (all combinations)
python scripts/alpha_research.py --full

# Generate summary report from existing results
python scripts/alpha_research.py --report-only
```

## Files

| File | Description |
|------|-------------|
| `alpha_research_results.csv` | All research runs with parameters and metrics |
| `summary_YYYYMMDD_HHMMSS.md` | Markdown summary with rankings and analysis |

## Parameter Space

The research loop tests combinations of these parameters:

### Momentum Parameters
| Parameter | Quick Mode | Full Mode | Description |
|-----------|------------|-----------|-------------|
| Lookback | 12mo | 6, 9, 12, 15mo | Momentum calculation period |
| Skip | 1mo | 0, 1, 2mo | Recent months to skip (avoid mean reversion) |
| MA Window | 200d | 50, 100, 200d | Moving average for trend filter |

### Value Parameters
| Parameter | Quick Mode | Full Mode | Description |
|-----------|------------|-----------|-------------|
| Max P/E | 50, None | 25, 50, 75, None | Maximum P/E ratio filter |

### Portfolio Parameters
| Parameter | Quick Mode | Full Mode | Description |
|-----------|------------|-----------|-------------|
| Rebalance | monthly | weekly, monthly | Rebalancing frequency |
| Positions | 20 | 10, 15, 20, 30 | Maximum positions held |

### Signal Weights
| Combo | Quick Mode | Full Mode |
|-------|------------|-----------|
| Pure momentum | ✓ | ✓ |
| 80/20 mom/val | - | ✓ |
| 70/30 mom/val | ✓ | ✓ |
| 60/40 mom/val | - | ✓ |
| 50/50 mom/val | - | ✓ |

## Output Metrics

Each configuration records:

### Performance Metrics
- **Total Return**: Cumulative return over backtest period
- **CAGR**: Compound annual growth rate
- **Sharpe Ratio**: Risk-adjusted return (excess return / volatility)
- **Sortino Ratio**: Downside risk-adjusted return
- **Calmar Ratio**: CAGR / Max Drawdown
- **Max Drawdown**: Worst peak-to-trough decline
- **Annualized Volatility**: Standard deviation of returns (annualized)

### Trade Statistics
- **Total Trades**: Number of trades executed
- **Win Rate**: Percentage of profitable trades
- **Profit Factor**: Gross profits / Gross losses
- **Average Win/Loss**: Mean profit/loss per trade

### Walk-Forward Validation
- **WF Windows**: Number of out-of-sample test periods
- **WF Avg Return**: Average return per walk-forward window
- **WF Std Return**: Standard deviation of walk-forward returns

## CLI Options

```
usage: alpha_research.py [options]

Mode Selection (mutually exclusive):
  --quick           Quick test mode (reduced space, 1 year)
  --full            Full exhaustive search
  --report-only     Generate summary from existing results

Execution:
  --resume          Skip already-completed configurations
  --no-walk-forward Disable walk-forward validation (faster)

Custom Parameters:
  --lookbacks N [N ...]     Custom lookback months
  --skips N [N ...]         Custom skip months
  --ma-windows N [N ...]    Custom MA windows
  --max-pes N [N ...]       Custom P/E thresholds (0 = no filter)
  --rebalance STR [STR ...] Rebalance frequencies (daily/weekly/monthly)
  --positions N [N ...]     Position counts

Date Range:
  --years N                 Years of history (default: 5)
  --start-date YYYY-MM-DD   Specific start date
  --end-date YYYY-MM-DD     Specific end date

Universe:
  --symbols SYM [SYM ...]   Test specific symbols
  --max-symbols N           Limit universe size (for testing)

Output:
  --output-dir PATH         Output directory
  --verbose, -v             Verbose logging
```

## Example Workflows

### 1. Initial Exploration
```bash
# Quick test to verify setup
python scripts/alpha_research.py --quick --max-symbols 50
```

### 2. Focused Research
```bash
# Test specific parameter ranges
python scripts/alpha_research.py \
    --lookbacks 9 12 \
    --skips 1 2 \
    --rebalance monthly \
    --positions 15 20 25 \
    --years 5
```

### 3. Full Research Run
```bash
# Complete search (can take hours)
python scripts/alpha_research.py --full --resume

# Monitor progress in another terminal
tail -f research/alpha_research_results.csv | cut -d',' -f1,14,15,16 | head -1 && \
tail -f research/alpha_research_results.csv | cut -d',' -f1,14,15,16
```

### 4. Analysis
```bash
# Generate summary after run completes
python scripts/alpha_research.py --report-only

# View in terminal
cat research/summary_*.md | head -100
```

## Interpreting Results

### What Makes a Good Configuration?

1. **High Sharpe Ratio (>1.0)**: Good risk-adjusted returns
2. **Low Max Drawdown (<20%)**: Manageable downside risk
3. **Positive CAGR**: Actually makes money
4. **Stable Walk-Forward Results**: Low WF Std Return indicates robustness
5. **Reasonable Turnover**: Trades not excessive for transaction costs

### Red Flags

- **Very high Sharpe (>3.0)**: Likely overfitting or data snooping
- **High volatility in WF returns**: Strategy may not be robust
- **Too few trades**: Results not statistically significant
- **Only works with specific parameters**: May be curve-fitting

### Statistical Considerations

Per AFML recommendations (see `docs/plans/2026-01-22-AFML-improvements.md`):

1. **Multiple Testing Correction**: When testing N configurations, expect some to show spurious alpha. Use deflated Sharpe ratio or Bonferroni correction.

2. **Walk-Forward Validation**: The research loop uses walk-forward by default, but single in-sample metrics can still mislead.

3. **Track Record Length**: More backtest years = more confidence. 5+ years recommended for production.

## File Format

`alpha_research_results.csv` columns:

```
config_hash         - Unique identifier for this configuration
run_id              - Timestamp of research run
timestamp           - When this config was tested
param_*             - All parameter values
total_return        - Cumulative return
cagr                - Compound annual growth rate
sharpe_ratio        - Risk-adjusted return
sortino_ratio       - Downside-adjusted return
max_drawdown        - Worst drawdown
calmar_ratio        - CAGR / Max Drawdown
annualized_volatility
total_trades
win_rate
profit_factor
avg_win
avg_loss
skewness
kurtosis
wf_windows          - Walk-forward window count
wf_avg_return       - Average per-window return
wf_std_return       - Std dev of per-window returns
backtest_days
universe_size
```

## Future Improvements

Based on AFML recommendations:

- [ ] Triple-barrier labeling instead of fixed-horizon
- [ ] Purged K-fold cross-validation
- [ ] Deflated Sharpe Ratio (PSR) for statistical significance
- [ ] Feature importance (MDA/SFI) for signal weighting
- [ ] Fractionally differentiated features
- [ ] Regime detection integration
