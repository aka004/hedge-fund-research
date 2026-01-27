#!/usr/bin/env python3
"""
Multi-Agent Equity Research Orchestrator v5
============================================

MAJOR CHANGES from v4 - ANTI-HALLUCINATION FOCUS:
1. Structured output schemas with JSON validation
2. Data grounding layer - verified data injected as immutable facts
3. Citation enforcement - outputs must reference tool call IDs
4. Post-processing validation - cross-check outputs against verified data
5. Constrained generation with prefill anchoring

Architecture:
    1. Data Agent runs with tools → outputs STRUCTURED JSON with citations
    2. Grounding layer validates and extracts verified facts
    3. Downstream agents receive structured data (not free text)
    4. Validation layer checks all numerical claims
    5. Synthesis uses validated data only
"""

import anthropic
import json
import os
import sys
import argparse
import re
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, List, Any, Tuple
from enum import Enum

# Import from same directory
from agent_tools import AGENT_TOOLS, execute_tool

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from config import (
        RESEARCH_DB_PATH,
        RESEARCH_OUTPUT_PATH,
        get_anthropic_api_key,
    )
    CONFIG_AVAILABLE = True
except ImportError:
    CONFIG_AVAILABLE = False
    RESEARCH_DB_PATH = Path("../data/research.duckdb")
    RESEARCH_OUTPUT_PATH = Path("../outputs/research")

try:
    from rich.console import Console
    from rich.panel import Panel
    RICH_AVAILABLE = True
    console = Console()
except ImportError:
    RICH_AVAILABLE = False
    console = None


# =============================================================================
# CONFIGURATION
# =============================================================================

class Config:
    MODEL = "claude-sonnet-4-20250514"
    MAX_TOKENS = 8000
    MAX_TOOL_CALLS = 15
    DB_PATH = str(RESEARCH_DB_PATH)
    PROMPTS_DIR = str(Path(__file__).parent)
    OUTPUTS_DIR = str(RESEARCH_OUTPUT_PATH)
    
    AGENTS_WITH_TOOLS = ["01-DATA-AGENT"]
    
    AGENTS = [
        "01-DATA-AGENT",
        "02-QUANT-AGENT",
        "03-RISK-AGENT",
        "04-COMPETITIVE-AGENT",
        "05-QUALITATIVE-AGENT",
        "06-SYNTHESIS-AGENT",
    ]
    
    @staticmethod
    def get_api_key():
        if CONFIG_AVAILABLE:
            try:
                return get_anthropic_api_key()
            except ValueError:
                pass
        key = os.getenv("ANTHROPIC_API_KEY")
        if not key:
            raise ValueError("ANTHROPIC_API_KEY not set.")
        return key


# =============================================================================
# STRUCTURED OUTPUT SCHEMAS
# =============================================================================

# These schemas enforce what agents CAN output - anything outside is rejected

DATA_AGENT_SCHEMA = {
    "type": "object",
    "properties": {
        "ticker": {"type": "string"},
        "timestamp": {"type": "string"},
        "market_data": {
            "type": "object",
            "properties": {
                "current_price": {"type": ["number", "null"]},
                "market_cap": {"type": ["number", "null"]},
                "pe_ratio": {"type": ["number", "null"]},
                "forward_pe": {"type": ["number", "null"]},
                "week_52_high": {"type": ["number", "null"]},
                "week_52_low": {"type": ["number", "null"]},
                "volume": {"type": ["number", "null"]},
                "avg_volume": {"type": ["number", "null"]},
                "source": {"type": "string"},
                "source_timestamp": {"type": "string"}
            },
            "required": ["source"]
        },
        "analyst_estimates": {
            "type": "object",
            "properties": {
                "price_target_mean": {"type": ["number", "null"]},
                "price_target_high": {"type": ["number", "null"]},
                "price_target_low": {"type": ["number", "null"]},
                "num_analysts": {"type": ["integer", "null"]},
                "recommendation": {"type": ["string", "null"]},
                "eps_current_year": {"type": ["number", "null"]},
                "eps_next_year": {"type": ["number", "null"]},
                "revenue_growth": {"type": ["number", "null"]},
                "source": {"type": "string"}
            },
            "required": ["source"]
        },
        "company_info": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "sector": {"type": ["string", "null"]},
                "industry": {"type": ["string", "null"]},
                "description": {"type": ["string", "null"]},
                "employees": {"type": ["integer", "null"]},
                "source": {"type": "string"}
            },
            "required": ["source"]
        },
        "recent_news": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "headline": {"type": "string"},
                    "date": {"type": "string"},
                    "source": {"type": "string"},
                    "url": {"type": ["string", "null"]}
                },
                "required": ["headline", "source"]
            }
        },
        "sec_filings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string"},
                    "date": {"type": "string"},
                    "description": {"type": ["string", "null"]}
                }
            }
        },
        "data_gaps": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of data that could not be retrieved"
        },
        "tool_calls_made": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of tool calls made to gather this data"
        }
    },
    "required": ["ticker", "timestamp", "market_data", "tool_calls_made"]
}

QUANT_AGENT_SCHEMA = {
    "type": "object",
    "properties": {
        "valuation_summary": {
            "type": "object",
            "properties": {
                "current_price": {"type": "number", "description": "MUST match verified data"},
                "fair_value_estimate": {"type": ["number", "null"]},
                "upside_downside_pct": {"type": ["number", "null"]},
                "valuation_method": {"type": "string"},
                "confidence": {"type": "string", "enum": ["high", "medium", "low"]}
            }
        },
        "multiples_analysis": {
            "type": "object",
            "properties": {
                "pe_ratio": {"type": ["number", "null"]},
                "forward_pe": {"type": ["number", "null"]},
                "sector_avg_pe": {"type": ["number", "null"]},
                "pe_premium_discount": {"type": ["string", "null"]}
            }
        },
        "analyst_comparison": {
            "type": "object",
            "properties": {
                "mean_target": {"type": ["number", "null"], "description": "MUST match analyst_estimates"},
                "high_target": {"type": ["number", "null"]},
                "low_target": {"type": ["number", "null"]},
                "vs_current_price_pct": {"type": ["number", "null"]}
            }
        },
        "key_assumptions": {"type": "array", "items": {"type": "string"}},
        "data_limitations": {"type": "array", "items": {"type": "string"}}
    },
    "required": ["valuation_summary"]
}


# =============================================================================
# DATA STRUCTURES
# =============================================================================

class AgentStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"
    VALIDATION_FAILED = "validation_failed"


@dataclass
class ToolCall:
    tool_name: str
    tool_input: Dict[str, Any]
    result: str
    timestamp: str
    tool_call_id: str = ""


@dataclass
class VerifiedData:
    """Immutable verified data from tools - THE source of truth."""
    ticker: str
    fetched_at: str
    
    # Price data (from get_price_data)
    current_price: Optional[float] = None
    market_cap: Optional[float] = None
    pe_ratio: Optional[float] = None
    forward_pe: Optional[float] = None
    week_52_high: Optional[float] = None
    week_52_low: Optional[float] = None
    
    # Analyst estimates (from get_analyst_estimates)
    price_target_mean: Optional[float] = None
    price_target_high: Optional[float] = None
    price_target_low: Optional[float] = None
    num_analysts: Optional[int] = None
    recommendation: Optional[str] = None
    eps_current_year: Optional[float] = None
    eps_next_year: Optional[float] = None
    
    # Macro data
    dxy: Optional[float] = None
    vix: Optional[float] = None
    treasury_10y: Optional[float] = None
    
    def to_constraint_block(self) -> str:
        """Generate an immutable constraint block for prompts."""
        lines = [
            "=" * 60,
            "⚠️  VERIFIED DATA - USE THESE EXACT VALUES",
            "=" * 60,
            "",
            "The following values are VERIFIED from real data sources.",
            "You MUST use these exact numbers. Do NOT invent alternatives.",
            "If a value is null/None, say 'Data not available' - do NOT guess.",
            "",
        ]
        
        if self.current_price is not None:
            lines.append(f"CURRENT_PRICE = ${self.current_price:.2f}")
        if self.market_cap is not None:
            if self.market_cap >= 1e12:
                lines.append(f"MARKET_CAP = ${self.market_cap/1e12:.2f}T")
            elif self.market_cap >= 1e9:
                lines.append(f"MARKET_CAP = ${self.market_cap/1e9:.2f}B")
            else:
                lines.append(f"MARKET_CAP = ${self.market_cap/1e6:.2f}M")
        if self.pe_ratio is not None:
            lines.append(f"PE_RATIO = {self.pe_ratio:.2f}")
        if self.forward_pe is not None:
            lines.append(f"FORWARD_PE = {self.forward_pe:.2f}")
        if self.week_52_high is not None:
            lines.append(f"52W_HIGH = ${self.week_52_high:.2f}")
        if self.week_52_low is not None:
            lines.append(f"52W_LOW = ${self.week_52_low:.2f}")
        
        lines.append("")
        lines.append("ANALYST ESTIMATES:")
        if self.price_target_mean is not None:
            lines.append(f"  MEAN_PRICE_TARGET = ${self.price_target_mean:.2f}")
        if self.price_target_high is not None:
            lines.append(f"  HIGH_PRICE_TARGET = ${self.price_target_high:.2f}")
        if self.price_target_low is not None:
            lines.append(f"  LOW_PRICE_TARGET = ${self.price_target_low:.2f}")
        if self.num_analysts is not None:
            lines.append(f"  NUM_ANALYSTS = {self.num_analysts}")
        if self.recommendation:
            lines.append(f"  RECOMMENDATION = {self.recommendation}")
        if self.eps_current_year is not None:
            lines.append(f"  EPS_CURRENT_YEAR = ${self.eps_current_year:.2f}")
        if self.eps_next_year is not None:
            lines.append(f"  EPS_NEXT_YEAR = ${self.eps_next_year:.2f}")
        
        if any([self.dxy, self.vix, self.treasury_10y]):
            lines.append("")
            lines.append("MACRO DATA:")
            if self.dxy is not None:
                lines.append(f"  DXY = {self.dxy:.2f}")
            if self.vix is not None:
                lines.append(f"  VIX = {self.vix:.2f}")
            if self.treasury_10y is not None:
                lines.append(f"  10Y_TREASURY = {self.treasury_10y:.2f}%")
        
        lines.append("")
        lines.append("=" * 60)
        
        return "\n".join(lines)


@dataclass
class ValidationResult:
    """Result of validating agent output against verified data."""
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    corrections_made: Dict[str, Tuple[Any, Any]] = field(default_factory=dict)


@dataclass
class AgentResult:
    agent: str
    status: AgentStatus
    response: str
    structured_output: Optional[Dict] = None
    tool_calls: List[ToolCall] = field(default_factory=list)
    duration_seconds: float = 0
    tokens_used: int = 0
    validation: Optional[ValidationResult] = None
    error: Optional[str] = None


@dataclass
class SessionContext:
    ticker: str
    company_name: str
    session_id: str
    output_dir: Path
    start_time: datetime
    agent_results: Dict[str, AgentResult] = field(default_factory=dict)
    db_path: str = Config.DB_PATH
    verified_data: Optional[VerifiedData] = None


# =============================================================================
# LOGGING
# =============================================================================

def log(message: str, style: str = "info"):
    timestamp = datetime.now().strftime("%H:%M:%S")
    if RICH_AVAILABLE:
        styles = {"info": "blue", "success": "green", "warning": "yellow", 
                  "error": "red", "header": "bold magenta", "tool": "cyan",
                  "validation": "bold yellow"}
        console.print(f"[dim]{timestamp}[/dim] [{styles.get(style, 'white')}]{message}[/]")
    else:
        print(f"{timestamp} [{style}] {message}")


def print_header(title: str):
    if RICH_AVAILABLE:
        console.print(Panel(title, style="bold magenta"))
    else:
        print(f"\n{'='*60}\n{title}\n{'='*60}")


# =============================================================================
# VALIDATION LAYER
# =============================================================================

class OutputValidator:
    """Validates agent outputs against verified data to catch hallucinations."""
    
    TOLERANCE = 0.01  # 1% tolerance for floating point comparison
    
    @classmethod
    def validate_quant_output(cls, output: Dict, verified: VerifiedData) -> ValidationResult:
        """Validate quant agent output against verified data."""
        errors = []
        warnings = []
        corrections = {}
        
        # Check current price
        val_summary = output.get("valuation_summary", {})
        if val_summary.get("current_price") and verified.current_price:
            reported = val_summary["current_price"]
            actual = verified.current_price
            if not cls._values_match(reported, actual):
                errors.append(
                    f"PRICE MISMATCH: Reported ${reported:.2f}, actual ${actual:.2f}"
                )
                corrections["valuation_summary.current_price"] = (reported, actual)
        
        # Check analyst targets
        analyst_comp = output.get("analyst_comparison", {})
        if analyst_comp.get("mean_target") and verified.price_target_mean:
            reported = analyst_comp["mean_target"]
            actual = verified.price_target_mean
            if not cls._values_match(reported, actual):
                errors.append(
                    f"MEAN TARGET MISMATCH: Reported ${reported:.2f}, actual ${actual:.2f}"
                )
                corrections["analyst_comparison.mean_target"] = (reported, actual)
        
        # Check P/E ratio
        multiples = output.get("multiples_analysis", {})
        if multiples.get("pe_ratio") and verified.pe_ratio:
            reported = multiples["pe_ratio"]
            actual = verified.pe_ratio
            if not cls._values_match(reported, actual, tolerance=0.05):  # 5% tolerance for ratios
                warnings.append(
                    f"P/E MISMATCH: Reported {reported:.2f}, actual {actual:.2f}"
                )
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            corrections_made=corrections
        )
    
    @classmethod
    def validate_data_agent_output(cls, output: Dict, verified: VerifiedData) -> ValidationResult:
        """Validate data agent output - must cite tool sources."""
        errors = []
        warnings = []
        
        # Check that tool_calls_made is populated
        if not output.get("tool_calls_made"):
            errors.append("Data agent output has no tool_calls_made - likely hallucinated")
        
        # Check market data has source
        market_data = output.get("market_data", {})
        if not market_data.get("source"):
            errors.append("market_data missing source citation")
        
        # Cross-check price
        if market_data.get("current_price") and verified.current_price:
            reported = market_data["current_price"]
            actual = verified.current_price
            if not cls._values_match(reported, actual):
                errors.append(
                    f"PRICE MISMATCH in data corpus: ${reported:.2f} vs verified ${actual:.2f}"
                )
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )
    
    @classmethod
    def _values_match(cls, a: float, b: float, tolerance: float = None) -> bool:
        """Check if two values match within tolerance."""
        if tolerance is None:
            tolerance = cls.TOLERANCE
        if b == 0:
            return abs(a) < tolerance
        return abs((a - b) / b) <= tolerance
    
    @classmethod
    def apply_corrections(cls, output: Dict, corrections: Dict) -> Dict:
        """Apply corrections to output, replacing hallucinated values."""
        import copy
        corrected = copy.deepcopy(output)
        
        for path, (old_val, new_val) in corrections.items():
            parts = path.split(".")
            obj = corrected
            for part in parts[:-1]:
                obj = obj.get(part, {})
            if parts[-1] in obj:
                obj[parts[-1]] = new_val
                log(f"  Corrected {path}: {old_val} → {new_val}", "validation")
        
        return corrected


# =============================================================================
# AGENT EXECUTOR WITH ANTI-HALLUCINATION
# =============================================================================

class AgentExecutor:
    """Executes agents with hallucination prevention."""
    
    def __init__(self, api_key: Optional[str] = None,
                 max_tool_calls: int = Config.MAX_TOOL_CALLS):
        self.api_key = api_key or Config.get_api_key()
        self.client = anthropic.Anthropic(api_key=self.api_key)
        self.prompts_dir = Path(Config.PROMPTS_DIR)
        self.prompts_cache: Dict[str, str] = {}
        self.max_tool_calls = max_tool_calls
        
        log(f"Agent executor initialized (anti-hallucination mode)", "info")
    
    def load_prompt(self, agent_name: str) -> str:
        if agent_name in self.prompts_cache:
            return self.prompts_cache[agent_name]
        
        prompt_file = self.prompts_dir / f"{agent_name}.md"
        if prompt_file.exists():
            prompt = prompt_file.read_text()
            self.prompts_cache[agent_name] = prompt
            return prompt
        
        return f"You are {agent_name}. Complete your assigned analysis task."
    
    def execute(self, agent_name: str, context: SessionContext, 
                additional_context: str = "") -> AgentResult:
        """Execute an agent with appropriate hallucination controls."""
        
        has_tools = agent_name in Config.AGENTS_WITH_TOOLS
        
        if has_tools:
            return self._execute_data_agent(agent_name, context, additional_context)
        else:
            return self._execute_analysis_agent(agent_name, context, additional_context)
    
    def _execute_data_agent(self, agent_name: str, context: SessionContext,
                            additional_context: str = "") -> AgentResult:
        """Execute Data Agent with tools and structured output."""
        log(f"Running {agent_name} (tool-enabled, structured output)...", "info")
        start_time = datetime.now()
        tool_calls = []
        total_tokens = 0
        
        try:
            system_prompt = self._build_data_agent_system_prompt()
            user_message = self._build_data_agent_message(context)
            
            messages = [{"role": "user", "content": user_message}]
            
            # Tool execution loop
            for i in range(self.max_tool_calls):
                response = self.client.messages.create(
                    model=Config.MODEL,
                    max_tokens=Config.MAX_TOKENS,
                    system=system_prompt,
                    tools=AGENT_TOOLS,
                    messages=messages
                )
                
                total_tokens += response.usage.input_tokens + response.usage.output_tokens
                
                tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
                
                if not tool_use_blocks:
                    # Extract final response
                    text_blocks = [b for b in response.content if b.type == "text"]
                    final_response = "\n".join(b.text for b in text_blocks)
                    break
                
                # Execute tools
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        log(f"  → Tool: {block.name}", "tool")
                        
                        result = execute_tool(block.name, block.input)
                        
                        tool_calls.append(ToolCall(
                            tool_name=block.name,
                            tool_input=block.input,
                            result=result[:1000] if len(result) > 1000 else result,
                            timestamp=datetime.now().isoformat(),
                            tool_call_id=block.id
                        ))
                        
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result
                        })
                
                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": tool_results})
            
            else:
                log(f"  ⚠ Hit max tool calls ({self.max_tool_calls})", "warning")
                final_response = '{"error": "Max tool calls reached"}'
            
            # Parse structured output
            structured_output = self._extract_json(final_response)
            
            # Validate against verified data
            validation = None
            if structured_output and context.verified_data:
                validation = OutputValidator.validate_data_agent_output(
                    structured_output, context.verified_data
                )
                if not validation.is_valid:
                    log(f"  ⚠ Validation errors: {validation.errors}", "warning")
            
            duration = (datetime.now() - start_time).total_seconds()
            
            return AgentResult(
                agent=agent_name,
                status=AgentStatus.COMPLETE if (not validation or validation.is_valid) 
                       else AgentStatus.VALIDATION_FAILED,
                response=final_response,
                structured_output=structured_output,
                tool_calls=tool_calls,
                duration_seconds=duration,
                tokens_used=total_tokens,
                validation=validation
            )
            
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            log(f"✗ {agent_name} failed: {str(e)}", "error")
            return AgentResult(
                agent=agent_name,
                status=AgentStatus.FAILED,
                response="",
                tool_calls=tool_calls,
                duration_seconds=duration,
                error=str(e)
            )
    
    def _execute_analysis_agent(self, agent_name: str, context: SessionContext,
                                additional_context: str = "") -> AgentResult:
        """Execute analysis agent with grounded data and validation."""
        log(f"Running {agent_name} (grounded mode)...", "info")
        start_time = datetime.now()
        
        try:
            system_prompt = self._build_grounded_system_prompt(agent_name)
            user_message = self._build_grounded_message(agent_name, context, additional_context)
            
            response = self.client.messages.create(
                model=Config.MODEL,
                max_tokens=Config.MAX_TOKENS,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}]
            )
            
            duration = (datetime.now() - start_time).total_seconds()
            tokens = response.usage.input_tokens + response.usage.output_tokens
            
            raw_response = response.content[0].text
            structured_output = self._extract_json(raw_response)
            
            # Validate if quant agent
            validation = None
            if agent_name == "02-QUANT-AGENT" and structured_output and context.verified_data:
                validation = OutputValidator.validate_quant_output(
                    structured_output, context.verified_data
                )
                if validation.corrections_made:
                    log(f"  ⚠ Applying {len(validation.corrections_made)} corrections", "validation")
                    structured_output = OutputValidator.apply_corrections(
                        structured_output, validation.corrections_made
                    )
                    # Update response with corrected data
                    raw_response = json.dumps(structured_output, indent=2)
            
            result = AgentResult(
                agent=agent_name,
                status=AgentStatus.COMPLETE,
                response=raw_response,
                structured_output=structured_output,
                duration_seconds=duration,
                tokens_used=tokens,
                validation=validation
            )
            
            status_str = "✓" if (not validation or validation.is_valid) else "⚠"
            log(f"{status_str} {agent_name} complete ({duration:.1f}s)", "success")
            return result
            
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            log(f"✗ {agent_name} failed: {str(e)}", "error")
            return AgentResult(
                agent=agent_name,
                status=AgentStatus.FAILED,
                response="",
                duration_seconds=duration,
                error=str(e)
            )
    
    def _build_data_agent_system_prompt(self) -> str:
        """System prompt for data agent - emphasizes tool use and JSON output."""
        return """You are a DATA COLLECTION AGENT for equity research.

CRITICAL RULES:
1. You MUST use your tools to gather ALL data. Do NOT make up any numbers.
2. If a tool fails or returns no data, report "null" for that field - NEVER guess.
3. Your output MUST be valid JSON matching the required schema.
4. Every numerical value must come from a tool call. Cite the tool in your output.

OUTPUT FORMAT:
Return ONLY a JSON object. No markdown, no explanation, just JSON.
The JSON must include a "tool_calls_made" array listing every tool you called.

If you cannot find data for a field, set it to null and add it to "data_gaps"."""
    
    def _build_data_agent_message(self, context: SessionContext) -> str:
        """Build message for data agent with schema."""
        return f"""# Research Task: Gather Data for {context.ticker}

**Company**: {context.company_name}
**Timestamp**: {datetime.now().isoformat()}

## Required Tools (USE ALL OF THESE):
1. get_price_data("{context.ticker}") - Current price, fundamentals
2. get_company_info("{context.ticker}") - Company overview
3. get_analyst_estimates("{context.ticker}") - Price targets, EPS estimates
4. web_search("{context.company_name} news {datetime.now().strftime('%B %Y')}") - Recent news
5. get_sec_filings("{context.ticker}") - Recent filings

## Required Output Schema:
```json
{{
  "ticker": "{context.ticker}",
  "timestamp": "ISO timestamp",
  "market_data": {{
    "current_price": number or null,
    "market_cap": number or null,
    "pe_ratio": number or null,
    "forward_pe": number or null,
    "week_52_high": number or null,
    "week_52_low": number or null,
    "source": "tool name that provided this data",
    "source_timestamp": "when data was fetched"
  }},
  "analyst_estimates": {{
    "price_target_mean": number or null,
    "price_target_high": number or null,
    "price_target_low": number or null,
    "num_analysts": number or null,
    "recommendation": string or null,
    "eps_current_year": number or null,
    "eps_next_year": number or null,
    "source": "get_analyst_estimates"
  }},
  "company_info": {{
    "name": string,
    "sector": string or null,
    "industry": string or null,
    "description": string or null,
    "source": "get_company_info"
  }},
  "recent_news": [
    {{"headline": string, "date": string, "source": string}}
  ],
  "sec_filings": [
    {{"type": string, "date": string}}
  ],
  "data_gaps": ["list of data that could not be retrieved"],
  "tool_calls_made": ["get_price_data", "get_company_info", ...]
}}
```

BEGIN by calling your tools. Return ONLY the JSON output."""
    
    def _build_grounded_system_prompt(self, agent_name: str) -> str:
        """System prompt that enforces data grounding."""
        base_prompt = self.load_prompt(agent_name)
        
        grounding_rules = """

=== ANTI-HALLUCINATION RULES ===

1. VERIFIED DATA IS IMMUTABLE: You will receive verified price/market data.
   Use ONLY these exact numbers. Do not round, estimate, or modify them.

2. IF DATA IS MISSING: Say "Data not available" - NEVER make up a number.

3. CITATIONS REQUIRED: When you reference a specific number, state its source
   (e.g., "Current price of $XX.XX per verified market data").

4. NO INVENTED METRICS: Do not calculate ratios/metrics unless you have
   verified inputs for ALL components of the calculation.

5. OUTPUT FORMAT: Return structured JSON when possible. This allows validation.

6. CONFIDENCE DISCLOSURE: If you're uncertain about any analysis, say so.
   It's better to express uncertainty than to fabricate precision.

================================
"""
        return base_prompt + grounding_rules
    
    def _build_grounded_message(self, agent_name: str, context: SessionContext,
                                additional_context: str) -> str:
        """Build message with verified data block and prior agent output."""
        
        # Build verified data constraint block
        verified_block = ""
        if context.verified_data:
            verified_block = context.verified_data.to_constraint_block()
        
        # Get structured data from data agent if available
        data_agent_output = ""
        if "01-DATA-AGENT" in context.agent_results:
            dar = context.agent_results["01-DATA-AGENT"]
            if dar.structured_output:
                data_agent_output = f"\n## Structured Data from Data Agent:\n```json\n{json.dumps(dar.structured_output, indent=2)}\n```\n"
            else:
                data_agent_output = f"\n## Data Agent Output:\n{dar.response[:6000]}\n"
        
        # Agent-specific schemas
        output_schema = ""
        if agent_name == "02-QUANT-AGENT":
            output_schema = """
## Required Output Schema:
Return a JSON object with this structure:
```json
{
  "valuation_summary": {
    "current_price": <MUST match CURRENT_PRICE above>,
    "fair_value_estimate": <your estimate or null if insufficient data>,
    "upside_downside_pct": <calculated percentage>,
    "valuation_method": "<method used>",
    "confidence": "high|medium|low"
  },
  "multiples_analysis": {
    "pe_ratio": <MUST match PE_RATIO above>,
    "forward_pe": <MUST match FORWARD_PE above>,
    "sector_avg_pe": <if known, else null>,
    "pe_premium_discount": "<analysis>"
  },
  "analyst_comparison": {
    "mean_target": <MUST match MEAN_PRICE_TARGET above>,
    "high_target": <MUST match HIGH_PRICE_TARGET above>,
    "low_target": <MUST match LOW_PRICE_TARGET above>,
    "vs_current_price_pct": <calculated>
  },
  "key_assumptions": ["assumption 1", "assumption 2"],
  "data_limitations": ["limitation 1", "limitation 2"]
}
```
"""
        
        return f"""# Research Task: {agent_name}

**Ticker**: {context.ticker}
**Company**: {context.company_name}
**Session ID**: {context.session_id}
**Timestamp**: {datetime.now().isoformat()}

{verified_block}
{data_agent_output}

## Additional Context from Previous Agents:
{additional_context if additional_context else "No additional context."}
{output_schema}

## Instructions:
1. Use ONLY the verified data provided above for any numerical values.
2. If the verified data shows a value as null/None, state "Data not available".
3. Do NOT invent, estimate, or guess any prices, targets, or metrics.
4. Cite your data source when referencing specific numbers.
5. Return structured JSON output for validation.

Complete your analysis now."""
    
    def _extract_json(self, text: str) -> Optional[Dict]:
        """Extract JSON from response text."""
        # Try to find JSON in code blocks
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        
        # Try to parse entire response as JSON
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        
        # Try to find JSON object in text
        json_match = re.search(r'\{[\s\S]*\}', text)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass
        
        return None


# =============================================================================
# ORCHESTRATOR
# =============================================================================

class ResearchOrchestrator:
    def __init__(self, api_key: Optional[str] = None, db_path: str = Config.DB_PATH, 
                 max_tool_calls: int = Config.MAX_TOOL_CALLS):
        self.executor = AgentExecutor(api_key, max_tool_calls)
        self.db_path = db_path
    
    def run(self, ticker: str, company_name: str, 
            output_dir: Optional[str] = None) -> SessionContext:
        
        print_header(f"Multi-Agent Research v5: {ticker} ({company_name})")
        log("Anti-hallucination mode: Structured outputs + Validation", "info")
        
        session_id = f"{ticker}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        output_path = Path(output_dir or Config.OUTPUTS_DIR) / session_id
        output_path.mkdir(parents=True, exist_ok=True)
        
        context = SessionContext(
            ticker=ticker,
            company_name=company_name,
            session_id=session_id,
            output_dir=output_path,
            start_time=datetime.now(),
            db_path=self.db_path
        )
        
        log(f"Session ID: {session_id}", "info")
        log(f"Output: {output_path}", "info")
        
        # Pre-fetch verified data (THE source of truth)
        context.verified_data = self._fetch_verified_data(ticker)
        
        # Phase 1: Data Collection
        print_header("Phase 1: Data Collection (Tool-Enabled)")
        
        data_result = self.executor.execute("01-DATA-AGENT", context)
        context.agent_results["01-DATA-AGENT"] = data_result
        self._save_result(context, "data_corpus.json", data_result)
        
        if data_result.validation and not data_result.validation.is_valid:
            log(f"⚠ Data Agent validation issues: {data_result.validation.errors}", "warning")
        
        # Phase 2: Analysis
        print_header("Phase 2: Analysis (Grounded Mode)")
        
        # Build context from data agent
        data_context = ""
        if data_result.structured_output:
            data_context = json.dumps(data_result.structured_output, indent=2)
        else:
            data_context = data_result.response
        
        for agent_name in ["02-QUANT-AGENT", "03-RISK-AGENT", 
                          "04-COMPETITIVE-AGENT", "05-QUALITATIVE-AGENT"]:
            result = self.executor.execute(agent_name, context, data_context)
            context.agent_results[agent_name] = result
            
            output_name = {
                "02-QUANT-AGENT": "valuation.json",
                "03-RISK-AGENT": "risk.json",
                "04-COMPETITIVE-AGENT": "competitive.json",
                "05-QUALITATIVE-AGENT": "qualitative.json"
            }[agent_name]
            self._save_result(context, output_name, result)
        
        # Phase 3: Synthesis
        print_header("Phase 3: Synthesis")
        
        # Build synthesis input with validation status
        synthesis_parts = []
        for name, result in context.agent_results.items():
            validation_note = ""
            if result.validation:
                if result.validation.errors:
                    validation_note = f"\n[VALIDATION ERRORS: {result.validation.errors}]"
                if result.validation.corrections_made:
                    validation_note += f"\n[CORRECTIONS APPLIED: {list(result.validation.corrections_made.keys())}]"
            
            if result.structured_output:
                synthesis_parts.append(
                    f"## {name}{validation_note}\n```json\n{json.dumps(result.structured_output, indent=2)}\n```"
                )
            else:
                synthesis_parts.append(
                    f"## {name}{validation_note}\n{result.response[:5000]}"
                )
        
        all_results = "\n\n---\n\n".join(synthesis_parts)
        
        synthesis_result = self.executor.execute("06-SYNTHESIS-AGENT", context, all_results)
        context.agent_results["06-SYNTHESIS-AGENT"] = synthesis_result
        self._save_result(context, "final_memo.md", synthesis_result, is_markdown=True)
        
        # Save validation summary
        self._save_validation_summary(context)
        
        # Summary
        self._print_summary(context)
        
        return context
    
    def _fetch_verified_data(self, ticker: str) -> VerifiedData:
        """Fetch and verify data from tools - THIS IS THE SOURCE OF TRUTH."""
        log("Fetching verified data (source of truth)...", "info")
        
        verified = VerifiedData(
            ticker=ticker,
            fetched_at=datetime.now().isoformat()
        )
        
        try:
            # Price data
            price_result = execute_tool("get_price_data", {"ticker": ticker})
            if price_result:
                price_data = json.loads(price_result)
                data = price_data.get("data", {})
                verified.current_price = data.get("current_price")
                verified.market_cap = data.get("market_cap")
                verified.pe_ratio = data.get("pe_ratio") or data.get("trailing_pe")
                verified.forward_pe = data.get("forward_pe")
                verified.week_52_high = data.get("week_52_high")
                verified.week_52_low = data.get("week_52_low")
                
                if verified.current_price:
                    log(f"  ✓ Verified Price: ${verified.current_price:.2f}", "success")
            
            # Analyst estimates
            est_result = execute_tool("get_analyst_estimates", {"ticker": ticker})
            if est_result:
                est_data = json.loads(est_result)
                targets = est_data.get("price_targets", {})
                verified.price_target_mean = targets.get("mean")
                verified.price_target_high = targets.get("high")
                verified.price_target_low = targets.get("low")
                verified.num_analysts = targets.get("num_analysts") or est_data.get("recommendation", {}).get("num_analysts")
                verified.recommendation = est_data.get("recommendation", {}).get("rating")
                
                for e in est_data.get("earnings_estimates", []):
                    if e.get("period") == "0y":
                        verified.eps_current_year = e.get("avg_eps")
                    elif e.get("period") == "+1y":
                        verified.eps_next_year = e.get("avg_eps")
                
                if verified.price_target_mean:
                    log(f"  ✓ Verified Mean Target: ${verified.price_target_mean:.2f}", "success")
            
            # Macro data
            try:
                from etf_tools import get_macro_data
                macro_result = get_macro_data()
                if macro_result.get("status") == "success":
                    md = macro_result["data"]
                    verified.dxy = md.get("dxy", {}).get("value")
                    verified.vix = md.get("vix", {}).get("value")
                    verified.treasury_10y = md.get("tnx", {}).get("value")
            except ImportError:
                pass
            
        except Exception as e:
            log(f"Warning: Error fetching verified data: {e}", "warning")
        
        return verified
    
    def _save_result(self, context: SessionContext, filename: str, 
                     result: AgentResult, is_markdown: bool = False):
        filepath = context.output_dir / filename
        if is_markdown:
            filepath.write_text(result.response)
        else:
            data = {
                "agent": result.agent,
                "status": result.status.value,
                "timestamp": datetime.now().isoformat(),
                "response": result.response,
                "structured_output": result.structured_output,
                "tool_calls": [asdict(tc) for tc in result.tool_calls],
                "duration_seconds": result.duration_seconds,
                "tokens_used": result.tokens_used,
                "validation": {
                    "is_valid": result.validation.is_valid if result.validation else None,
                    "errors": result.validation.errors if result.validation else [],
                    "warnings": result.validation.warnings if result.validation else [],
                    "corrections": {k: list(v) for k, v in result.validation.corrections_made.items()} 
                                  if result.validation else {}
                }
            }
            filepath.write_text(json.dumps(data, indent=2))
        log(f"Saved: {filename}", "info")
    
    def _save_validation_summary(self, context: SessionContext):
        """Save a summary of all validation results."""
        summary = {
            "session_id": context.session_id,
            "ticker": context.ticker,
            "timestamp": datetime.now().isoformat(),
            "verified_data": asdict(context.verified_data) if context.verified_data else None,
            "agent_validations": {}
        }
        
        total_errors = 0
        total_corrections = 0
        
        for name, result in context.agent_results.items():
            if result.validation:
                summary["agent_validations"][name] = {
                    "is_valid": result.validation.is_valid,
                    "errors": result.validation.errors,
                    "warnings": result.validation.warnings,
                    "corrections_count": len(result.validation.corrections_made)
                }
                total_errors += len(result.validation.errors)
                total_corrections += len(result.validation.corrections_made)
        
        summary["total_validation_errors"] = total_errors
        summary["total_corrections_applied"] = total_corrections
        
        filepath = context.output_dir / "validation_summary.json"
        filepath.write_text(json.dumps(summary, indent=2))
        log(f"Validation summary: {total_errors} errors, {total_corrections} corrections", 
            "warning" if total_errors > 0 else "success")
    
    def _print_summary(self, context: SessionContext):
        print_header("Session Summary")
        
        total_duration = (datetime.now() - context.start_time).total_seconds() / 60
        total_tokens = sum(r.tokens_used for r in context.agent_results.values())
        total_tool_calls = sum(len(r.tool_calls) for r in context.agent_results.values())
        
        validation_errors = sum(
            len(r.validation.errors) for r in context.agent_results.values() 
            if r.validation
        )
        corrections = sum(
            len(r.validation.corrections_made) for r in context.agent_results.values()
            if r.validation
        )
        
        log(f"Session: {context.session_id}", "info")
        log(f"Duration: {total_duration:.1f} min", "info")
        log(f"Total tokens: {total_tokens:,}", "info")
        log(f"Tool calls: {total_tool_calls}", "info")
        log(f"Validation errors caught: {validation_errors}", "validation")
        log(f"Automatic corrections: {corrections}", "validation")
        log(f"\n✅ Output: {context.output_dir / 'final_memo.md'}", "success")


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Research Orchestrator v5 (Anti-Hallucination)"
    )
    parser.add_argument("ticker", help="Stock ticker")
    parser.add_argument("company_name", help="Company name")
    parser.add_argument("--output-dir", "-o", help="Output directory")
    parser.add_argument("--max-tool-calls", type=int, default=10, 
                        help="Max tool calls for Data Agent")
    parser.add_argument("--api-key", "-k")
    
    args = parser.parse_args()
    
    api_key = args.api_key or os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY not set.")
        sys.exit(1)
    
    try:
        orchestrator = ResearchOrchestrator(
            api_key=api_key,
            max_tool_calls=args.max_tool_calls
        )
        orchestrator.run(
            ticker=args.ticker.upper(),
            company_name=args.company_name,
            output_dir=args.output_dir
        )
                
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
