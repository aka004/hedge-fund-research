#!/usr/bin/env python3
"""
Multi-Agent Research Orchestrator v2 (CLI Version)
===================================================

Uses Claude CLI instead of direct API calls - no separate API key needed.
Leverages existing Claude CLI authentication.

Usage:
    python orchestrator_v2_cli.py AAPL "Apple Inc."
"""

import subprocess
import json
import os
import sys
import argparse
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, List, Any
from enum import Enum
import tempfile

# Import methodology injection
from methodology_injection import MethodologyInjector

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

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
    PROMPTS_DIR = str(Path(__file__).parent.parent / "research")
    OUTPUTS_DIR = str(Path(__file__).parent / "test_output")
    DEFAULT_METHODOLOGY = "AFML"
    
    AGENTS = [
        "08-DATA-QUALITY-AGENT",
        "01-DATA-AGENT", 
        "02-QUANT-AGENT",
        "03-RISK-AGENT",
        "04-COMPETITIVE-AGENT",
        "05-QUALITATIVE-AGENT",
        "06-SYNTHESIS-AGENT",
    ]


# =============================================================================
# DATA STRUCTURES
# =============================================================================

class AgentStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass
class DataGap:
    gap_id: str
    timestamp: str
    agent: str
    data_needed: str
    table_checked: str
    result: str
    workaround: str
    time_cost_minutes: int
    priority: str
    methodology_relevant: bool = False


@dataclass
class AgentResult:
    agent: str
    status: AgentStatus
    response: str
    data_gaps: List[DataGap] = field(default_factory=list)
    duration_seconds: float = 0
    error: Optional[str] = None


@dataclass
class SessionContext:
    ticker: str
    company_name: str
    session_id: str
    output_dir: Path
    start_time: datetime
    methodology: str = "AFML"
    data_gaps: List[DataGap] = field(default_factory=list)
    agent_results: Dict[str, AgentResult] = field(default_factory=dict)


# =============================================================================
# LOGGING
# =============================================================================

def log(message: str, style: str = "info"):
    timestamp = datetime.now().strftime("%H:%M:%S")
    if RICH_AVAILABLE:
        styles = {"info": "blue", "success": "green", "warning": "yellow", "error": "red", "header": "bold magenta"}
        console.print(f"[dim]{timestamp}[/dim] [{styles.get(style, 'white')}]{message}[/]")
    else:
        print(f"{timestamp} [{style}] {message}")


def print_header(title: str):
    if RICH_AVAILABLE:
        console.print(Panel(title, style="bold magenta"))
    else:
        print(f"\n{'='*60}\n{title}\n{'='*60}")


# =============================================================================
# CLAUDE CLI EXECUTOR
# =============================================================================

class ClaudeCliExecutor:
    """Executes agents via Claude CLI - uses existing authentication."""
    
    def __init__(self, methodology: str = "AFML"):
        self.prompts_dir = Path(Config.PROMPTS_DIR)
        self.prompts_cache: Dict[str, str] = {}
        self.methodology = MethodologyInjector(methodology)
        log(f"Using Claude CLI with {methodology} methodology", "info")
    
    def load_prompt(self, agent_name: str) -> str:
        if agent_name in self.prompts_cache:
            return self.prompts_cache[agent_name]
        
        prompt_file = self.prompts_dir / f"{agent_name}.md"
        if prompt_file.exists():
            prompt = prompt_file.read_text()
            self.prompts_cache[agent_name] = prompt
            return prompt
        
        return f"You are {agent_name}. Complete your assigned analysis task."
    
    def execute(self, agent_name: str, context: SessionContext, additional_context: str = "") -> AgentResult:
        log(f"Running {agent_name} via Claude CLI...", "info")
        start_time = datetime.now()
        
        try:
            # Build the full prompt
            system_prompt = self.load_prompt(agent_name)
            method_context = self.methodology.format_for_prompt(agent_name)
            
            if method_context:
                log(f"  + Injecting {context.methodology} methodology context", "info")
            
            user_message = self._build_user_message(agent_name, context, additional_context, method_context)
            
            # Combine system + user into single prompt for CLI
            full_prompt = f"""SYSTEM INSTRUCTIONS:
{system_prompt}

---

USER REQUEST:
{user_message}
"""
            
            # Call Claude CLI
            response = self._call_claude_cli(full_prompt)
            
            duration = (datetime.now() - start_time).total_seconds()
            data_gaps = self._extract_data_gaps(response, agent_name, context.session_id)
            
            result = AgentResult(
                agent=agent_name,
                status=AgentStatus.COMPLETE,
                response=response,
                data_gaps=data_gaps,
                duration_seconds=duration,
            )
            
            log(f"✓ {agent_name} complete ({duration:.1f}s)", "success")
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
    
    def _call_claude_cli(self, prompt: str) -> str:
        """Call Claude CLI with the prompt via stdin."""
        
        # Use stdin for prompt to avoid shell escaping issues with large prompts
        result = subprocess.run(
            ['claude', '--print', '--model', 'sonnet'],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout per agent
        )
        
        if result.returncode != 0:
            raise RuntimeError(f"Claude CLI error: {result.stderr}")
        
        return result.stdout.strip()
    
    def _build_user_message(
        self, 
        agent_name: str, 
        context: SessionContext, 
        additional_context: str,
        method_context: str
    ) -> str:
        """Build user message with methodology injection."""
        
        message = f"""
# Research Task

**Ticker**: {context.ticker}
**Company**: {context.company_name}
**Session ID**: {context.session_id}
**Timestamp**: {datetime.now().isoformat()}
**Methodology**: {context.methodology}

{method_context}

## Previous Agent Outputs
{additional_context if additional_context else "This is the first agent in the sequence."}

## Instructions
1. Complete your assigned analysis tasks
2. Log any data gaps you encounter (missing data, stale data, quality issues)
3. **For methodology-related gaps, mark them explicitly**
4. Output your results in structured JSON format where applicable

## Data Gap Logging Format
When you encounter missing or inadequate data, note it as:
```
DATA_GAP: {{
    "data_needed": "description",
    "table_checked": "table_name or N/A",
    "result": "NOT_AVAILABLE|STALE|INCOMPLETE|METHODOLOGY_MISSING",
    "workaround": "what you did instead",
    "time_cost_minutes": estimated_minutes,
    "priority": "P0|P1|P2|P3",
    "methodology_relevant": true|false
}}
```

**P0 for methodology gaps** = Blocks AFML analysis (e.g., no labels, no sample weights)
"""
        return message
    
    def _extract_data_gaps(self, response: str, agent_name: str, session_id: str) -> List[DataGap]:
        gaps = []
        import re
        pattern = r'DATA_GAP:\s*\{([^}]+)\}'
        matches = re.findall(pattern, response, re.DOTALL)
        
        for i, match in enumerate(matches):
            try:
                gap_data = json.loads('{' + match + '}')
                gap = DataGap(
                    gap_id=f"GAP-{session_id}-{agent_name}-{i:03d}",
                    timestamp=datetime.now().isoformat(),
                    agent=agent_name,
                    data_needed=gap_data.get("data_needed", "Unknown"),
                    table_checked=gap_data.get("table_checked", "N/A"),
                    result=gap_data.get("result", "NOT_AVAILABLE"),
                    workaround=gap_data.get("workaround", "None"),
                    time_cost_minutes=gap_data.get("time_cost_minutes", 5),
                    priority=gap_data.get("priority", "P2"),
                    methodology_relevant=gap_data.get("methodology_relevant", False)
                )
                gaps.append(gap)
            except:
                pass
        
        return gaps


# =============================================================================
# ORCHESTRATOR (Simplified for testing)
# =============================================================================

class ResearchOrchestrator:
    def __init__(self, methodology: str = Config.DEFAULT_METHODOLOGY):
        self.executor = ClaudeCliExecutor(methodology)
        self.methodology = methodology
    
    def run_single_agent(self, ticker: str, company_name: str, agent_name: str,
                         output_dir: Optional[str] = None) -> AgentResult:
        """Run a single agent for testing."""
        
        print_header(f"Single Agent Test: {agent_name}")
        log(f"Ticker: {ticker} ({company_name})", "info")
        log(f"Methodology: {self.methodology}", "info")
        
        session_id = f"{ticker}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        output_path = Path(output_dir or Config.OUTPUTS_DIR) / session_id
        output_path.mkdir(parents=True, exist_ok=True)
        
        context = SessionContext(
            ticker=ticker,
            company_name=company_name,
            session_id=session_id,
            output_dir=output_path,
            start_time=datetime.now(),
            methodology=self.methodology,
        )
        
        # Provide some mock database context
        db_context = """
Database Status (AFML tables):
- labels: 0 records (MISSING)
- sample_weights: 0 records (MISSING)  
- volatility: 0 records (MISSING)
- regime: 0 records (MISSING)
- cv_folds: 0 records (MISSING)

Standard Data:
- prices: Available (2019-2026)
- fundamentals: Partial (schema issues)
"""
        
        result = self.executor.execute(agent_name, context, db_context)
        
        # Save result
        filepath = output_path / f"{agent_name}_result.json"
        data = {
            "agent": result.agent,
            "status": result.status.value,
            "timestamp": datetime.now().isoformat(),
            "methodology": context.methodology,
            "response": result.response,
            "data_gaps": [asdict(g) for g in result.data_gaps],
            "duration_seconds": result.duration_seconds,
        }
        filepath.write_text(json.dumps(data, indent=2))
        log(f"Saved: {filepath}", "success")
        
        # Print summary
        print_header("Result Summary")
        log(f"Status: {result.status.value}", "success" if result.status == AgentStatus.COMPLETE else "error")
        log(f"Duration: {result.duration_seconds:.1f}s", "info")
        log(f"Data gaps found: {len(result.data_gaps)}", "info")
        
        methodology_gaps = [g for g in result.data_gaps if g.methodology_relevant]
        if methodology_gaps:
            log(f"  - AFML methodology gaps: {len(methodology_gaps)}", "warning")
            for gap in methodology_gaps:
                log(f"    [{gap.priority}] {gap.data_needed}", "warning")
        
        if result.response:
            log(f"\nResponse preview ({len(result.response)} chars):", "info")
            print(result.response[:1000] + "..." if len(result.response) > 1000 else result.response)
        
        return result


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Test AFML-aware agent via Claude CLI")
    parser.add_argument("ticker", help="Stock ticker")
    parser.add_argument("company_name", help="Company name")
    parser.add_argument("--agent", "-a", default="08-DATA-QUALITY-AGENT", 
                        help="Agent to test (default: 08-DATA-QUALITY-AGENT)")
    parser.add_argument("--output-dir", "-o", help="Output directory")
    parser.add_argument("--methodology", "-m", default="AFML")
    
    args = parser.parse_args()
    
    try:
        orchestrator = ResearchOrchestrator(methodology=args.methodology)
        orchestrator.run_single_agent(
            ticker=args.ticker.upper(),
            company_name=args.company_name,
            agent_name=args.agent,
            output_dir=args.output_dir,
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
