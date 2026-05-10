# Hedge Fund Research System - Progress Tracker

**Started:** 2026-01-18
**Target Completion:** 2026-01-18
**Status:** COMPLETE

> Re-prioritized 2026-04-16 based on stuck-search diagnosis (stop-loss exits 45–58%, Sharpe negative, operator combos recycling).

---

## Setup Phase

| # | Task | Status | Completed At |
|---|------|--------|--------------|
| 1 | Create Python virtual environment | [x] | 2026-01-18 |
| 2 | Install dependencies | [x] | 2026-01-18 |
| 3 | Verify project structure | [x] | 2026-01-18 |
| 4 | Run initial tests | [x] | 2026-01-18 |

**Setup Phase Completed:** 2026-01-18

---

## Implementation Phase

### 1. Data Providers

| # | Task | Status | Completed At |
|---|------|--------|--------------|
| 1.1 | Create base provider interface | [x] | 2026-01-18 |
| 1.2 | Implement Yahoo Finance provider | [x] | 2026-01-18 |
| 1.3 | Implement StockTwits provider | [x] | 2026-01-18 |
| 1.4 | Add rate limiting | [x] | 2026-01-18 |
| 1.5 | Add error handling & retries | [x] | 2026-01-18 |

**Data Providers Completed:** 2026-01-18

### 2. Data Storage

| # | Task | Status | Completed At |
|---|------|--------|--------------|
| 2.1 | Set up Parquet storage | [x] | 2026-01-18 |
| 2.2 | Implement DuckDB queries | [x] | 2026-01-18 |
| 2.3 | Create data caching layer | [x] | 2026-01-18 |
| 2.4 | S&P 500 universe management | [x] | 2026-01-18 |

**Data Storage Completed:** 2026-01-18

### 3. Signal Generators

| # | Task | Status | Completed At |
|---|------|--------|--------------|
| 3.1 | Implement momentum signal | [x] | 2026-01-18 |
| 3.2 | Implement value filter | [x] | 2026-01-18 |
| 3.3 | Implement social signal | [x] | 2026-01-18 |
| 3.4 | Create signal combiner | [x] | 2026-01-18 |

**Signal Generators Completed:** 2026-01-18

### 4. Backtesting Engine

| # | Task | Status | Completed At |
|---|------|--------|--------------|
| 4.1 | Portfolio management | [x] | 2026-01-18 |
| 4.2 | Transaction cost modeling | [x] | 2026-01-18 |
| 4.3 | Walk-forward validation | [x] | 2026-01-18 |
| 4.4 | Bias safeguards | [x] | 2026-01-18 |

**Backtesting Engine Completed:** 2026-01-18

### 5. Analysis & Reporting

| # | Task | Status | Completed At |
|---|------|--------|--------------|
| 5.1 | Performance metrics | [x] | 2026-01-18 |
| 5.2 | Visualization tools | [x] | 2026-01-18 |
| 5.3 | Report generation | [x] | 2026-01-18 |

**Analysis Completed:** 2026-01-18

---

## Testing Phase

| # | Task | Status | Completed At |
|---|------|--------|--------------|
| T1 | Data provider tests | [x] | 2026-01-18 |
| T2 | Storage layer tests | [x] | 2026-01-18 |
| T3 | Signal generator tests | [x] | 2026-01-18 |
| T4 | Backtest engine tests | [x] | 2026-01-18 |
| T5 | Integration tests | [x] | 2026-01-18 |

**Testing Phase Completed:** 2026-01-18

---

## Verification Phase

| # | Task | Status | Completed At |
|---|------|--------|--------------|
| V1 | `mypy .` passes | [x] | 2026-01-18 |
| V2 | `ruff check .` passes | [x] | 2026-01-18 |
| V3 | `pytest tests/ -v` passes | [x] | 2026-01-18 |

**All Verification Passed:** 2026-01-18

---

## Summary

| Phase | Tasks | Completed | Progress |
|-------|-------|-----------|----------|
| Setup | 4 | 4 | 100% |
| Data Providers | 5 | 5 | 100% |
| Data Storage | 4 | 4 | 100% |
| Signal Generators | 4 | 4 | 100% |
| Backtesting | 4 | 4 | 100% |
| Analysis | 3 | 3 | 100% |
| Testing | 5 | 5 | 100% |
| Verification | 3 | 3 | 100% |
| **TOTAL** | **32** | **32** | **100%** |

---

**Project Completed:** 2026-01-18
**Total Duration:** Same day

---

## Notes & Issues

_Log any blockers, decisions, or issues here:_

1. All components implemented and tested successfully
2. 61 unit tests passing
3. Type checking (mypy) and linting (ruff) passing

---

## Active Priority (2026-04-16)

Diagnosis: LLM expression search is stuck — primary signals firing too often (stop-loss 45–58%, `meta_prob` stuck at 0.5, `cusum_entry_rate=1.0`), validation not rejecting overfit noise across 145+ iterations.

1. **AFML Stage 9 — Meta-labeling & feature importance.** Direct fix for false-entry domination; plumbing exists (`meta_prob=0.5`) but the secondary classifier isn't trained/tuned. Biggest expected reduction in stop-loss rate.
2. **AFML Stage 6 — CPCV + Sequential Bootstrap.** Produces a *distribution* of Sharpes across the iteration space rather than a single Purged-K-Fold number; catches overfitting that current CV misses.
3. **B6 — `expected_max_sharpe()` usage for multiple testing correction.** One-function fix that makes PSR honest when testing many strategies. Complements Stage 9 (fewer false entries) and Stage 6 (honest distribution).

> Note: equity research orchestrator extracted to its own repo on 2026-05-10 — see github.com/aka004/equity-research.

---

## Code Quality & Bug Fixes

**Added:** 2026-01-26
**Source:** Book analysis reports (Pardo, AFML, MLAM, Chan)

| # | Task | Status | Priority |
|---|------|--------|----------|
| B1 | Fix PSR benchmark formula (remove /sqrt(annualization)) | [x] | High — done in b781988 (2026-03-28) |
| B2 | Add bi-directional purging to cross-validation | [ ] | High |
| B3 | Add Walk-Forward Efficiency (WFE) metric | [ ] | High |
| B4 | Add Marcenko-Pastur covariance denoising | [ ] | Medium |
| B5 | Run backtests to generate actual metrics | [x] | High — running continuously via auto_research_loop |
| B6 | Add expected_max_sharpe() for multiple testing correction | [ ] | Medium |
| B7 | Add EWMA volatility estimation | [ ] | Low |

---

## AFML Implementation Stages

**Added:** 2026-01-26
**Source:** Revised AFML roadmap (Obsidian vault)
**Full plan:** docs/plans/2026-02-18-unified-backtest-roadmap.md

### Current Status Summary

| Stage | Description | Status |
|-------|-------------|--------|
| 0 | Foundation (scaffold, config, storage, providers) | COMPLETE |
| 1 | Core Labeling (triple-barrier, volatility) | COMPLETE |
| 2 | Sample Weights & Purged CV | COMPLETE |
| 3 | Basic Signals & Backtest Engine | MOSTLY COMPLETE |
| 4 | Advanced Metrics (PSR, DSR, WFE) | PARTIAL |
| 5 | Bet Sizing & HRP Portfolio | PARTIAL |
| 6 | Sequential Bootstrap & CPCV | NOT STARTED |
| 7 | Entropy & Microstructure Features | NOT STARTED |
| 8 | Regime Detection (CUSUM, SADF) | PARTIAL (needs audit) |
| 9 | Meta-Labeling & Feature Importance | NOT STARTED |
| 10 | Alternative Bars (dollar, volume, imbalance) | NOT STARTED |
| 11 | Reporting & Full Pipeline | PARTIAL |

### Files to Audit (Tomorrow)

| File | Stage | Check Against |
|------|-------|---------------|
| afml/labels.py | 1 | AFML Ch. 3 |
| afml/weights.py | 2 | AFML Ch. 4 |
| afml/cv.py | 2 | AFML Ch. 7 |
| afml/metrics.py | 4 | AFML Ch. 14 |
| afml/portfolio.py | 5 | AFML Ch. 16 |
| afml/regime.py | 8 | AFML Ch. 17 |

### Missing Implementations (Priority Order)

1. **Stage 4 (High)**
   - Deflated Sharpe Ratio
   - Walk-Forward Efficiency
   - Runs statistics

2. **Stage 6 (High)**
   - Combinatorial Purged CV (CPCV)
   - Sequential bootstrap

3. **Stage 5 (Medium)**
   - Kelly sizing
   - Verify HRP implementation

4. **Stage 1 (Medium)**
   - Fractional differentiation
   - ADF test integration

5. **Stages 7-10 (Lower)**
   - Entropy features
   - Microstructure features
   - Alternative bars
   - Meta-labeling

---

## Phase 2: Social Sentiment & Alternative Data

**Added:** 2026-01-26
**Status:** TODO

### Social Arbitrage Data Sources

| # | Task | Status | Priority |
|---|------|--------|----------|
| S1 | Google Trends API provider | [ ] | High |
| S2 | Reddit sentiment provider (enhance existing) | [ ] | High |
| S3 | TikTok trend scraper | [ ] | Medium |
| S4 | SimilarWeb API integration | [ ] | Medium |
| S5 | AltIndex API integration | [ ] | Low |
| S6 | Amazon Best Sellers scraper | [ ] | Low |
| S7 | Glassdoor sentiment provider | [ ] | Low |

### Congress/Political Trading

| # | Task | Status | Priority |
|---|------|--------|----------|
| P1 | CapitolTrades scraper (browser-based) | [ ] | Low |
| P2 | Quiver API integration (if paid) | [ ] | Low |
| P3 | SEC EDGAR Form 4 parser | [ ] | Medium |

### Macro Regime Indicators (Suggestions)

| # | Indicator | Signal | Notes |
|---|-----------|--------|-------|
| M1 | Dow/Gold ratio | Regime change | Extremes = systemic shift (1929, 1973, 2008, 2026) |
| M2 | SOFR volume | Banking stress | Drop then rise = bailout incoming |
| M3 | Credit spreads | Stress vs rotation | Widening + gold rally = real stress |
| M4 | Financials vs Defensives | Risk appetite | Relative strength divergence |

Reference: https://x.com/FinanceLancelot/status/2015484376360829184

### References

- Social arbitrage guide: https://x.com/investingluc/status/2015529292680269914
- Dow/Gold macro thread: https://x.com/FinanceLancelot/status/2015484376360829184
- Google Trends: trends.google.com
- TikTok Trends: ads.tiktok.com/business/creativecenter
- AltIndex: altindex.com
- Key subreddits: r/Quant, r/wallstreetbets, r/stocks, r/ValueInvesting

---

## Completion Signal

**LOOP_COMPLETE**
