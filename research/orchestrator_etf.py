#!/usr/bin/env python3
"""
Multi-Agent ETF Research Orchestrator
======================================

Specialized orchestrator for ETF research with asset-type-aware
agent selection and ETF-specific tools.

Supports:
- Commodity ETFs (SLV, GLD) - physical commodity exposure
- Commodity Futures ETFs (USO, UNG) - futures-based
- Equity Index ETFs (SPY, QQQ) - broad market
- Sector ETFs (XLF, XLE) - sector exposure
- Fixed Income ETFs (TLT, BND) - bonds
- Leveraged ETFs (TQQQ, SQQQ) - leveraged/inverse

Usage:
    python orchestrator_etf.py SLV
    python orchestrator_etf.py GLD --obsidian
"""

import anthropic
import json
import os
import sys
import argparse
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any
from enum import Enum

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import from same directory
from asset_classifier import classify_asset, AssetType, get_etf_research_agents
from etf_tools import ETF_TOOLS, execute_etf_tool
from agent_tools import AGENT_TOOLS, execute_tool

try:
    from config import (
        RESEARCH_OUTPUT_PATH,
        get_anthropic_api_key,
    )
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
    MAX_TOOL_CALLS = 10
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
# DATA STRUCTURES
# =============================================================================

class AgentStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass
class AgentResult:
    agent: str
    status: AgentStatus
    response: str
    tool_calls: List[Dict] = field(default_factory=list)
    duration_seconds: float = 0
    tokens_used: int = 0
    error: Optional[str] = None


@dataclass
class SessionContext:
    ticker: str
    asset_type: AssetType
    asset_info: Dict[str, Any]
    session_id: str
    output_dir: Path
    start_time: datetime
    agent_results: Dict[str, AgentResult] = field(default_factory=dict)


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
        print(f"{timestamp} {message}")


def header(title: str):
    if RICH_AVAILABLE:
        console.print(Panel(title, style="bold cyan"))
    else:
        print(f"\n{'='*60}\n{title}\n{'='*60}")


# =============================================================================
# AGENT EXECUTION
# =============================================================================

class ETFAgentExecutor:
    def __init__(self, api_key: str, max_tool_calls: int = 10):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.max_tool_calls = max_tool_calls
        
        # Combine ETF tools with general tools (web_search, web_fetch)
        self.tools = ETF_TOOLS + [
            t for t in AGENT_TOOLS 
            if t["name"] in ["web_search", "web_fetch"]
        ]
        
        log(f"ETF Agent executor initialized (max_tool_calls={max_tool_calls})")
    
    def load_prompt(self, agent_name: str) -> str:
        """Load agent prompt from file."""
        prompt_file = Path(Config.PROMPTS_DIR) / f"{agent_name}.md"
        if prompt_file.exists():
            return prompt_file.read_text()
        else:
            # Return a default prompt if file doesn't exist
            return f"You are the {agent_name}. Analyze the provided data and provide your assessment."
    
    def run_agent(
        self,
        agent_name: str,
        context: SessionContext,
        prior_results: Dict[str, str],
        use_tools: bool = True,
    ) -> AgentResult:
        """Run a single agent with optional tool use."""
        
        start_time = datetime.now()
        
        # Load prompt
        system_prompt = self.load_prompt(agent_name)
        
        # Build user message with context
        user_message = self._build_user_message(agent_name, context, prior_results)
        
        messages = [{"role": "user", "content": user_message}]
        
        tool_calls = []
        total_tokens = 0
        
        try:
            if use_tools:
                # Tool-enabled loop
                for i in range(self.max_tool_calls + 1):
                    response = self.client.messages.create(
                        model=Config.MODEL,
                        max_tokens=Config.MAX_TOKENS,
                        system=system_prompt,
                        tools=self.tools,
                        messages=messages,
                    )
                    
                    total_tokens += response.usage.input_tokens + response.usage.output_tokens
                    
                    # Check if we have a final response
                    if response.stop_reason == "end_turn":
                        final_text = self._extract_text(response)
                        break
                    
                    # Process tool calls
                    if response.stop_reason == "tool_use":
                        tool_results = []
                        for block in response.content:
                            if block.type == "tool_use":
                                tool_name = block.name
                                tool_input = block.input
                                
                                # Log tool call
                                log(f"  → Tool: {tool_name}({json.dumps(tool_input)[:60]}...)", "tool")
                                
                                # Execute tool
                                if tool_name in ["web_search", "web_fetch"]:
                                    result = execute_tool(tool_name, tool_input)
                                else:
                                    result = execute_etf_tool(tool_name, tool_input)
                                
                                tool_calls.append({
                                    "tool": tool_name,
                                    "input": tool_input,
                                    "result_preview": result[:200] if result else "",
                                })
                                
                                tool_results.append({
                                    "type": "tool_result",
                                    "tool_use_id": block.id,
                                    "content": result,
                                })
                        
                        # Add assistant response and tool results
                        messages.append({"role": "assistant", "content": response.content})
                        messages.append({"role": "user", "content": tool_results})
                    else:
                        final_text = self._extract_text(response)
                        break
                else:
                    # Max tool calls reached
                    final_text = self._extract_text(response) if response else ""
                    log(f"  ⚠ Max tool calls reached", "warning")
            else:
                # No tools
                response = self.client.messages.create(
                    model=Config.MODEL,
                    max_tokens=Config.MAX_TOKENS,
                    system=system_prompt,
                    messages=messages,
                )
                total_tokens = response.usage.input_tokens + response.usage.output_tokens
                final_text = self._extract_text(response)
            
            duration = (datetime.now() - start_time).total_seconds()
            
            return AgentResult(
                agent=agent_name,
                status=AgentStatus.COMPLETE,
                response=final_text,
                tool_calls=tool_calls,
                duration_seconds=duration,
                tokens_used=total_tokens,
            )
            
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            return AgentResult(
                agent=agent_name,
                status=AgentStatus.FAILED,
                response="",
                tool_calls=tool_calls,
                duration_seconds=duration,
                tokens_used=total_tokens,
                error=str(e),
            )
    
    def _build_user_message(
        self,
        agent_name: str,
        context: SessionContext,
        prior_results: Dict[str, str],
    ) -> str:
        """Build the user message with context for the agent."""
        
        parts = [
            f"# Research Request: {context.ticker}",
            f"",
            f"**Asset Type**: {context.asset_type.value}",
            f"**Name**: {context.asset_info.get('name', context.ticker)}",
            f"**Category**: {context.asset_info.get('category', 'N/A')}",
            f"**Date**: {datetime.now().strftime('%Y-%m-%d')}",
            f"**Session ID**: {context.session_id}",
            f"",
        ]
        
        # Add VERIFIED price data with strong warning
        parts.append("## ⚠️ VERIFIED REAL-TIME PRICES (DO NOT HALLUCINATE)")
        parts.append("")
        parts.append("**USE THESE EXACT VALUES. DO NOT MAKE UP PRICES.**")
        parts.append("")
        
        if context.asset_info.get("real_price"):
            parts.append(f"- **{context.ticker} Current Price**: ${context.asset_info['real_price']:.2f}")
        if context.asset_info.get("real_nav"):
            parts.append(f"- **{context.ticker} NAV**: ${context.asset_info['real_nav']:.2f}")
        if context.asset_info.get("commodity_price"):
            cp = context.asset_info["commodity_price"]
            parts.append(f"- **Underlying Commodity Price**: ${cp.get('price', 'N/A')}")
        if context.asset_info.get("gold_silver_ratio"):
            gsr = context.asset_info["gold_silver_ratio"]
            parts.append(f"- **Gold/Silver Ratio**: {gsr.get('current_ratio', 'N/A'):.1f}")
        if context.asset_info.get("etf_data"):
            ed = context.asset_info["etf_data"]
            parts.append(f"- **52W High**: ${ed.get('52w_high', 'N/A')}")
            parts.append(f"- **52W Low**: ${ed.get('52w_low', 'N/A')}")
            parts.append(f"- **50-Day MA**: ${ed.get('50d_ma', 'N/A')}")
            parts.append(f"- **200-Day MA**: ${ed.get('200d_ma', 'N/A')}")
            parts.append(f"- **AUM**: ${ed.get('aum_billions', 'N/A'):.2f}B")
            parts.append(f"- **Expense Ratio**: {ed.get('expense_ratio_pct', 'N/A')}%")
        
        # Add macro data
        if context.asset_info.get("macro_data"):
            md = context.asset_info["macro_data"]
            parts.append("")
            parts.append("**Verified Macro Data:**")
            if md.get("dxy", {}).get("value"):
                parts.append(f"- **DXY (Dollar Index)**: {md['dxy']['value']:.2f}")
            if md.get("vix", {}).get("value"):
                parts.append(f"- **VIX**: {md['vix']['value']:.2f}")
            if md.get("tnx", {}).get("value"):
                parts.append(f"- **10Y Treasury**: {md['tnx']['value']:.2f}%")
            if md.get("tyx", {}).get("value"):
                parts.append(f"- **30Y Treasury**: {md['tyx']['value']:.2f}%")
            if md.get("irx", {}).get("value"):
                parts.append(f"- **3M T-Bill**: {md['irx']['value']:.2f}%")
            if md.get("yield_curve_10y_3m"):
                yc = md["yield_curve_10y_3m"]
                parts.append(f"- **Yield Curve (10Y-3M)**: {yc.get('spread', 0):.2f}% ({'INVERTED' if yc.get('inverted') else 'normal'})")
        
        parts.append("")
        
        # Add full asset info as JSON
        parts.append("## Full Asset Data")
        parts.append("```json")
        parts.append(json.dumps(context.asset_info, indent=2, default=str))
        parts.append("```")
        parts.append("")
        
        # Add prior agent results
        if prior_results:
            parts.append("## Prior Agent Analysis")
            for agent, result in prior_results.items():
                parts.append(f"### {agent}")
                parts.append(result[:5000])  # Truncate to avoid context overflow
                parts.append("")
        
        parts.append("## Your Task")
        parts.append(f"Provide your {agent_name} analysis for {context.ticker}.")
        parts.append("Use the tools available to fetch additional data as needed.")
        parts.append("Format your output according to your agent specification.")
        
        return "\n".join(parts)
    
    def _extract_text(self, response) -> str:
        """Extract text from response content blocks."""
        texts = []
        for block in response.content:
            if hasattr(block, "text"):
                texts.append(block.text)
        return "\n".join(texts)


# =============================================================================
# ORCHESTRATOR
# =============================================================================

def run_etf_research(
    ticker: str,
    max_tool_calls: int = 10,
    save_to_obsidian: bool = False,
    output_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run ETF research pipeline.
    
    Args:
        ticker: ETF ticker symbol
        max_tool_calls: Maximum tool calls per agent
        save_to_obsidian: Whether to save to Obsidian vault
        output_dir: Custom output directory
    
    Returns:
        Dict with session results
    """
    
    # Classify asset
    log(f"Classifying asset: {ticker}")
    asset_info = classify_asset(ticker)
    
    if asset_info.asset_type == AssetType.EQUITY:
        log("This is an equity, not an ETF. Use orchestrator_v4.py for equities.", "warning")
        return {"status": "error", "error": "Use orchestrator_v4.py for equities"}
    
    if asset_info.asset_type == AssetType.UNKNOWN:
        log(f"Unknown asset type for {ticker}", "warning")
    
    header(f"ETF Research: {ticker} ({asset_info.name})")
    log(f"Asset Type: {asset_info.asset_type.value}")
    log(f"Category: {asset_info.category}")
    
    # Create session
    session_id = f"{ticker}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    output_path = Path(output_dir) if output_dir else Path(Config.OUTPUTS_DIR)
    session_output = output_path / session_id
    session_output.mkdir(parents=True, exist_ok=True)
    
    log(f"Session ID: {session_id}")
    log(f"Output: {session_output}")
    
    context = SessionContext(
        ticker=ticker,
        asset_type=asset_info.asset_type,
        asset_info=asset_info.to_dict(),
        session_id=session_id,
        output_dir=session_output,
        start_time=datetime.now(),
    )
    
    # Get agents for this asset type
    agents = get_etf_research_agents(asset_info.asset_type)
    log(f"Agents: {agents}")
    
    # Initialize executor
    executor = ETFAgentExecutor(
        api_key=Config.get_api_key(),
        max_tool_calls=max_tool_calls,
    )
    
    # Fetch real price data upfront to prevent hallucination
    from etf_tools import get_etf_info, get_commodity_price, get_macro_data, get_gold_silver_ratio
    
    log("Fetching real-time price data...")
    etf_data = get_etf_info(ticker)
    if etf_data["status"] == "success":
        real_price = etf_data["data"].get("price")
        real_nav = etf_data["data"].get("nav")
        log(f"Real Price: ${real_price:.2f}, NAV: ${real_nav:.2f}")
        context.asset_info["real_price"] = real_price
        context.asset_info["real_nav"] = real_nav
        context.asset_info["etf_data"] = etf_data["data"]
    
    # For commodity ETFs, also fetch underlying commodity price
    if asset_info.asset_type in [AssetType.ETF_COMMODITY, AssetType.ETF_COMMODITY_FUTURES]:
        # Determine commodity from category/name
        name_lower = (asset_info.name or "").lower()
        if "silver" in name_lower:
            commodity = "silver"
        elif "gold" in name_lower:
            commodity = "gold"
        elif "oil" in name_lower:
            commodity = "oil"
        else:
            commodity = None
        
        if commodity:
            commodity_data = get_commodity_price(commodity)
            if commodity_data["status"] == "success":
                log(f"{commodity.title()} Futures: ${commodity_data['data'].get('price'):.2f}")
                context.asset_info["commodity_price"] = commodity_data["data"]
        
        # Get gold/silver ratio for precious metals
        if commodity in ["gold", "silver"]:
            ratio_data = get_gold_silver_ratio()
            if ratio_data["status"] == "success":
                log(f"Gold/Silver Ratio: {ratio_data['data'].get('current_ratio'):.1f}")
                context.asset_info["gold_silver_ratio"] = ratio_data["data"]
    
    # Get macro data
    macro_data = get_macro_data()
    if macro_data["status"] == "success":
        context.asset_info["macro_data"] = macro_data["data"]
        dxy = macro_data["data"].get("dxy", {}).get("value")
        vix = macro_data["data"].get("vix", {}).get("value")
        tnx = macro_data["data"].get("tnx", {}).get("value")
        if dxy:
            log(f"DXY: {dxy:.2f}, VIX: {vix:.2f}, 10Y: {tnx:.2f}%", "info")
    
    # Run agents
    prior_results = {}
    total_tokens = 0
    
    for agent_name in agents:
        header(f"Running {agent_name}")
        
        # Only first agent (data gathering) uses tools - Synthesis works with pre-fetched data
        use_tools = (agent_name == agents[0]) or ("STRUCTURE" in agent_name)
        
        result = executor.run_agent(
            agent_name=agent_name,
            context=context,
            prior_results=prior_results,
            use_tools=use_tools,
        )
        
        context.agent_results[agent_name] = result
        total_tokens += result.tokens_used
        
        if result.status == AgentStatus.COMPLETE:
            log(f"✓ {agent_name} complete ({result.duration_seconds:.1f}s, {result.tokens_used} tokens)", "success")
            prior_results[agent_name] = result.response
            
            # Save individual result
            result_file = session_output / f"{agent_name.lower().replace('-', '_')}.json"
            with open(result_file, "w") as f:
                json.dump({
                    "agent": agent_name,
                    "status": result.status.value,
                    "timestamp": datetime.now().isoformat(),
                    "response": result.response,
                    "tool_calls": result.tool_calls,
                    "duration_seconds": result.duration_seconds,
                    "tokens_used": result.tokens_used,
                }, f, indent=2)
            log(f"Saved: {result_file.name}")
        else:
            log(f"✗ {agent_name} failed: {result.error}", "error")
            # Save failed result too
            result_file = session_output / f"{agent_name.lower().replace('-', '_')}.json"
            with open(result_file, "w") as f:
                json.dump({
                    "agent": agent_name,
                    "status": result.status.value,
                    "timestamp": datetime.now().isoformat(),
                    "error": result.error,
                    "duration_seconds": result.duration_seconds,
                }, f, indent=2)
    
    # Get final memo from synthesis agent
    synthesis_agent = [a for a in agents if "SYNTHESIS" in a]
    if synthesis_agent:
        final_memo = context.agent_results.get(synthesis_agent[0])
        if final_memo and final_memo.status == AgentStatus.COMPLETE:
            memo_file = session_output / "final_memo.md"
            with open(memo_file, "w") as f:
                f.write(final_memo.response)
            log(f"Saved: final_memo.md", "success")
            
            # Save to Obsidian if requested
            if save_to_obsidian:
                obsidian_path = Path.home() / "Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian/Research/Equity-Memos"
                obsidian_path.mkdir(parents=True, exist_ok=True)
                obsidian_file = obsidian_path / f"{ticker}_{datetime.now().strftime('%Y-%m-%d')}.md"
                with open(obsidian_file, "w") as f:
                    f.write(final_memo.response)
                log(f"Saved to Obsidian: {obsidian_file}", "success")
    
    # Summary
    duration = (datetime.now() - context.start_time).total_seconds() / 60
    header("Session Summary")
    log(f"Session: {session_id}")
    log(f"Duration: {duration:.1f} min")
    log(f"Total tokens: {total_tokens:,}")
    log(f"")
    log(f"✅ Output: {session_output / 'final_memo.md'}", "success")
    
    return {
        "status": "success",
        "session_id": session_id,
        "ticker": ticker,
        "asset_type": asset_info.asset_type.value,
        "duration_minutes": duration,
        "total_tokens": total_tokens,
        "output_dir": str(session_output),
    }


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="ETF Research Orchestrator")
    parser.add_argument("ticker", help="ETF ticker symbol (e.g., SLV, GLD, SPY)")
    parser.add_argument("--max-tool-calls", type=int, default=10, help="Max tool calls per agent")
    parser.add_argument("--obsidian", action="store_true", help="Save to Obsidian vault")
    parser.add_argument("--output-dir", help="Custom output directory")
    
    args = parser.parse_args()
    
    result = run_etf_research(
        ticker=args.ticker.upper(),
        max_tool_calls=args.max_tool_calls,
        save_to_obsidian=args.obsidian,
        output_dir=args.output_dir,
    )
    
    if result["status"] != "success":
        sys.exit(1)


if __name__ == "__main__":
    main()
