# Hedge Fund Simulation Improvements from AFML

**Date:** 2026-01-22
**Source:** "Advances in Financial Machine Learning" by Marcos López de Prado
**Status:** Proposed Improvements

---

## Executive Summary

Seven specialist agents analyzed your hedge fund simulation design against López de Prado's AFML framework. This document synthesizes their recommendations into **prioritized, actionable improvements**.

### Critical Gaps Identified

| Gap | Current State | AFML Recommendation | Impact |
|-----|---------------|---------------------|--------|
| **Labeling** | Fixed-time returns | Triple-Barrier Method | More realistic P&L |
| **Cross-Validation** | Standard k-fold | Purged K-Fold + Embargo | No information leakage |
| **Sharpe Ratio** | Raw calculation | Deflated SR (PSR) | Selection bias correction |
| **Portfolio Construction** | Score-weighted | Hierarchical Risk Parity | Better OOS variance |
| **Regime Detection** | None explicit | CUSUM + SADF + Entropy | Early warning system |
| **Feature Engineering** | Returns | Fractional Differentiation | Memory + stationarity |
| **Bet Sizing** | Equal weights | Probability-based sizing | Reduced turnover |

---

## Priority 1: Immediate Implementation (High Impact, Foundational)

### 1.1 Triple-Barrier Labeling (All Researchers)

**Current:** Fixed-time horizon returns
**Replace with:** Dynamic exit conditions

```yaml
triple_barrier:
  profit_taking: 2 * daily_volatility  # Upper barrier
  stop_loss: -2 * daily_volatility      # Lower barrier
  max_holding: 10 days                  # Vertical barrier

  # Label = first barrier touched
  # Returns = actual P&L at exit
```

**Why:** Fixed-time assumes returns arrive on schedule. Reality: trades exit at stop-loss, profit target, OR time limit. Triple-barrier captures actual trading dynamics.

**Agent Source:** Momentum Researcher, Backtest Unit

---

### 1.2 Purged K-Fold Cross-Validation (Backtest Unit)

**Current:** Standard sklearn k-fold
**Replace with:** Purged + Embargo CV

```yaml
purged_kfold:
  k: 5
  purge_gap: max_holding_period  # Remove training overlap with test labels
  embargo_pct: 0.01              # Buffer after test period

  # CRITICAL: sklearn k-fold leaks information in finance!
```

**Implementation:**
1. For each fold, identify test label time span
2. **Purge:** Remove training samples whose labels overlap test period
3. **Embargo:** Add buffer equal to 1% of data after test set
4. Compute metrics only on out-of-sample predictions

**Agent Source:** Backtest Unit, Statistical Agent, Math Professor

---

### 1.3 Deflated Sharpe Ratio (Statistical Agent)

**Current:** Raw Sharpe = μ/σ
**Replace with:** PSR (Probabilistic Sharpe Ratio)

```python
# Adjust for:
# 1. Non-normality (skewness, kurtosis)
# 2. Selection bias (N strategies tested)
# 3. Track record length

PSR = Φ[ (SR_observed - SR_benchmark) / SE(SR) ]

where SE(SR) = sqrt((1 + 0.5*SR² - skew*SR + ((kurtosis-3)/4)*SR²) / n)
```

**New Validation Check:**
- `stats.approved` requires PSR > 0.95 (95% confidence SR exceeds benchmark)
- Track number of strategy variations tested → adjust for multiple testing

**Agent Source:** Statistical Agent, Math Professor

---

### 1.4 Feature Importance Diagnostics (Portfolio Constructor)

**Current:** Equal signal weights (0.33 each)
**Replace with:** Data-driven weights via MDA/SFI

```yaml
feature_importance:
  methods:
    - MDA: "Permutation importance - shuffle feature, measure accuracy drop"
    - SFI: "Single feature importance - fit model on each feature alone"
    - MDI: "Mean decrease impurity (for tree models)"

  example_result:
    momentum: 0.60  # Drives 60% of returns
    value: 0.30     # Drives 30%
    social: 0.10    # Mostly noise!
```

**Agent Source:** Portfolio Constructor, Math Professor

---

## Priority 2: Architecture Improvements (Medium-Term)

### 2.1 Hierarchical Risk Parity (Risk Manager, Portfolio Constructor)

**Current:** Score-proportional weights
**Replace with:** HRP (handles correlated assets without matrix inversion)

**Algorithm:**
```
Step 1: Compute correlation distance: d = sqrt(0.5 * (1 - corr))
Step 2: Hierarchical clustering (single-linkage)
Step 3: Quasi-diagonalize matrix (reorder by cluster)
Step 4: Recursive bisection - allocate by inverse variance
```

**Benefits:**
- No covariance matrix inversion (numerically stable)
- Lower out-of-sample variance than CLA
- Handles singular/ill-conditioned matrices
- More stable weights over time

**Condition Number Monitoring:**
```python
kappa = λ_max / λ_min
if kappa > 100:
    risk.concerns("Ill-conditioned covariance - weights unreliable")
```

**Agent Source:** Risk Manager, Portfolio Constructor

---

### 2.2 Meta-Labeling (All Researchers)

**Current:** Single model predicts side + size
**Replace with:** Two-stage approach

```yaml
meta_labeling:
  primary_model:
    task: "Predict direction (long/short)"
    method: "Your existing momentum/value signals"
    output: "side"

  secondary_model:
    task: "Predict whether to ACT on primary signal"
    output: "size (0 = pass, 1 = full position)"
    features:
      - market_regime
      - signal_strength
      - liquidity_conditions
      - concurrent_signals
```

**Benefits:**
- Primary model focuses on direction (high recall)
- Secondary model filters false positives (high precision)
- Combine for better F1-score
- Can use different features for each task

**Agent Source:** Momentum Researcher, Math Professor

---

### 2.3 Strategy Risk Calculation (Risk Manager)

**Current:** Only portfolio risk (volatility)
**Add:** Strategy failure probability

```python
# P[strategy fails to hit target Sharpe]

# Required precision for target SR:
p_star = 0.5 * (1 + SR_target * sqrt(1 / (n + SR_target²)))

# Example: SR=2, n=260 daily bets
p_star = 0.67  # Need 67% precision to achieve SR=2

# Strategy risk = P[p < p_star]
# Compute via bootstrapping precision from historical outcomes
```

**Key Insight:** A low-volatility portfolio can have HIGH strategy risk if:
- Betting frequency is low
- Profit-taking and stop-loss are asymmetric
- Required precision is barely met

**Agent Source:** Risk Manager, Statistical Agent

---

## Priority 3: Advanced Features (Long-Term)

### 3.1 Fractionally Differentiated Features (Momentum Researcher)

**Current:** Returns = diff(log_price, 1) → Stationary but loses memory
**Replace with:** Fractional differentiation

```python
# Find minimum d where ADF test passes
# d=0: price (has memory, not stationary)
# d=1: returns (stationary, no memory)
# d~0.4: both stationarity AND memory!

def fractional_diff(series, d):
    # FFD (Fixed-Width Window Fracdiff)
    # Uses fractional calculus to differentiate by non-integer order
    weights = get_weights_ffd(d, threshold=1e-5)
    return series.rolling(len(weights)).apply(lambda x: np.dot(weights, x))
```

**Agent Source:** Momentum Researcher, Math Professor

---

### 3.2 Regime Detection Enhancement (Regime Agent)

**Current:** Implicit in researchers
**Add:** Explicit regime detection infrastructure

```yaml
regime_detection:
  structural_breaks:
    cusum_test:
      description: "Cumulative sum of standardized residuals"
      use_case: "Detect gradual parameter shifts"

    sadf_gsadf:
      description: "Sup ADF / Generalized Sup ADF"
      use_case: "Detect bubble formation/collapse"

  information_metrics:
    entropy:
      shannon: "H = -Σ p*log(p)"
      lempel_ziv: "Count unique patterns (complexity)"
      use_case: "Low entropy = predictable regime (exploitable)"

  microstructure:
    vpin: "Volume-synchronized probability of informed trading"
    kyle_lambda: "Price impact coefficient"
    use_case: "Often lead price changes"
```

**New Events:**
- `regime.bubble_forming` (SADF statistic exceeds threshold)
- `regime.structural_break` (CUSUM crosses boundary)
- `regime.low_entropy` (predictable period detected)

**Agent Source:** Regime Agent

---

### 3.3 Sample Weights by Uniqueness (All Models)

**Current:** Equal sample weights
**Replace with:** Average uniqueness weighting

```python
def compute_uniqueness(labels_df):
    """
    If two labels share overlapping return periods,
    they're correlated. Weight by inverse concurrency.
    """
    concurrent = labels_df.expanding().sum()  # Count overlapping labels
    uniqueness = 1.0 / concurrent
    avg_uniqueness = uniqueness.mean(axis=1)
    return avg_uniqueness

# Use in cross-validation, model training, statistics
sample_weights = compute_uniqueness(labels)
```

**Agent Source:** Statistical Agent, Math Professor, Backtest Unit

---

### 3.4 Bet Averaging & Discretization (Portfolio Constructor)

**Current:** Rebalance to exact target weights
**Replace with:** Smoothed, discretized positions

```yaml
bet_management:
  averaging:
    method: "5-day rolling average of signals"
    benefit: "Reduces whipsaw from noisy predictions"

  discretization:
    method: "Round weights to 10% increments"
    example: "0.0847 → 0.10"
    benefit: "Avoids trading tiny fractions"

  combined_impact:
    baseline_turnover: "40% monthly"
    with_averaging: "24% monthly"
    with_discretization: "14% monthly"
    transaction_cost_savings: "2-3% annualized"
```

**Agent Source:** Portfolio Constructor, Risk Manager

---

## Implementation Roadmap

### Phase 1: Foundation (Weeks 1-2)
- [ ] Implement Triple-Barrier labeling
- [ ] Replace k-fold with Purged K-Fold CV
- [ ] Add Deflated Sharpe Ratio to Statistical Agent checks
- [ ] Add Feature Importance diagnostics

### Phase 2: Architecture (Weeks 3-4)
- [ ] Implement HRP for portfolio construction
- [ ] Add Meta-Labeling infrastructure
- [ ] Implement Strategy Risk calculation
- [ ] Add Condition Number monitoring

### Phase 3: Advanced (Weeks 5-8)
- [ ] Implement Fractional Differentiation
- [ ] Build Regime Detection module (CUSUM, SADF, Entropy)
- [ ] Add Sample Uniqueness weighting
- [ ] Implement Bet Averaging/Discretization

---

## References

All recommendations derived from:
- López de Prado, M. (2018). *Advances in Financial Machine Learning*. Wiley.
  - Ch 3: Labeling (Triple-Barrier, Meta-Labeling)
  - Ch 4: Sample Weights
  - Ch 5: Fractionally Differentiated Features
  - Ch 6: Ensemble Methods
  - Ch 7: Cross-Validation in Finance
  - Ch 10: Bet Sizing
  - Ch 14: Backtest Statistics (PSR)
  - Ch 15: Understanding Strategy Risk
  - Ch 16: Machine Learning Asset Allocation (HRP)
  - Ch 17: Structural Breaks
  - Ch 18: Entropy Features

---

## Agent Contributions

| Agent | Key Recommendations |
|-------|---------------------|
| **Momentum Researcher** | Fractional differentiation, Triple-barrier, Meta-labeling |
| **Statistical Agent** | Deflated Sharpe, Sample uniqueness, Multiple testing corrections |
| **Backtest Unit** | Purged K-Fold, Synthetic data testing, Walk-forward variants |
| **Risk Manager** | HRP, Strategy risk vs portfolio risk, Bet sizing |
| **Portfolio Constructor** | HRP, Feature importance, Bet averaging |
| **Regime Agent** | CUSUM, SADF/GSADF, Entropy features, Microstructure |
| **Math Professor** | IID violation checks, Stationarity tests, CV pitfalls |

---

*Generated: 2026-01-22 by multi-agent analysis of AFML*
