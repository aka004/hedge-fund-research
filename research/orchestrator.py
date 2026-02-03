#!/usr/bin/env python3
"""
Multi-Agent Equity Research Orchestrator v6
============================================

MAJOR CHANGES from v5 - HIERARCHICAL VERIFICATION:
1. Verification layer between analysis and synthesis
2. Each verifier cross-references claims against data_corpus (source of truth)
3. Unverified claims are DROPPED before synthesis
4. 90% context reduction for final synthesis
5. Parallel execution possible for verifiers

Architecture:
    Phase 1: Data Collection
        01-DATA-AGENT → data_corpus.json (source of truth)
    
    Phase 2: Analysis (unchanged)
        02-QUANT-AGENT → valuation.json
        03-RISK-AGENT → risk.json  
        04-COMPETITIVE-AGENT → competitive.json
        05-QUALITATIVE-AGENT → qualitative.json
    
    Phase 3: Verification (NEW)
        QUANT-VERIFIER: valuation.json + data_corpus → verified_quant.json
        RISK-VERIFIER: risk.json + data_corpus → verified_risk.json
        MOAT-VERIFIER: competitive + qualitative + data_corpus → verified_moat.json
    
    Phase 4: Synthesis
        06-SYNTHESIS-AGENT: 3 verified summaries (~4KB) → final_memo.md
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
from concurrent.futures import ThreadPoolExecutor, as_completed

# Import from same directory
from agent_tools import AGENT_TOOLS, execute_tool

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / ".env"
    load_dotenv(env_path, override=True)  # Override shell env vars with .env
except ImportError:
    # python-dotenv not installed, rely on system environment variables
    pass

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
    MODEL = "claude-sonnet-4-5-20250929"  # Sonnet 4.5 (September 2025) - matches Clawdbot
    MAX_TOKENS = 8000
    MAX_TOKENS_VERIFIER = 4000  # Smaller for verification agents
    MAX_TOKENS_SYNTHESIS = 8000
    MAX_TOOL_CALLS = 15
    DB_PATH = str(RESEARCH_DB_PATH)
    PROMPTS_DIR = str(Path(__file__).parent)
    OUTPUTS_DIR = str(RESEARCH_OUTPUT_PATH)
    
    AGENTS_WITH_TOOLS = ["01-DATA-AGENT"]
    
    # Analysis agents (Phase 2)
    ANALYSIS_AGENTS = [
        "02-QUANT-AGENT",
        "03-RISK-AGENT",
        "04-COMPETITIVE-AGENT",
        "05-QUALITATIVE-AGENT",
    ]
    
    # Verification agents (Phase 3)
    VERIFIER_AGENTS = [
        "QUANT-VERIFIER",
        "RISK-VERIFIER", 
        "MOAT-VERIFIER",
    ]
    
    # Mapping: verifier -> which analysis outputs it checks
    VERIFIER_INPUTS = {
        "QUANT-VERIFIER": ["02-QUANT-AGENT"],
        "RISK-VERIFIER": ["03-RISK-AGENT"],
        "MOAT-VERIFIER": ["04-COMPETITIVE-AGENT", "05-QUALITATIVE-AGENT"],
    }
    
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
# VERIFIER PROMPTS
# =============================================================================

VERIFIER_SYSTEM_PROMPT = """You are a VERIFICATION AGENT for equity research.

YOUR PURPOSE: Classify claims from analysis agents and catch errors/hallucinations.

You receive TWO inputs:
- DATA_CORPUS: The verified source of truth (from tools)
- ANALYSIS_OUTPUT: Claims from an analysis agent

CLASSIFY each claim into one of these categories:

1. VERIFIED: Claim matches data_corpus exactly
   → Pass with source citation
   
2. DERIVED: Calculated from verified inputs (e.g., shares = mcap/price)
   → Pass with calculation shown
   
3. OPINION: Analyst judgment, scenario, or industry knowledge
   → Pass but label as opinion/analysis
   
4. CONTRADICTS: Claim conflicts with verified data
   → DROP and flag the contradiction
   
5. FABRICATED: Claims fake source, invented statistic, or false precision
   → DROP and explain why

IMPORTANT:
- Do NOT drop legitimate analysis work (scenarios, calculations, opinions)
- DO drop anything that contradicts verified data or cites fake sources
- Your job is catching ERRORS, not filtering out analysis

Output format:
{
  "verified_claims": [...],      // VERIFIED + DERIVED + OPINION
  "dropped_claims": [...],       // CONTRADICTS + FABRICATED only
  "classification_stats": {...},
  "summary": "..."               // 500-800 words for synthesis
}

Your summary should include verified facts, valid derivations, and labeled opinions."""


QUANT_VERIFIER_PROMPT = """You are the QUANT VERIFIER. You classify valuation and quantitative claims.

VERIFIED (pass with source):
- Price, market cap, P/E ratios that match data_corpus exactly
- Analyst targets and recommendations from data_corpus

DERIVED (pass with calculation):
- Shares outstanding = market cap / price
- Implied growth rates from EPS estimates
- Upside/downside percentages from price vs targets

OPINION (pass as labeled opinion):
- Fair value estimates and DCF outputs
- Bull/base/bear scenarios with probability weights
- Expected return calculations
- Margin of safety assessments

CONTRADICTS (DROP):
- Price that doesn't match verified price
- P/E ratio that conflicts with data_corpus
- Analyst targets that don't match

FABRICATED (DROP):
- Made-up revenue/earnings not in data
- Fake peer comparisons
- Invented industry metrics

Output JSON with verified_claims (all passing), dropped_claims (contradicts/fabricated only), and summary."""


RISK_VERIFIER_PROMPT = """You are the RISK VERIFIER. You classify risk assessment claims.

VERIFIED (pass with source):
- 52-week high/low from data_corpus
- Current price, analyst targets
- Beta, volatility metrics if in data

DERIVED (pass with calculation):
- Drawdown from current to bear target
- Upside/downside ratios
- Stop loss levels based on % from current

OPINION (pass as labeled analysis):
- Bear case scenarios and probabilities
- Risk factor assessments
- Catalyst impact estimates
- Recovery time projections

CONTRADICTS (DROP):
- Price levels that don't match data_corpus
- 52-week range that conflicts with verified

FABRICATED (DROP):
- Made-up historical drawdown stats not derivable from data
- Fake volatility metrics
- Invented catalyst dates not in news

Output JSON with verified_claims, dropped_claims, and summary."""


MOAT_VERIFIER_PROMPT = """You are the MOAT VERIFIER. You classify competitive and qualitative claims.

VERIFIED (pass with source):
- Company sector/industry from data_corpus
- News headlines and dates from data_corpus
- SEC filing types and dates

DERIVED (pass as industry knowledge):
- Well-known market positions (e.g., ASML's EUV monopoly is common knowledge)
- Industry structure (oligopoly, fragmented, etc.)
- General TAM/SAM estimates from reputable sources

OPINION (pass as labeled analysis):
- Moat strength assessments
- Management quality judgments
- Competitive advantage durability
- Customer switching cost estimates

CONTRADICTS (DROP):
- Sector/industry that doesn't match data_corpus
- News dates that conflict with verified

FABRICATED (DROP):
- Made-up market share with false precision (e.g., "exactly 73.2%")
- Invented customer names not in data
- Fake financial metrics

Note: Industry common knowledge (like "ASML is the only EUV supplier") is 
acceptable even if not in data_corpus - it's verifiable public information.

Output JSON with verified_claims, dropped_claims, and summary."""


SYNTHESIS_PROMPT_V6 = """You are the SYNTHESIS AGENT for the v6 research system.

You receive THREE verified summaries from verification agents:
1. QUANT-VERIFIER: Valuation analysis (verified + derived + opinions)
2. RISK-VERIFIER: Risk assessment (verified + derived + opinions)
3. MOAT-VERIFIER: Competitive analysis (verified + derived + opinions)

=== CRITICAL RULES ===

1. DO NOT HALLUCINATE: Only use information from the summaries provided.
   - If a number is in the summaries, use it
   - If a number is NOT in the summaries, do NOT invent it
   - Do NOT make up statistics, percentages, or metrics

2. NO EXTERNAL KNOWLEDGE: Do not add facts from your training data.
   - Stick to what's in the verified context
   - If something seems missing, note it as a data gap

3. LABEL OPINIONS: When including analyst opinions/scenarios, make clear
   they are opinions, not verified facts.

4. NO TOOLS NEEDED: You have everything you need in the context.
   Just write the memo from the provided summaries.

=== OUTPUT FORMAT ===

Write a well-structured markdown investment memo with:
- YAML frontmatter (ticker, date, rating, price_target, current_price, tags)
- Company Description (FIRST - use the description from VERIFIED DATA verbatim)
- Executive Summary
- Investment Thesis  
- Valuation Analysis
- Risk Assessment
- Competitive Position
- Recommendation
- Data Gaps (if any)

IMPORTANT: Always include a "Company Description" section at the start that uses the company description from the verified data. This describes what the company does.

Be concise. Quality over quantity. Trust the verified inputs."""


# =============================================================================
# DATA STRUCTURES (inherited from v5)
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
    # Company info
    name: Optional[str] = None
    description: Optional[str] = None  # Company/asset description
    sector: Optional[str] = None
    industry: Optional[str] = None
    # Price data
    current_price: Optional[float] = None
    market_cap: Optional[float] = None
    pe_ratio: Optional[float] = None
    forward_pe: Optional[float] = None
    week_52_high: Optional[float] = None
    week_52_low: Optional[float] = None
    price_target_mean: Optional[float] = None
    price_target_high: Optional[float] = None
    price_target_low: Optional[float] = None
    num_analysts: Optional[int] = None
    recommendation: Optional[str] = None
    eps_current_year: Optional[float] = None
    eps_next_year: Optional[float] = None
    dxy: Optional[float] = None
    vix: Optional[float] = None
    treasury_10y: Optional[float] = None
    
    def to_constraint_block(self) -> str:
        """Generate constraint block for prompts."""
        lines = ["=" * 60, "VERIFIED DATA - SOURCE OF TRUTH", "=" * 60, ""]
        
        lines.append(f"TICKER: {self.ticker}")
        if self.name:
            lines.append(f"NAME: {self.name}")
        if self.sector:
            lines.append(f"SECTOR: {self.sector}")
        if self.industry:
            lines.append(f"INDUSTRY: {self.industry}")
        lines.append("")
        
        if self.description:
            lines.append("COMPANY DESCRIPTION:")
            lines.append(f"  {self.description}")
            lines.append("")
        
        if self.current_price is not None:
            lines.append(f"CURRENT_PRICE = ${self.current_price:.2f}")
        if self.market_cap is not None:
            mc_str = f"${self.market_cap/1e12:.2f}T" if self.market_cap >= 1e12 else f"${self.market_cap/1e9:.2f}B"
            lines.append(f"MARKET_CAP = {mc_str}")
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
            lines.append(f"  MEAN_TARGET = ${self.price_target_mean:.2f}")
        if self.price_target_high is not None:
            lines.append(f"  HIGH_TARGET = ${self.price_target_high:.2f}")
        if self.price_target_low is not None:
            lines.append(f"  LOW_TARGET = ${self.price_target_low:.2f}")
        if self.num_analysts is not None:
            lines.append(f"  NUM_ANALYSTS = {self.num_analysts}")
        if self.recommendation:
            lines.append(f"  RECOMMENDATION = {self.recommendation}")
        
        lines.append("")
        lines.append("=" * 60)
        return "\n".join(lines)


@dataclass
class VerificationResult:
    """Result from a verification agent."""
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
    company_name: str
    session_id: str
    output_dir: Path
    start_time: datetime
    agent_results: Dict[str, AgentResult] = field(default_factory=dict)
    verification_results: Dict[str, VerificationResult] = field(default_factory=dict)
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
                  "verify": "bold cyan"}
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

class AgentExecutor:
    """Executes agents with anti-hallucination controls."""
    
    def __init__(self, api_key: Optional[str] = None,
                 max_tool_calls: int = Config.MAX_TOOL_CALLS):
        self.api_key = api_key or Config.get_api_key()
        self.client = anthropic.Anthropic(api_key=self.api_key)
        self.prompts_dir = Path(Config.PROMPTS_DIR)
        self.prompts_cache: Dict[str, str] = {}
        self.max_tool_calls = max_tool_calls
        
        log("Agent executor initialized (v6 hierarchical verification)", "info")
    
    def load_prompt(self, agent_name: str) -> str:
        if agent_name in self.prompts_cache:
            return self.prompts_cache[agent_name]
        
        prompt_file = self.prompts_dir / f"{agent_name}.md"
        if prompt_file.exists():
            prompt = prompt_file.read_text()
            self.prompts_cache[agent_name] = prompt
            return prompt
        
        return f"You are {agent_name}. Complete your assigned analysis task."
    
    def execute_data_agent(self, context: SessionContext) -> AgentResult:
        """Execute Data Agent with tools."""
        agent_name = "01-DATA-AGENT"
        log(f"Running {agent_name} (tool-enabled)...", "info")
        start_time = datetime.now()
        tool_calls = []
        total_tokens = 0
        
        try:
            system_prompt = self._build_data_agent_system_prompt()
            user_message = self._build_data_agent_message(context)
            messages = [{"role": "user", "content": user_message}]
            
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
                    text_blocks = [b for b in response.content if b.type == "text"]
                    final_response = "\n".join(b.text for b in text_blocks)
                    break
                
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
        """Execute an analysis agent with grounded data."""
        log(f"Running {agent_name} (grounded mode)...", "info")
        start_time = datetime.now()
        
        try:
            system_prompt = self._build_grounded_system_prompt(agent_name)
            user_message = self._build_grounded_message(agent_name, context, data_context)
            
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
    
    def execute_verifier(self, verifier_name: str, context: SessionContext) -> VerificationResult:
        """Execute a verification agent."""
        log(f"Running {verifier_name} (verification mode)...", "verify")
        start_time = datetime.now()
        
        try:
            # Get the appropriate prompt
            verifier_prompts = {
                "QUANT-VERIFIER": QUANT_VERIFIER_PROMPT,
                "RISK-VERIFIER": RISK_VERIFIER_PROMPT,
                "MOAT-VERIFIER": MOAT_VERIFIER_PROMPT,
            }
            
            system_prompt = VERIFIER_SYSTEM_PROMPT + "\n\n" + verifier_prompts.get(verifier_name, "")
            
            # Build verification message
            user_message = self._build_verifier_message(verifier_name, context)
            
            response = self.client.messages.create(
                model=Config.MODEL,
                max_tokens=Config.MAX_TOKENS_VERIFIER,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}]
            )
            
            duration = (datetime.now() - start_time).total_seconds()
            raw_response = response.content[0].text
            
            # Parse verification output
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
                # Fallback: treat entire response as summary
                result = VerificationResult(
                    agent=verifier_name,
                    verified_claims=[],
                    dropped_claims=[],
                    verification_stats={"parse_error": True},
                    summary=raw_response[:2000],
                    raw_response=raw_response
                )
            
            stats = result.verification_stats
            verified = stats.get("verified", len(result.verified_claims))
            dropped = stats.get("dropped", len(result.dropped_claims))
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
        """Execute final synthesis with verified summaries only."""
        agent_name = "06-SYNTHESIS-AGENT"
        log(f"Running {agent_name} (verified inputs only)...", "info")
        start_time = datetime.now()
        
        try:
            # Build synthesis input from verified summaries ONLY
            synthesis_input = self._build_synthesis_message(context)
            
            # Load base prompt and add v6 instructions
            base_prompt = self.load_prompt(agent_name)
            system_prompt = base_prompt + "\n\n" + SYNTHESIS_PROMPT_V6
            
            response = self.client.messages.create(
                model=Config.MODEL,
                max_tokens=Config.MAX_TOKENS_SYNTHESIS,
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
    
    def _build_verifier_message(self, verifier_name: str, context: SessionContext) -> str:
        """Build message for verification agent."""
        # Get data corpus (source of truth)
        data_corpus = "{}"
        if "01-DATA-AGENT" in context.agent_results:
            dar = context.agent_results["01-DATA-AGENT"]
            if dar.structured_output:
                data_corpus = json.dumps(dar.structured_output, indent=2)
            else:
                data_corpus = dar.response
        
        # Get analysis outputs this verifier needs to check
        input_agents = Config.VERIFIER_INPUTS.get(verifier_name, [])
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
        
        analysis_text = "\n\n".join(analysis_outputs)
        
        return f"""# Verification Task: {verifier_name}

**Ticker**: {context.ticker}
**Company**: {context.company_name}

## DATA CORPUS (Source of Truth)
This is the verified data from tools. Use this to verify claims.

```json
{data_corpus}
```

## ANALYSIS OUTPUT (To Be Verified)
Check EVERY claim below against the data corpus.

{analysis_text}

## Instructions
1. Go through each claim in the analysis output
2. For numerical claims: Find the EXACT value in data corpus
3. For qualitative claims: Check if supporting evidence exists
4. DROP any claim that cannot be verified
5. Output structured JSON with verified_claims, dropped_claims, and summary

Your summary will be the ONLY thing passed to final synthesis.
Make it comprehensive but concise (~500-800 words).
"""
    
    def _build_synthesis_message(self, context: SessionContext) -> str:
        """Build message for synthesis from verified summaries only."""
        parts = [
            f"# Research Synthesis: {context.ticker} ({context.company_name})",
            f"\n**Date**: {datetime.now().strftime('%Y-%m-%d')}",
            "\n## Verified Summaries\n",
            "These summaries contain ONLY claims that passed verification.",
            "Do NOT add any facts not present here.\n"
        ]
        
        # Add verified summaries
        for verifier_name in Config.VERIFIER_AGENTS:
            if verifier_name in context.verification_results:
                vr = context.verification_results[verifier_name]
                stats = vr.verification_stats
                verified = stats.get("verified", len(vr.verified_claims))
                dropped = stats.get("dropped", len(vr.dropped_claims))
                
                parts.append(f"\n### {verifier_name}")
                parts.append(f"*Verification: {verified} claims verified, {dropped} dropped*\n")
                parts.append(vr.summary)
        
        # Add verified data block for reference
        if context.verified_data:
            parts.append("\n---\n## Verified Data Reference")
            parts.append(context.verified_data.to_constraint_block())
        
        parts.append("\n---\n## Output Instructions")
        parts.append("Write a complete investment memo in markdown format.")
        parts.append("Include YAML frontmatter with: ticker, company, date, rating, price_target, current_price, tags")
        
        return "\n".join(parts)
    
    # === Helper methods from v5 ===
    
    def _build_data_agent_system_prompt(self) -> str:
        return """You are a DATA COLLECTION AGENT for equity research.

CRITICAL RULES:
1. You MUST use your tools to gather ALL data. Do NOT make up any numbers.
2. If a tool fails or returns no data, report "null" for that field.
3. Your output MUST be valid JSON.
4. Every numerical value must come from a tool call.

Return ONLY a JSON object. No markdown, no explanation."""
    
    def _build_data_agent_message(self, context: SessionContext) -> str:
        return f"""# Research Task: Gather Data for {context.ticker}

**Company**: {context.company_name}
**Timestamp**: {datetime.now().isoformat()}

## Required Tools:
1. get_price_data("{context.ticker}")
2. get_company_info("{context.ticker}")
3. get_analyst_estimates("{context.ticker}")
4. web_search("{context.company_name} news {datetime.now().strftime('%B %Y')}")
5. get_sec_filings("{context.ticker}")

Return JSON with: ticker, timestamp, market_data, analyst_estimates, company_info, recent_news, sec_filings, data_gaps, tool_calls_made"""
    
    def _build_grounded_system_prompt(self, agent_name: str) -> str:
        base_prompt = self.load_prompt(agent_name)
        return base_prompt + """

=== ANTI-HALLUCINATION RULES ===
1. Use ONLY verified data provided. Do NOT invent numbers.
2. If data is missing, say "Data not available" - NEVER guess.
3. Return structured JSON for validation.
================================"""
    
    def _build_grounded_message(self, agent_name: str, context: SessionContext,
                                data_context: str) -> str:
        verified_block = context.verified_data.to_constraint_block() if context.verified_data else ""
        
        return f"""# Research Task: {agent_name}

**Ticker**: {context.ticker}
**Company**: {context.company_name}

{verified_block}

## Data from Data Agent:
```json
{data_context}
```

Complete your analysis. Return structured JSON."""
    
    def _extract_json(self, text: str) -> Optional[Dict]:
        """Extract JSON from response text."""
        # Try code blocks
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        
        # Try entire response
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        
        # Try to find JSON object
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

class ResearchOrchestratorV6:
    """Orchestrator with hierarchical verification."""
    
    def __init__(self, api_key: Optional[str] = None, db_path: str = Config.DB_PATH,
                 max_tool_calls: int = Config.MAX_TOOL_CALLS):
        self.executor = AgentExecutor(api_key, max_tool_calls)
        self.db_path = db_path
    
    def run(self, ticker: str, company_name: str,
            output_dir: Optional[str] = None,
            parallel_verify: bool = True) -> SessionContext:
        
        print_header(f"Multi-Agent Research v6: {ticker} ({company_name})")
        log("Hierarchical verification mode", "info")
        
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
        
        # Pre-fetch verified data
        context.verified_data = self._fetch_verified_data(ticker)
        
        # Phase 1: Data Collection
        print_header("Phase 1: Data Collection")
        data_result = self.executor.execute_data_agent(context)
        context.agent_results["01-DATA-AGENT"] = data_result
        self._save_result(context, "data_corpus.json", data_result)
        
        # Get data context for analysis agents
        data_context = ""
        if data_result.structured_output:
            data_context = json.dumps(data_result.structured_output, indent=2)
        else:
            data_context = data_result.response
        
        # Phase 2: Analysis
        print_header("Phase 2: Analysis")
        for agent_name in Config.ANALYSIS_AGENTS:
            result = self.executor.execute_analysis_agent(agent_name, context, data_context)
            context.agent_results[agent_name] = result
            
            output_name = {
                "02-QUANT-AGENT": "valuation.json",
                "03-RISK-AGENT": "risk.json",
                "04-COMPETITIVE-AGENT": "competitive.json",
                "05-QUALITATIVE-AGENT": "qualitative.json"
            }[agent_name]
            self._save_result(context, output_name, result)
        
        # Phase 3: Verification (can run in parallel)
        print_header("Phase 3: Verification")
        
        if parallel_verify:
            # Run verifiers in parallel
            with ThreadPoolExecutor(max_workers=3) as executor:
                futures = {
                    executor.submit(self.executor.execute_verifier, name, context): name
                    for name in Config.VERIFIER_AGENTS
                }
                
                for future in as_completed(futures):
                    verifier_name = futures[future]
                    try:
                        result = future.result()
                        context.verification_results[verifier_name] = result
                        self._save_verification(context, verifier_name, result)
                    except Exception as e:
                        log(f"  {verifier_name} failed: {e}", "error")
        else:
            # Sequential execution
            for verifier_name in Config.VERIFIER_AGENTS:
                result = self.executor.execute_verifier(verifier_name, context)
                context.verification_results[verifier_name] = result
                self._save_verification(context, verifier_name, result)
        
        # Phase 4: Synthesis
        print_header("Phase 4: Synthesis (Verified Inputs Only)")
        synthesis_result = self.executor.execute_synthesis(context)
        context.agent_results["06-SYNTHESIS-AGENT"] = synthesis_result
        self._save_result(context, "final_memo.md", synthesis_result, is_markdown=True)
        
        # Summary
        self._print_summary(context)
        
        return context
    
    def _fetch_verified_data(self, ticker: str) -> VerifiedData:
        """Fetch verified data from tools."""
        log("Fetching verified data (source of truth)...", "info")
        
        verified = VerifiedData(ticker=ticker, fetched_at=datetime.now().isoformat())
        
        try:
            # Company overview (name, description, sector, industry)
            overview_result = execute_tool("get_company_overview", {"ticker": ticker})
            if overview_result:
                overview_data = json.loads(overview_result)
                info = overview_data.get("info", {})
                verified.name = info.get("name")
                verified.description = info.get("description")
                verified.sector = info.get("sector")
                verified.industry = info.get("industry")
                
                if verified.name:
                    log(f"  Verified Company: {verified.name}", "success")
            
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
                    log(f"  Verified Price: ${verified.current_price:.2f}", "success")
            
            # Analyst estimates
            est_result = execute_tool("get_analyst_estimates", {"ticker": ticker})
            if est_result:
                est_data = json.loads(est_result)
                targets = est_data.get("price_targets", {})
                verified.price_target_mean = targets.get("mean")
                verified.price_target_high = targets.get("high")
                verified.price_target_low = targets.get("low")
                verified.num_analysts = targets.get("num_analysts")
                verified.recommendation = est_data.get("recommendation", {}).get("rating")
                
                if verified.price_target_mean:
                    log(f"  Verified Mean Target: ${verified.price_target_mean:.2f}", "success")
                    
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
        
        # Verification stats
        total_verified = 0
        total_dropped = 0
        for vr in context.verification_results.values():
            total_verified += len(vr.verified_claims)
            total_dropped += len(vr.dropped_claims)
        
        log(f"Session: {context.session_id}", "info")
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
        description="Research Orchestrator v6 (Hierarchical Verification)"
    )
    parser.add_argument("ticker", help="Stock ticker")
    parser.add_argument("company_name", help="Company name")
    parser.add_argument("--output-dir", "-o", help="Output directory")
    parser.add_argument("--max-tool-calls", type=int, default=10)
    parser.add_argument("--no-parallel", action="store_true",
                        help="Run verifiers sequentially")
    parser.add_argument("--api-key", "-k")
    
    args = parser.parse_args()
    
    api_key = args.api_key or os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY not set.")
        sys.exit(1)
    
    try:
        orchestrator = ResearchOrchestratorV6(
            api_key=api_key,
            max_tool_calls=args.max_tool_calls
        )
        orchestrator.run(
            ticker=args.ticker.upper(),
            company_name=args.company_name,
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
