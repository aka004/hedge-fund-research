# Unified Backtest & AFML Roadmap

**Created:** 2026-02-18
**Supersedes:** `docs/plans/2026-01-26-AFML-implementation-roadmap.md`, Obsidian `afml_implementation_roadmap.md`
**Status:** ACTIVE

---

## Guiding Principle

Organized by **what the engine needs**, not by book chapter. AFML techniques are tools that plug into engine capabilities — not standalone stages.

---

## Code Inventory (What Actually Exists)

Before planning what to build, here's what's already implemented and working:

### Backtest Engine (`strategy/backtest/`)
| Component | File | Status |
|-----------|------|--------|
| BacktestEngine (rebalance loop) | `engine.py` | Working |
| WalkForwardValidator | `engine.py` | Working |
| Portfolio / Position / Trade | `portfolio.py` | Working |
| TransactionCosts (slippage + commission) | `portfolio.py` | Working |
| PortfolioManager (buy/sell/rebalance) | `portfolio.py` | Working |

### AFML Module (`afml/`)
| Component | File | AFML Chapter | Status |
|-----------|------|-------------|--------|
| Triple-barrier labeling | `labels.py` | Ch 3 | Working |
| CUSUM filter | `cusum.py` | Ch 17 | Working |
| Purged K-Fold CV | `cv.py` | Ch 7 | Working (unidirectional purge only) |
| Combinatorial Purged CV | `cpcv.py` | Ch 12 | Working |
| Sample uniqueness weights | `weights.py` | Ch 4 | Working |
| Sequential bootstrap | `bootstrap.py` | Ch 4 | Working |
| Deflated Sharpe / PSR | `metrics.py` | Ch 14 | Working (has B1 benchmark bug) |
| Kelly criterion | `bet_sizing.py` | Ch 10 | Working |
| HRP portfolio | `portfolio.py` | Ch 16 | Working |
| Meta-labeling (RF) | `meta_labeling.py` | Ch 3/8 | Working |
| Regime detection (200MA) | `regime.py` | Ch 17 | Working (MVP) |
| ADF stationarity | `checks.py` | Ch 5 | Working |

### Signals (`strategy/signals/`)
| Signal | File | Status |
|--------|------|--------|
| Momentum (12-1) | `momentum.py` | Working |
| Value (P/E filter) | `value.py` | Working |
| Social (StockTwits) | `social.py` | Working |
| Politician (STOCK Act) | `politician.py` | Working |
| Signal combiner | `combiner.py` | Working |

### Analysis & Backend
| Component | File | Status |
|-----------|------|--------|
| PerformanceMetrics | `analysis/metrics.py` | Working |
| DashboardBacktestRunner | `backend/app/services/backtest_runner.py` | Working |
| Multi-agent orchestrator | `agents/orchestrator.py` | Working |

---

## What's Missing (Gaps Between Code and Goals)

### Category A: Engine Mechanics (No AFML code exists for these)
| Gap | Impact | Exists Anywhere? |
|-----|--------|-----------------|
| Trade lifecycle tracking (entry/exit reason, holding period) | Can't analyze why trades won/lost | No |
| Event-driven exits (barriers as live exit logic) | Engine can only exit at rebalance | No |
| Daily mark-to-market equity curve | Equity only recorded on rebalance dates | No |
| Cash tracking with mid-period exits | Cash doesn't update between rebalances | No |
| `get_returns_series()` is a dead stub | PortfolioManager can't report returns | No |

### Category B: Known Bugs & Improvements
| Bug | File | Ref |
|-----|------|-----|
| PSR benchmark formula (remove `/sqrt(annualization)`) | `afml/metrics.py` | TODO B1 |
| Bidirectional purging in CV | `afml/cv.py` | TODO B2 |
| Walk-Forward Efficiency metric | `strategy/backtest/engine.py` | TODO B3 |
| Marcenko-Pastur covariance denoising | `afml/portfolio.py` | TODO B4 |
| `expected_max_sharpe()` for multiple testing | `afml/metrics.py` | TODO B6 |

### Category C: AFML Techniques Not Yet Implemented
| Technique | AFML Chapter | Priority |
|-----------|-------------|----------|
| Fractional differentiation (FFD) | Ch 5 | Medium |
| Time decay weights | Ch 4 | Low |
| Runs statistics | Ch 14 | Medium |
| Strategy risk metrics (required precision, failure prob) | Ch 15 | Medium |
| Entropy features (Shannon, Lempel-Ziv) | Ch 18 | Low |
| Microstructure features (Parkinson, Garman-Klass, Corwin-Schultz, Amihud) | Ch 19 | Low |
| Alternative bars (dollar, volume, tick/volume imbalance) | Ch 2 | Low |
| Chow test | Ch 17 | Low |
| SADF / GSADF (bubble detection) | Ch 17 | Low |
| Synthetic price generator + strategy verification | Ch 13 | Low |
| Feature importance (MDA, SFI, Clustered MDA) | Ch 8 | Low |
| Nested Clustered Optimization | Ch 16 | Low |

---

## Implementation Phases

### Phase 1: Proper Backtest Engine

**Goal:** The engine can track individual trades from entry to exit with reasons, run daily mark-to-market, handle mid-period exits, and produce a complete trade log for downstream analysis.

**Prerequisite configs to decide (brainstorm output):** See "Arbitrary Configurations" section below.

| # | Task | Depends On | Touches |
|---|------|-----------|---------|
| 1.1 | Extend `Trade` with lifecycle fields (entry/exit reason, exit_price, exit_date, holding_period, pnl) | — | `portfolio.py` |
| 1.2 | Create `ExitManager` with barrier-based exit logic (profit target, stop loss, timeout) | 1.1 | New: `exit_manager.py` |
| 1.3 | Add daily-step loop to engine (iterate every trading day, not just rebalance dates) | 1.2 | `engine.py` |
| 1.4 | Daily mark-to-market equity tracking (record equity every day, not just rebalance) | 1.3 | `engine.py` |
| 1.5 | Cash tracking with mid-period exits (sell proceeds available immediately) | 1.3 | `portfolio.py` |
| 1.6 | Fix `get_returns_series()` stub | 1.4 | `portfolio.py` |
| 1.7 | Structured trade log output (DataFrame with full lifecycle per trade) | 1.1 | `engine.py` |
| 1.8 | Update `PerformanceMetrics` to use trade log (proper win rate, profit factor from round-trip trades) | 1.7 | `analysis/metrics.py` |

**Deliverable:** Can run `engine.run()` and get daily equity curve + complete trade log with entry/exit reasons.

---

### Phase 2: AFML Integration Into Engine

**Goal:** AFML techniques drive engine decisions — CUSUM generates entry events, triple-barrier defines exit conditions, meta-labeling sizes positions, HRP+Kelly allocate capital.

| # | Task | Depends On | Touches |
|---|------|-----------|---------|
| 2.1 | CUSUM → event generation (CUSUM filter produces entry timestamps for the engine) | Phase 1 | `engine.py`, `afml/cusum.py` |
| 2.2 | Triple-barrier → exit conditions (barrier params feed into `ExitManager`) | 1.2 | `exit_manager.py`, `afml/labels.py` |
| 2.3 | Meta-labeling → position sizing (RF P(win) scales position size) | 2.1 | `engine.py`, `afml/meta_labeling.py` |
| 2.4 | Kelly + HRP → capital allocation (Kelly fraction × HRP weight = final position size) | 2.3 | `engine.py`, `afml/bet_sizing.py`, `afml/portfolio.py` |
| 2.5 | PSR + CPCV → post-hoc validation (run after backtest, gate strategy approval) | 2.4 | `analysis/`, `afml/metrics.py`, `afml/cpcv.py` |
| 2.6 | Fix PSR benchmark formula (B1) | — | `afml/metrics.py` |
| 2.7 | Add bidirectional purging (B2) | — | `afml/cv.py` |
| 2.8 | Wire regime detection into entry filter (only enter in bull regime) | 2.1 | `engine.py`, `afml/regime.py` |

**Deliverable:** Full pipeline: CUSUM events → signal check → meta-label sizing → barrier exits → PSR validation.

---

### Phase 3: Bug Fixes & Metric Hardening

**Goal:** All known bugs fixed, metrics match AFML book formulas exactly.

| # | Task | Ref |
|---|------|-----|
| 3.1 | Walk-Forward Efficiency (WFE) metric | TODO B3 |
| 3.2 | Marcenko-Pastur covariance denoising for HRP | TODO B4 |
| 3.3 | `expected_max_sharpe()` for multiple testing correction | TODO B6 |
| 3.4 | Runs statistics (win/loss streaks) | Ch 14 |
| 3.5 | Strategy risk metrics (required precision, failure probability) | Ch 15 |
| 3.6 | Fractional differentiation (FFD) | Ch 5 |

**Deliverable:** Metrics are publication-quality, not MVP approximations.

---

### Phase 4: Advanced Features (Lower Priority)

**Goal:** Deeper AFML coverage for research exploration. Build as needed.

| # | Task | AFML Chapter |
|---|------|-------------|
| 4.1 | Entropy features (Shannon, Lempel-Ziv, rolling) | Ch 18 |
| 4.2 | Microstructure features (Parkinson, Garman-Klass, Corwin-Schultz, Amihud) | Ch 19 |
| 4.3 | Alternative bars (dollar, volume, tick/volume imbalance) | Ch 2 |
| 4.4 | SADF / GSADF bubble detection | Ch 17 |
| 4.5 | Synthetic price generator + strategy verification framework | Ch 13 |
| 4.6 | Feature importance (MDA, SFI, Clustered MDA) beyond current RF | Ch 8 |
| 4.7 | Nested Clustered Optimization | Ch 16 |
| 4.8 | Full tearsheet generator | — |
| 4.9 | Experiment tracker | — |

---

## Arbitrary Configurations (Must Decide Before Phase 1)

These are the parameters that need explicit values before implementation can begin. Each one is currently either hardcoded, missing, or inconsistent.

### A. Exit Manager / Barrier Parameters
| Parameter | Current Value | Where Used | Decision Needed |
|-----------|--------------|-----------|-----------------|
| `profit_take` multiplier | 2.0× daily vol | `afml/labels.py` (labeling only) | Same for live exits, or different? |
| `stop_loss` multiplier | 2.0× daily vol | `afml/labels.py` (labeling only) | Same for live exits, or different? |
| `max_holding_days` | 10 | `afml/labels.py` (labeling only) | Same for live exits? Too short for monthly rebalance? |
| Volatility estimator window | 100-day EWMA | `afml/labels.py` | Match between labeling and live exits? |
| Exit price assumption | Close of barrier-touch day | Not implemented | Next-day open (more realistic)? |

### B. Engine Loop Parameters
| Parameter | Current Value | Decision Needed |
|-----------|--------------|-----------------|
| `rebalance_frequency` | "monthly" | Keep monthly entry cadence alongside daily exit checks? |
| Daily step mode | Not implemented | Step every calendar day or every trading day? |
| Execution price | Same-day close | Switch to next-day open to avoid look-ahead? |
| Position re-entry cooldown | None | Allow re-entry to same symbol immediately after exit? |

### C. CUSUM Event Generation
| Parameter | Current Value | Decision Needed |
|-----------|--------------|-----------------|
| CUSUM `threshold` | Auto (daily vol × multiplier) | What multiplier? (affects event frequency) |
| CUSUM input | Log prices | Use returns instead? Standardized? |
| Min events per year | No constraint | Set a floor to avoid too few signals? |
| Max events per day | No constraint | Cap to avoid overtrading? |

### D. Position Sizing & Allocation
| Parameter | Current Value | Decision Needed |
|-----------|--------------|-----------------|
| Kelly fraction cap | `half_kelly` in `bet_sizing.py` | Half-Kelly, quarter-Kelly, or configurable? |
| Max single position weight | No limit (equal weight = 1/max_positions) | Hard cap (e.g., 10% of equity)? |
| Max gross exposure | 1.0 (fully invested) | Allow leverage? Cash reserve? |
| Min position size | No minimum | Minimum $value or share count? |
| HRP rebalance frequency | Not wired to engine | How often recalculate HRP weights? |
| Sizing blend | Not implemented | How to combine Kelly × HRP × meta-label? |

### E. Regime & Filtering
| Parameter | Current Value | Decision Needed |
|-----------|--------------|-----------------|
| Regime MA window | 200 days | Configurable or fixed? |
| Regime action | Not wired | Reduce size? Skip entries? Exit positions? |
| Bear market behavior | Not implemented | Go to cash? Reduce to half-Kelly? Short? |

### F. Validation Gates
| Parameter | Current Value | Decision Needed |
|-----------|--------------|-----------------|
| PSR threshold | 0.95 | Keep 95% or relax for exploration? |
| Min backtest length | No minimum | How many years minimum for valid results? |
| CPCV n_splits / n_test_groups | 6 / 2 | Keep or adjust for sample size? |
| Number of strategies tested | 1 (undercount) | Track honestly across all runs? |

---

## Decision Log

Record parameter decisions here as they're made during brainstorming.

| Date | Parameter | Decision | Rationale |
|------|-----------|----------|-----------|
| | | | |

---

## References

- López de Prado, *Advances in Financial Machine Learning* (AFML)
- Pardo, *Design, Testing, and Optimization of Trading Systems*
- Chan, *Algorithmic Trading*
- Project TODO.md for bug references (B1-B7)
