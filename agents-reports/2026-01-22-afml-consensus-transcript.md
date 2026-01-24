# AFML Architecture Consensus Meeting

**Date:** 2026-01-22
**Participants:**
- 🏗️ Software Architect (Moderator)
- 📈 Momentum Researcher
- 📊 Statistical Agent
- 🔬 Backtest Unit
- ⚠️ Risk Manager
- 📦 Portfolio Constructor
- 🌍 Regime Agent
- 🧮 Math Professor

**Input Document:** `docs/plans/2026-01-22-AFML-improvements.md`

---

## Phase 1: Opening

### 🏗️ Software Architect

Good morning everyone. We've all analyzed López de Prado's AFML and identified 7 critical gaps in our hedge fund simulation design. Before we dive in, let me summarize what we're working with:

| Gap | Current | AFML Solution |
|-----|---------|---------------|
| Labeling | Fixed-time returns | Triple-Barrier Method |
| Cross-Validation | Standard k-fold | Purged K-Fold + Embargo |
| Sharpe Ratio | Raw calculation | Deflated SR (PSR) |
| Portfolio Construction | Score-weighted | Hierarchical Risk Parity |
| Regime Detection | Implicit | CUSUM + SADF + Entropy |
| Feature Engineering | Returns | Fractional Differentiation |
| Bet Sizing | Equal weights | Probability-based sizing |

My question to each of you: **What is your single most critical recommendation that we CANNOT ship without?**

---

### 📈 Momentum Researcher

**Triple-Barrier Labeling** is non-negotiable.

Why: Our current fixed-time returns assume trades hold for exactly N days. In reality, I'd exit early on a stop-loss or profit-target. Without triple-barrier, our backtest P&L is fiction.

Implementation complexity: Medium. It's a labeling function change, not architectural.

---

### 📊 Statistical Agent

**Purged K-Fold Cross-Validation** is foundational.

Why: Standard sklearn k-fold creates massive information leakage in time-series data. Every metric we compute (Sharpe, accuracy, etc.) will be inflated. We'll think strategies work when they don't.

Implementation complexity: Medium. Replace sklearn's KFold with custom implementation. About 100 lines of Python.

---

### 🔬 Backtest Unit

I second Statistical Agent. **Purged K-Fold** is my top priority.

If our cross-validation leaks, ALL validation is suspect. Triple-barrier is important, but with leaked CV we won't know if it actually helps.

Build order: Purged CV first, then triple-barrier labeling.

---

### ⚠️ Risk Manager

**Hierarchical Risk Parity (HRP)** for portfolio construction.

Why: Our current equal-weight approach ignores correlations. Mean-variance optimization is unstable (matrix inversion fails on correlated assets). HRP is the only numerically stable approach for real portfolios.

Implementation complexity: Medium-High. Requires hierarchical clustering + recursive bisection. About 200 lines, but well-documented in AFML.

---

### 📦 Portfolio Constructor

I'd prioritize **Feature Importance (MDA/SFI)** before HRP.

Why: We need to know which signals actually contribute returns. Without this, we might be running expensive HRP on garbage inputs.

But I acknowledge HRP is important. I'd be okay with HRP in MVP if we add feature importance in v2.

---

### 🌍 Regime Agent

**Simple regime classification** (bull/bear/sideways) is sufficient for MVP.

The advanced stuff (CUSUM, SADF, entropy) is powerful but complex. I recommend deferring to v2.

For MVP: Use a simple 200-day moving average rule. Market > 200MA = bull, else bear. It's crude but captures 80% of the benefit.

---

### 🧮 Math Professor

I want to flag something: **Most AFML techniques assume IID violations are handled.**

Before anything else, we need:
1. Stationarity tests (ADF) on features
2. Autocorrelation checks on residuals

But for MVP, I'd accept: Run ADF once during backtest setup, warn if non-stationary. Don't block, just warn.

My critical requirement: **Deflated Sharpe Ratio (PSR)**. Raw Sharpe is meaningless without correction for non-normality and multiple testing.

---

## Phase 2: Discussion - Dependencies & Build Order

### 🏗️ Software Architect

Good. I'm hearing a consensus forming around:

**Definitely MVP:**
- Purged K-Fold CV (Statistical Agent, Backtest Unit)
- Triple-Barrier Labeling (Momentum Researcher)
- Deflated Sharpe Ratio (Math Professor)

**Contested:**
- HRP (Risk Manager wants it, Portfolio Constructor says feature importance first)
- Regime Detection (Regime Agent says simple is fine)

Let me ask: **What are the dependencies?**

Backtest Unit: Can we implement triple-barrier without purged CV?

---

### 🔬 Backtest Unit

Yes, they're independent. But I'd do Purged CV first because:

1. CV is used to validate EVERYTHING else
2. If we implement triple-barrier first and validate with leaky CV, we'll get false confidence
3. Then we'll have to re-validate after fixing CV anyway

**Proposed order:** Purged CV → Triple-Barrier → PSR

---

### 🏗️ Software Architect

Statistical Agent: Does PSR depend on triple-barrier?

---

### 📊 Statistical Agent

No. PSR is a post-hoc adjustment to any Sharpe calculation. It can be added at any time.

However, PSR is MORE important when:
- We test many strategy variations (multiple testing)
- Returns are non-normal (triple-barrier creates asymmetric P&L)

So the cleaner flow is: Triple-Barrier → PSR (because triple-barrier changes the return distribution that PSR adjusts for).

---

### 🏗️ Software Architect

Risk Manager vs Portfolio Constructor: Let's resolve HRP vs Feature Importance.

Risk Manager: Can we do equal-weight for MVP and add HRP in v2?

---

### ⚠️ Risk Manager

I'm uncomfortable with that. Equal-weight is naive. It over-allocates to correlated assets and under-diversifies.

Counter-proposal: Implement **simple HRP** (just the clustering + inverse-variance part, skip the fancy refinements). It's maybe 100 lines instead of 200.

The book provides pseudocode. It's not that hard.

---

### 📦 Portfolio Constructor

I can live with simple HRP in MVP if we add feature importance in v2.

My concern: Without feature importance, we're flying blind on WHICH signals matter. But I admit that's an optimization, not a foundation.

---

### 🏗️ Software Architect

Regime Agent: Your 200MA rule - is that truly sufficient?

---

### 🌍 Regime Agent

For **learning and research** (which is our stated goal), yes.

The advanced tests (CUSUM, SADF) are for detecting subtle regime shifts before they're obvious. That matters for live trading. For backtesting historical data, simple rules work.

My recommendation:
- MVP: 200MA bull/bear classification
- V2: Add volatility regime (VIX-based)
- V3: CUSUM/SADF if we go to production

---

### 🧮 Math Professor

I want to add: The simple 200MA rule has a **known mathematical property** - it's a low-pass filter with ~10 month lookback. It's not arbitrary.

I approve the simplification for MVP.

---

## Phase 3: What to Skip/Defer

### 🏗️ Software Architect

Let me propose what we **skip entirely** for now:

| Feature | Recommendation | Reason |
|---------|----------------|--------|
| Fractional Differentiation | Defer to v3+ | Complex, marginal benefit for our timeframe |
| Microstructure signals (VPIN) | Skip | Requires tick data we don't have |
| Meta-Labeling | Defer to v2 | Good idea but adds model complexity |
| Bet Averaging/Discretization | Defer to v2 | Optimization, not foundation |
| Sample Uniqueness Weighting | Defer to v2 | Complex, marginal benefit |
| Entropy Features | Skip | Research-grade, not production-ready |

Any objections?

---

### 📈 Momentum Researcher

**I object to skipping Fractional Differentiation entirely.**

But I accept deferring it. It should be v2, not v3+. The book shows it preserves 40% more memory than standard returns. That's significant for momentum signals.

---

### 🧮 Math Professor

I second that. Fractional diff is the mathematically correct way to handle financial time series. Returns (d=1) throw away too much information.

Compromise: Defer to v2, not skip.

---

### 📊 Statistical Agent

**I object to deferring Sample Uniqueness Weighting.**

It's actually simple to implement (10-20 lines) and fixes a real problem: overlapping labels in our weekly-to-monthly timeframe.

Proposal: Add to MVP. It's cheap and important.

---

### 🏗️ Software Architect

Fair point. Sample uniqueness is simpler than I thought. Let me revise.

---

### ⚠️ Risk Manager

I'm fine with deferring bet sizing optimization. Equal sizing based on signal confidence (0-1 score → position size) is acceptable for MVP.

The full Kelly criterion / probability-based sizing can wait.

---

### 📦 Portfolio Constructor

I agree Meta-Labeling can wait. It's elegant but adds a whole second model layer. Not MVP territory.

---

### 🌍 Regime Agent

Confirmed: CUSUM, SADF, entropy all deferred. Simple 200MA for MVP.

---

## Phase 4: Consensus Proposal

### 🏗️ Software Architect

Based on our discussion, here is my proposed consensus:

---

## MVP (Tier 1) - Must Ship

| Feature | Owner | Complexity | Dependencies |
|---------|-------|------------|--------------|
| **Purged K-Fold CV** | Backtest Unit | Medium | None |
| **Triple-Barrier Labeling** | Momentum Researcher | Medium | None (but validate with Purged CV) |
| **Deflated Sharpe Ratio (PSR)** | Statistical Agent | Low | None |
| **Simple HRP** | Risk Manager + Portfolio Constructor | Medium | None |
| **Sample Uniqueness Weighting** | Statistical Agent | Low | None |
| **Simple Regime (200MA)** | Regime Agent | Low | None |
| **Stationarity Warnings** | Math Professor | Low | None |

**Build Order:**
1. Purged K-Fold CV (foundation - everything else validated against this)
2. Triple-Barrier Labeling (changes return distribution)
3. Sample Uniqueness Weighting (affects training)
4. Deflated Sharpe Ratio (validates strategies)
5. Simple HRP (portfolio construction)
6. Simple Regime Classification (context for signals)
7. Stationarity Warnings (guard rails)

---

## Version 2 (Tier 2) - Should Have

| Feature | Owner | Why Deferred |
|---------|-------|--------------|
| **Fractional Differentiation** | Momentum Researcher, Math Professor | Complex but valuable |
| **Meta-Labeling** | All Researchers | Adds model layer |
| **Feature Importance (MDA/SFI)** | Portfolio Constructor | Optimization |
| **Bet Averaging/Discretization** | Portfolio Constructor | Reduces turnover |
| **Strategy Risk Calculation** | Risk Manager | Advanced risk metric |
| **Volatility Regime** | Regime Agent | Adds VIX context |
| **Condition Number Monitoring** | Risk Manager | Matrix stability check |

---

## Defer/Skip (Tier 3)

| Feature | Reason |
|---------|--------|
| CUSUM/SADF structural breaks | Research-grade, complex |
| Entropy features | Research-grade, complex |
| Microstructure (VPIN, Kyle's lambda) | Requires tick data |
| Full Kelly bet sizing | Optimization, not foundation |

---

### 🏗️ Software Architect

**I need each agent to confirm or object to this plan.**

---

### 📈 Momentum Researcher

**CONFIRMED.** Triple-barrier in MVP, fractional diff in v2. I can work with this.

---

### 📊 Statistical Agent

**CONFIRMED.** Purged CV + PSR + Sample Uniqueness in MVP. Core statistical rigor preserved.

---

### 🔬 Backtest Unit

**CONFIRMED.** Build order makes sense. Purged CV first, then everything else.

---

### ⚠️ Risk Manager

**CONFIRMED.** Simple HRP in MVP, advanced risk metrics in v2.

---

### 📦 Portfolio Constructor

**CONFIRMED.** HRP now, feature importance later. Acceptable.

---

### 🌍 Regime Agent

**CONFIRMED.** Simple regime for MVP, advanced detection deferred.

---

### 🧮 Math Professor

**CONFIRMED.** Mathematical foundations (PSR, stationarity) preserved. Fractional diff appropriately deferred to v2, not skipped.

---

## Final Consensus: REACHED

**Date:** 2026-01-22
**Status:** APPROVED by all agents

### Summary

**MVP Scope (7 features):**
1. Purged K-Fold CV
2. Triple-Barrier Labeling
3. Deflated Sharpe Ratio
4. Simple HRP
5. Sample Uniqueness Weighting
6. Simple Regime (200MA)
7. Stationarity Warnings

**Estimated Implementation:** 500-700 lines of Python across modules

**Key Principle:** Get the validation infrastructure right (Purged CV, PSR) before adding features. A solid foundation catches bugs in everything built on top.

---

*Meeting concluded: 2026-01-22*
*Transcript recorded by: Scribe Agent*
