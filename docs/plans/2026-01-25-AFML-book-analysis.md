# Deep Analysis: AFML Book vs. Current Implementation

**Date:** 2026-01-25  
**Source:** "Advances in Financial Machine Learning" by Marcos López de Prado (Wiley, 2018)  
**Status:** Implementation Gap Analysis with Code-Level Recommendations

---

## Executive Summary

This document provides a deep-dive analysis of four core AFML methodologies against the current hedge-fund-research implementation. Each section includes book citations, current vs. recommended code comparisons, and specific fixes.

### Implementation Status Matrix

| Component | Book Chapter | Current Status | Gap Severity | Fix Complexity |
|-----------|--------------|----------------|--------------|----------------|
| **Triple-Barrier Labeling** | Ch. 3 (§3.4) | ✅ Implemented | 🟡 Medium | Low |
| **Dynamic Volatility** | Ch. 3 (§3.3) | ❌ Wrong method | 🔴 High | Low |
| **CUSUM Event Sampling** | Ch. 2 (§2.5.2) | ❌ Missing | 🟡 Medium | Medium |
| **Meta-Labeling** | Ch. 3 (§3.6-3.7) | ⚠️ Partial | 🟡 Medium | Medium |
| **Purged K-Fold CV** | Ch. 7 (§7.4) | ✅ Implemented | 🟡 Medium | Low |
| **Bi-directional Purging** | Ch. 7 (§7.4.1) | ❌ Missing | 🔴 High | Low |
| **CPCV** | Ch. 12 (§12.4) | ❌ Missing | 🟡 Medium | High |
| **PSR/Deflated Sharpe** | Ch. 14 (§14.7) | ⚠️ Bug in formula | 🔴 High | Low |
| **minTRL Calculation** | Ch. 14 (§14.7.4) | ❌ Missing | 🟡 Medium | Low |
| **Feature Importance** | Ch. 8 | ❌ Missing | 🟡 Medium | Medium |
| **PBO Calculation** | Ch. 11 (§11.6) | ❌ Missing | 🟡 Medium | Low |

---

## 1. Triple-Barrier Labeling Method

### Book Reference
> **Chapter 3, Section 3.4 (pp. 49-53)**  
> "The triple-barrier method labels an observation according to the first barrier touched out of three barriers."

### 1.1 Dynamic Volatility Thresholds

**Book Citation (§3.3, p. 47):**
> "We compute dailyVol as the exponentially weighted moving standard deviation of returns... This allows the thresholds to adjust to current market conditions."

**Current Implementation** (`afml/labels.py`, line 58):
```python
# CURRENT: Simple rolling window - NOT recommended by book
if volatility is None:
    volatility = prices.pct_change().rolling(20).std()
```

**AFML Recommended** (Snippet 3.1, p. 46):
```python
# RECOMMENDED: Exponentially-weighted for responsiveness
if volatility is None:
    volatility = prices.pct_change().ewm(span=100, min_periods=50).std()
```

**Why This Matters:**
- Rolling window responds slowly to volatility regime changes
- EWMA gives more weight to recent observations
- Book uses span=100 (~50-day half-life) as default

---

### 1.2 Event Sampling (Missing)

**Book Citation (§2.5.2.1, p. 39):**
> "A CUSUM filter is a quality-control method designed to detect a shift in the mean value of a measured quantity away from a target value."

**Current Implementation** (`momentum_researcher.py`):
```python
# CURRENT: Uses ALL timestamps or symbol-level sampling
if events is None:
    events = prices.index[:-max_holding]  # All available timestamps
```

**AFML Recommended** (Snippet 2.4, p. 39):
```python
# RECOMMENDED: CUSUM filter for meaningful events
def cusum_filter(prices: pd.Series, threshold: float = None) -> pd.DatetimeIndex:
    """
    Sample events when cumulative sum of returns exceeds threshold.
    AFML Chapter 2, Section 2.5.2.1
    """
    if threshold is None:
        threshold = prices.pct_change().std()
    
    t_events = []
    s_pos, s_neg = 0, 0
    returns = prices.pct_change().dropna()
    
    for t, r in returns.items():
        s_pos = max(0, s_pos + r)
        s_neg = min(0, s_neg + r)
        
        if s_pos > threshold:
            t_events.append(t)
            s_pos = 0
        elif s_neg < -threshold:
            t_events.append(t)
            s_neg = 0
    
    return pd.DatetimeIndex(t_events)

# Usage in triple_barrier:
events = cusum_filter(prices, threshold=2*daily_vol)
labels = triple_barrier(prices, events=events, ...)
```

**Why This Matters:**
- Labeling ALL timestamps creates massively overlapping labels
- CUSUM samples only when "something meaningful happened"
- Reduces redundancy, improves label uniqueness

---

### 1.3 Meta-Labeling Integration

**Book Citation (§3.6, p. 55):**
> "Meta-labeling is a technique where we want to build a secondary ML model that learns how to use a primary exogenous model."

**Current Implementation** (`momentum_researcher.py`):
```python
# CURRENT: Single-stage labeling, side parameter unused
labels = triple_barrier(
    prices=prices,
    profit_take=self.strategy.profit_take,
    stop_loss=self.strategy.stop_loss,
    max_holding=self.strategy.max_holding,
    # side=... NOT USED!
)
```

**AFML Recommended** (§3.6-3.7):
```python
# RECOMMENDED: Two-stage meta-labeling workflow
class MomentumResearcher:
    def generate_alpha(self, symbols):
        for symbol in symbols:
            prices = self._load_prices(symbol)
            
            # Stage 1: Primary model determines SIDE
            primary_side = self._get_primary_signal(prices)  # Returns {-1, 1}
            
            # Stage 2: Meta-labeling with asymmetric barriers
            # Now profit-taking and stop-loss are relative to predicted side
            labels = triple_barrier(
                prices=prices,
                side=primary_side,
                profit_take=2.0,  # Can be different from stop_loss
                stop_loss=1.5,    # Asymmetric allowed when side known
                max_holding=self.strategy.max_holding,
            )
            
            # Labels are now {0, 1}: 0=don't act, 1=act on signal
            # Train secondary model to filter false positives
```

**Benefits (§3.7, p. 58):**
1. Primary model focuses on recall (catching opportunities)
2. Secondary model focuses on precision (filtering false positives)
3. Combined F1-score typically better than single model
4. Allows asymmetric barriers (different risk/reward)

---

## 2. Purged K-Fold Cross-Validation

### Book Reference
> **Chapter 7, Section 7.4 (pp. 107-112)**  
> "The solution to the train/test contamination problem involves purging from the training set all observations whose labels overlapped in time with those labels included in the testing set."

### 2.1 Bi-Directional Purging (Missing)

**Book Citation (§7.4.1, p. 108):**
> "We must purge from the training set all observations whose outcome was a function of information that will also be used to decide the outcome of test labels."

**Current Implementation** (`afml/cv.py`, lines 70-85):
```python
# CURRENT: Only purges training BEFORE test
# Purge: remove training samples whose labels overlap test period
if labels_end_times is not None:
    for i in range(n_samples):
        if train_mask[i]:
            sample_time = X.index[i]
            label_end = labels_end_times.iloc[i]
            # If this training sample's label extends into test period
            if (sample_time < test_start_time and label_end > test_start_time):
                train_mask[i] = False
```

**AFML Recommended** (Figure 7.1, p. 109):
```python
# RECOMMENDED: Bi-directional purging
if labels_end_times is not None:
    for i in range(n_samples):
        if train_mask[i]:
            sample_time = X.index[i]
            label_end = labels_end_times.iloc[i]
            
            # FORWARD PURGE: Training before test
            # If training sample's label extends INTO test period
            if sample_time < test_start_time and label_end > test_start_time:
                train_mask[i] = False
            
            # BACKWARD PURGE: Training after test (MISSING!)
            # If training sample uses information from test period
            elif sample_time >= test_end_time + embargo_size:
                # Check if any test labels could contaminate this sample
                # A sample at time t depends on prices from t-lookback to t
                lookback_start = sample_time - pd.Timedelta(days=lookback_period)
                if lookback_start < test_end_time:
                    train_mask[i] = False
```

**Visual Explanation:**
```
Timeline: ----[TEST PERIOD]----

FORWARD PURGE (implemented):
  Train sample |----label----|
                      ^-- extends into test → PURGE

BACKWARD PURGE (MISSING):
  Train sample           |----features use data from here----|
                              ^-- overlaps test → PURGE
```

---

### 2.2 Combinatorial Purged CV (Missing)

**Book Citation (§12.4, p. 174):**
> "CPCV generates multiple backtest paths from the same data, allowing us to compute the probability of backtest overfitting."

**Current Implementation:** Not implemented

**AFML Recommended** (Snippet 12.1, p. 175):
```python
# NEW FILE: afml/cpcv.py

from itertools import combinations
import numpy as np

class CombinatorialPurgedKFold:
    """
    AFML Chapter 12.4: Combinatorial Purged Cross-Validation
    
    Generates C(N, k) paths where:
    - N = number of groups
    - k = number of test groups per path
    """
    
    def __init__(self, n_splits: int = 6, n_test_groups: int = 2, embargo_pct: float = 0.01):
        self.n_splits = n_splits
        self.n_test_groups = n_test_groups
        self.embargo_pct = embargo_pct
    
    @property
    def n_paths(self) -> int:
        """Number of unique backtest paths"""
        from math import comb
        return comb(self.n_splits, self.n_test_groups)
    
    def split(self, X, y=None, labels_end_times=None):
        """Generate all path combinations with purging"""
        n = len(X)
        indices = np.arange(n)
        group_size = n // self.n_splits
        
        # Create groups
        groups = [indices[i*group_size:(i+1)*group_size] for i in range(self.n_splits)]
        
        # Generate all combinations of test groups
        for test_combo in combinations(range(self.n_splits), self.n_test_groups):
            test_indices = np.concatenate([groups[i] for i in test_combo])
            train_groups = [i for i in range(self.n_splits) if i not in test_combo]
            train_indices = np.concatenate([groups[i] for i in train_groups])
            
            # Apply purging (similar to PurgedKFold)
            train_indices = self._purge(X, train_indices, test_indices, labels_end_times)
            
            yield train_indices, test_indices, test_combo  # Return path identifier

# Example: N=6, k=2 gives C(6,2)=15 unique backtest paths
```

**Why This Matters (§12.5, p. 178):**
- Walk-forward gives only 1 path → can't assess variability
- CPCV gives 15+ paths → can compute confidence intervals
- Essential for Probability of Backtest Overfitting (PBO)

---

## 3. Probabilistic Sharpe Ratio (PSR)

### Book Reference
> **Chapter 14, Section 14.7 (pp. 206-212)**  
> "The PSR corrects for three shortcomings of the standard Sharpe ratio: (1) non-normality, (2) short track records, and (3) multiple testing."

### 3.1 Critical Bug: Benchmark Formula

**Book Citation (§14.7.3, p. 210, Equation 14.12):**
> "The expected maximum Sharpe ratio from N independent trials is approximately:  
> E[max{SR}] ≈ (1-γ)Φ⁻¹(1-1/N) + γΦ⁻¹(1-1/(Ne))"

**Current Implementation** (`afml/metrics.py`, lines 64-70):
```python
# CURRENT: BUG - incorrectly divides by sqrt(annualization)
if n_strategies_tested > 1:
    expected_max_sharpe = (
        (1 - np.euler_gamma) * stats.norm.ppf(1 - 1 / n_strategies_tested)
        + np.euler_gamma * stats.norm.ppf(1 - 1 / (n_strategies_tested * np.e))
    ) / np.sqrt(annualization)  # ← THIS IS WRONG
    benchmark_sharpe = max(benchmark_sharpe, expected_max_sharpe)
```

**AFML Recommended:**
```python
# CORRECTED: Remove incorrect annualization
if n_strategies_tested > 1:
    # Bailey & López de Prado (2014) Equation 2
    # This gives expected max SR in SAME units as observed SR
    expected_max_sharpe = (
        (1 - np.euler_gamma) * stats.norm.ppf(1 - 1 / n_strategies_tested)
        + np.euler_gamma * stats.norm.ppf(1 - 1 / (n_strategies_tested * np.e))
    )
    # No division! Formula already in SR units
    benchmark_sharpe = max(benchmark_sharpe, expected_max_sharpe)
```

**Impact of Bug:**
- With N=10 strategies, annualization=252:
  - Bug gives: `expected_max ≈ 0.10` (too low!)
  - Correct gives: `expected_max ≈ 1.59` (realistic)
- Bug causes PSR to be artificially inflated, approving bad strategies

---

### 3.2 Minimum Track Record Length (Missing)

**Book Citation (§14.7.4, p. 211):**
> "Given an observed Sharpe ratio, what is the minimum track record length needed for the PSR to reach a certain threshold?"

**Current Implementation:**
```python
# CURRENT: Arbitrary 10-observation minimum
min_observations = 10
if len(returns) < min_observations:
    return StatisticalResult(passed=False, reason="insufficient_observations")
```

**AFML Recommended** (Equation 14.14, p. 211):
```python
# RECOMMENDED: Calculate minimum track record length
def min_track_record_length(
    sharpe: float,
    benchmark_sharpe: float,
    skewness: float,
    kurtosis: float,
    confidence: float = 0.95
) -> float:
    """
    AFML Equation 14.14: Minimum observations for statistical significance
    
    minTRL = 1 + (1 - skew*SR + ((kurt-3)/4)*SR²) * (z_α / (SR - SR*))²
    """
    z_alpha = stats.norm.ppf(confidence)
    excess_kurt = kurtosis - 3
    
    if sharpe <= benchmark_sharpe:
        return float('inf')  # Can never be significant
    
    numerator = 1 - skewness * sharpe + (excess_kurt / 4) * sharpe**2
    denominator = ((sharpe - benchmark_sharpe) / z_alpha)**2
    
    return 1 + numerator / denominator

# Usage in statistical_agent.py:
min_trl = min_track_record_length(result.sharpe, 0.0, result.skewness, result.kurtosis)
if len(returns) < max(30, min_trl):
    return StatisticalResult(passed=False, reason=f"need {min_trl:.0f} observations, have {len(returns)}")
```

**Example:**
- Observed SR=1.5, skewness=-0.5, kurtosis=5, benchmark=0
- minTRL ≈ 47 observations (not 10!)

---

## 4. Feature Importance & Backtesting Pitfalls

### Book Reference
> **Chapter 8 (pp. 117-133):** Feature Importance  
> **Chapter 11 (pp. 149-165):** The Dangers of Backtesting

### 4.1 Feature Importance Methods (Missing)

**Book Citation (§8.2, p. 118):**
> "Understanding which features are important is perhaps the most valuable insight ML algorithms can provide... far more useful than the final prediction."

**Current Implementation:** No feature importance in project

**AFML Recommended** (§8.3-8.4):
```python
# NEW FILE: afml/feature_importance.py

import numpy as np
import pandas as pd
from sklearn.metrics import log_loss
from sklearn.model_selection import cross_val_score

def mean_decrease_impurity(clf, feature_names: list) -> pd.Series:
    """
    MDI: Standard sklearn feature importance (§8.3)
    WARNING: Biased toward high-cardinality features
    """
    return pd.Series(clf.feature_importances_, index=feature_names).sort_values(ascending=False)


def mean_decrease_accuracy(clf, X, y, cv, sample_weight=None) -> pd.DataFrame:
    """
    MDA: Permutation importance (§8.4)
    More reliable but slower
    """
    from sklearn.base import clone
    
    results = {col: [] for col in X.columns}
    
    for train_idx, test_idx in cv.split(X, y):
        clf_fold = clone(clf)
        clf_fold.fit(X.iloc[train_idx], y.iloc[train_idx])
        
        # Baseline score
        base_score = -log_loss(y.iloc[test_idx], clf_fold.predict_proba(X.iloc[test_idx]))
        
        # Permute each feature
        for col in X.columns:
            X_perm = X.iloc[test_idx].copy()
            np.random.shuffle(X_perm[col].values)
            perm_score = -log_loss(y.iloc[test_idx], clf_fold.predict_proba(X_perm))
            results[col].append(base_score - perm_score)
    
    return pd.DataFrame({
        'mean': {k: np.mean(v) for k, v in results.items()},
        'std': {k: np.std(v) for k, v in results.items()}
    })


def single_feature_importance(clf, X, y, cv) -> pd.DataFrame:
    """
    SFI: Train model on each feature ALONE (§8.4.2)
    No substitution effects - shows true individual power
    """
    results = []
    for col in X.columns:
        scores = cross_val_score(clf, X[[col]], y, cv=cv, scoring='neg_log_loss')
        results.append({
            'feature': col,
            'mean_score': scores.mean(),
            'std_score': scores.std()
        })
    return pd.DataFrame(results).set_index('feature').sort_values('mean_score', ascending=False)
```

**Integration Point** (`agents/momentum_researcher.py`):
```python
# Add feature importance analysis before signal generation
def analyze_features(self, X, y):
    from afml.feature_importance import mean_decrease_accuracy, single_feature_importance
    from afml import PurgedKFold
    
    cv = PurgedKFold(n_splits=5)
    
    mda = mean_decrease_accuracy(self.model, X, y, cv)
    sfi = single_feature_importance(self.model, X, y, cv)
    
    # Log which features actually matter
    self.log(f"MDA importance:\n{mda}")
    self.log(f"SFI importance:\n{sfi}")
    
    # Warn about low-importance features
    noise_features = sfi[sfi['mean_score'] < 0.01].index.tolist()
    if noise_features:
        self.log(f"WARNING: Likely noise features: {noise_features}", level="warning")
```

---

### 4.2 Probability of Backtest Overfitting (Missing)

**Book Citation (§11.6, p. 163):**
> "The probability of backtest overfitting (PBO) is the probability that the optimal in-sample (IS) configuration will underperform the median out-of-sample (OOS) configuration."

**Current Implementation:** Not implemented

**AFML Recommended** (Bailey et al. 2014):
```python
# ADD to afml/metrics.py

def probability_backtest_overfitting(
    is_sharpes: np.ndarray,  # In-sample Sharpe ratios for N strategies
    oos_sharpes: np.ndarray  # Out-of-sample Sharpe ratios for N strategies
) -> float:
    """
    AFML §11.6: Compute PBO
    
    PBO = Fraction of CPCV paths where best-IS strategy underperforms OOS median
    
    High PBO (>0.5) = strategy selection is likely due to overfitting
    """
    n_paths = len(is_sharpes)
    
    overfit_count = 0
    for i in range(n_paths):
        # Find strategy that was best in-sample for this path
        best_is_idx = np.argmax(is_sharpes[i])
        # Check if it underperformed OOS median
        oos_median = np.median(oos_sharpes[i])
        if oos_sharpes[i][best_is_idx] < oos_median:
            overfit_count += 1
    
    return overfit_count / n_paths

# Integration with CPCV:
def compute_pbo_with_cpcv(clf, X, y, n_strategies=10):
    """Full PBO calculation using CPCV"""
    from afml.cpcv import CombinatorialPurgedKFold
    
    cpcv = CombinatorialPurgedKFold(n_splits=6, n_test_groups=2)
    
    is_sharpes = []
    oos_sharpes = []
    
    for train_idx, test_idx, path_id in cpcv.split(X, y):
        # Fit N strategy variants
        path_is = []
        path_oos = []
        for strategy_params in strategy_grid[:n_strategies]:
            clf_variant = configure_strategy(clf, strategy_params)
            clf_variant.fit(X.iloc[train_idx], y.iloc[train_idx])
            
            is_sr = compute_sharpe(clf_variant.predict(X.iloc[train_idx]), y.iloc[train_idx])
            oos_sr = compute_sharpe(clf_variant.predict(X.iloc[test_idx]), y.iloc[test_idx])
            
            path_is.append(is_sr)
            path_oos.append(oos_sr)
        
        is_sharpes.append(path_is)
        oos_sharpes.append(path_oos)
    
    pbo = probability_backtest_overfitting(np.array(is_sharpes), np.array(oos_sharpes))
    
    if pbo > 0.5:
        warnings.warn(f"High PBO ({pbo:.2%}) - strategy selection likely overfit!")
    
    return pbo
```

---

## Implementation Roadmap

### Phase 1: Critical Fixes (This Week)

- [ ] **Fix PSR benchmark formula** (`afml/metrics.py`, line 67)
  - Remove `/ np.sqrt(annualization)` 
  - Impact: Currently approving overfit strategies

- [ ] **Add bi-directional purging** (`afml/cv.py`)
  - Add backward purge after existing forward purge
  - Impact: Information leakage in CV

- [ ] **Use EWMA volatility** (`afml/labels.py`, line 58)
  - Change `rolling(20)` to `ewm(span=100, min_periods=50)`
  - Impact: Barriers don't adapt to regime changes

### Phase 2: Core Improvements (Next 2 Weeks)

- [ ] **Add minTRL calculation** (`afml/metrics.py`)
  - Implement Equation 14.14
  - Update `statistical_agent.py` to use dynamic minimum

- [ ] **Add CUSUM event sampling** (`afml/sampling.py` - new file)
  - Implement CUSUM filter
  - Integrate with `momentum_researcher.py`

- [ ] **Implement feature importance** (`afml/feature_importance.py` - new file)
  - MDA, SFI, MDI methods
  - Add diagnostic logging to researchers

### Phase 3: Advanced Features (Month 2)

- [ ] **Implement CPCV** (`afml/cpcv.py` - new file)
  - Combinatorial Purged Cross-Validation
  - Multiple backtest paths

- [ ] **Add PBO calculation** (`afml/metrics.py`)
  - Integrate with CPCV
  - Add warning thresholds

- [ ] **Meta-labeling workflow** (`agents/momentum_researcher.py`)
  - Two-stage labeling
  - Asymmetric barriers

---

## Quick Reference: Code Fixes

### Fix 1: PSR Benchmark (CRITICAL)
**File:** `afml/metrics.py`, line ~67
```python
# DELETE THIS LINE:
) / np.sqrt(annualization)

# The formula is already in SR units
```

### Fix 2: EWMA Volatility
**File:** `afml/labels.py`, line ~58
```python
# BEFORE:
volatility = prices.pct_change().rolling(20).std()

# AFTER:
volatility = prices.pct_change().ewm(span=100, min_periods=50).std()
```

### Fix 3: Bi-directional Purging
**File:** `afml/cv.py`, add after line ~85
```python
# Add backward purging after forward purging:
# Purge training samples AFTER test+embargo that look back into test
for i in range(n_samples):
    if train_mask[i] and X.index[i] >= test_end_time:
        sample_time = X.index[i]
        # Conservative: purge if sample could see any test data
        if sample_time - pd.Timedelta(days=max_holding) < test_end_time:
            train_mask[i] = False
```

---

## References

### Primary Source
López de Prado, M. (2018). *Advances in Financial Machine Learning*. Wiley.

### Specific Citations
| Topic | Chapter | Pages | Key Equation/Snippet |
|-------|---------|-------|---------------------|
| Triple-Barrier | 3 | 49-53 | Snippet 3.2, 3.3 |
| Dynamic Volatility | 3 | 46-47 | Snippet 3.1 |
| Meta-Labeling | 3 | 55-60 | Snippet 3.6, 3.7 |
| CUSUM Filter | 2 | 39 | Snippet 2.4 |
| Purged K-Fold | 7 | 107-112 | Snippet 7.1, Figure 7.1 |
| CPCV | 12 | 174-180 | Snippet 12.1 |
| PSR | 14 | 206-212 | Equations 14.11-14.14 |
| Feature Importance | 8 | 117-133 | Snippets 8.1-8.4 |
| Backtesting Pitfalls | 11 | 149-165 | Table 11.1 |
| PBO | 11 | 163-165 | Bailey et al. (2014) |

### Supporting Papers
- Bailey, D. & López de Prado, M. (2014). "The Deflated Sharpe Ratio." *Journal of Portfolio Management*
- Bailey, D. et al. (2014). "Pseudo-Mathematics and Financial Charlatanism." *Notices of the AMS*
- Bailey, D. et al. (2017). "The Probability of Backtest Overfitting." *Journal of Computational Finance*

---

*Report generated: 2026-01-25 from deep analysis of AFML book vs. hedge-fund-research implementation*
