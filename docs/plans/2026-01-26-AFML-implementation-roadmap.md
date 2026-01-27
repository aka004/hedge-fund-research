# AFML Implementation Roadmap - Revised

**Created:** 2026-01-26
**Source:** Revised Obsidian notes consolidating AFML, MLAM, Pardo, Chan

## Current Implementation Status

### Stage 0: Foundation - COMPLETE
- [x] Project scaffold (pyproject.toml, directory structure)
- [x] Configuration system (config.py with env vars)
- [x] Data storage layer (data/storage/parquet.py)
- [x] Yahoo Finance provider (data/providers/yahoo.py)
- [x] Basic price validation

### Stage 1: Core Labeling & Features - COMPLETE
- [x] Triple-barrier labels (afml/labels.py)
- [x] Volatility estimators (in labels module)
- [ ] Fractional differentiation (afml/fracdiff.py) - NOT IMPLEMENTED
- [ ] ADF stationarity test integration - NOT IMPLEMENTED

### Stage 2: Sample Weights & Basic CV - COMPLETE
- [x] Concurrent labels count (afml/weights.py)
- [x] Average uniqueness (afml/weights.py)
- [x] Purged K-Fold CV (afml/cv.py)
- [ ] Time decay weights - NOT IMPLEMENTED
- [ ] Class weights - NOT IMPLEMENTED

### Stage 3: Basic Signals & Backtest Engine - MOSTLY COMPLETE
- [x] Momentum signal (strategy/signals/momentum.py)
- [x] Signal registry/combiner (strategy/signals/combiner.py)
- [x] Basic backtest engine (strategy/backtest/engine.py)
- [x] Transaction cost model (in engine)
- [x] Basic metrics (analysis/metrics.py)
- [ ] Verify metrics match AFML Ch. 14 formulas

### Stage 4: Advanced Metrics & Validation - PARTIAL
- [ ] Probabilistic Sharpe Ratio (PSR) - needs verification
- [ ] Deflated Sharpe Ratio - needs implementation
- [ ] Runs statistics - NOT IMPLEMENTED
- [ ] Efficiency ratio - NOT IMPLEMENTED
- [ ] Walk-forward validation - EXISTS but needs audit
- [ ] Strategy risk metrics (Ch. 15) - NOT IMPLEMENTED

### Stage 5: Bet Sizing & Portfolio Construction - PARTIAL
- [ ] Kelly criterion - needs implementation
- [ ] Probability to bet size mapping - NOT IMPLEMENTED
- [ ] Bet averaging - NOT IMPLEMENTED
- [ ] HRP implementation (afml/portfolio.py) - needs audit
- [ ] Condition number monitoring - NOT IMPLEMENTED

### Stage 6: Sequential Bootstrap & CPCV - NOT IMPLEMENTED
- [ ] Sequential bootstrap
- [ ] Indicator matrix
- [ ] Combinatorial Purged CV
- [ ] Path distribution analysis

### Stage 7: Entropy & Microstructure Features - NOT IMPLEMENTED
- [ ] Shannon entropy
- [ ] Lempel-Ziv complexity
- [ ] Encoding schemes (binary, quantile, sigma)
- [ ] Parkinson volatility
- [ ] Garman-Klass volatility
- [ ] Corwin-Schultz spread
- [ ] Amihud illiquidity

### Stage 8: Regime Detection & Structural Breaks - PARTIAL
- [x] afml/regime.py exists - needs audit against AFML
- [ ] CUSUM filter - needs verification
- [ ] Chow test - NOT IMPLEMENTED
- [ ] SADF test - needs verification
- [ ] GSADF test - NOT IMPLEMENTED

### Stage 9: Meta-Labeling & Feature Importance - NOT IMPLEMENTED
- [ ] Meta-labeling framework
- [ ] MDA importance
- [ ] SFI importance
- [ ] Clustered MDA
- [ ] Synthetic data tests

### Stage 10: Alternative Bars - NOT IMPLEMENTED
- [ ] Dollar bars
- [ ] Volume bars
- [ ] Tick imbalance bars
- [ ] Volume imbalance bars
- [ ] Synthetic price generator
- [ ] Strategy verification framework

### Stage 11: Reporting & Integration - PARTIAL
- [x] Obsidian reports (analysis/obsidian_reports.py)
- [ ] Full tearsheet generator
- [ ] Experiment tracker
- [ ] Full pipeline script

## Priority Implementation Order

Based on gaps, recommended order:

1. **High Priority (Stage 4 gaps)**
   - PSR formula fix (B1 in TODO.md)
   - Deflated Sharpe Ratio
   - Walk-Forward Efficiency metric

2. **High Priority (Stage 2 gaps)**
   - Bi-directional purging in CV (B2 in TODO.md)

3. **Medium Priority (Stage 5)**
   - Audit afml/portfolio.py against HRP spec
   - Add Kelly sizing

4. **Medium Priority (Stage 6)**
   - CPCV for multiple backtest paths
   - Sequential bootstrap

5. **Lower Priority (Stages 7-10)**
   - Entropy features
   - Alternative bars
   - Meta-labeling

## Files to Audit

| File | Stage | Audit Against |
|------|-------|---------------|
| afml/labels.py | 1 | AFML Ch. 3 |
| afml/weights.py | 2 | AFML Ch. 4 |
| afml/cv.py | 2 | AFML Ch. 7 |
| afml/metrics.py | 4 | AFML Ch. 14 |
| afml/portfolio.py | 5 | AFML Ch. 16 |
| afml/regime.py | 8 | AFML Ch. 17 |
| strategy/backtest/engine.py | 3 | AFML Ch. 10-12 |

## Timeline Estimate

- MVS (Stages 0-4 complete): ~2 weeks of focused work
- Research-ready (Stages 0-6): ~4 weeks
- Full AFML (Stages 0-11): ~8-10 weeks

## Reference

Full concept list with code snippets in Obsidian vault:
`AFML Complete Implementation Roadmap.md`
