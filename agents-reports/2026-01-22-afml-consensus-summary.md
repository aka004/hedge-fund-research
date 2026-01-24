# AFML Consensus Summary

**Date:** 2026-01-22
**Source:** Multi-agent consensus meeting analyzing AFML recommendations

---

## Final Decision: MVP Features

| # | Feature | Owner | Complexity |
|---|---------|-------|------------|
| 1 | **Purged K-Fold CV** | Backtest Unit | Medium |
| 2 | **Triple-Barrier Labeling** | Momentum Researcher | Medium |
| 3 | **Deflated Sharpe Ratio (PSR)** | Statistical Agent | Low |
| 4 | **Simple HRP** | Risk Manager + Portfolio Constructor | Medium |
| 5 | **Sample Uniqueness Weighting** | Statistical Agent | Low |
| 6 | **Simple Regime (200MA)** | Regime Agent | Low |
| 7 | **Stationarity Warnings** | Math Professor | Low |

---

## Build Order

```
1. Purged K-Fold CV        ← Foundation (validates everything else)
2. Triple-Barrier Labeling ← Changes return distribution
3. Sample Uniqueness       ← Affects model training
4. Deflated Sharpe Ratio   ← Validates strategies
5. Simple HRP              ← Portfolio construction
6. Simple Regime           ← Context for signals
7. Stationarity Warnings   ← Guard rails
```

---

## Version 2 (Deferred)

- Fractional Differentiation
- Meta-Labeling
- Feature Importance (MDA/SFI)
- Bet Averaging/Discretization
- Strategy Risk Calculation
- Volatility Regime
- Condition Number Monitoring

---

## Skipped (Not Worth Complexity)

- CUSUM/SADF structural breaks
- Entropy features
- Microstructure signals (VPIN)
- Full Kelly bet sizing

---

## Key Decisions

| Question | Resolution |
|----------|------------|
| HRP vs Feature Importance | HRP in MVP, Feature Importance in v2 |
| Advanced vs Simple Regime | Simple 200MA for MVP |
| Fractional Diff | Deferred to v2 (not skipped) |
| Sample Uniqueness | Added to MVP (low complexity, high value) |

---

## Estimated Scope

- **MVP:** ~500-700 lines of Python
- **Build time:** Implementation-ready with AFML pseudocode as reference

---

*Full transcript: `2026-01-22-afml-consensus-transcript.md`*
