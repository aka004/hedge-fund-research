# Multi-Agent Equity Research System

**Version**: 2.0
**Derived From**: Monolithic Research Prompt v1.0 + AFML Improvements
**Date**: 2026-01-26

---

## Overview

This system restructures a monolithic equity research prompt into a **multi-agent architecture** with specialized roles, explicit handoff contracts, and gate-based decision logic.

### Why Multi-Agent?

| Monolithic Approach | Multi-Agent Approach |
|---------------------|---------------------|
| One agent does everything | Specialists focus on core competencies |
| Sequential, single-pass | Parallel analysis, iterative refinement |
| Difficult to debug | Clear handoff points for inspection |
| All-or-nothing output | Modular outputs, partial completion |
| Hard to extend | Add new agents without rewriting |

---

## System Architecture

```
                         ┌─────────────────────────────────────┐
                         │         ORCHESTRATOR AGENT          │
                         │  (00-ORCHESTRATOR.md)               │
                         │                                     │
                         │  • Routes tasks to specialists      │
                         │  • Enforces quality gates           │
                         │  • Compiles quality scorecard       │
                         │  • Manages feedback loop            │
                         └──────────────────┬──────────────────┘
                                            │
                    ┌───────────────────────┼───────────────────────┐
                    │                       │                       │
                    ▼                       │                       │
        ┌─────────────────┐                 │                       │
        │ DATA QUALITY    │◄────────────────┘                       │
        │ AGENT (08)      │ (Phase 0 & 7)                           │
        │                 │                                         │
        │ • Query DuckDB  │                                         │
        │ • Assess gaps   │                                         │
        │ • Session       │                                         │
        │   feedback      │                                         │
        └────────┬────────┘                                         │
                 │                                                  │
                 ▼                                                  │
        ┌─────────────────┐                                         │
        │   DATA AGENT    │◄────────────────────────────────────────┤
        │ (01-DATA)       │                                         │
        │                 │                                         │
        │ • Fill gaps     │                                         │
        │ • 60+ sources   │                                         │
        └────────┬────────┘                                         │
                 │                                                  │
                 ├──────────────────┬───────────────┬───────────────┤
                 ▼                  ▼               ▼               ▼
        ┌─────────────┐    ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
        │ QUANT (02)  │    │ RISK (03)   │ │ COMP (04)   │ │ QUAL (05)   │
        └──────┬──────┘    └──────┬──────┘ └──────┬──────┘ └──────┬──────┘
               │                  │               │               │
               └──────────────────┴───────────────┴───────────────┘
                                            │
                         ┌──────────────────▼──────────────────┐
                         │         SYNTHESIS AGENT             │
                         │  (06-SYNTHESIS.md)                  │
                         │                                     │
                         │  • Drafts 21-section memo           │
                         │  • Includes feedback appendix       │
                         └─────────────────────────────────────┘
```

---

## File Structure

```
multi-agent-research-system/
├── README.md                    # This file
├── 00-ORCHESTRATOR.md           # Master coordinator
├── 01-DATA-AGENT.md             # Source gathering & validation
├── 02-QUANT-AGENT.md            # Valuation & financial analysis
├── 03-RISK-AGENT.md             # Downside & risk assessment
├── 04-COMPETITIVE-AGENT.md      # Market & moat analysis
├── 05-QUALITATIVE-AGENT.md      # Execution & management
├── 06-SYNTHESIS-AGENT.md        # Memo drafting + feedback synthesis
├── 07-HANDOFF-CONTRACTS.md      # JSON schemas & protocols
└── 08-DATA-QUALITY-AGENT.md     # Database-first research & feedback loop (NEW)
```

---

## Database-First Research (NEW)

The system now prioritizes your native Parquet/DuckDB database before external research.

### Workflow Enhancement

```
┌─────────────────────────────────────────────────────────────────┐
│                    RESEARCH SESSION FLOW                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. DATA_QUALITY_AGENT queries native database                  │
│     ├── Check prices, fundamentals, social_metrics tables       │
│     ├── Assess freshness, completeness, accuracy                │
│     └── Output: data_availability.json                          │
│                         │                                       │
│                         ▼                                       │
│  2. DATA_AGENT fills ONLY the gaps                              │
│     ├── Skip data already in database                           │
│     ├── Focus external research on missing items                │
│     └── Output: coverage_log.json                               │
│                         │                                       │
│                         ▼                                       │
│  3. Analysis agents use database + external sources             │
│     ├── Log every gap encountered                               │
│     └── Track workaround time                                   │
│                         │                                       │
│                         ▼                                       │
│  4. SYNTHESIS_AGENT includes feedback appendix                  │
│     ├── Data gaps encountered                                   │
│     ├── Schema improvements needed                              │
│     └── SQL for recommended changes                             │
│                         │                                       │
│                         ▼                                       │
│  5. Session feedback updates improvement backlog                │
│     └── Track system health over time                           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Key Metrics Tracked

| Metric | Definition | Target |
|--------|------------|--------|
| Database Hit Rate | % of data needs met by native DB | ≥80% |
| Workaround Time | Minutes spent on manual data gathering | <15 min/session |
| Data Quality Score | Composite of freshness, completeness, accuracy | ≥90/100 |

### Expected Database Tables

| Table | Purpose | Key Fields |
|-------|---------|------------|
| `prices` | Daily OHLCV | ticker, date, ohlcv, adj_close |
| `fundamentals` | Quarterly financials | ticker, period, revenue, earnings, margins |
| `social_metrics` | StockTwits/Reddit | ticker, date, sentiment_score, mention_count |
| `filings` | SEC filings metadata | ticker, filing_type, date, url |
| `earnings_transcripts` | Call transcripts (planned) | ticker, quarter, transcript_text |
| `competitors` | Competitor financials (planned) | primary_ticker, competitor_ticker, metrics |

---

## Continuous Improvement Loop (NEW)

After every research session, the system generates actionable feedback.

### Session Feedback Output

```json
{
  "session_efficiency": {
    "database_hit_rate": 0.45,
    "workaround_time_minutes": 75,
    "data_quality_score": 74
  },
  "critical_gaps": [
    {
      "gap": "No earnings transcript table",
      "priority": "P1",
      "time_lost": "30 min/session",
      "recommendation": "Implement earnings_transcripts table"
    }
  ],
  "schema_improvements": [
    {
      "table": "fundamentals",
      "add_fields": ["segment_revenue", "nrr", "debt_maturity_schedule"]
    }
  ]
}
```

### Improvement Priority Framework

| Priority | Criteria | Action Timeline |
|----------|----------|-----------------|
| P0 | Blocks research entirely | Fix within 1 day |
| P1 | Adds >30 min workaround | Fix within 1 week |
| P2 | Adds 10-30 min workaround | Fix within 1 month |
| P3 | Minor inconvenience | Backlog |

### Cumulative Tracking

The system maintains `improvement_backlog.json` tracking:
- All reported gaps across sessions
- Total time lost per gap
- Resolution status
- System health trend over time

---

## Quick Start

### Option A: Sequential Invocation (Recommended for Claude)

Use Claude with role-switching by prefixing each request:

```
[ORCHESTRATOR MODE]
Research AAPL (Apple Inc.)

[DATA AGENT MODE]
Gather 60+ sources per coverage standards for AAPL.
Output: coverage_log.json, coverage_validator.json

[QUANT AGENT MODE]
Using the coverage log, build valuation model for AAPL.
Output: valuation_package.json

[RISK AGENT MODE]
Build bear case and risk assessment for AAPL.
Output: risk_assessment.json

[COMPETITIVE AGENT MODE]
Analyze market structure and moat for AAPL.
Output: competitive_analysis.json

[QUALITATIVE AGENT MODE]
Assess management and execution quality for AAPL.
Output: qualitative_assessment.json

[ORCHESTRATOR MODE]
Compile quality scorecard and enforce gates.
Output: quality_scorecard.json, rating_decision.json

[SYNTHESIS AGENT MODE]
Draft final memo from all agent outputs.
Output: final_memo.md
```

### Option B: Parallel Invocation (For Multi-Agent Frameworks)

If using a framework that supports parallel execution:

1. Run DATA_AGENT first (required input for others)
2. Run QUANT, RISK, COMPETITIVE, QUALITATIVE in parallel
3. Run ORCHESTRATOR for gate enforcement
4. Run SYNTHESIS_AGENT for final memo

---

## Gate Logic

### Mandatory Gates (ALL must pass for BUY rating)

| Gate | Threshold | Blocker |
|------|-----------|---------|
| Coverage | 60+ sources, all validator PASS | Cannot proceed without data |
| Expected Return | E[TR] ≥ 30% | Cannot recommend BUY below |
| Skew | E[TR] / bear_drawdown ≥ 1.7× | Insufficient asymmetry |
| Margin of Safety | Price ≤ 75% of mid FV | Valuation stretched |
| Quality | Score ≥ 70/100 | Business quality insufficient |
| Sell Floor | Score ≥ 60/100 | FORCE SELL if below |
| Why Now | Catalyst within 24 months | No timing urgency |

### Gate Exemptions

Only the **Margin of Safety gate** can be exempted, and only if:
- A near-certain catalyst exists (≥80% probability)
- Within 6 months
- With quantified impact
- Cited source for probability estimate

---

## Quality Scorecard

| Component | Weight | Source Agent |
|-----------|--------|--------------|
| Market | 25 | COMPETITIVE_AGENT |
| Moat | 25 | COMPETITIVE_AGENT |
| Unit Economics | 20 | QUANT_AGENT |
| Execution | 15 | QUALITATIVE_AGENT |
| Financial Quality | 15 | RISK_AGENT |

**Scoring (0-5 per component):**
- 5 = Exceptional, evidence required
- 4 = Strong
- 3 = Adequate
- 2 = Weak
- 1 = Poor
- 0 = Absent/Critical issues

**Total Score** = Σ (raw_score × weight) / 5 × 100

---

## AFML Integration

This system incorporates improvements from "Advances in Financial Machine Learning":

| AFML Concept | Integrated In | Implementation |
|--------------|---------------|----------------|
| Triple-Barrier Labeling | QUANT_AGENT | Dynamic exit scenarios |
| Purged K-Fold CV | QUANT_AGENT | Backtest validation |
| Deflated Sharpe Ratio | QUANT_AGENT | Statistical significance |
| Strategy Risk | RISK_AGENT | Beyond portfolio volatility |
| HRP | RISK_AGENT | Portfolio construction |
| Regime Detection | RISK_AGENT | CUSUM, SADF, Entropy |
| Sample Uniqueness | DATA_AGENT | Source weighting |

---

## Output Specification

### Final Memo Structure

1. **Executive Summary** (ALWAYS FIRST)
2. Rating & Price Targets
3. Investment Thesis & Variant Perception
4. Decision Rules / Quality Scorecard / Entry Overlay
5. **Sections 1-21** (full memo body)
6. Coverage Log + Validator (appendix)
7. Model Appendix

### Required Formatting

- Every paragraph labeled: **[Fact]**, **[Analysis]**, or **[Inference]**
- Acronyms expanded on first use
- Exact calendar dates (never "recently")
- All math shown step-by-step
- Units always included (%, $, bps, mm, bn)

---

## Extending the System

### Adding a New Agent

1. Create `XX-NEW-AGENT.md` following the template
2. Define inputs/outputs in `07-HANDOFF-CONTRACTS.md`
3. Add routing logic in `00-ORCHESTRATOR.md`
4. Update quality scorecard if applicable

### Agent Template

```markdown
# [AGENT NAME] — [Purpose]

**Role**: [One-line description]
**Reports To**: Orchestrator Agent
**Version**: X.X

## ROLE AND OBJECTIVE
[What this agent does]

## REQUIRED OUTPUTS
[JSON schemas for outputs]

## ANALYTICAL FRAMEWORKS
[Methods and calculations]

## OUTPUT FORMAT RULES
[DO and DO NOT]

## HANDOFF TO ORCHESTRATOR
[Standard handoff message format]

## QUALITY SCORECARD CONTRIBUTION
[If applicable]
```

---

## Troubleshooting

### Coverage Gate Fails
- DATA_AGENT should continue gathering silently
- Check domain concentration (≤10% per domain)
- Verify source type classification

### Rating Blocked Despite Good Business
- Check all gates individually
- Most common: Margin of Safety gate fails (valuation stretched)
- Consider Wait-for-entry instead of Hold

### Inconsistent Data Across Agents
- Orchestrator validates consistency
- Bear case prices must match between QUANT and RISK
- Probabilities must sum to 1.0

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 2.0 | 2026-01-26 | Multi-agent restructure, AFML integration |
| 1.0 | Original | Monolithic research prompt |

---

## License

Internal use only. Derived from proprietary research methodology.
