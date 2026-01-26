# Machine Learning for Asset Managers - Analysis Report

**Date:** 2026-01-25  
**Source:** "Machine Learning for Asset Managers" by Marcos M. López de Prado (Cambridge University Press, 2020)  
**Status:** Analysis & Recommendations for hedge-fund-research project

---

## Executive Summary

This report analyzes López de Prado's MLAM book and maps its techniques to the hedge-fund-research project, which tests momentum factors using triple-barrier labeling and purged k-fold CV. The project already implements several AFML techniques; MLAM provides **expanded coverage** on clustering, false discovery detection, and portfolio optimization.

### Critical Gaps Identified

| Gap | Current State | MLAM Recommendation | Book Reference |
|-----|---------------|---------------------|----------------|
| **False Discovery Detection** | PSR with fixed threshold | Deflated SR with False Strategy Theorem | Ch 8, pp. 108-113 |
| **Effective Trials Estimation** | Manual n_strategies_tested | ONC clustering of backtest returns | Ch 8, p. 114 |
| **Covariance Denoising** | None | Marcenko-Pastur eigenvalue filtering | Ch 2, pp. 24-29 |
| **Feature Clustering** | None | ONC for redundancy detection | Ch 4, pp. 52-63 |
| **Clustered Importance** | Standard MDI/MDA | CFI handles multicollinearity | Ch 6, pp. 84-90 |
| **Portfolio Construction** | HRP only | Add NCO for when mu is reliable | Ch 7, pp. 98-103 |
| **Sharpe Adjustment** | Basic non-normality | Full skewness/kurtosis adjustment | Ch 8, pp. 107-108 |

---

## Priority 1: Critical Improvements (False Discovery Detection)

### 1.1 False Strategy Theorem Implementation

**Current:** `deflated_sharpe()` uses fixed benchmark_sharpe=0  
**Replace with:** Compute expected max SR from number of trials

**Book Citation (p. 109):**
> "Given a sample of estimated performance statistics {SR̂_k}, k=1,...,K, drawn from IID Gaussians N[0, V[SR̂_k]], then E[max_k{SR̂_k}] ≈ V[SR̂_k]^(1/2) × [(1-γ)Z⁻¹(1-1/K) + γZ⁻¹(1-1/(Ke))]"

Where γ ≈ 0.5772 (Euler-Mascheroni constant)

```python
# Add to afml/metrics.py
def expected_max_sharpe(n_trials: int, sr_std: float = 1.0) -> float:
    """
    False Strategy Theorem (MLAM p. 109).
    Expected maximum Sharpe from K trials of a null strategy.
    """
    gamma = 0.5772156649015329  # Euler-Mascheroni
    if n_trials <= 1:
        return 0.0
    
    z1 = norm.ppf(1 - 1/n_trials)
    z2 = norm.ppf(1 - 1/(n_trials * np.e))
    
    return sr_std * ((1 - gamma) * z1 + gamma * z2)
```

**Integration with StatisticalAgent:**
```python
# In statistical_agent.py validate_statistics()
e_max_sr = expected_max_sharpe(self.n_strategies_tested, sr_variance)
# Use e_max_sr as benchmark instead of 0
dsr = deflated_sharpe(returns, benchmark_sharpe=e_max_sr, ...)
```

**Agent Source:** Statistical Agent

---

### 1.2 Effective Number of Trials Estimation

**Current:** Manual `n_strategies_tested` parameter  
**Replace with:** ONC clustering of backtest returns

**Book Citation (p. 114):**
> "The ONC algorithm discovers the existence of [K] differentiated strategies. Hence, we would estimate that E[K]=4. This is a conservative estimate, since the true number K of independent strategies must be smaller than the number of low-correlated strategies."

```python
# Add to afml/clustering.py
def estimate_effective_trials(
    backtest_returns: pd.DataFrame,  # Each column = one trial's returns
) -> tuple[int, float]:
    """
    Estimate effective independent trials via ONC (MLAM p. 114).
    
    Returns: (n_effective_trials, sr_variance_across_clusters)
    """
    # 1. Compute correlation of backtest returns
    corr = backtest_returns.corr()
    
    # 2. Apply ONC clustering
    clusters = optimal_num_clusters(corr)
    n_effective = len(clusters)
    
    # 3. Compute cluster-level Sharpe ratios for variance
    cluster_srs = []
    for cluster_assets in clusters.values():
        # Min-variance weighted returns within cluster
        cluster_ret = min_var_aggregate(backtest_returns[cluster_assets])
        sr = cluster_ret.mean() / cluster_ret.std() * np.sqrt(252)
        cluster_srs.append(sr)
    
    sr_variance = np.var(cluster_srs)
    return n_effective, sr_variance
```

**Agent Source:** Statistical Agent, Orchestrator

---

### 1.3 FWER-Adjusted P-Values

**Current:** Single-test p-value from PSR  
**Add:** Familywise Error Rate correction

**Book Citation (p. 117):**
> "After a 'family' of K independent tests, we would reject H₀ with confidence (1-α)^K, hence the 'family' false positive probability (FWER) is α_K = 1 - (1-α)^K."

**Book Citation (p. 120, Type II adjustment):**
> "Because we have conducted [K] trials, β_K ≈ β^K. The test detects more than 97.5% of the strategies with a true Sharpe ratio SR* ≥ 0.0632."

```python
# Add to afml/metrics.py
def fwer_adjusted_errors(
    observed_sr: float,
    n_trials: int,
    n_obs: int,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
) -> dict:
    """
    FWER-adjusted Type I and Type II errors (MLAM pp. 117-121).
    """
    # Mertens (2002) standard error with non-normality
    denom = np.sqrt(1 - skewness*observed_sr + (kurtosis-1)/4 * observed_sr**2)
    z = observed_sr * np.sqrt(n_obs - 1) / denom
    
    # Single-trial alpha
    alpha = 1 - norm.cdf(z)
    
    # FWER: P(at least one false positive)
    alpha_k = 1 - (1 - alpha)**n_trials
    
    # Type II (miss probability)
    z_crit = norm.ppf((1 - alpha_k)**(1/n_trials))  # Šidák correction
    theta = observed_sr * np.sqrt(n_obs - 1) / denom
    beta = norm.cdf(z_crit - theta)
    beta_k = beta**n_trials  # P(all positives missed)
    
    return {
        'alpha': alpha,           # Single-test Type I
        'alpha_k': alpha_k,       # Familywise Type I
        'beta': beta,             # Single-test Type II
        'beta_k': beta_k,         # Familywise Type II (miss rate)
        'power': 1 - beta,        # Single-test power
        'power_k': 1 - beta_k,    # Familywise power
    }
```

**Agent Source:** Statistical Agent

---

## Priority 2: Foundation Improvements (Denoising & Clustering)

### 2.1 Covariance Matrix Denoising

**Current:** Raw correlation/covariance matrices used directly  
**Replace with:** Marcenko-Pastur denoising

**Book Citation (p. 28-29):**
> "We can fit the function f[λ] to the empirical distribution of the eigenvalues to derive the implied σ². That will give us the variance explained by the random eigenvectors present in the correlation matrix, and it will determine the cutoff level λ₊."

**Book Citation (p. 35, results):**
> "Denoising reduces the RMSE by ~60% for minimum variance portfolio, compared to ~30% for Ledoit-Wolf shrinkage."

```python
# Add to afml/denoise.py
def denoise_cov(cov: pd.DataFrame, q: float, bwidth: float = 0.01) -> pd.DataFrame:
    """
    Denoise covariance matrix using Marcenko-Pastur (MLAM Ch 2).
    
    Parameters:
        cov: Covariance matrix
        q: T/N ratio (observations / assets)
        bwidth: KDE bandwidth for fitting MP distribution
    """
    corr = cov2corr(cov)
    eVal, eVec = np.linalg.eigh(corr)
    
    # Find λ+ by fitting Marcenko-Pastur
    eMax, var = find_max_eval(eVal, q, bwidth)
    
    # Count signal factors
    n_facts = len(eVal) - np.searchsorted(eVal[::-1], eMax)
    
    # Replace noise eigenvalues with average
    eVal_denoised = eVal.copy()
    eVal_denoised[n_facts:] = eVal_denoised[n_facts:].mean()
    
    # Reconstruct correlation
    corr_denoised = eVec @ np.diag(eVal_denoised) @ eVec.T
    corr_denoised = cov2corr(corr_denoised)  # Rescale diagonal to 1
    
    # Convert back to covariance
    std = np.sqrt(np.diag(cov))
    return pd.DataFrame(
        corr_denoised * np.outer(std, std),
        index=cov.index, columns=cov.columns
    )
```

**Agent Source:** Portfolio Constructor, Risk Manager

---

### 2.2 Correlation Matrix Detoning

**Current:** Market component included in all analyses  
**Add:** Detoning for clustering applications

**Book Citation (p. 30-31):**
> "Removing the market components present in the correlation matrix reinforces the more subtle signals hiding under the market 'tone.' For example, if we are trying to cluster a correlation matrix of stock returns, detoning that matrix will likely help amplify the signals associated with other exposures."

```python
# Add to afml/denoise.py
def detone_cov(cov: pd.DataFrame, n_market_factors: int = 1) -> pd.DataFrame:
    """
    Remove market component(s) for clustering applications (MLAM p. 30-31).
    WARNING: Result is singular - only use for clustering, not optimization.
    """
    corr = cov2corr(cov)
    eVal, eVec = np.linalg.eigh(corr)
    
    # Remove top n_market_factors eigenvectors
    eVal_detoned = eVal.copy()
    eVal_detoned[-n_market_factors:] = 0  # Zero out market components
    
    corr_detoned = eVec @ np.diag(eVal_detoned) @ eVec.T
    corr_detoned = cov2corr(corr_detoned)
    
    std = np.sqrt(np.diag(cov))
    return pd.DataFrame(
        corr_detoned * np.outer(std, std),
        index=cov.index, columns=cov.columns
    )
```

**Agent Source:** Feature Clustering, Portfolio Constructor

---

### 2.3 Optimal Number of Clusters (ONC)

**Current:** No formal feature clustering  
**Add:** ONC algorithm for feature grouping

**Book Citation (p. 55-56):**
> "Our measure of clustering quality q is defined as q = E[{S_i}] / √V[{S_i}], where E[{S_i}] is the mean of the silhouette coefficients and V[{S_i}] is the variance."

**Book Citation (p. 57-58, two-level approach):**
> "If the number of clusters to rerun is K₁ ≥ 2, we rerun the clustering of the items in those K₁ clusters... To check its efficacy, we compare the average cluster quality before and after reclustering."

```python
# Add to afml/clustering.py
def optimal_num_clusters(
    corr: pd.DataFrame,
    max_k: int = None,
    n_init: int = 10,
) -> dict[int, list[str]]:
    """
    ONC Algorithm (MLAM Chapter 4, pp. 56-58).
    
    Returns: {cluster_id: [feature_names]}
    """
    if max_k is None:
        max_k = corr.shape[0] // 2
    
    # Convert correlation to observation matrix
    X = np.sqrt(0.5 * (1 - corr))
    
    best_silh = None
    best_clusters = None
    
    # Base clustering: try k=2 to max_k
    for init in range(n_init):
        for k in range(2, max_k + 1):
            kmeans = KMeans(n_clusters=k, n_init=1).fit(X)
            silh = silhouette_samples(X, kmeans.labels_)
            quality = silh.mean() / silh.std()  # t-stat
            
            if best_silh is None or quality > best_silh:
                best_silh = quality
                best_clusters = {
                    i: corr.columns[kmeans.labels_ == i].tolist()
                    for i in range(k)
                }
    
    # Higher-level: re-cluster low-quality clusters
    cluster_qualities = {
        k: np.mean([silh[corr.index.get_loc(f)] for f in feats])
        for k, feats in best_clusters.items()
    }
    mean_quality = np.mean(list(cluster_qualities.values()))
    
    redo_clusters = [k for k, q in cluster_qualities.items() if q < mean_quality]
    
    if len(redo_clusters) >= 2:
        # Recursively re-cluster poor clusters
        redo_features = [f for k in redo_clusters for f in best_clusters[k]]
        sub_corr = corr.loc[redo_features, redo_features]
        sub_clusters = optimal_num_clusters(sub_corr, max_k=len(redo_features)//2)
        
        # Merge results
        # ... (combine good clusters with re-clustered ones)
    
    return best_clusters
```

**Agent Source:** Momentum Researcher, Feature Analysis

---

## Priority 3: Enhanced Analysis (Feature Importance)

### 3.1 Clustered Feature Importance (CFI)

**Current:** Standard MDI/MDA on individual features  
**Replace with:** Cluster-level importance to handle substitution effects

**Book Citation (p. 84):**
> "Substitution effects arise when two features share predictive information. In the case of MDI, the importance of two identical features will be halved. In the case of MDA, two identical features may be considered relatively unimportant, even if they are critical."

**Book Citation (p. 86, Clustered MDA):**
> "When computing clustered MDA, instead of shuffling one feature at a time, we shuffle all of the features that constitute a given cluster."

```python
# Add to afml/importance.py
def clustered_mda(
    clf,
    X: pd.DataFrame,
    y: pd.Series,
    clusters: dict[int, list[str]],
    n_splits: int = 5,
) -> pd.DataFrame:
    """
    Clustered MDA (MLAM p. 86-87).
    Shuffle entire cluster to assess combined importance.
    """
    cv = KFold(n_splits=n_splits)
    baseline_scores = []
    cluster_scores = {k: [] for k in clusters}
    
    for train_idx, test_idx in cv.split(X):
        X_train, y_train = X.iloc[train_idx], y.iloc[train_idx]
        X_test, y_test = X.iloc[test_idx], y.iloc[test_idx]
        
        clf.fit(X_train, y_train)
        baseline = -log_loss(y_test, clf.predict_proba(X_test))
        baseline_scores.append(baseline)
        
        for k, features in clusters.items():
            X_shuffled = X_test.copy()
            for f in features:
                np.random.shuffle(X_shuffled[f].values)
            
            score = -log_loss(y_test, clf.predict_proba(X_shuffled))
            cluster_scores[k].append(score)
    
    # Importance = relative decrease from baseline
    importance = pd.DataFrame({
        f'C_{k}': [(np.mean(baseline_scores) - np.mean(scores)) / 
                   (-np.mean(scores))]
        for k, scores in cluster_scores.items()
    })
    
    return importance
```

**Agent Source:** Momentum Researcher, Statistical Agent

---

## Priority 4: Portfolio Construction Enhancement

### 4.1 Nested Clustered Optimization (NCO)

**Current:** HRP only (ignores expected returns)  
**Add:** NCO when alpha estimates are reliable

**Book Citation (p. 98-100):**
> "NCO belongs to a class of algorithms known as 'wrappers': it is agnostic as to what member of the efficient frontier is computed... NCO provides a strategy for addressing the effect of Markowitz's curse on an existing mean-variance allocation method."

**Book Citation (p. 102, results):**
> "NCO computes the minimum variance portfolio with 52.98% of Markowitz's RMSE, i.e., a 47.02% reduction in the RMSE."

```python
# Add to afml/portfolio.py
@dataclass
class NCOResult:
    weights: pd.Series
    clusters: dict[int, list[str]]
    intra_weights: dict[int, pd.Series]
    inter_weights: pd.Series

def nco(
    cov: pd.DataFrame,
    mu: pd.Series = None,
    max_clusters: int = None,
    denoise: bool = True,
) -> NCOResult:
    """
    Nested Clustered Optimization (MLAM Chapter 7).
    
    Use when:
    - You have reliable expected returns (mu)
    - You want mean-variance optimization but need stability
    
    Use HRP instead when:
    - Expected returns are uncertain
    - You only want risk-based allocation
    """
    # 1. Denoise covariance
    if denoise:
        cov = denoise_cov(cov, q=1.0)
    
    # 2. Cluster
    corr = cov2corr(cov)
    clusters = optimal_num_clusters(corr, max_k=max_clusters)
    
    # 3. Intra-cluster optimization
    w_intra = {}
    for k, assets in clusters.items():
        cov_k = cov.loc[assets, assets]
        mu_k = mu.loc[assets] if mu is not None else None
        w_intra[k] = min_var_portfolio(cov_k, mu_k)
    
    # 4. Reduced covariance matrix
    cov_reduced = pd.DataFrame(index=clusters.keys(), columns=clusters.keys())
    for i in clusters:
        for j in clusters:
            w_i = w_intra[i]
            w_j = w_intra[j]
            cov_ij = cov.loc[clusters[i], clusters[j]]
            cov_reduced.loc[i, j] = float(w_i @ cov_ij @ w_j)
    
    # 5. Inter-cluster optimization
    mu_reduced = None
    if mu is not None:
        mu_reduced = pd.Series({
            k: float(w_intra[k] @ mu.loc[clusters[k]])
            for k in clusters
        })
    
    w_inter = min_var_portfolio(cov_reduced.astype(float), mu_reduced)
    
    # 6. Final weights = intra × inter
    weights = pd.Series(0.0, index=cov.index)
    for k, assets in clusters.items():
        weights[assets] = w_intra[k] * w_inter[k]
    
    return NCOResult(
        weights=weights,
        clusters=clusters,
        intra_weights=w_intra,
        inter_weights=w_inter,
    )
```

**When to use which:**
| Method | When to Use | Book Reference |
|--------|-------------|----------------|
| **HRP** | Uncertain expected returns, risk-parity | AFML Ch 16 |
| **NCO** | Reliable alpha estimates, max Sharpe | MLAM Ch 7 |

**Agent Source:** Portfolio Constructor, Risk Manager

---

## Implementation Roadmap

### Phase 1: False Discovery Prevention (Week 1)
- [ ] Add `expected_max_sharpe()` implementing False Strategy Theorem
- [ ] Add `estimate_effective_trials()` using ONC on backtest returns
- [ ] Add `fwer_adjusted_errors()` for Type I/II error correction
- [ ] Integrate with `StatisticalAgent.validate_statistics()`

### Phase 2: Denoising Infrastructure (Week 2)
- [ ] Add `denoise_cov()` using Marcenko-Pastur
- [ ] Add `detone_cov()` for clustering applications
- [ ] Apply denoising before HRP/NCO portfolio construction
- [ ] Apply denoising before feature correlation analysis

### Phase 3: Clustering & Importance (Week 3)
- [ ] Add `optimal_num_clusters()` (ONC algorithm)
- [ ] Add `clustered_mda()` and `clustered_mdi()`
- [ ] Integrate feature clustering into momentum researcher diagnostics
- [ ] Add cluster-level importance reporting

### Phase 4: Portfolio Enhancement (Week 4)
- [ ] Add `nco()` portfolio construction
- [ ] Add comparison infrastructure (HRP vs NCO)
- [ ] Add condition number monitoring
- [ ] Integrate NCO option when alpha estimates available

---

## Current vs Recommended Comparison

| Component | Current Implementation | MLAM Recommended | Status |
|-----------|----------------------|------------------|--------|
| Triple-Barrier Labels | ✅ `afml/labels.py` | ✅ Already implemented | Done |
| Purged K-Fold CV | ✅ `afml/cv.py` | ✅ Already implemented | Done |
| PSR/Deflated Sharpe | ⚠️ Basic version | Add False Strategy Theorem | Gap |
| Sample Uniqueness | ✅ `afml/weights.py` | ✅ Already implemented | Done |
| HRP Portfolio | ✅ `afml/portfolio.py` | Add NCO alternative | Enhancement |
| Covariance Denoising | ❌ Not implemented | Add Marcenko-Pastur | Gap |
| Feature Clustering | ❌ Not implemented | Add ONC | Gap |
| Clustered Importance | ❌ Not implemented | Add CFI | Gap |
| FWER Correction | ❌ Not implemented | Add Šidák correction | Gap |
| Effective Trials | ❌ Manual parameter | Auto-estimate via ONC | Gap |

---

## References

All page numbers and quotes from:
- López de Prado, M. (2020). *Machine Learning for Asset Managers*. Cambridge University Press. DOI: 10.1017/9781108883658

Key chapters:
- **Ch 2:** Denoising and Detoning (pp. 24-37)
- **Ch 3:** Distance Metrics (pp. 38-51) 
- **Ch 4:** Optimal Clustering (pp. 52-64)
- **Ch 5:** Financial Labels (pp. 65-73)
- **Ch 6:** Feature Importance Analysis (pp. 74-91)
- **Ch 7:** Portfolio Construction (pp. 92-104)
- **Ch 8:** Testing Set Overfitting (pp. 105-124)

Related work:
- López de Prado, M. (2018). *Advances in Financial Machine Learning*. Wiley. (Referenced as "AFML")
- Bailey, D. H., & López de Prado, M. (2014). The Deflated Sharpe Ratio. *Journal of Portfolio Management*.

---

*Generated: 2026-01-25 by analysis of MLAM book*
