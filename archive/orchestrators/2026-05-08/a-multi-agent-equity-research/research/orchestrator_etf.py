#!/usr/bin/env python3
"""
Multi-Agent ETF Research Orchestrator v6
=========================================

ETF-specific research with hierarchical verification.
Supports commodity ETFs, equity index ETFs, sector ETFs, etc.

Architecture:
    Phase 1: Data Collection
        ETF-DATA-AGENT → etf_corpus.json
    
    Phase 2: Analysis
        ETF-STRUCTURE-AGENT → structure.json
        FUNDAMENTALS-AGENT → fundamentals.json (commodity/sector specific)
        MACRO-AGENT → macro.json
        TECHNICAL-AGENT → technical.json
    
    Phase 3: Verification
        STRUCTURE-VERIFIER → verified_structure.json
        FUNDAMENTALS-VERIFIER → verified_fundamentals.json
        MACRO-VERIFIER → verified_macro.json
    
    Phase 4: Synthesis
        ETF-SYNTHESIS-AGENT → final_memo.md

Usage:
    python orchestrator_etf_v6.py SLV "iShares Silver Trust"
    python orchestrator_etf_v6.py XLE "Energy Select Sector SPDR"
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
from typing import Optional, Dict, List, Any
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

# Import ETF tools and asset classifier
from etf_tools import (
    get_etf_info, get_commodity_price, get_macro_data,
    get_gold_silver_ratio, get_etf_holdings
)
from asset_classifier import classify_asset, AssetType
from agent_tools import execute_tool

try:
    from config import RESEARCH_OUTPUT_PATH, get_anthropic_api_key
    CONFIG_AVAILABLE = True
except ImportError:
    CONFIG_AVAILABLE = False
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
    MAX_TOKENS_VERIFIER = 4000
    MAX_TOOL_CALLS = 12
    PROMPTS_DIR = str(Path(__file__).parent / "etf")
    OUTPUTS_DIR = str(RESEARCH_OUTPUT_PATH)
    
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
# ETF TOOL DEFINITIONS
# =============================================================================

ETF_TOOLS = [
    {
        "name": "get_etf_info",
        "description": "Get comprehensive ETF information: expense ratio, AUM, NAV, premium/discount, performance, beta",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "ETF ticker symbol"}
            },
            "required": ["ticker"]
        }
    },
    {
        "name": "get_commodity_price",
        "description": "Get commodity futures price. Supports: gold, silver, oil, natural_gas, copper, platinum, palladium",
        "input_schema": {
            "type": "object",
            "properties": {
                "commodity": {"type": "string", "description": "Commodity name (gold, silver, oil, etc.)"}
            },
            "required": ["commodity"]
        }
    },
    {
        "name": "get_macro_data",
        "description": "Get macro indicators: DXY (dollar index), VIX, Treasury yields (10Y, 30Y, 3M), yield curve",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "get_gold_silver_ratio",
        "description": "Get gold/silver ratio with historical context",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "get_etf_holdings",
        "description": "Get ETF holdings and sector weights (for equity ETFs)",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "ETF ticker symbol"}
            },
            "required": ["ticker"]
        }
    },
    {
        "name": "web_search",
        "description": "Search the web for recent news and information",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"}
            },
            "required": ["query"]
        }
    }
]


def execute_etf_tool(name: str, args: Dict) -> str:
    """Execute an ETF tool and return JSON result."""
    try:
        if name == "get_etf_info":
            result = get_etf_info(args.get("ticker", ""))
        elif name == "get_commodity_price":
            result = get_commodity_price(args.get("commodity", ""))
        elif name == "get_macro_data":
            result = get_macro_data()
        elif name == "get_gold_silver_ratio":
            result = get_gold_silver_ratio()
        elif name == "get_etf_holdings":
            result = get_etf_holdings(args.get("ticker", ""))
        elif name == "web_search":
            # Use the general web_search from agent_tools
            return execute_tool("web_search", args)
        else:
            result = {"status": "error", "error": f"Unknown tool: {name}"}
        
        return json.dumps(result, indent=2, default=str)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)})


# =============================================================================
# VERIFIER PROMPTS
# =============================================================================

VERIFIER_SYSTEM_PROMPT = """You are a VERIFICATION AGENT for ETF research.

Classify each claim into one of these categories:

1. VERIFIED: Claim matches data_corpus exactly (ETF info, prices, etc.)
   → Pass with source citation
   
2. DERIVED: Calculated from verified inputs (premium/discount, ratios)
   → Pass with calculation shown
   
3. OPINION: Analyst judgment, scenario, or market knowledge
   → Pass but label as opinion/analysis
   
4. CONTRADICTS: Claim conflicts with verified data
   → DROP and flag the contradiction
   
5. FABRICATED: Claims fake source, invented statistic, or false precision
   → DROP and explain why

Output format:
{
  "verified_claims": [...],      // VERIFIED + DERIVED + OPINION
  "dropped_claims": [...],       // CONTRADICTS + FABRICATED only
  "classification_stats": {...},
  "summary": "..."               // 500-800 words for synthesis
}"""


STRUCTURE_VERIFIER_PROMPT = """You are the ETF STRUCTURE VERIFIER.

VERIFIED (pass with source):
- Expense ratio, AUM, NAV from data_corpus
- Premium/discount to NAV
- Trading metrics (volume, bid-ask spread)
- 52-week high/low, moving averages

DERIVED (pass with calculation):
- Implied tracking cost
- Volume trends
- Relative valuations

OPINION (pass as labeled):
- Liquidity assessments
- Structure quality judgments
- ETF vs alternatives comparison

CONTRADICTS/FABRICATED (DROP):
- Expense ratios that don't match
- Made-up AUM figures
- Fake NAV data"""


FUNDAMENTALS_VERIFIER_PROMPT = """You are the FUNDAMENTALS VERIFIER.

For COMMODITY ETFs:
- Verify commodity prices against data_corpus
- Verify gold/silver ratio if applicable
- Allow industry knowledge (supply/demand dynamics)

For SECTOR/EQUITY ETFs:
- Verify holdings data if available
- Verify sector weights
- Allow sector analysis opinions

VERIFIED: Prices, ratios, holdings from corpus
DERIVED: Calculated exposures, relative values
OPINION: Supply/demand outlook, sector rotation
CONTRADICTS/FABRICATED: Wrong prices, fake holdings"""


MACRO_VERIFIER_PROMPT = """You are the MACRO VERIFIER.

VERIFIED (pass with source):
- DXY, VIX values from data_corpus
- Treasury yields (10Y, 30Y, 3M)
- Yield curve spread

DERIVED (pass with calculation):
- Real yield estimates
- Correlation implications
- Relative positioning

OPINION (pass as labeled):
- Fed policy outlook
- Inflation expectations
- Risk sentiment assessment
- Macro scenario analysis

CONTRADICTS/FABRICATED (DROP):
- Wrong macro values
- Fake correlation stats"""


SYNTHESIS_PROMPT_V6 = """You are the ETF SYNTHESIS AGENT.

You receive THREE verified summaries:
1. STRUCTURE-VERIFIER: ETF mechanics, costs, liquidity
2. FUNDAMENTALS-VERIFIER: Underlying asset analysis
3. MACRO-VERIFIER: Macro environment context

=== CRITICAL RULES ===

1. DO NOT HALLUCINATE: Only use information from the summaries.
   - If a number is in the summaries, use it
   - If NOT in summaries, do NOT invent it

2. NO EXTERNAL KNOWLEDGE: Stick to verified context.

3. LABEL OPINIONS: Make clear when something is opinion vs fact.

4. ETF-SPECIFIC FOCUS:
   - Expense ratio impact on returns
   - Premium/discount analysis
   - Liquidity considerations
   - Structure risks (if applicable)

=== OUTPUT FORMAT ===

Markdown memo with:
- YAML frontmatter (ticker, date, rating, etc.)
- Fund Description (use the description from verified data verbatim)
- Executive Summary
- ETF Structure Analysis
- Underlying Asset/Sector Analysis
- Macro Environment
- Risk Factors
- Recommendation

IMPORTANT: Include a "Fund Description" section right after the header that uses the fund description from the verified data. This describes what the fund invests in and its investment objective.

Be concise. Trust the verified inputs."""


# =============================================================================
# DATA STRUCTURES
# =============================================================================

class AgentStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass
class ToolCall:
    tool_name: str
    tool_input: Dict[str, Any]
    result: str
    timestamp: str
    tool_call_id: str = ""


@dataclass
class VerifiedData:
    """Verified ETF data - source of truth."""
    ticker: str
    fetched_at: str
    asset_type: str = ""
    # ETF info
    name: Optional[str] = None
    description: Optional[str] = None  # Fund/asset description
    expense_ratio: Optional[float] = None
    aum_billions: Optional[float] = None
    nav: Optional[float] = None
    price: Optional[float] = None
    premium_discount_pct: Optional[float] = None
    week_52_high: Optional[float] = None
    week_52_low: Optional[float] = None
    ytd_return_pct: Optional[float] = None
    # Commodity (if applicable)
    commodity_price: Optional[float] = None
    commodity_name: Optional[str] = None
    gold_silver_ratio: Optional[float] = None
    # Macro
    dxy: Optional[float] = None
    vix: Optional[float] = None
    treasury_10y: Optional[float] = None
    
    def to_constraint_block(self) -> str:
        lines = ["=" * 60, "VERIFIED ETF DATA - SOURCE OF TRUTH", "=" * 60, ""]
        
        lines.append(f"TICKER: {self.ticker}")
        lines.append(f"TYPE: {self.asset_type}")
        if self.name:
            lines.append(f"NAME: {self.name}")
        lines.append("")
        
        if self.description:
            lines.append("DESCRIPTION:")
            lines.append(f"  {self.description}")
            lines.append("")
        
        lines.append("ETF STRUCTURE:")
        if self.price is not None:
            lines.append(f"  PRICE = ${self.price:.2f}")
        if self.nav is not None:
            lines.append(f"  NAV = ${self.nav:.2f}")
        if self.premium_discount_pct is not None:
            lines.append(f"  PREMIUM/DISCOUNT = {self.premium_discount_pct:.2f}%")
        if self.expense_ratio is not None:
            lines.append(f"  EXPENSE_RATIO = {self.expense_ratio:.2f}%")
        if self.aum_billions is not None:
            lines.append(f"  AUM = ${self.aum_billions:.2f}B")
        if self.week_52_high is not None:
            lines.append(f"  52W_HIGH = ${self.week_52_high:.2f}")
        if self.week_52_low is not None:
            lines.append(f"  52W_LOW = ${self.week_52_low:.2f}")
        if self.ytd_return_pct is not None:
            lines.append(f"  YTD_RETURN = {self.ytd_return_pct:.2f}%")
        
        if self.commodity_price:
            lines.append("")
            lines.append("UNDERLYING COMMODITY:")
            lines.append(f"  {self.commodity_name} = ${self.commodity_price:.2f}")
            if self.gold_silver_ratio:
                lines.append(f"  GOLD/SILVER_RATIO = {self.gold_silver_ratio:.2f}")
        
        if self.dxy or self.vix or self.treasury_10y:
            lines.append("")
            lines.append("MACRO:")
            if self.dxy:
                lines.append(f"  DXY = {self.dxy:.2f}")
            if self.vix:
                lines.append(f"  VIX = {self.vix:.2f}")
            if self.treasury_10y:
                lines.append(f"  10Y_YIELD = {self.treasury_10y:.2f}%")
        
        lines.append("")
        lines.append("=" * 60)
        return "\n".join(lines)


@dataclass
class VerificationResult:
    agent: str
    verified_claims: List[Dict]
    dropped_claims: List[Dict]
    verification_stats: Dict
    summary: str
    raw_response: str


@dataclass
class AgentResult:
    agent: str
    status: AgentStatus
    response: str
    structured_output: Optional[Dict] = None
    tool_calls: List[ToolCall] = field(default_factory=list)
    duration_seconds: float = 0
    tokens_used: int = 0
    error: Optional[str] = None


@dataclass
class SessionContext:
    ticker: str
    etf_name: str
    asset_type: AssetType
    session_id: str
    output_dir: Path
    start_time: datetime
    agent_results: Dict[str, AgentResult] = field(default_factory=dict)
    verification_results: Dict[str, VerificationResult] = field(default_factory=dict)
    verified_data: Optional[VerifiedData] = None


# =============================================================================
# LOGGING
# =============================================================================

def log(message: str, style: str = "info"):
    timestamp = datetime.now().strftime("%H:%M:%S")
    if RICH_AVAILABLE:
        styles = {"info": "blue", "success": "green", "warning": "yellow",
                  "error": "red", "tool": "cyan", "verify": "bold cyan"}
        console.print(f"[dim]{timestamp}[/dim] [{styles.get(style, 'white')}]{message}[/]")
    else:
        print(f"{timestamp} [{style}] {message}")


def print_header(title: str):
    if RICH_AVAILABLE:
        console.print(Panel(title, style="bold magenta"))
    else:
        print(f"\n{'='*60}\n{title}\n{'='*60}")


# =============================================================================
# AGENT EXECUTOR
# =============================================================================

class ETFAgentExecutor:
    """Executes ETF research agents with verification."""
    
    def __init__(self, api_key: Optional[str] = None,
                 max_tool_calls: int = Config.MAX_TOOL_CALLS):
        self.api_key = api_key or Config.get_api_key()
        self.client = anthropic.Anthropic(api_key=self.api_key)
        self.prompts_dir = Path(Config.PROMPTS_DIR)
        self.max_tool_calls = max_tool_calls
        
        log("ETF Agent executor initialized (v6 verification)", "info")
    
    def load_prompt(self, agent_name: str) -> str:
        prompt_file = self.prompts_dir / f"{agent_name}.md"
        if prompt_file.exists():
            return prompt_file.read_text()
        return f"You are {agent_name}. Complete your analysis task."
    
    def execute_data_agent(self, context: SessionContext) -> AgentResult:
        """Execute ETF Data Agent with tools."""
        agent_name = "ETF-DATA-AGENT"
        log(f"Running {agent_name} (tool-enabled)...", "info")
        start_time = datetime.now()
        tool_calls = []
        total_tokens = 0
        
        try:
            system_prompt = self._build_data_agent_system_prompt(context)
            user_message = self._build_data_agent_message(context)
            messages = [{"role": "user", "content": user_message}]
            
            for i in range(self.max_tool_calls):
                response = self.client.messages.create(
                    model=Config.MODEL,
                    max_tokens=Config.MAX_TOKENS,
                    system=system_prompt,
                    tools=ETF_TOOLS,
                    messages=messages
                )
                
                total_tokens += response.usage.input_tokens + response.usage.output_tokens
                tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
                
                if not tool_use_blocks:
                    text_blocks = [b for b in response.content if b.type == "text"]
                    final_response = "\n".join(b.text for b in text_blocks)
                    break
                
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        log(f"  → Tool: {block.name}", "tool")
                        result = execute_etf_tool(block.name, block.input)
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
                log(f"  Hit max tool calls ({self.max_tool_calls})", "warning")
                final_response = '{"error": "Max tool calls reached"}'
            
            structured_output = self._extract_json(final_response)
            duration = (datetime.now() - start_time).total_seconds()
            
            log(f"  {agent_name} complete ({duration:.1f}s)", "success")
            
            return AgentResult(
                agent=agent_name,
                status=AgentStatus.COMPLETE,
                response=final_response,
                structured_output=structured_output,
                tool_calls=tool_calls,
                duration_seconds=duration,
                tokens_used=total_tokens
            )
            
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            log(f"  {agent_name} failed: {str(e)}", "error")
            return AgentResult(
                agent=agent_name,
                status=AgentStatus.FAILED,
                response="",
                tool_calls=tool_calls,
                duration_seconds=duration,
                error=str(e)
            )
    
    def execute_analysis_agent(self, agent_name: str, context: SessionContext,
                               data_context: str) -> AgentResult:
        """Execute an ETF analysis agent."""
        log(f"Running {agent_name} (grounded mode)...", "info")
        start_time = datetime.now()
        
        try:
            system_prompt = self._build_analysis_system_prompt(agent_name)
            user_message = self._build_analysis_message(agent_name, context, data_context)
            
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
            
            log(f"  {agent_name} complete ({duration:.1f}s)", "success")
            
            return AgentResult(
                agent=agent_name,
                status=AgentStatus.COMPLETE,
                response=raw_response,
                structured_output=structured_output,
                duration_seconds=duration,
                tokens_used=tokens
            )
            
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            log(f"  {agent_name} failed: {str(e)}", "error")
            return AgentResult(
                agent=agent_name,
                status=AgentStatus.FAILED,
                response="",
                duration_seconds=duration,
                error=str(e)
            )
    
    def execute_verifier(self, verifier_name: str, context: SessionContext,
                         input_agents: List[str]) -> VerificationResult:
        """Execute a verification agent."""
        log(f"Running {verifier_name} (verification mode)...", "verify")
        start_time = datetime.now()
        
        try:
            verifier_prompts = {
                "STRUCTURE-VERIFIER": STRUCTURE_VERIFIER_PROMPT,
                "FUNDAMENTALS-VERIFIER": FUNDAMENTALS_VERIFIER_PROMPT,
                "MACRO-VERIFIER": MACRO_VERIFIER_PROMPT,
            }
            
            system_prompt = VERIFIER_SYSTEM_PROMPT + "\n\n" + verifier_prompts.get(verifier_name, "")
            user_message = self._build_verifier_message(verifier_name, context, input_agents)
            
            response = self.client.messages.create(
                model=Config.MODEL,
                max_tokens=Config.MAX_TOKENS_VERIFIER,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}]
            )
            
            duration = (datetime.now() - start_time).total_seconds()
            raw_response = response.content[0].text
            parsed = self._extract_json(raw_response)
            
            if parsed:
                result = VerificationResult(
                    agent=verifier_name,
                    verified_claims=parsed.get("verified_claims", []),
                    dropped_claims=parsed.get("dropped_claims", []),
                    verification_stats=parsed.get("verification_stats", {}),
                    summary=parsed.get("summary", ""),
                    raw_response=raw_response
                )
            else:
                result = VerificationResult(
                    agent=verifier_name,
                    verified_claims=[],
                    dropped_claims=[],
                    verification_stats={"parse_error": True},
                    summary=raw_response[:2000],
                    raw_response=raw_response
                )
            
            verified = len(result.verified_claims)
            dropped = len(result.dropped_claims)
            log(f"  {verifier_name} complete: {verified} verified, {dropped} dropped ({duration:.1f}s)", "success")
            
            return result
            
        except Exception as e:
            log(f"  {verifier_name} failed: {str(e)}", "error")
            return VerificationResult(
                agent=verifier_name,
                verified_claims=[],
                dropped_claims=[],
                verification_stats={"error": str(e)},
                summary=f"Verification failed: {str(e)}",
                raw_response=""
            )
    
    def execute_synthesis(self, context: SessionContext) -> AgentResult:
        """Execute final synthesis."""
        agent_name = "ETF-SYNTHESIS-AGENT"
        log(f"Running {agent_name} (verified inputs only)...", "info")
        start_time = datetime.now()
        
        try:
            synthesis_input = self._build_synthesis_message(context)
            base_prompt = self.load_prompt("05-ETF-SYNTHESIS-AGENT")
            system_prompt = base_prompt + "\n\n" + SYNTHESIS_PROMPT_V6
            
            response = self.client.messages.create(
                model=Config.MODEL,
                max_tokens=Config.MAX_TOKENS,
                system=system_prompt,
                messages=[{"role": "user", "content": synthesis_input}]
            )
            
            duration = (datetime.now() - start_time).total_seconds()
            tokens = response.usage.input_tokens + response.usage.output_tokens
            raw_response = response.content[0].text
            
            log(f"  {agent_name} complete ({duration:.1f}s)", "success")
            
            return AgentResult(
                agent=agent_name,
                status=AgentStatus.COMPLETE,
                response=raw_response,
                duration_seconds=duration,
                tokens_used=tokens
            )
            
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            log(f"  {agent_name} failed: {str(e)}", "error")
            return AgentResult(
                agent=agent_name,
                status=AgentStatus.FAILED,
                response="",
                duration_seconds=duration,
                error=str(e)
            )
    
    # === Builder methods ===
    
    def _build_data_agent_system_prompt(self, context: SessionContext) -> str:
        asset_type = context.asset_type.value
        return f"""You are an ETF DATA COLLECTION AGENT.

This is a {asset_type} ETF. Gather all relevant data using your tools.

RULES:
1. Use ALL relevant tools. Do NOT make up numbers.
2. If a tool fails, report null - NEVER guess.
3. Return valid JSON with all data gathered.

Return ONLY a JSON object with the data."""
    
    def _build_data_agent_message(self, context: SessionContext) -> str:
        tools_to_use = ["get_etf_info"]
        
        # Add asset-type specific tools
        if context.asset_type in [AssetType.ETF_COMMODITY, AssetType.ETF_COMMODITY_FUTURES]:
            tools_to_use.extend(["get_commodity_price", "get_gold_silver_ratio"])
        elif context.asset_type in [AssetType.ETF_EQUITY_SECTOR, AssetType.ETF_EQUITY_INDEX]:
            tools_to_use.append("get_etf_holdings")
        
        tools_to_use.extend(["get_macro_data", "web_search"])
        
        return f"""# ETF Data Collection: {context.ticker}

**ETF Name**: {context.etf_name}
**Asset Type**: {context.asset_type.value}
**Timestamp**: {datetime.now().isoformat()}

## Required Tools:
{chr(10).join(f'{i+1}. {t}' for i, t in enumerate(tools_to_use))}

For web_search, search for: "{context.etf_name} {context.ticker} outlook {datetime.now().strftime('%B %Y')}"

Return JSON with all gathered data."""
    
    def _build_analysis_system_prompt(self, agent_name: str) -> str:
        base_prompt = self.load_prompt(agent_name)
        return base_prompt + """

=== ANTI-HALLUCINATION RULES ===
1. Use ONLY verified data provided. Do NOT invent numbers.
2. If data is missing, say "Data not available" - NEVER guess.
3. Return structured JSON for validation.
================================"""
    
    def _build_analysis_message(self, agent_name: str, context: SessionContext,
                                data_context: str) -> str:
        verified_block = context.verified_data.to_constraint_block() if context.verified_data else ""
        
        return f"""# ETF Analysis Task: {agent_name}

**Ticker**: {context.ticker}
**ETF Name**: {context.etf_name}
**Asset Type**: {context.asset_type.value}

{verified_block}

## Data from Data Agent:
```json
{data_context}
```

Complete your analysis. Return structured JSON."""
    
    def _build_verifier_message(self, verifier_name: str, context: SessionContext,
                                input_agents: List[str]) -> str:
        # Get data corpus
        data_corpus = "{}"
        if "ETF-DATA-AGENT" in context.agent_results:
            dar = context.agent_results["ETF-DATA-AGENT"]
            if dar.structured_output:
                data_corpus = json.dumps(dar.structured_output, indent=2)
            else:
                data_corpus = dar.response
        
        # Get analysis outputs
        analysis_outputs = []
        for agent_name in input_agents:
            if agent_name in context.agent_results:
                result = context.agent_results[agent_name]
                if result.structured_output:
                    analysis_outputs.append(
                        f"## {agent_name}\n```json\n{json.dumps(result.structured_output, indent=2)}\n```"
                    )
                else:
                    analysis_outputs.append(
                        f"## {agent_name}\n{result.response[:4000]}"
                    )
        
        return f"""# Verification Task: {verifier_name}

**Ticker**: {context.ticker}
**ETF**: {context.etf_name}

## DATA CORPUS (Source of Truth)
```json
{data_corpus}
```

## ANALYSIS OUTPUT (To Be Verified)
{chr(10).join(analysis_outputs)}

## Instructions
Verify each claim. Output JSON with verified_claims, dropped_claims, and summary."""
    
    def _build_synthesis_message(self, context: SessionContext) -> str:
        parts = [
            f"# ETF Research Synthesis: {context.ticker} ({context.etf_name})",
            f"\n**Date**: {datetime.now().strftime('%Y-%m-%d')}",
            f"**Asset Type**: {context.asset_type.value}",
            "\n## Verified Summaries\n"
        ]
        
        for verifier_name in ["STRUCTURE-VERIFIER", "FUNDAMENTALS-VERIFIER", "MACRO-VERIFIER"]:
            if verifier_name in context.verification_results:
                vr = context.verification_results[verifier_name]
                verified = len(vr.verified_claims)
                dropped = len(vr.dropped_claims)
                parts.append(f"\n### {verifier_name}")
                parts.append(f"*{verified} verified, {dropped} dropped*\n")
                parts.append(vr.summary)
        
        if context.verified_data:
            parts.append("\n---\n## Verified Data Reference")
            parts.append(context.verified_data.to_constraint_block())
        
        return "\n".join(parts)
    
    def _extract_json(self, text: str) -> Optional[Dict]:
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
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

class ETFResearchOrchestratorV6:
    """ETF Research Orchestrator with hierarchical verification."""
    
    def __init__(self, api_key: Optional[str] = None,
                 max_tool_calls: int = Config.MAX_TOOL_CALLS):
        self.executor = ETFAgentExecutor(api_key, max_tool_calls)
    
    def run(self, ticker: str, etf_name: str,
            output_dir: Optional[str] = None,
            parallel_verify: bool = True) -> SessionContext:
        
        # Classify asset type
        asset_info = classify_asset(ticker)
        asset_type = asset_info.asset_type
        
        print_header(f"ETF Research v6: {ticker} ({etf_name})")
        log(f"Asset type: {asset_type.value}", "info")
        log("Hierarchical verification mode", "info")
        
        session_id = f"{ticker}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        output_path = Path(output_dir or Config.OUTPUTS_DIR) / session_id
        output_path.mkdir(parents=True, exist_ok=True)
        
        context = SessionContext(
            ticker=ticker,
            etf_name=etf_name,
            asset_type=asset_type,
            session_id=session_id,
            output_dir=output_path,
            start_time=datetime.now()
        )
        
        log(f"Session ID: {session_id}", "info")
        log(f"Output: {output_path}", "info")
        
        # Pre-fetch verified data
        context.verified_data = self._fetch_verified_data(ticker, asset_type)
        
        # Phase 1: Data Collection
        print_header("Phase 1: Data Collection")
        data_result = self.executor.execute_data_agent(context)
        context.agent_results["ETF-DATA-AGENT"] = data_result
        self._save_result(context, "etf_corpus.json", data_result)
        
        data_context = ""
        if data_result.structured_output:
            data_context = json.dumps(data_result.structured_output, indent=2)
        else:
            data_context = data_result.response
        
        # Phase 2: Analysis
        print_header("Phase 2: Analysis")
        
        # Select agents based on asset type
        analysis_agents = self._get_analysis_agents(asset_type)
        
        for agent_name in analysis_agents:
            result = self.executor.execute_analysis_agent(agent_name, context, data_context)
            context.agent_results[agent_name] = result
            
            output_name = agent_name.lower().replace("-", "_") + ".json"
            self._save_result(context, output_name, result)
        
        # Phase 3: Verification
        print_header("Phase 3: Verification")
        
        verifier_mapping = {
            "STRUCTURE-VERIFIER": ["01-ETF-STRUCTURE-AGENT"],
            "FUNDAMENTALS-VERIFIER": ["02-COMMODITY-FUNDAMENTALS-AGENT"] if "COMMODITY" in asset_type.value.upper() 
                                     else ["02-COMMODITY-FUNDAMENTALS-AGENT"],
            "MACRO-VERIFIER": ["03-MACRO-AGENT", "04-TECHNICAL-AGENT"],
        }
        
        if parallel_verify:
            with ThreadPoolExecutor(max_workers=3) as executor:
                futures = {}
                for vname, inputs in verifier_mapping.items():
                    # Only verify agents that ran
                    valid_inputs = [a for a in inputs if a in context.agent_results]
                    if valid_inputs:
                        futures[executor.submit(
                            self.executor.execute_verifier, vname, context, valid_inputs
                        )] = vname
                
                for future in as_completed(futures):
                    vname = futures[future]
                    try:
                        result = future.result()
                        context.verification_results[vname] = result
                        self._save_verification(context, vname, result)
                    except Exception as e:
                        log(f"  {vname} failed: {e}", "error")
        else:
            for vname, inputs in verifier_mapping.items():
                valid_inputs = [a for a in inputs if a in context.agent_results]
                if valid_inputs:
                    result = self.executor.execute_verifier(vname, context, valid_inputs)
                    context.verification_results[vname] = result
                    self._save_verification(context, vname, result)
        
        # Phase 4: Synthesis
        print_header("Phase 4: Synthesis")
        synthesis_result = self.executor.execute_synthesis(context)
        context.agent_results["ETF-SYNTHESIS-AGENT"] = synthesis_result
        self._save_result(context, "final_memo.md", synthesis_result, is_markdown=True)
        
        # Summary
        self._print_summary(context)
        
        return context
    
    def _get_analysis_agents(self, asset_type: AssetType) -> List[str]:
        """Get analysis agents based on asset type."""
        agents = ["01-ETF-STRUCTURE-AGENT"]
        
        if asset_type in [AssetType.ETF_COMMODITY, AssetType.ETF_COMMODITY_FUTURES]:
            agents.append("02-COMMODITY-FUNDAMENTALS-AGENT")
        else:
            agents.append("02-COMMODITY-FUNDAMENTALS-AGENT")  # Use as generic fundamentals
        
        agents.extend(["03-MACRO-AGENT", "04-TECHNICAL-AGENT"])
        return agents
    
    def _fetch_verified_data(self, ticker: str, asset_type: AssetType) -> VerifiedData:
        """Fetch verified ETF data."""
        log("Fetching verified data...", "info")
        
        verified = VerifiedData(
            ticker=ticker,
            fetched_at=datetime.now().isoformat(),
            asset_type=asset_type.value
        )
        
        try:
            # ETF info
            etf_result = get_etf_info(ticker)
            if etf_result.get("status") == "success":
                data = etf_result["data"]
                verified.name = data.get("name")
                verified.description = data.get("description")
                verified.expense_ratio = data.get("expense_ratio_pct")
                verified.aum_billions = data.get("aum_billions")
                verified.nav = data.get("nav")
                verified.price = data.get("price")
                verified.premium_discount_pct = data.get("premium_discount_pct")
                verified.week_52_high = data.get("52w_high")
                verified.week_52_low = data.get("52w_low")
                verified.ytd_return_pct = data.get("ytd_return_pct")
                
                if verified.price:
                    log(f"  Verified Price: ${verified.price:.2f}", "success")
            
            # Commodity prices for commodity ETFs
            if asset_type in [AssetType.ETF_COMMODITY, AssetType.ETF_COMMODITY_FUTURES]:
                # Determine commodity
                commodity_map = {
                    "SLV": "silver", "GLD": "gold", "IAU": "gold",
                    "USO": "oil", "UNG": "natural_gas"
                }
                commodity = commodity_map.get(ticker.upper())
                if commodity:
                    comm_result = get_commodity_price(commodity)
                    if comm_result.get("status") == "success":
                        verified.commodity_name = commodity
                        verified.commodity_price = comm_result["data"].get("price")
                        log(f"  Verified {commodity}: ${verified.commodity_price:.2f}", "success")
                
                # Gold/silver ratio
                if ticker.upper() in ["SLV", "GLD", "IAU"]:
                    ratio_result = get_gold_silver_ratio()
                    if ratio_result.get("status") == "success":
                        verified.gold_silver_ratio = ratio_result["data"].get("current_ratio")
            
            # Macro data
            macro_result = get_macro_data()
            if macro_result.get("status") == "success":
                data = macro_result["data"]
                verified.dxy = data.get("dxy", {}).get("value")
                verified.vix = data.get("vix", {}).get("value")
                verified.treasury_10y = data.get("tnx", {}).get("value")
                
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
                "tokens_used": result.tokens_used
            }
            filepath.write_text(json.dumps(data, indent=2))
        log(f"Saved: {filename}", "info")
    
    def _save_verification(self, context: SessionContext, verifier_name: str,
                           result: VerificationResult):
        filename = f"verified_{verifier_name.lower().replace('-', '_')}.json"
        filepath = context.output_dir / filename
        data = {
            "agent": result.agent,
            "timestamp": datetime.now().isoformat(),
            "verified_claims": result.verified_claims,
            "dropped_claims": result.dropped_claims,
            "verification_stats": result.verification_stats,
            "summary": result.summary
        }
        filepath.write_text(json.dumps(data, indent=2))
        log(f"Saved: {filename}", "info")
    
    def _print_summary(self, context: SessionContext):
        print_header("Session Summary")
        
        total_duration = (datetime.now() - context.start_time).total_seconds() / 60
        total_tokens = sum(r.tokens_used for r in context.agent_results.values())
        
        total_verified = sum(len(vr.verified_claims) for vr in context.verification_results.values())
        total_dropped = sum(len(vr.dropped_claims) for vr in context.verification_results.values())
        
        log(f"Session: {context.session_id}", "info")
        log(f"Asset Type: {context.asset_type.value}", "info")
        log(f"Duration: {total_duration:.1f} min", "info")
        log(f"Total tokens: {total_tokens:,}", "info")
        log(f"Claims verified: {total_verified}", "verify")
        log(f"Claims dropped: {total_dropped}", "verify")
        
        if total_verified + total_dropped > 0:
            rate = total_verified / (total_verified + total_dropped) * 100
            log(f"Verification rate: {rate:.1f}%", "verify")
        
        log(f"\n Output: {context.output_dir / 'final_memo.md'}", "success")


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="ETF Research Orchestrator v6 (Hierarchical Verification)"
    )
    parser.add_argument("ticker", help="ETF ticker symbol")
    parser.add_argument("etf_name", help="ETF name")
    parser.add_argument("--output-dir", "-o", help="Output directory")
    parser.add_argument("--no-parallel", action="store_true",
                        help="Run verifiers sequentially")
    parser.add_argument("--api-key", "-k")
    
    args = parser.parse_args()
    
    api_key = args.api_key or os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY not set.")
        sys.exit(1)
    
    try:
        orchestrator = ETFResearchOrchestratorV6(api_key=api_key)
        orchestrator.run(
            ticker=args.ticker.upper(),
            etf_name=args.etf_name,
            output_dir=args.output_dir,
            parallel_verify=not args.no_parallel
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
