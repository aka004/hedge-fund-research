# HANDOFF CONTRACTS & SCHEMA DEFINITIONS

**Purpose**: Define the data contracts between agents for reliable inter-agent communication
**Version**: 2.0

---

## OVERVIEW

This document defines the JSON schemas and handoff protocols for all agent interactions. Every agent MUST conform to these contracts to ensure the multi-agent system functions correctly.

---

## AGENT COMMUNICATION FLOW

```
┌─────────────┐     coverage_log.json      ┌─────────────┐
│             │ ──────────────────────────▶│             │
│  DATA       │     coverage_validator.json│  ORCHES-    │
│  AGENT      │ ──────────────────────────▶│  TRATOR     │
│             │                            │             │
└─────────────┘                            └──────┬──────┘
                                                  │
                    ┌─────────────────────────────┼─────────────────────────────┐
                    │                             │                             │
                    ▼                             ▼                             ▼
            ┌─────────────┐              ┌─────────────┐              ┌─────────────┐
            │             │              │             │              │             │
            │  QUANT      │              │  RISK       │              │ COMPETITIVE │
            │  AGENT      │              │  AGENT      │              │   AGENT     │
            │             │              │             │              │             │
            └──────┬──────┘              └──────┬──────┘              └──────┬──────┘
                   │                            │                            │
                   │ valuation_package.json     │ risk_assessment.json       │ competitive_analysis.json
                   │                            │                            │
                   └────────────────────────────┼────────────────────────────┘
                                                │
                                                ▼
                                        ┌─────────────┐
                                        │             │
                                        │  SYNTHESIS  │
                                        │  AGENT      │
                                        │             │
                                        └──────┬──────┘
                                               │
                                               │ final_memo.md
                                               ▼
                                        ┌─────────────┐
                                        │             │
                                        │  ORCHES-    │
                                        │  TRATOR     │
                                        │             │
                                        └─────────────┘
```

---

## SCHEMA DEFINITIONS

### 1. Coverage Log Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "CoverageLog",
  "type": "object",
  "required": ["ticker", "company_name", "research_date", "total_sources", "sources"],
  "properties": {
    "ticker": {"type": "string"},
    "company_name": {"type": "string"},
    "research_date": {"type": "string", "format": "date"},
    "total_sources": {"type": "integer", "minimum": 60},
    "sources": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["id", "title", "link", "date", "source_type", "domain", "recency"],
        "properties": {
          "id": {"type": "integer"},
          "title": {"type": "string"},
          "link": {"type": "string", "format": "uri"},
          "date": {"type": "string", "format": "date"},
          "source_type": {
            "type": "string",
            "enum": ["filing", "earnings_ir", "industry_trade", "high_quality_media", "competitor_primary", "academic_expert"]
          },
          "region": {"type": "string"},
          "domain": {"type": "string"},
          "sections_covered": {"type": "array", "items": {"type": "string"}},
          "note": {"type": "string"},
          "recency": {"type": "boolean"}
        }
      }
    }
  }
}
```

### 2. Coverage Validator Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "CoverageValidator",
  "type": "object",
  "required": ["ticker", "validation_date", "results", "overall_status", "ready_for_analysis"],
  "properties": {
    "ticker": {"type": "string"},
    "validation_date": {"type": "string", "format": "date"},
    "results": {
      "type": "object",
      "properties": {
        "unique_sources": {"$ref": "#/definitions/ValidationResult"},
        "hq_media": {"$ref": "#/definitions/ValidationResult"},
        "competitor_primary": {"$ref": "#/definitions/ValidationResult"},
        "academic_expert": {"$ref": "#/definitions/ValidationResult"},
        "recency_pct": {"$ref": "#/definitions/ValidationResult"},
        "max_domain_concentration": {"$ref": "#/definitions/ValidationResult"}
      }
    },
    "overall_status": {"type": "string", "enum": ["ALL_PASS", "SOME_FAIL"]},
    "ready_for_analysis": {"type": "boolean"}
  },
  "definitions": {
    "ValidationResult": {
      "type": "object",
      "required": ["required", "actual", "status"],
      "properties": {
        "required": {"type": "number"},
        "actual": {"type": "number"},
        "status": {"type": "string", "enum": ["PASS", "FAIL"]}
      }
    }
  }
}
```

### 3. Valuation Package Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "ValuationPackage",
  "type": "object",
  "required": ["ticker", "valuation_date", "current_price", "fair_value_band", "expected_total_return", "margin_of_safety", "skew_ratio"],
  "properties": {
    "ticker": {"type": "string"},
    "valuation_date": {"type": "string", "format": "date"},
    "current_price": {"type": "number"},
    "shares_outstanding_mm": {"type": "number"},
    "market_cap_bn": {"type": "number"},
    "fair_value_band": {
      "type": "object",
      "required": ["low", "mid", "high"],
      "properties": {
        "low": {"type": "number"},
        "mid": {"type": "number"},
        "high": {"type": "number"},
        "method": {"type": "string"}
      }
    },
    "expected_total_return": {
      "type": "object",
      "required": ["E_TR", "components"],
      "properties": {
        "E_TR": {"type": "number"},
        "components": {
          "type": "object",
          "properties": {
            "bull": {"$ref": "#/definitions/ScenarioComponent"},
            "base": {"$ref": "#/definitions/ScenarioComponent"},
            "bear": {"$ref": "#/definitions/ScenarioComponent"}
          }
        },
        "formula": {"type": "string"},
        "dividend_yield": {"type": "number"},
        "buyback_yield": {"type": "number"}
      }
    },
    "margin_of_safety": {
      "type": "object",
      "required": ["current_discount_to_mid", "required", "gate_status"],
      "properties": {
        "current_discount_to_mid": {"type": "number"},
        "required": {"type": "number"},
        "gate_status": {"type": "string", "enum": ["PASS", "FAIL"]}
      }
    },
    "skew_ratio": {
      "type": "object",
      "required": ["E_TR", "bear_drawdown", "ratio", "required", "gate_status"],
      "properties": {
        "E_TR": {"type": "number"},
        "bear_drawdown": {"type": "number"},
        "ratio": {"type": "number"},
        "required": {"type": "number"},
        "gate_status": {"type": "string", "enum": ["PASS", "FAIL"]}
      }
    }
  },
  "definitions": {
    "ScenarioComponent": {
      "type": "object",
      "required": ["probability", "return", "price_target"],
      "properties": {
        "probability": {"type": "number", "minimum": 0, "maximum": 1},
        "return": {"type": "number"},
        "price_target": {"type": "number"}
      }
    }
  }
}
```

### 4. Risk Assessment Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "RiskAssessment",
  "type": "object",
  "required": ["ticker", "assessment_date", "bear_case", "downside_metrics", "catalyst_analysis", "stop_loss_trigger"],
  "properties": {
    "ticker": {"type": "string"},
    "assessment_date": {"type": "string", "format": "date"},
    "bear_case": {
      "type": "object",
      "required": ["scenario", "probability", "price_target", "return"],
      "properties": {
        "scenario": {"type": "string"},
        "probability": {"type": "number", "minimum": 0, "maximum": 1},
        "price_target": {"type": "number"},
        "return": {"type": "number"},
        "timeline": {"type": "string"},
        "key_assumptions": {"type": "array", "items": {"type": "string"}}
      }
    },
    "downside_metrics": {
      "type": "object",
      "required": ["bear_drawdown"],
      "properties": {
        "bear_drawdown": {"type": "number"},
        "expected_shortfall_5pct": {"type": "number"},
        "max_adverse_excursion": {"type": "number"},
        "recovery_time_estimate": {"type": "string"}
      }
    },
    "catalyst_analysis": {
      "type": "object",
      "required": ["nearest_catalyst", "catalyst_date", "within_horizon"],
      "properties": {
        "nearest_catalyst": {"type": "string"},
        "catalyst_date": {"type": "string", "format": "date"},
        "within_horizon": {"type": "boolean"}
      }
    },
    "stop_loss_trigger": {
      "type": "object",
      "required": ["price_level", "trigger_condition", "action_on_trigger"],
      "properties": {
        "price_level": {"type": "number"},
        "percentage_from_current": {"type": "number"},
        "trigger_condition": {"type": "string"},
        "action_on_trigger": {"type": "string"}
      }
    }
  }
}
```

### 5. Quality Scorecard Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "QualityScorecard",
  "type": "object",
  "required": ["ticker", "scorecard_date", "components", "total_score", "gate_status"],
  "properties": {
    "ticker": {"type": "string"},
    "scorecard_date": {"type": "string", "format": "date"},
    "components": {
      "type": "object",
      "required": ["market", "moat", "unit_economics", "execution", "financial_quality"],
      "properties": {
        "market": {"$ref": "#/definitions/ScoreComponent"},
        "moat": {"$ref": "#/definitions/ScoreComponent"},
        "unit_economics": {"$ref": "#/definitions/ScoreComponent"},
        "execution": {"$ref": "#/definitions/ScoreComponent"},
        "financial_quality": {"$ref": "#/definitions/ScoreComponent"}
      }
    },
    "total_score": {"type": "number", "minimum": 0, "maximum": 100},
    "gate_status": {
      "type": "object",
      "properties": {
        "quality_pass": {"type": "string", "enum": ["PASS", "FAIL"]},
        "sell_floor": {"type": "string", "enum": ["PASS", "FAIL"]}
      }
    }
  },
  "definitions": {
    "ScoreComponent": {
      "type": "object",
      "required": ["raw_score", "weight", "weighted_score", "evidence"],
      "properties": {
        "raw_score": {"type": "number", "minimum": 0, "maximum": 5},
        "weight": {"type": "number"},
        "weighted_score": {"type": "number"},
        "evidence": {"type": "string"}
      }
    }
  }
}
```

### 6. Rating Decision Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "RatingDecision",
  "type": "object",
  "required": ["ticker", "decision_date", "rating", "posture", "gate_results", "rationale"],
  "properties": {
    "ticker": {"type": "string"},
    "decision_date": {"type": "string", "format": "date"},
    "rating": {"type": "string", "enum": ["Buy", "Hold", "Wait-for-entry", "Sell"]},
    "posture": {"type": "string", "enum": ["Strong Buy", "Buy", "Watch", "Trim"]},
    "gate_results": {
      "type": "object",
      "properties": {
        "coverage_gate": {"$ref": "#/definitions/GateResult"},
        "expected_return_gate": {"$ref": "#/definitions/GateResult"},
        "skew_gate": {"$ref": "#/definitions/GateResult"},
        "margin_of_safety_gate": {"$ref": "#/definitions/GateResult"},
        "quality_gate": {"$ref": "#/definitions/GateResult"},
        "sell_floor_gate": {"$ref": "#/definitions/GateResult"},
        "why_now_gate": {"$ref": "#/definitions/GateResult"}
      }
    },
    "rationale": {"type": "string"},
    "catalyst_exemption_applied": {"type": "boolean"}
  },
  "definitions": {
    "GateResult": {
      "type": "object",
      "required": ["required", "actual", "status"],
      "properties": {
        "required": {"type": ["number", "string"]},
        "actual": {"type": ["number", "string"]},
        "status": {"type": "string", "enum": ["PASS", "FAIL"]}
      }
    }
  }
}
```

---

## HANDOFF PROTOCOL

### Standard Handoff Message

Every agent MUST return a handoff message in this format:

```json
{
  "agent": "[AGENT_NAME]",
  "status": "COMPLETE | IN_PROGRESS | FAILED",
  "timestamp": "ISO8601 timestamp",
  "outputs": {
    "file_name": "path/to/file.json"
  },
  "gate_results": {
    "gate_name": {"required": "X", "actual": "Y", "status": "PASS|FAIL"}
  },
  "errors": [],
  "warnings": [],
  "key_insight": "Single sentence summary of most important finding"
}
```

### Error Handling

If an agent encounters an error:

```json
{
  "agent": "QUANT_AGENT",
  "status": "FAILED",
  "timestamp": "2026-01-26T14:30:00Z",
  "outputs": {},
  "errors": [
    {
      "code": "MISSING_DATA",
      "message": "Could not find FY2025 10-K in coverage log",
      "severity": "CRITICAL",
      "recovery_action": "Request DATA_AGENT to gather additional filings"
    }
  ],
  "warnings": [],
  "key_insight": null
}
```

### Partial Completion

If an agent can partially complete:

```json
{
  "agent": "COMPETITIVE_AGENT",
  "status": "COMPLETE",
  "timestamp": "2026-01-26T14:30:00Z",
  "outputs": {
    "market_structure": "market_structure.json",
    "competitive_landscape": "competitive_landscape.json",
    "moat_assessment": "moat_assessment.json"
  },
  "errors": [],
  "warnings": [
    {
      "code": "INCOMPLETE_DATA",
      "message": "Ecosystem health analysis skipped - not applicable for this company",
      "severity": "LOW"
    }
  ],
  "key_insight": "Strong moat from switching costs; AI gap is emerging threat"
}
```

---

## VALIDATION RULES

### Orchestrator Validation

The Orchestrator MUST validate all incoming handoffs:

```python
def validate_handoff(handoff, expected_schema):
    # 1. Check required fields
    assert handoff['agent'] in VALID_AGENTS
    assert handoff['status'] in ['COMPLETE', 'IN_PROGRESS', 'FAILED']
    
    # 2. Validate outputs against schema
    for output_name, output_path in handoff['outputs'].items():
        data = load_json(output_path)
        validate(data, expected_schema[output_name])
    
    # 3. Check for blocking errors
    critical_errors = [e for e in handoff['errors'] if e['severity'] == 'CRITICAL']
    if critical_errors:
        raise BlockingError(critical_errors)
    
    return True
```

### Cross-Agent Consistency

The Orchestrator validates consistency across agent outputs:

```python
def validate_consistency(valuation_pkg, risk_assessment):
    # Bear case prices must match
    assert valuation_pkg['expected_total_return']['components']['bear']['price_target'] == \
           risk_assessment['bear_case']['price_target']
    
    # Drawdowns must match
    assert valuation_pkg['expected_total_return']['components']['bear']['return'] == \
           risk_assessment['downside_metrics']['bear_drawdown']
    
    # Probabilities must sum to 1
    probs = valuation_pkg['expected_total_return']['components']
    total_prob = probs['bull']['probability'] + probs['base']['probability'] + probs['bear']['probability']
    assert abs(total_prob - 1.0) < 0.001
```

---

## VERSIONING

All schemas follow semantic versioning:
- **Major**: Breaking changes to required fields
- **Minor**: New optional fields added
- **Patch**: Documentation or validation rule updates

Current version: **2.0.0**

Agents MUST include schema version in outputs:
```json
{
  "schema_version": "2.0.0",
  "ticker": "AAPL",
  ...
}
```
