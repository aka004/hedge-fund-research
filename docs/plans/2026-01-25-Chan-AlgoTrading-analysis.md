# Hedge Fund Simulation Improvements from Chan's Algorithmic Trading

**Date:** 2026-01-25  
**Source:** Chan, Ernest P. *Algorithmic Trading: Winning Strategies and Their Rationale*. Wiley, 2013.  
**Status:** Proposed Improvements

---

## Executive Summary

Analysis of the hedge-fund-research project against Ernest Chan's algorithmic trading framework reveals significant opportunities to improve momentum factor testing, backtesting rigor, and risk management. The project's 12-1 momentum implementation aligns with Chan's recommendations but lacks critical validation infrastructure.

### Critical Gaps Identified

| Gap | Current State | Chan Recommendation | Impact |
|-----|---------------|---------------------|--------|
| **Statistical Significance** | No p-values | t-test with √n × SR threshold | Selection bias detection |
| **Lookback Optimization** | Fixed 12-1 only | Grid search multiple periods | Better parameter selection |
| **Position Sizing** | Fixed weights | Kelly/Half-Kelly formula | Optimal leverage |
| **Regime Awareness** | None | VIX > 35 threshold | Crisis protection |
| **Drawdown Protection** | None | CPPI insurance | Max drawdown limits |
| **Correlation Testing** | Overlapping data | Non-overlapping periods | Valid significance |
| **Monte Carlo Testing** | None | Pearson system simulation | Robust validation |

---

## Priority 1: Immediate Implementation (High Impact, Foundational)

### 1.1 Statistical Significance Testing (Ch.1 p.16-21)

**Current:** Raw Sharpe ratio only  
**Replace with:** Hypothesis testing with p-values

```python
# Chan Table 1.1: Critical Values for √n × Daily Sharpe Ratio
CRITICAL_VALUES = {
    0.10: 1.282,  # 90% confidence
    0.05: 1.645,  # 95% confidence  
    0.01: 2.326,  # 99% confidence
    0.001: 3.091  # 99.9% confidence
}

def test_statistical_significance(returns: pd.Series) -> dict:
    """Per Chan Ch.1 p.17: Test if strategy returns are significant."""
    n = len(returns)
    daily_sharpe = returns.mean() / returns.std()
    test_stat = daily_sharpe * np.sqrt(n)
    
    from scipy.stats import norm
    p_value = 1 - norm.cdf(test_stat)
    
    return {
        "test_statistic": test_stat,
        "p_value": p_value,
        "significant_at_0.05": test_stat >= 1.645,
        "significant_at_0.01": test_stat >= 2.326
    }
```

**Why:** Chan emphasizes (p.17): *"If the daily Sharpe ratio multiplied by the square root of the number of days (n) is greater than or equal to the critical value 2.326, then the p-value is smaller than or equal to 0.01."*

**Citation:** Chapter 1, Table 1.1 (p.17)

---

### 1.2 Non-Overlapping Correlation Tests (Ch.6 Box 6.1)

**Current:** Standard correlation on all data points  
**Replace with:** Non-overlapping period sampling

```python
def test_momentum_correlation(
    prices: pd.Series,
    lookback: int,
    holddays: int
) -> tuple[float, float]:
    """
    Per Chan Box 6.1 (p.135-136): Use non-overlapping data
    to avoid spurious correlations.
    """
    ret_lag = (prices - prices.shift(lookback)) / prices.shift(lookback)
    ret_fut = (prices.shift(-holddays) - prices) / prices
    
    # CRITICAL: Non-overlapping sampling
    # "If look-back is greater than the holding period, we have to
    # shift forward by the holding period to generate a new returns pair"
    step = max(lookback, holddays)
    
    # Sample every 'step' periods
    indices = list(range(0, len(ret_lag), step))
    ret_lag_sample = ret_lag.iloc[indices].dropna()
    ret_fut_sample = ret_fut.iloc[indices].dropna()
    
    from scipy.stats import pearsonr
    corr, pval = pearsonr(ret_lag_sample, ret_fut_sample)
    return corr, pval
```

**Why:** Chan Box 6.1 (p.135): *"In computing the correlations of pairs of returns resulting from different look-back and holding periods, we must take care not to use overlapping data."*

**Citation:** Chapter 6, Box 6.1 (p.135-136)

---

### 1.3 Lookback/Holding Period Optimization (Ch.6 p.134-137)

**Current:** Fixed 12-month lookback, 1-month skip  
**Add:** Parameter grid search with validation

```python
class MomentumValidator:
    """
    Per Chan Ch.6 p.135: 'We should find the optimal pair of past
    and future periods that gives the highest positive correlation.'
    """
    
    def optimize_parameters(
        self,
        prices: pd.DataFrame,
        lookbacks: list[int] = [21, 63, 126, 189, 252],  # 1, 3, 6, 9, 12 months
        holddays: list[int] = [5, 10, 21, 42, 63]        # 1wk to 3mo
    ) -> pd.DataFrame:
        """Test all lookback/holddays combinations."""
        results = []
        
        for lb in lookbacks:
            for hd in holddays:
                corr, pval = self.test_momentum_correlation(prices, lb, hd)
                results.append({
                    'lookback': lb,
                    'holddays': hd,
                    'correlation': corr,
                    'p_value': pval,
                    'significant': pval < 0.05
                })
        
        return pd.DataFrame(results).sort_values('correlation', ascending=False)
```

**Chan's Results (Table 6.1, p.137):** For TU futures, best pairs were:
- (60, 10): corr=0.17, p=0.017
- (60, 25): corr=0.26, p=0.023  
- (250, 25): corr=0.27, p=0.024

**Citation:** Chapter 6, Table 6.1 (p.137)

---

### 1.4 VIX Regime Overlay (Ch.8 p.184)

**Current:** No regime awareness  
**Add:** VIX-based risk overlay

```python
class RiskOverlay:
    """
    Per Chan Ch.8 p.184: 'If the preceding day's VIX is over 35,
    a common threshold for highly risky periods...'
    """
    
    VIX_THRESHOLD = 35.0
    
    def adjust_momentum_position(
        self,
        base_position: float,
        current_vix: float
    ) -> float:
        """
        Chan: 'For the FSTX opening gap strategy... If the preceding 
        day's VIX is over 35, then the day's annualized average return 
        drops to 2.6 percent and the Sharpe ratio to 0.16.'
        """
        if current_vix > self.VIX_THRESHOLD:
            # Momentum strategies suffer in high-VIX regimes
            return base_position * 0.5  # Reduce by half
        return base_position
```

**Why:** Chan documents momentum crash during 2008 crisis (p.145, 147): *"This model performed very negatively from January 2, 2008, to December 31, 2009, with an APR of –33 percent."*

**Citation:** Chapter 8, p.184; Chapter 6, p.145

---

## Priority 2: Position Sizing & Risk (Medium-Term)

### 2.1 Kelly Formula Position Sizing (Ch.8 p.172)

**Current:** Equal or score-weighted positions  
**Replace with:** Kelly/Half-Kelly optimal leverage

```python
def calculate_kelly_leverage(
    returns: pd.Series,
    risk_free_rate: float = 0.02,
    periods_per_year: int = 252
) -> dict:
    """
    Chan Ch.8 p.172: 'The Kelly formula gives us a very simple
    answer for optimal leverage f: f = m / σ²'
    """
    rf_per_period = risk_free_rate / periods_per_year
    excess_returns = returns - rf_per_period
    
    m = excess_returns.mean()  # Mean excess return
    sigma_sq = excess_returns.var()  # Variance
    
    kelly_f = m / sigma_sq if sigma_sq > 0 else 0
    
    return {
        "kelly_leverage": kelly_f,
        "half_kelly": kelly_f / 2,  # Chan p.172: "so-called half-Kelly leverage"
        "recommended": min(kelly_f / 2, 2.0)  # Conservative cap
    }
```

**Why:** Chan (p.172): *"Many traders justifiably prefer [a conservative] scenario, and they routinely deploy a leverage equal to half of what the Kelly formula recommends."*

**Citation:** Chapter 8, Equation 8.1 (p.172)

---

### 2.2 CPPI Drawdown Protection (Ch.8 p.180-181)

**Current:** No drawdown protection  
**Add:** Constant Proportion Portfolio Insurance

```python
def cppi_position_size(
    current_equity: float,
    high_water_mark: float,
    max_drawdown_allowed: float,  # e.g., 0.20 for 20%
    kelly_leverage: float
) -> float:
    """
    Chan Ch.8 p.180: 'Set aside D of our initial total account
    equity for trading, and apply a leverage of f to this subaccount.'
    
    Benefits:
    - Guarantees max drawdown won't exceed D
    - Automatically winds down losing strategy
    - Preserves upside when winning
    """
    # Trading capital = max_drawdown * total equity
    trading_capital = max_drawdown_allowed * current_equity
    
    # Current drawdown from HWM
    current_dd = (current_equity / high_water_mark) - 1
    
    # Remaining drawdown budget
    remaining_dd_budget = max_drawdown_allowed + current_dd
    
    if remaining_dd_budget <= 0:
        return 0.0  # Stop trading - max DD reached
    
    # Adjust trading capital based on remaining budget
    adjusted_capital = remaining_dd_budget * high_water_mark
    
    # Apply Kelly to adjusted trading capital
    return adjusted_capital * kelly_leverage
```

**Why:** Chan (p.181): *"CPPI will decrease order size much faster than the alternative, thus making it almost impossible... that the account would approach the maximum drawdown –D."*

**Citation:** Chapter 8, p.180-181, Box 8.6

---

### 2.3 Stop-Loss for Momentum (Ch.8 p.182-184)

**Current:** No stop-loss logic  
**Add:** Strategy-appropriate stop-loss

```python
class StopLossManager:
    """
    Per Chan Ch.8 p.184: Stop-loss behavior differs by strategy type.
    
    For momentum: 'Momentum strategies benefit from stop loss in a
    very logical and straightforward way. If a momentum strategy is
    losing, it means that momentum has reversed.'
    
    For mean-reversion: 'Stop loss for mean-reverting strategies
    should be set so that they are never triggered in backtests.'
    """
    
    def should_exit(
        self,
        strategy_type: str,
        position_pnl_pct: float,
        signal_reversed: bool,
        stop_loss_threshold: float = -0.10
    ) -> bool:
        if strategy_type == "momentum":
            # Exit if momentum reverses OR hits stop
            if signal_reversed:
                return True
            if position_pnl_pct < stop_loss_threshold:
                return True
                
        elif strategy_type == "mean_reversion":
            # Only exit on catastrophic loss (regime change protection)
            # Chan: "set so that they are never triggered in backtests"
            catastrophic_threshold = stop_loss_threshold * 3  # e.g., -30%
            if position_pnl_pct < catastrophic_threshold:
                return True
        
        return False
```

**Citation:** Chapter 8, p.182-184

---

## Priority 3: Advanced Validation (Long-Term)

### 3.1 Monte Carlo Hypothesis Testing (Ch.1 Example 1.1)

**Current:** No Monte Carlo validation  
**Add:** Simulated returns testing

```python
def monte_carlo_significance(
    strategy_returns: pd.Series,
    market_returns: pd.Series,
    n_simulations: int = 10000
) -> dict:
    """
    Per Chan Ch.1 Example 1.1 (p.18-21): Generate simulated returns
    with same statistical moments, test if strategy beats random.
    
    'We can use the Pearson system to model the distribution...
    taking as input the mean, standard deviation, skewness, 
    and kurtosis of the empirical distribution.'
    """
    from scipy.stats import pearsonr
    
    observed_mean = strategy_returns.mean()
    
    # Pearson system moments
    moments = {
        'mean': market_returns.mean(),
        'std': market_returns.std(),
        'skew': market_returns.skew(),
        'kurtosis': market_returns.kurtosis()
    }
    
    # Count simulations that beat observed
    n_better = 0
    for _ in range(n_simulations):
        # Generate returns with same moments (simplified)
        sim_returns = np.random.normal(
            moments['mean'], 
            moments['std'], 
            len(market_returns)
        )
        
        if sim_returns.mean() >= observed_mean:
            n_better += 1
    
    p_value = n_better / n_simulations
    
    return {
        "p_value": p_value,
        "reject_null": p_value < 0.05,
        "n_simulations": n_simulations,
        "interpretation": (
            "Strategy captures real patterns" if p_value < 0.05 
            else "Strategy may be due to distribution shape, not skill"
        )
    }
```

**Why:** Chan (p.20): *"Out of 10,000 random returns sets, 1,166 have average strategy return greater than or equal to the observed average return. So the null hypothesis can be rejected with only 88 percent probability."*

**Citation:** Chapter 1, Example 1.1 (p.18-21), Box 8.1-8.2 (p.176)

---

### 3.2 Cross-Sectional Momentum Framework (Ch.6 p.145-147)

**Current:** Single-stock momentum signals  
**Add:** Proper cross-sectional ranking

```python
class CrossSectionalMomentum:
    """
    Per Chan Example 6.2 (p.146): Rank stocks by 12-month
    returns, long top decile, short bottom decile.
    """
    
    def rank_and_select(
        self,
        returns_12m: pd.DataFrame,  # Stocks as columns
        top_n: int = 50,
        holddays: int = 25
    ) -> dict:
        """
        Chan p.146: 'buy and hold stocks within the top decile
        of 12-month lagged returns for a month, and vice versa
        for the bottom decile.'
        """
        longs = {}
        shorts = {}
        
        for date in returns_12m.index:
            daily_returns = returns_12m.loc[date].dropna()
            sorted_idx = daily_returns.sort_values(ascending=False).index
            
            # Top N = longs, Bottom N = shorts
            longs[date] = sorted_idx[:top_n].tolist()
            shorts[date] = sorted_idx[-top_n:].tolist()
        
        return {"longs": longs, "shorts": shorts}
    
    def calculate_ls_returns(
        self,
        longs: dict,
        shorts: dict,
        forward_returns: pd.DataFrame,
        holddays: int = 25
    ) -> pd.Series:
        """
        Chan's approach: Daily position updates with 1/holddays
        of capital allocated each day (p.138).
        """
        daily_returns = []
        
        for date in longs.keys():
            long_ret = forward_returns.loc[date, longs[date]].mean()
            short_ret = forward_returns.loc[date, shorts[date]].mean()
            ls_ret = (long_ret - short_ret) / 2 / holddays
            daily_returns.append(ls_ret)
        
        return pd.Series(daily_returns)
```

**Chan's Results:** Pre-crisis (May-Dec 2007): APR=37%, Sharpe=4.1  
Post-crisis (2008-2009): APR=-30%

**Citation:** Chapter 6, Example 6.2 (p.146-147), Figure 6.6

---

### 3.3 Combined Momentum + Mean Reversion (Ch.6 p.140)

**Current:** Momentum only  
**Add:** Combined strategy filter

```python
def combined_momentum_mean_reversion_signal(
    price: float,
    price_30d_ago: float,
    price_40d_ago: float
) -> int:
    """
    Per Chan Ch.6 p.140: 'Sometimes, the combination of mean-reverting
    and momentum rules may work better than each strategy by itself.
    
    One example strategy on CL is this: buy at the market close if
    the price is lower than that of 30 days ago and is higher than
    that of 40 days ago; vice versa for shorts.'
    
    Returns: 1 (long), -1 (short), 0 (no trade)
    """
    # Mean reversion: price < 30d ago (oversold)
    # Momentum: price > 40d ago (uptrend intact)
    
    if price < price_30d_ago and price > price_40d_ago:
        return 1  # Buy: mean reversion with momentum support
    elif price > price_30d_ago and price < price_40d_ago:
        return -1  # Sell: mean reversion with momentum support
    else:
        return 0  # No clear signal
```

**Results:** Chan reports APR=12%, Sharpe=1.1 for this combined approach on CL futures.

**Citation:** Chapter 6, p.140

---

## Implementation Roadmap

### Phase 1: Statistical Foundation (Week 1)
- [ ] Add `test_statistical_significance()` to `analysis/metrics.py`
- [ ] Implement non-overlapping correlation tests
- [ ] Add VIX regime detection and overlay
- [ ] Create parameter optimization grid for lookback/holddays

### Phase 2: Position Sizing (Week 2)
- [ ] Implement Kelly formula leverage calculation
- [ ] Add Half-Kelly recommendation to risk metrics
- [ ] Build CPPI position sizing module
- [ ] Add strategy-specific stop-loss logic

### Phase 3: Validation Framework (Week 3-4)
- [ ] Implement Monte Carlo hypothesis testing
- [ ] Add Pearson system distribution matching
- [ ] Build cross-sectional momentum framework
- [ ] Create combined momentum + mean-reversion signals

### Phase 4: Integration (Week 5-6)
- [ ] Integrate VIX overlay into signal generation
- [ ] Connect Kelly sizing to portfolio construction
- [ ] Add walk-forward validation for parameters
- [ ] Document all Chan-based improvements

---

## Comparison: Current vs Recommended

| Component | Current Implementation | Chan-Based Improvement |
|-----------|----------------------|------------------------|
| **Momentum Signal** | 12-1 return + MA200 | + Grid search + p-values |
| **Significance** | Sharpe ratio only | + t-test + Monte Carlo |
| **Position Sizing** | Equal weights | Kelly/Half-Kelly formula |
| **Risk Management** | Max position limits | + CPPI + VIX overlay |
| **Correlation Tests** | Overlapping data | Non-overlapping samples |
| **Regime Handling** | None | VIX > 35 reduces exposure |
| **Stop-Loss** | None | Strategy-specific logic |
| **Validation** | In-sample metrics | + Out-of-sample + Monte Carlo |

---

## Key Book References

| Topic | Chapter | Page(s) | Key Quote |
|-------|---------|---------|-----------|
| Statistical Significance | 1 | 16-21 | "√n × Daily Sharpe must exceed 1.645 for p<0.05" |
| Data Snooping | 1 | 4-7 | "Make the model as simple as possible" |
| Survivorship Bias | 1 | 8-9 | "More dangerous to mean-reverting long-only strategies" |
| Momentum Causes | 6 | 133 | "Four main causes of momentum" |
| Correlation Testing | 6 | 135-136 | "Must take care not to use overlapping data" |
| Cross-Sectional | 6 | 145-147 | "Rank the 12-month return... buy top decile" |
| Momentum Crash | 6 | 145, 147 | "APR of –33 percent" during 2008-2009 |
| Combined Strategies | 6 | 140 | "Combination of mean-reverting and momentum" |
| Kelly Formula | 8 | 172 | "f = m / σ²" |
| Half-Kelly | 8 | 172 | "Half of what the Kelly formula recommends" |
| CPPI | 8 | 180-181 | "Set aside D of equity for trading" |
| Stop-Loss | 8 | 182-184 | "Momentum strategies benefit from stop loss" |
| VIX Threshold | 8 | 184 | "VIX is over 35, a common threshold" |

---

## Risk Warnings from Chan

1. **Momentum Crash Risk (p.145, 147):**  
   *"The financial crisis of 2008–2009 ruined this momentum strategy."*

2. **Regime Shifts (p.24-25):**  
   *"Strategies that performed superbly prior to each of these 'regime shifts' may stop performing and vice versa."*

3. **Overconfidence (Preface p.xiii):**  
   *"Overconfidence in a strategy is the greatest danger to us all."*

4. **Leverage Risk (p.172):**  
   *"The consequence of using an overestimated mean or an underestimated variance is dire: Either case will lead to an overestimated optimal leverage, and if this overestimated leverage is high enough, it will eventually lead to ruin."*

---

*Generated: 2026-01-25 by analysis of Chan's "Algorithmic Trading" (2013)*
