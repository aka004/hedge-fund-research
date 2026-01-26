# Walk-Forward Analysis Integration from Pardo

**Date:** 2026-01-25
**Source:** "The Evaluation and Optimization of Trading Strategies" (2nd Ed.) by Robert Pardo
**Status:** Proposed Improvements

---

## Executive Summary

Analysis of Robert Pardo's seminal work on trading strategy evaluation reveals that our current 5-fold Purged K-Fold CV, while preventing information leakage, **does not simulate real-time deployment**. Pardo's Walk-Forward Analysis (WFA) serves as the **definitive final test** for trading strategies.

**Key Insight:** Purged K-Fold and Walk-Forward Analysis solve *different* problems and should be used *together* in a staged validation pipeline.

### Critical Gaps Identified

| Gap | Current State | Pardo Recommendation | Impact |
|-----|---------------|---------------------|--------|
| **Final Validation** | Purged K-Fold only | Walk-Forward Analysis | Simulates real deployment |
| **Efficiency Metric** | None | Walk-Forward Efficiency (WFE) | Detect overfitting |
| **Parameter Shelf Life** | Not tracked | Rolling optimization windows | Know when to reoptimize |
| **Drawdown Analysis** | Not implemented | MDD tracking + RRR | Proper capitalization |
| **Overfit Detection** | Implicit | Optimization profile analysis | Explicit robustness checks |
| **Performance Trajectory** | Not tracked | Profit/loss distribution | Early warning of decay |

---

## Priority 1: Immediate Implementation (High Impact)

### 1.1 Walk-Forward Analysis (Final Validation Stage)

**Current:** Purged K-Fold → Done
**Add:** Purged K-Fold → Walk-Forward Analysis → Done

> "Walk-Forward Analysis is the most comprehensive form of testing to which a trading strategy can be submitted. It is also the most reliable—and easiest—method of evaluating the robustness of a trading strategy." (Pardo, p. 251)

```yaml
walk_forward_analysis:
  optimization_window: 36 months      # In-sample period
  walk_forward_window: 6 months       # Out-of-sample period
  step_window: 6 months               # Advance interval
  objective_function: "prom"          # Pessimistic Return on Margin

  # Process:
  # 1. Optimize on months 1-36 → select best params
  # 2. Test on months 37-42 (unseen data)
  # 3. Step forward: Optimize months 7-42 → test 43-48
  # 4. Repeat until data exhausted
  # 5. Concatenate all walk-forward results
```

**Two-Step Walk-Forward Process (p. 247):**
1. **Step 1:** Standard optimization on in-sample window
2. **Step 2:** Evaluate top parameter set on adjacent, unseen data

**Why it differs from K-Fold:**
- K-Fold: Shuffled folds, no reoptimization between folds
- WFA: Sequential windows, reoptimize before each test period
- WFA simulates *actual deployment* where you periodically reoptimize

**Book Reference:** Chapter 11, pp. 237-261

---

### 1.2 Walk-Forward Efficiency (WFE) Metric

**Current:** Raw Sharpe from CV folds
**Add:** WFE = Annualized Walk-Forward Profit / Annualized Optimization Profit

> "Research has clearly demonstrated that robust trading strategies have WFEs greater than 50 or 60 percent and in the case of extremely robust strategies, even higher." (Pardo, p. 239)

```python
def calculate_wfe(optimization_results, walkforward_results):
    """
    WFE measures how well in-sample performance translates to out-of-sample.
    """
    opt_annualized = sum(r.profit for r in optimization_results) / total_opt_years
    wf_annualized = sum(r.profit for r in walkforward_results) / total_wf_years

    wfe = (wf_annualized / opt_annualized) * 100
    return wfe
```

**Validation Thresholds (p. 239):**
| WFE | Interpretation | Action |
|-----|----------------|--------|
| < 25% | Likely overfit | **Reject** |
| 25-50% | Poor strategy or overfit | Investigate |
| 50-60% | Robust strategy | **Accept** |
| > 100% | Excellent (favorable conditions) | Accept with caution |

**Book Reference:** Chapter 11, pp. 238-239, 260-261

---

### 1.3 Maximum Drawdown Tracking

**Current:** Not tracked in `BacktestResult`
**Add:** MDD, Average Drawdown, Drawdown trajectory

> "Maximum drawdown (MDD) is the dollar value of the largest decline from equity high to a subsequent equity low... the most important measure of risk for a trading strategy." (Pardo, p. 265)

```python
@dataclass
class BacktestResult:
    # Existing
    sharpe_estimate: float
    win_rate: float
    n_trades: int

    # Add these (from Pardo Ch 12)
    max_drawdown: float
    avg_drawdown: float
    min_drawdown: float
    drawdown_std: float
    max_runup: float  # Largest equity gain peak-to-trough

    # Risk-adjusted
    reward_to_risk_ratio: float  # net_profit / max_drawdown
```

**Required Capital Formula (p. 271):**
```
RC = Margin + (MDD × 2)   # Standard
RC = Margin + (MDD × 3)   # Conservative
```

**Book Reference:** Chapter 12, pp. 265-272

---

### 1.4 Reward-to-Risk Ratio (RRR)

**Current:** Not calculated
**Add:** RRR = Net Profit / Maximum Drawdown

> "A RRR should be three or better." (Pardo, p. 273)

```python
def calculate_rrr(net_profit: float, max_drawdown: float) -> float:
    """
    Annualized Reward-to-Risk Ratio.
    Target: RRR >= 3.0
    """
    if max_drawdown == 0:
        return float('inf')
    return abs(net_profit / max_drawdown)
```

**Validation:**
- RRR < 1.0: Reject (risk exceeds reward)
- RRR 1.0-3.0: Marginal
- RRR ≥ 3.0: Acceptable

**Book Reference:** Chapter 12, p. 273

---

## Priority 2: Overfitting Detection (Medium-Term)

### 2.1 Optimization Profile Analysis

**Current:** Select best parameter set only
**Add:** Analyze entire parameter space distribution

> "A good performing parameter set—a profit spike—surrounded by poor ones is unlikely to be a robust strategy capable of producing real-time profit." (Pardo, p. 228)

```yaml
optimization_profile_analysis:
  metrics:
    profitable_pct: "% of parameter sets with profit > 0"
    avg_profit: "Mean profit across all parameter sets"
    std_profit: "Standard deviation of profits"
    top_vs_neighbors: "Compare top params to adjacent params"

  robustness_thresholds:
    severe_overfit: "profitable_pct < 5%"    # Reject (p. 229)
    marginal: "profitable_pct < 20%"         # Investigate
    robust: "profitable_pct >= 20%"          # Accept

  shape_analysis:
    robust: "Smooth, gradual decline from optimum"
    overfit: "Isolated spikes surrounded by losses"
```

**Signs of Overfit (p. 227-235):**
1. <5% of parameter sets profitable → statistically suspect
2. Top parameter isolated (neighbors unprofitable)
3. Sharp/discontinuous performance changes
4. Large gap between max and average profit

**Signs of Robust Strategy:**
1. ≥20% of parameter sets profitable
2. Top parameter surrounded by profitable neighbors
3. Smooth, continuous parameter space
4. Small standard deviation in profits

**Book Reference:** Chapter 10, pp. 227-235

---

### 2.2 Degrees of Freedom Check

**Current:** Implicit in sample size requirements
**Add:** Explicit DoF validation

> "The size of the data sample must be large enough to accommodate these restrictions and retain sufficient degrees of freedom." (Pardo, p. 220)

```python
def check_degrees_of_freedom(
    n_samples: int,
    n_parameters: int,
    max_lookback: int,
    min_trades: int = 30
) -> tuple[bool, str]:
    """
    Validate sufficient degrees of freedom.

    Rules:
    - At least 30 trades (preferably more)
    - Data consumed by lookback < 25% of sample
    - Parameters should be proportional to sample size
    """
    effective_samples = n_samples - max_lookback

    if effective_samples < min_trades * 10:
        return False, f"Insufficient data: {effective_samples} < {min_trades * 10}"

    if max_lookback / n_samples > 0.25:
        return False, f"Lookback consumes {max_lookback/n_samples:.0%} of data"

    # Rule of thumb: ~10 samples per parameter minimum
    if n_samples / n_parameters < 10:
        return False, f"Too many parameters: {n_parameters} for {n_samples} samples"

    return True, "Sufficient degrees of freedom"
```

**Book Reference:** Chapter 13, pp. 292-295

---

### 2.3 Overfit Symptom Detection

**Current:** No explicit detection
**Add:** Automated warning system

> "The overfit trading strategy will produce very impressive results during simulation and often devastatingly poor performance during real-time trading." (Pardo, p. 240)

```python
@dataclass
class OverfitWarning:
    level: Literal["none", "low", "medium", "severe"]
    reasons: list[str]

def detect_overfitting(
    optimization_results: list,
    walkforward_results: list,
    wfe: float
) -> OverfitWarning:
    reasons = []

    # Check 1: WFE too low
    if wfe < 25:
        reasons.append(f"WFE={wfe:.0f}% < 25% threshold")

    # Check 2: Concentrated profits
    profits = [r.profit for r in walkforward_results]
    if max(profits) > sum(profits) * 0.5:
        reasons.append("50%+ of profit from single period")

    # Check 3: Optimization profile
    opt_profitable = sum(1 for r in optimization_results if r.profit > 0)
    opt_pct = opt_profitable / len(optimization_results)
    if opt_pct < 0.05:
        reasons.append(f"Only {opt_pct:.1%} of params profitable")

    # Check 4: Trajectory
    recent = profits[-3:]  # Last 3 periods
    if all(p < 0 for p in recent):
        reasons.append("Last 3 periods all negative (decay)")

    # Determine level
    if len(reasons) >= 3:
        level = "severe"
    elif len(reasons) == 2:
        level = "medium"
    elif len(reasons) == 1:
        level = "low"
    else:
        level = "none"

    return OverfitWarning(level=level, reasons=reasons)
```

**Causes of Overfitting (Chapter 13, pp. 291-298):**
| Cause | Description | Prevention |
|-------|-------------|------------|
| Overparameterization | Too many optimizable params | Keep params minimal |
| Overscanning | Too fine parameter steps | Proportional step sizes |
| Small sample | Insufficient trades | ≥30 trades minimum |
| Profit spike selection | Isolated peak chosen | Check neighbors |
| Big fish/small pond | Great on one market/period | Multi-market testing |

**Book Reference:** Chapter 13, pp. 281-298

---

## Priority 3: Advanced Features (Long-Term)

### 3.1 Model Efficiency Metric

**Current:** Not implemented
**Add:** ME = Net Profit / Perfect Profit

> "Model Efficiency is a measure of how efficiently a trading strategy converts or 'transforms' the perfect potential profit offered by a market into realized trading proﬁts." (Pardo, p. 274)

```python
def calculate_perfect_profit(prices: pd.Series) -> float:
    """
    Sum of all possible swing captures (buy every bottom, sell every top).
    """
    # Find all local peaks and troughs
    peaks = find_peaks(prices)
    troughs = find_peaks(-prices)

    # Sum absolute swings
    pp = 0
    for i in range(len(peaks) - 1):
        swing = abs(prices[peaks[i]] - prices[troughs[i]])
        pp += swing

    return pp

def model_efficiency(net_profit: float, prices: pd.Series) -> float:
    """
    ME >= 5% is considered very good.
    """
    pp = calculate_perfect_profit(prices)
    return (net_profit / pp) * 100 if pp > 0 else 0
```

**Utility:**
- Allows cross-market, cross-period comparison
- Controls for market opportunity (trending vs choppy)
- ME stays stable even as raw profits fluctuate with volatility

**Book Reference:** Chapter 12, pp. 273-276

---

### 3.2 Performance Trajectory Analysis

**Current:** Aggregate metrics only
**Add:** Period-by-period trend analysis

> "A glance at the distribution of profit and loss on a year-by-year basis gives pause." (Pardo, p. 277)

```python
def analyze_trajectory(period_results: list[PeriodResult]) -> TrajectoryAnalysis:
    """
    Analyze profit/drawdown trends over time.
    """
    profits = [r.profit for r in period_results]
    drawdowns = [r.max_drawdown for r in period_results]

    # Linear regression on profits
    profit_slope = linregress(range(len(profits)), profits).slope

    # Classify trajectory
    if profit_slope > 0 and profits[-1] > np.mean(profits):
        trajectory = "improving"
    elif profit_slope < 0 and profits[-1] < np.mean(profits):
        trajectory = "declining"  # WARNING
    else:
        trajectory = "stable"

    return TrajectoryAnalysis(
        trajectory=trajectory,
        profit_slope=profit_slope,
        best_period=max(range(len(profits)), key=lambda i: profits[i]),
        worst_period=min(range(len(profits)), key=lambda i: profits[i]),
        warning=trajectory == "declining"
    )
```

**Red Flags (pp. 277-280):**
1. Largest profit in distant past, losses recently
2. Drawdowns trending upward over time
3. Best performance in single anomalous period

**Green Flags:**
1. Even distribution of profits across periods
2. Drawdowns stable or declining
3. Recent performance consistent with historical

**Book Reference:** Chapter 12, pp. 276-280

---

### 3.3 Parameter Shelf Life Tracking

**Current:** Parameters never expire
**Add:** Track optimal reoptimization frequency

> "Walk-Forward Analysis provides the shelf life of the parameter set in the form of the length of the walk-forward window." (Pardo, p. 243)

```yaml
parameter_shelf_life:
  from_wfa:
    optimization_window: 36 months
    walk_forward_window: 6 months

    # Shelf life = walk_forward_window
    # Reoptimize every 6 months!

  empirical_rules:
    fast_strategy: "1-2 year opt window → 3-6 month shelf life"
    slow_strategy: "3-6 year opt window → 1-2 year shelf life"

  decay_detection:
    trigger: "Performance drops 1+ std dev below WFA average"
    action: "Trigger reoptimization regardless of schedule"
```

**Book Reference:** Chapter 11, pp. 242-243, 249

---

## Current vs Recommended: Comparison Table

| Aspect | Current Implementation | Pardo Recommendation | Priority |
|--------|----------------------|---------------------|----------|
| **Validation Method** | Purged K-Fold (5 folds) | Purged K-Fold → Walk-Forward Analysis | P1 |
| **Key Metric** | Sharpe estimate | WFE (50%+ required) | P1 |
| **Reoptimization** | Not simulated | Rolling windows in WFA | P1 |
| **Drawdown** | Not tracked | MDD + RRR (≥3.0 target) | P1 |
| **Overfit Detection** | None explicit | Optimization profile analysis | P2 |
| **Degrees of Freedom** | Not checked | Explicit validation | P2 |
| **Trajectory** | Not analyzed | Period-by-period trends | P3 |
| **Model Efficiency** | Not calculated | ME vs Perfect Profit | P3 |
| **Shelf Life** | Not tracked | From WFA window size | P3 |

---

## Proposed Validation Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│                    VALIDATION PIPELINE                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. ALPHA GENERATION                                             │
│     └── Momentum/Value/Social signals                            │
│              ↓                                                   │
│  2. TRIPLE-BARRIER LABELING (AFML)                               │
│     └── Dynamic exits (profit/stop/time)                         │
│              ↓                                                   │
│  3. PURGED K-FOLD CV (Current - Quick Screening)                 │
│     └── 5 folds, embargo, purging                                │
│     └── GATE: Sharpe > 0.5                                       │
│              ↓                                                   │
│  4. WALK-FORWARD ANALYSIS (New - Final Validation) ← ADD THIS    │
│     └── 36-month opt / 6-month WF windows                        │
│     └── GATE: WFE > 50%                                          │
│     └── GATE: RRR > 3.0                                          │
│              ↓                                                   │
│  5. PSR FILTERING (AFML)                                         │
│     └── Deflated Sharpe > 0.95 probability                       │
│              ↓                                                   │
│  6. PRODUCTION DEPLOYMENT                                        │
│     └── Reoptimize every [WF window] months                      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Implementation Roadmap

### Phase 1: Core WFA (Week 1-2)
- [ ] Create `WalkForwardAnalysis` class in `afml/`
- [ ] Implement rolling optimization/test windows
- [ ] Add WFE calculation
- [ ] Add MDD and RRR to `BacktestResult`
- [ ] Integrate as step after purged k-fold

### Phase 2: Overfitting Detection (Week 3)
- [ ] Implement optimization profile analysis
- [ ] Add degrees of freedom validation
- [ ] Create `OverfitWarning` detection system
- [ ] Add automated warnings to backtest output

### Phase 3: Advanced Metrics (Week 4)
- [ ] Implement Perfect Profit calculation
- [ ] Add Model Efficiency metric
- [ ] Implement trajectory analysis
- [ ] Add parameter shelf life tracking

### Phase 4: Integration (Week 5)
- [ ] Update `BacktestUnit` agent to use WFA
- [ ] Add WFE threshold to validation gates
- [ ] Create reoptimization scheduler
- [ ] Update documentation and tests

---

## Key Quotes from Pardo

### On Walk-Forward as Final Test
> "If a trading strategy performs well under a Walk-Forward Analysis, it has shown itself to be robust and capable of producing real-time trading profit." (p. 237)

### On WFE Thresholds
> "A trading strategy is likely overfit if it has a low Walk-Forward Efficiency; in other words, if the rate of return of out-of-sample trading is decidedly lower than that of in-sample trading." (p. 239)

### On Overfitting
> "An overfit trading strategy is one that is excessively fit or fit to an unwanted degree... not suitable for producing real-time trading profits." (p. 282)

### On Robustness
> "The most robust trading strategy is that trading strategy that performs in a profitable and relatively consistent manner over: (1) The broadest possible range of parameter sets, (2) All the major market types, (3) A majority of different historical time periods, (4) Many different types of markets." (p. 226)

### On Parameter Space
> "A robust one-variable optimization will produce a plot of profit performance with a top parameter set and performance that gradually declines on both sides of it." (p. 232)

---

## References

**Primary Source:**
- Pardo, R. (2008). *The Evaluation and Optimization of Trading Strategies* (2nd ed.). Wiley.
  - Chapter 10: Optimization (pp. 211-236)
  - Chapter 11: Walk-Forward Analysis (pp. 237-261)
  - Chapter 12: The Evaluation of Performance (pp. 263-280)
  - Chapter 13: The Many Faces of Overfitting (pp. 281-298)

**Complementary (already implemented):**
- López de Prado, M. (2018). *Advances in Financial Machine Learning*. Wiley.
  - Chapter 7: Cross-Validation in Finance (Purged K-Fold)

---

## Relationship to AFML Improvements

This document complements the [2026-01-22-AFML-improvements.md](./2026-01-22-AFML-improvements.md) plan:

| AFML Recommendation | Pardo Addition |
|---------------------|----------------|
| Purged K-Fold CV | + Walk-Forward Analysis as final step |
| Deflated Sharpe (PSR) | + Walk-Forward Efficiency (WFE) |
| Triple-Barrier Labels | Use within WFA optimization windows |
| Feature Importance | Apply during WFA parameter selection |

**Key Insight:** AFML addresses *information leakage* in cross-validation. Pardo addresses *deployment simulation*. Both are necessary for robust strategy validation.

---

*Generated: 2026-01-25 by analysis of Pardo (2008)*
