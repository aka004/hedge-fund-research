#!/usr/bin/env python3
"""
Multi-Agent Equity Research Orchestrator v4
============================================

MAJOR CHANGES from v3:
- Data Agent now has TOOLS (web_search, get_price_data, get_analyst_estimates, etc.)
- Agent can autonomously fetch what it needs
- Tool execution loop handles multiple tool calls
- Uses real analyst estimates for valuation (no hallucination)
- Removed AFML methodology (not relevant for fundamental research)

Architecture:
    1. Data Agent runs with tools → fetches real data + analyst estimates → outputs research corpus
    2. Other agents receive Data Agent's corpus (no tools needed)
    3. Quant Agent uses real analyst price targets and EPS/revenue estimates for valuation

Usage:
    python orchestrator_v4.py MU "Micron Technology"
    python orchestrator_v4.py BABA "Alibaba Group" --max-tool-calls 10
"""

import anthropic
import duckdb
import json
import os
import sys
import argparse
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, List, Any
from enum import Enum

# Import from same directory
from agent_tools import AGENT_TOOLS, execute_tool

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from config import (
        RESEARCH_DB_PATH,
        RESEARCH_OUTPUT_PATH,
        RESEARCH_FEEDBACK_PATH,
        get_anthropic_api_key,
    )
    CONFIG_AVAILABLE = True
except ImportError:
    CONFIG_AVAILABLE = False
    RESEARCH_DB_PATH = Path("../data/research.duckdb")
    RESEARCH_OUTPUT_PATH = Path("../outputs/research")
    RESEARCH_FEEDBACK_PATH = Path("../feedback")

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
    MAX_TOOL_CALLS = 15  # Max tool calls per agent
    DB_PATH = str(RESEARCH_DB_PATH)
    PROMPTS_DIR = str(Path(__file__).parent)
    OUTPUTS_DIR = str(RESEARCH_OUTPUT_PATH)
    
    # Data Agent gets tools, others don't
    AGENTS_WITH_TOOLS = ["01-DATA-AGENT"]
    
    AGENTS = [
        "01-DATA-AGENT",  # Has tools
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


@dataclass
class AgentResult:
    agent: str
    status: AgentStatus
    response: str
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
    db_path: str = Config.DB_PATH
    verified_data: Dict[str, Any] = field(default_factory=dict)  # Pre-fetched real price data


# =============================================================================
# LOGGING
# =============================================================================

def log(message: str, style: str = "info"):
    timestamp = datetime.now().strftime("%H:%M:%S")
    if RICH_AVAILABLE:
        styles = {"info": "blue", "success": "green", "warning": "yellow", 
                  "error": "red", "header": "bold magenta", "tool": "cyan"}
        console.print(f"[dim]{timestamp}[/dim] [{styles.get(style, 'white')}]{message}[/]")
    else:
        print(f"{timestamp} [{style}] {message}")


def print_header(title: str):
    if RICH_AVAILABLE:
        console.print(Panel(title, style="bold magenta"))
    else:
        print(f"\n{'='*60}\n{title}\n{'='*60}")


# =============================================================================
# AGENT EXECUTOR WITH TOOL USE
# =============================================================================

class AgentExecutor:
    """Executes agents - Data Agent gets tools, others don't."""
    
    def __init__(self, api_key: Optional[str] = None,
                 max_tool_calls: int = Config.MAX_TOOL_CALLS):
        self.api_key = api_key or Config.get_api_key()
        self.client = anthropic.Anthropic(api_key=self.api_key)
        self.prompts_dir = Path(Config.PROMPTS_DIR)
        self.prompts_cache: Dict[str, str] = {}
        self.max_tool_calls = max_tool_calls
        
        log(f"Agent executor initialized (max_tool_calls={max_tool_calls})", "info")
    
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
        """Execute an agent, with or without tools."""
        
        has_tools = agent_name in Config.AGENTS_WITH_TOOLS
        
        if has_tools:
            return self._execute_with_tools(agent_name, context, additional_context)
        else:
            return self._execute_without_tools(agent_name, context, additional_context)
    
    def _execute_with_tools(self, agent_name: str, context: SessionContext,
                            additional_context: str = "") -> AgentResult:
        """Execute Data Agent with tools - runs tool loop."""
        log(f"Running {agent_name} WITH TOOLS...", "info")
        start_time = datetime.now()
        tool_calls = []
        total_tokens = 0
        
        try:
            system_prompt = self.load_prompt(agent_name)
            
            # Build initial message with tool instructions
            user_message = self._build_tool_agent_message(
                agent_name, context, additional_context
            )
            
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
                
                # Check if we got tool_use blocks
                tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
                
                if not tool_use_blocks:
                    # No more tool calls - extract final text response
                    text_blocks = [b for b in response.content if b.type == "text"]
                    final_response = "\n".join(b.text for b in text_blocks)
                    break
                
                # Execute tools and continue
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        log(f"  → Tool: {block.name}({json.dumps(block.input)[:60]}...)", "tool")
                        
                        result = execute_tool(block.name, block.input)
                        
                        tool_calls.append(ToolCall(
                            tool_name=block.name,
                            tool_input=block.input,
                            result=result[:500] + "..." if len(result) > 500 else result,
                            timestamp=datetime.now().isoformat()
                        ))
                        
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result
                        })
                
                # Add assistant response and tool results to messages
                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": tool_results})
            
            else:
                # Hit max tool calls
                log(f"  ⚠ Hit max tool calls ({self.max_tool_calls})", "warning")
                final_response = "Max tool calls reached. Partial analysis completed."
            
            duration = (datetime.now() - start_time).total_seconds()
            
            result = AgentResult(
                agent=agent_name,
                status=AgentStatus.COMPLETE,
                response=final_response,
                tool_calls=tool_calls,
                duration_seconds=duration,
                tokens_used=total_tokens
            )
            
            log(f"✓ {agent_name} complete ({duration:.1f}s, {total_tokens} tokens, {len(tool_calls)} tool calls)", "success")
            return result
            
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
    
    def _execute_without_tools(self, agent_name: str, context: SessionContext,
                               additional_context: str = "") -> AgentResult:
        """Execute agent without tools (standard completion)."""
        log(f"Running {agent_name}...", "info")
        start_time = datetime.now()
        
        try:
            system_prompt = self.load_prompt(agent_name)
            
            user_message = self._build_standard_message(
                agent_name, context, additional_context
            )
            
            response = self.client.messages.create(
                model=Config.MODEL,
                max_tokens=Config.MAX_TOKENS,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}]
            )
            
            duration = (datetime.now() - start_time).total_seconds()
            tokens = response.usage.input_tokens + response.usage.output_tokens
            
            result = AgentResult(
                agent=agent_name,
                status=AgentStatus.COMPLETE,
                response=response.content[0].text,
                duration_seconds=duration,
                tokens_used=tokens
            )
            
            log(f"✓ {agent_name} complete ({duration:.1f}s, {tokens} tokens)", "success")
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
    
    def _build_tool_agent_message(self, agent_name: str, context: SessionContext,
                                  additional_context: str) -> str:
        """Build message for Data Agent with tool instructions."""
        return f"""
# Research Task - DATA COLLECTION

**Ticker**: {context.ticker}
**Company**: {context.company_name}
**Session ID**: {context.session_id}
**Timestamp**: {datetime.now().isoformat()}

## Your Tools

You have access to these tools to gather REAL data:

1. **get_price_data(ticker)** - Get current price, fundamentals, key metrics
2. **get_company_info(ticker)** - Get company overview, sector, description
3. **get_analyst_estimates(ticker)** - Get analyst price targets, EPS/revenue estimates (USE THIS FOR DCF!)
4. **web_search(query)** - Search for recent news, articles
5. **get_sec_filings(ticker)** - Get list of recent SEC filings
6. **web_fetch(url)** - Fetch content from a specific URL

## Instructions

1. **USE YOUR TOOLS** to gather real, verified data. Do not make up data.
2. Start by calling get_price_data, get_company_info, and get_analyst_estimates.
3. **For valuation: USE get_analyst_estimates** - Do NOT hallucinate price targets or growth rates.
4. Search for recent news that might affect the investment thesis.
5. Check recent SEC filings for material events.
6. Compile all gathered data into a structured research corpus.

When you cite information, include the source (e.g., "Price: $415.06 (yfinance)").

## Output Format

After gathering data, output a comprehensive research corpus in this format:

```
# RESEARCH CORPUS FOR {context.ticker}

## Verified Market Data
[Price, fundamentals, key metrics with sources]

## Analyst Consensus (from get_analyst_estimates)
[Price targets, recommendations, EPS/revenue estimates]

## Company Overview
[Sector, industry, business description]

## Recent News & Events
[Headlines with dates and sources]

## SEC Filings
[Recent filings with dates and types]

## Key Data Points for Analysis
[Summarized data points for other agents to use]
```

Begin by calling your tools to gather real data.
"""
    
    def _build_standard_message(self, agent_name: str, context: SessionContext,
                                additional_context: str) -> str:
        """Build message for agents without tools."""
        
        # Build verified data section
        verified_section = ""
        if context.verified_data:
            verified_section = "\n## ⚠️ VERIFIED PRICES (DO NOT HALLUCINATE)\n\n"
            verified_section += "**USE THESE EXACT VALUES. DO NOT MAKE UP PRICES.**\n\n"
            if context.verified_data.get("price"):
                verified_section += f"- **Current Price**: ${context.verified_data['price']}\n"
            if context.verified_data.get("market_cap"):
                mc = context.verified_data['market_cap']
                if mc >= 1e12:
                    verified_section += f"- **Market Cap**: ${mc/1e12:.2f}T\n"
                elif mc >= 1e9:
                    verified_section += f"- **Market Cap**: ${mc/1e9:.2f}B\n"
                else:
                    verified_section += f"- **Market Cap**: ${mc/1e6:.2f}M\n"
            if context.verified_data.get("pe_ratio"):
                verified_section += f"- **P/E Ratio**: {context.verified_data['pe_ratio']:.1f}\n"
            if context.verified_data.get("52w_high"):
                verified_section += f"- **52W High**: ${context.verified_data['52w_high']}\n"
            if context.verified_data.get("52w_low"):
                verified_section += f"- **52W Low**: ${context.verified_data['52w_low']}\n"
            
            if context.verified_data.get("analyst_estimates"):
                est = context.verified_data["analyst_estimates"]
                verified_section += "\n**Analyst Estimates:**\n"
                price_targets = est.get("price_targets", {})
                if price_targets.get("mean"):
                    verified_section += f"- Mean Price Target: ${price_targets['mean']:.2f}\n"
                if price_targets.get("high"):
                    verified_section += f"- High Price Target: ${price_targets['high']:.2f}\n"
                if price_targets.get("low"):
                    verified_section += f"- Low Price Target: ${price_targets['low']:.2f}\n"
                rec = est.get("recommendation", {})
                if rec.get("rating"):
                    verified_section += f"- Recommendation: {rec['rating']} ({rec.get('num_analysts', 'N/A')} analysts)\n"
                earnings = est.get("earnings_estimates", [])
                for e in earnings:
                    if e.get("period") == "0y":
                        verified_section += f"- EPS Current Year: ${e.get('avg_eps', 0):.2f}\n"
                    elif e.get("period") == "+1y":
                        verified_section += f"- EPS Next Year: ${e.get('avg_eps', 0):.2f}\n"
            
            if context.verified_data.get("macro_data"):
                md = context.verified_data["macro_data"]
                verified_section += "\n**Verified Macro Data:**\n"
                if md.get("dxy", {}).get("value"):
                    verified_section += f"- DXY (Dollar Index): {md['dxy']['value']:.2f}\n"
                if md.get("vix", {}).get("value"):
                    verified_section += f"- VIX: {md['vix']['value']:.2f}\n"
                if md.get("tnx", {}).get("value"):
                    verified_section += f"- 10Y Treasury: {md['tnx']['value']:.2f}%\n"
            verified_section += "\n"
        
        return f"""
# Research Task

**Ticker**: {context.ticker}
**Company**: {context.company_name}
**Session ID**: {context.session_id}
**Timestamp**: {datetime.now().isoformat()}
{verified_section}
## Data from Previous Agents
{additional_context if additional_context else "No previous data available."}

## Instructions
1. Complete your assigned analysis using the data provided above.
2. Use ONLY the verified data from the Data Agent - do not invent prices, price targets, or growth estimates.
3. For valuation: Use the analyst estimates provided (price targets, EPS forecasts, revenue estimates).
4. Cite sources when referencing specific data points.
5. Output your results in structured format.
"""


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
        
        print_header(f"Multi-Agent Research v4: {ticker} ({company_name})")
        log("Data Agent has TOOLS for real data fetching", "info")
        log("Using analyst estimates for valuation (no hallucination)", "info")
        
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
        
        # Pre-fetch verified price data to prevent hallucination
        log("Fetching verified price data...", "info")
        from agent_tools import execute_tool
        import json
        
        try:
            price_result = execute_tool("get_price_data", {"ticker": ticker})
            price_data = json.loads(price_result) if price_result else {}
            data = price_data.get("data", {})
            if data:
                context.verified_data["price"] = data.get("current_price")
                context.verified_data["market_cap"] = data.get("market_cap")
                context.verified_data["pe_ratio"] = data.get("pe_ratio") or data.get("forward_pe")
                context.verified_data["52w_high"] = data.get("week_52_high")
                context.verified_data["52w_low"] = data.get("week_52_low")
                log(f"Verified Price: ${context.verified_data.get('price', 'N/A')}", "success")
            
            estimates_result = execute_tool("get_analyst_estimates", {"ticker": ticker})
            estimates_data = json.loads(estimates_result) if estimates_result else {}
            if estimates_data:
                context.verified_data["analyst_estimates"] = estimates_data
                price_targets = estimates_data.get("price_targets", {})
                mean_target = price_targets.get("mean")
                if mean_target:
                    log(f"Analyst Mean Target: ${mean_target:.2f}", "success")
            
            # Fetch macro data for context
            from etf_tools import get_macro_data
            macro_result = get_macro_data()
            if macro_result.get("status") == "success":
                context.verified_data["macro_data"] = macro_result["data"]
                dxy = macro_result["data"].get("dxy", {}).get("value")
                tnx = macro_result["data"].get("tnx", {}).get("value")
                if dxy and tnx:
                    log(f"Macro: DXY={dxy:.1f}, 10Y={tnx:.2f}%", "info")
        except Exception as e:
            log(f"Warning: Could not pre-fetch price data: {e}", "warning")
        
        # Phase 1: Data Collection (WITH TOOLS)
        print_header("Phase 1: Data Collection (Tool-Enabled)")
        
        data_result = self.executor.execute("01-DATA-AGENT", context)
        context.agent_results["01-DATA-AGENT"] = data_result
        self._save_result(context, "data_corpus.json", data_result)
        
        # Log tool usage summary
        if data_result.tool_calls:
            log(f"Tool calls made: {len(data_result.tool_calls)}", "info")
            for tc in data_result.tool_calls[:5]:
                log(f"  - {tc.tool_name}", "tool")
        
        # Phase 2: Analysis (no tools, uses Data Agent corpus)
        print_header("Phase 2: Analysis")
        
        data_corpus = data_result.response
        
        for agent_name in ["02-QUANT-AGENT", "03-RISK-AGENT", 
                          "04-COMPETITIVE-AGENT", "05-QUALITATIVE-AGENT"]:
            result = self.executor.execute(agent_name, context, data_corpus)
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
        
        all_results = "\n\n---\n\n".join([
            f"## {name}\n{result.response[:4000]}"
            for name, result in context.agent_results.items()
        ])
        
        synthesis_result = self.executor.execute("06-SYNTHESIS-AGENT", context, all_results)
        context.agent_results["06-SYNTHESIS-AGENT"] = synthesis_result
        self._save_result(context, "final_memo.md", synthesis_result, is_markdown=True)
        
        # Summary
        self._print_summary(context)
        
        return context
    
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
                "tool_calls": [asdict(tc) for tc in result.tool_calls],
                "duration_seconds": result.duration_seconds,
                "tokens_used": result.tokens_used
            }
            filepath.write_text(json.dumps(data, indent=2))
        log(f"Saved: {filename}", "info")
    
    def _print_summary(self, context: SessionContext):
        print_header("Session Summary")
        
        total_duration = (datetime.now() - context.start_time).total_seconds() / 60
        total_tokens = sum(r.tokens_used for r in context.agent_results.values())
        total_tool_calls = sum(len(r.tool_calls) for r in context.agent_results.values())
        
        log(f"Session: {context.session_id}", "info")
        log(f"Duration: {total_duration:.1f} min", "info")
        log(f"Total tokens: {total_tokens:,}", "info")
        log(f"Tool calls: {total_tool_calls}", "info")
        log(f"\n✅ Output: {context.output_dir / 'final_memo.md'}", "success")


# =============================================================================
# CLI
# =============================================================================

OBSIDIAN_VAULT = "/Users/yung004/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian"

def save_to_obsidian(ticker: str, memo_path: Path) -> str:
    """Save research memo to Obsidian vault."""
    import shutil
    date = datetime.now().strftime("%Y-%m-%d")
    dest_dir = Path(OBSIDIAN_VAULT) / "Research" / "Equity-Memos"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{ticker}_{date}.md"
    shutil.copy(memo_path, dest)
    return str(dest)

def main():
    parser = argparse.ArgumentParser(description="Research Orchestrator v4 (Tool-Enabled, Analyst Estimates)")
    parser.add_argument("ticker", help="Stock ticker")
    parser.add_argument("company_name", help="Company name")
    parser.add_argument("--output-dir", "-o", help="Output directory")
    parser.add_argument("--max-tool-calls", type=int, default=10, help="Max tool calls for Data Agent (default: 10)")
    parser.add_argument("--obsidian", action="store_true", help="Save output to Obsidian vault")
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
        context = orchestrator.run(
            ticker=args.ticker.upper(),
            company_name=args.company_name,
            output_dir=args.output_dir
        )
        
        # Save to Obsidian if requested
        if args.obsidian:
            memo_path = context.output_dir / "final_memo.md"
            if memo_path.exists():
                obsidian_path = save_to_obsidian(args.ticker.upper(), memo_path)
                log(f"Saved to Obsidian: {obsidian_path}", "success")
            else:
                log("Final memo not found, skipping Obsidian save", "warning")
                
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
