"""
Methodology Injection System for Multi-Agent Research
======================================================

Injects relevant AFML (or other methodology) context per agent.
Agents only receive concepts applicable to their role.

Usage:
    from methodology_injection import MethodologyInjector
    
    injector = MethodologyInjector()
    context = injector.get_context("02-QUANT-AGENT")
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class MethodologyConcept:
    """A single methodology concept with context for agents."""
    name: str
    description: str
    data_requirements: list[str]
    validation_checks: list[str]
    references: list[str] = field(default_factory=list)


# =============================================================================
# AFML METHODOLOGY DEFINITIONS
# =============================================================================

AFML_CONCEPTS = {
    "triple_barrier": MethodologyConcept(
        name="Triple-Barrier Labeling",
        description="""
Labels are assigned based on which barrier is touched first:
- Upper barrier (profit-take): label = 1
- Lower barrier (stop-loss): label = -1  
- Vertical barrier (timeout): label = sign(return)

This replaces fixed-horizon returns which assume trades exit on schedule.
Barriers are sized as multiples of volatility (e.g., 2x daily vol).
""",
        data_requirements=[
            "prices (OHLCV with DatetimeIndex)",
            "volatility (rolling std, typically 20-day)",
            "events (timestamps to label, e.g., CUSUM detections)",
        ],
        validation_checks=[
            "Labels should have ~balanced classes (not >70% one label)",
            "Exit types should show mix of profit/stop/timeout",
            "Average holding period should be < max_holding parameter",
        ],
        references=["AFML Chapter 3"],
    ),
    
    "sample_weights": MethodologyConcept(
        name="Sample Uniqueness Weights",
        description="""
When label periods overlap, samples are correlated. Weighting by inverse
concurrency corrects for pseudo-replication.

uniqueness[i] = 1 / (number of labels overlapping with label i)

Use these weights in model.fit(X, y, sample_weight=weights).
Without weighting, effective sample size is artificially inflated.
""",
        data_requirements=[
            "label_start_times (when each position entered)",
            "label_end_times (when each position exited)",
            "concurrency counts per sample",
        ],
        validation_checks=[
            "Average uniqueness should be < 1.0 (if = 1.0, no overlap detected)",
            "Highly concurrent periods should have low weights",
            "Weights should sum to 1.0 (if normalized)",
        ],
        references=["AFML Chapter 4"],
    ),
    
    "purged_cv": MethodologyConcept(
        name="Purged K-Fold Cross-Validation",
        description="""
Standard k-fold leaks information when labels have overlapping evaluation periods.
Purged CV removes training samples whose labels extend into the test period.
Embargo adds a gap after test set to prevent leakage from lagged features.

NEVER use sklearn's KFold for financial time series backtesting.
""",
        data_requirements=[
            "label_end_times for each sample (to determine overlap)",
            "embargo_pct parameter (typically 0.01 = 1%)",
            "n_splits parameter (typically 5)",
        ],
        validation_checks=[
            "Training set should shrink vs. standard k-fold (purging effect)",
            "No training sample's label should extend past test start",
            "Embargo period should be respected",
        ],
        references=["AFML Chapter 7"],
    ),
    
    "regime_detection": MethodologyConcept(
        name="Regime Detection (CUSUM/SADF)",
        description="""
Markets operate in different regimes (trending, mean-reverting, high-vol).
CUSUM detects structural breaks. SADF detects bubbles.

Use regime state as:
- Feature for models
- Filter for strategy activation
- Context for risk management
""",
        data_requirements=[
            "prices for CUSUM calculation",
            "threshold parameter for break detection",
            "regime_states output (categorical: bull/bear/neutral)",
        ],
        validation_checks=[
            "Regime changes should be infrequent (not noise)",
            "Regimes should have economic interpretation",
            "Transitions should align with known market events",
        ],
        references=["AFML Chapter 17"],
    ),
    
    "meta_labeling": MethodologyConcept(
        name="Meta-Labeling",
        description="""
Two-stage model:
1. Primary model predicts direction (side)
2. Meta-model predicts whether primary is correct (size)

Meta-labels are binary: 1 if primary model's trade was profitable, 0 otherwise.
This separates "what to trade" from "when to trade".
""",
        data_requirements=[
            "primary_model predictions (side: long/short)",
            "triple_barrier labels (actual outcomes)",
            "meta_labels (1 if primary correct, 0 otherwise)",
        ],
        validation_checks=[
            "Meta-model should have better precision than recall",
            "Combined model should have higher Sharpe than primary alone",
            "Meta-model should filter out low-confidence primary signals",
        ],
        references=["AFML Chapter 3.6"],
    ),
    
    "fractional_diff": MethodologyConcept(
        name="Fractional Differentiation",
        description="""
Integer differencing (d=1) removes memory but achieves stationarity.
Fractional differencing (0 < d < 1) balances stationarity vs. memory retention.

Find minimum d that passes ADF test for stationarity while preserving
maximum predictive information.
""",
        data_requirements=[
            "price series (original, non-stationary)",
            "d parameter (fractional differencing order)",
            "fracdiff_series (output)",
        ],
        validation_checks=[
            "Output should pass ADF stationarity test",
            "d should be minimized (preserve memory)",
            "Correlation with original series should be high",
        ],
        references=["AFML Chapter 5"],
    ),
}


# =============================================================================
# AGENT-METHODOLOGY MAPPING
# =============================================================================

AGENT_METHODOLOGY_MAP = {
    "08-DATA-QUALITY-AGENT": {
        "concepts": ["triple_barrier", "sample_weights", "purged_cv", "regime_detection"],
        "role": "data_requirements",
        "instructions": """
## AFML Methodology Data Requirements

This system implements AFML (Advances in Financial Machine Learning) methodology.
Beyond standard market data, check for these AFML-specific data structures:

### Required Tables/Data

| Table | Purpose | Key Fields | Check |
|-------|---------|------------|-------|
| `labels` | Triple-barrier labels | ticker, event_time, label, return, exit_time, exit_type | Must exist per ticker |
| `sample_weights` | Uniqueness weights | ticker, event_time, weight, concurrency | Needed for training |
| `volatility` | Barrier sizing | ticker, date, vol_20d | For label generation |
| `regime` | Market regime | ticker, date, regime_state, cusum_value | For filtering |
| `cv_folds` | Pre-computed folds | ticker, fold_id, train_idx, test_idx | Optional optimization |

### Validation Checks

When assessing data quality for AFML:
1. **Labels exist?** - Can't train without triple-barrier labels
2. **Weights computed?** - Models need sample_weight parameter
3. **Label end times available?** - Required for purged CV
4. **Volatility current?** - Stale vol = wrong barrier sizes
5. **Regime states?** - Needed for regime-conditional strategies

Flag as P0 gap if labels or weights are missing - blocks all AFML modeling.
""",
    },
    
    "02-QUANT-AGENT": {
        "concepts": ["triple_barrier", "sample_weights", "purged_cv", "meta_labeling", "fractional_diff"],
        "role": "methodology_application",
        "instructions": """
## AFML Methodology Application

Apply AFML methods for all quantitative analysis:

### Labeling
- Use **triple-barrier labeling**, NOT fixed-horizon returns
- Size barriers using rolling volatility (e.g., 2x 20-day std)
- Report exit_type distribution (profit/stop/timeout)

### Sample Weighting  
- Compute **sample uniqueness weights** for all overlapping labels
- Report average uniqueness (should be < 1.0)
- Use weights in all model fitting: `model.fit(X, y, sample_weight=weights)`

### Cross-Validation
- Use **purged k-fold CV**, NEVER standard k-fold
- Set embargo_pct (typically 1%)
- Report effective training size after purging

### Backtesting
- Walk-forward only (no lookahead)
- Report: Sharpe, max drawdown, hit rate by exit_type
- Compare purged CV scores vs. walk-forward (should be similar if no overfit)

### Meta-Labeling (if applicable)
- Separate side (direction) from size (confidence)
- Primary model → meta-model pipeline
- Report precision vs. recall tradeoff

DO NOT use:
- Fixed-time returns for labels
- sklearn KFold for CV
- Equal sample weights with overlapping labels
""",
    },
    
    "03-RISK-AGENT": {
        "concepts": ["regime_detection", "triple_barrier"],
        "role": "risk_application",
        "instructions": """
## AFML Risk Methodology

Apply AFML concepts for risk assessment:

### Regime Detection
- Use **CUSUM** for structural break detection
- Identify regime states: bull / bear / neutral / high-vol
- Assess current regime and transition probabilities

### Drawdown Analysis
- Compute **maximum drawdown** and **time underwater**
- Analyze drawdowns by regime (worse in which states?)
- Report drawdown at 95th percentile

### Tail Risk
- Use regime-conditional VaR (risk differs by regime)
- Analyze stop-loss hit rate from triple-barrier labels
- Report: % of trades hitting stop-loss by regime

### Position Sizing Context
- Recommend position limits based on regime
- Higher cash allocation in high-uncertainty regimes
- Flag regime transitions as risk events

DO NOT:
- Assume constant volatility across regimes
- Ignore structural breaks in risk calculations
""",
    },
    
    "04-COMPETITIVE-AGENT": {
        "concepts": [],
        "role": None,
        "instructions": None,
    },
    
    "05-QUALITATIVE-AGENT": {
        "concepts": [],
        "role": None,
        "instructions": None,
    },
    
    "06-SYNTHESIS-AGENT": {
        "concepts": ["triple_barrier", "sample_weights", "purged_cv", "regime_detection"],
        "role": "interpretation",
        "instructions": """
## AFML Methodology Interpretation

When synthesizing the research memo, explain AFML concepts accessibly:

### Translation Guide

| AFML Term | Plain English |
|-----------|---------------|
| Triple-barrier labels | "Trades labeled by how they actually exit (profit target, stop-loss, or time limit)" |
| Sample uniqueness | "Adjusted for overlapping trade periods to avoid double-counting" |
| Purged CV | "Backtested with strict separation of training and test data to prevent lookahead bias" |
| Regime detection | "Identified distinct market environments (trending, volatile, etc.)" |
| Meta-labeling | "Two-stage model: first predicts direction, second predicts confidence" |

### In the Executive Summary
- Mention methodology briefly: "Analysis uses AFML methodology for statistically rigorous backtesting"
- Don't overwhelm with jargon

### In Technical Sections
- Explain why these methods matter (e.g., "standard backtests overstate performance by 30-50%")
- Reference specific AFML checks performed

### Data Quality Appendix
- Include AFML-specific data gaps identified
- Note impact on analysis confidence
""",
    },
}


# =============================================================================
# INJECTOR CLASS
# =============================================================================

class MethodologyInjector:
    """
    Injects methodology context into agent prompts.
    """
    
    def __init__(self, methodology: str = "AFML"):
        self.methodology = methodology
        self.concepts = AFML_CONCEPTS
        self.agent_map = AGENT_METHODOLOGY_MAP
    
    def get_context(self, agent_name: str) -> Optional[str]:
        if agent_name not in self.agent_map:
            return None
        
        agent_config = self.agent_map[agent_name]
        
        if agent_config["instructions"] is None:
            return None
        
        return agent_config["instructions"]
    
    def get_relevant_concepts(self, agent_name: str) -> list[MethodologyConcept]:
        if agent_name not in self.agent_map:
            return []
        
        concept_names = self.agent_map[agent_name]["concepts"]
        return [self.concepts[name] for name in concept_names if name in self.concepts]
    
    def get_data_requirements(self, concept_name: str) -> list[str]:
        if concept_name not in self.concepts:
            return []
        return self.concepts[concept_name].data_requirements
    
    def get_validation_checks(self, concept_name: str) -> list[str]:
        if concept_name not in self.concepts:
            return []
        return self.concepts[concept_name].validation_checks
    
    def get_all_data_requirements(self) -> dict[str, list[str]]:
        return {
            name: concept.data_requirements 
            for name, concept in self.concepts.items()
        }
    
    def format_for_prompt(self, agent_name: str) -> str:
        context = self.get_context(agent_name)
        if context is None:
            return ""
        
        return f"\n\n{'='*60}\n{context}\n{'='*60}\n"


if __name__ == "__main__":
    injector = MethodologyInjector()
    
    print("=" * 60)
    print("METHODOLOGY INJECTION TEST")
    print("=" * 60)
    
    for agent in AGENT_METHODOLOGY_MAP.keys():
        context = injector.get_context(agent)
        concepts = injector.get_relevant_concepts(agent)
        
        print(f"\n{agent}:")
        print(f"  Concepts: {[c.name for c in concepts]}")
        print(f"  Has context: {context is not None}")
