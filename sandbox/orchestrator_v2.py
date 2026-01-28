#!/usr/bin/env python3
"""
Multi-Agent Equity Research Orchestrator v2
============================================

Enhanced with methodology injection for AFML-aware agents.

Changes from v1:
- Added MethodologyInjector integration
- Agents receive relevant AFML context based on their role
- Data Quality Agent checks for AFML data structures
- Validation checks include AFML-specific requirements

Usage:
    python orchestrator_v2.py AAPL "Apple Inc."
    python orchestrator_v2.py CDE "Coeur Mining" --methodology AFML
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

# Import methodology injection
from methodology_injection import MethodologyInjector, AFML_CONCEPTS

# Add parent directory to path
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
    from rich.table import Table
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
    DB_PATH = str(RESEARCH_DB_PATH)
    PROMPTS_DIR = str(Path(__file__).parent.parent / "research")
    OUTPUTS_DIR = str(RESEARCH_OUTPUT_PATH)
    FEEDBACK_DIR = str(RESEARCH_FEEDBACK_PATH)
    
    AGENTS = [
        "08-DATA-QUALITY-AGENT",
        "01-DATA-AGENT", 
        "02-QUANT-AGENT",
        "03-RISK-AGENT",
        "04-COMPETITIVE-AGENT",
        "05-QUALITATIVE-AGENT",
        "06-SYNTHESIS-AGENT",
    ]
    
    # NEW: Default methodology
    DEFAULT_METHODOLOGY = "AFML"
    
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
# DATA STRUCTURES (unchanged)
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
    methodology_relevant: bool = False  # NEW: Flag if gap is methodology-related


@dataclass
class AgentResult:
    agent: str
    status: AgentStatus
    response: str
    data_gaps: List[DataGap] = field(default_factory=list)
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
    methodology: str = "AFML"  # NEW
    data_gaps: List[DataGap] = field(default_factory=list)
    agent_results: Dict[str, AgentResult] = field(default_factory=dict)
    database_available: bool = True
    db_path: str = Config.DB_PATH


@dataclass 
class SessionFeedback:
    session_id: str
    ticker: str
    date: str
    duration_minutes: float
    methodology: str  # NEW
    efficiency_metrics: Dict[str, Any]
    data_gaps: List[Dict]
    methodology_gaps: List[Dict]  # NEW: Separate tracking
    schema_improvements: List[Dict]
    system_health: Dict[str, Any]


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
# AGENT EXECUTOR WITH METHODOLOGY INJECTION
# =============================================================================

class AgentExecutor:
    """Executes agents with methodology-aware context injection."""
    
    def __init__(self, api_key: Optional[str] = None, methodology: str = "AFML"):
        if api_key:
            self.api_key = api_key
        else:
            self.api_key = Config.get_api_key()
        
        self.client = anthropic.Anthropic(api_key=self.api_key)
        self.prompts_dir = Path(Config.PROMPTS_DIR)
        self.prompts_cache: Dict[str, str] = {}
        
        # NEW: Initialize methodology injector
        self.methodology = MethodologyInjector(methodology)
        log(f"Methodology injector initialized: {methodology}", "info")
    
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
        log(f"Running {agent_name}...", "info")
        start_time = datetime.now()
        
        try:
            system_prompt = self.load_prompt(agent_name)
            
            # NEW: Inject methodology context
            method_context = self.methodology.format_for_prompt(agent_name)
            if method_context:
                log(f"  + Injecting {context.methodology} methodology context", "info")
            
            user_message = self._build_user_message(agent_name, context, additional_context, method_context)
            
            response = self.client.messages.create(
                model=Config.MODEL,
                max_tokens=Config.MAX_TOKENS,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}]
            )
            
            duration = (datetime.now() - start_time).total_seconds()
            data_gaps = self._extract_data_gaps(response.content[0].text, agent_name, context.session_id)
            
            result = AgentResult(
                agent=agent_name,
                status=AgentStatus.COMPLETE,
                response=response.content[0].text,
                data_gaps=data_gaps,
                duration_seconds=duration,
                tokens_used=response.usage.input_tokens + response.usage.output_tokens
            )
            
            log(f"✓ {agent_name} complete ({duration:.1f}s, {result.tokens_used} tokens)", "success")
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
    
    def _build_user_message(
        self, 
        agent_name: str, 
        context: SessionContext, 
        additional_context: str,
        method_context: str  # NEW parameter
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
3. **For methodology-related gaps, mark them explicitly** (e.g., missing labels table)
4. Output your results in structured JSON format where applicable

## Data Gap Logging Format
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
# DATABASE MANAGER (unchanged from v1)
# =============================================================================

class DatabaseManager:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.connection = None
    
    def connect(self) -> bool:
        try:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            self.connection = duckdb.connect(self.db_path)
            return True
        except Exception as e:
            log(f"Database connection failed: {e}", "error")
            return False
    
    def close(self):
        if self.connection:
            self.connection.close()
    
    def execute(self, query: str) -> Dict[str, Any]:
        try:
            result = self.connection.execute(query).fetchdf()
            return {"success": True, "data": result.to_dict('records'), "row_count": len(result)}
        except Exception as e:
            return {"success": False, "error": str(e), "data": [], "row_count": 0}
    
    def initialize_schema(self):
        """Initialize schema including AFML tables."""
        schema = """
        -- Standard tables
        CREATE TABLE IF NOT EXISTS prices (
            ticker VARCHAR, date DATE, open DECIMAL, high DECIMAL, low DECIMAL,
            close DECIMAL, adj_close DECIMAL, volume BIGINT,
            PRIMARY KEY (ticker, date)
        );
        
        CREATE TABLE IF NOT EXISTS fundamentals (
            ticker VARCHAR, period_end DATE, period_type VARCHAR,
            revenue DECIMAL, gross_profit DECIMAL, operating_income DECIMAL,
            net_income DECIMAL, eps DECIMAL, pe_ratio DECIMAL, market_cap DECIMAL,
            PRIMARY KEY (ticker, period_end, period_type)
        );
        
        CREATE TABLE IF NOT EXISTS social_metrics (
            ticker VARCHAR, date DATE, source VARCHAR,
            mention_count INT, sentiment_score DECIMAL, bullish_count INT, bearish_count INT,
            PRIMARY KEY (ticker, date, source)
        );
        
        CREATE TABLE IF NOT EXISTS filings (
            ticker VARCHAR, filing_type VARCHAR, filing_date DATE, url VARCHAR,
            PRIMARY KEY (ticker, filing_type, filing_date)
        );
        
        -- AFML-specific tables (NEW)
        CREATE TABLE IF NOT EXISTS labels (
            ticker VARCHAR,
            event_time TIMESTAMP,
            label INT,
            return_pct DECIMAL,
            exit_time TIMESTAMP,
            exit_type VARCHAR,
            volatility DECIMAL,
            profit_take DECIMAL,
            stop_loss DECIMAL,
            max_holding INT,
            PRIMARY KEY (ticker, event_time)
        );
        
        CREATE TABLE IF NOT EXISTS sample_weights (
            ticker VARCHAR,
            event_time TIMESTAMP,
            weight DECIMAL,
            concurrency INT,
            uniqueness DECIMAL,
            PRIMARY KEY (ticker, event_time)
        );
        
        CREATE TABLE IF NOT EXISTS volatility (
            ticker VARCHAR,
            date DATE,
            vol_20d DECIMAL,
            vol_60d DECIMAL,
            vol_120d DECIMAL,
            PRIMARY KEY (ticker, date)
        );
        
        CREATE TABLE IF NOT EXISTS regime (
            ticker VARCHAR,
            date DATE,
            regime_state VARCHAR,
            cusum_value DECIMAL,
            confidence DECIMAL,
            PRIMARY KEY (ticker, date)
        );
        
        CREATE TABLE IF NOT EXISTS cv_folds (
            ticker VARCHAR,
            fold_id INT,
            n_splits INT,
            embargo_pct DECIMAL,
            train_size INT,
            test_size INT,
            purged_count INT,
            created_at TIMESTAMP,
            PRIMARY KEY (ticker, fold_id)
        );
        
        -- Improvement backlog
        CREATE TABLE IF NOT EXISTS improvement_backlog (
            gap_id VARCHAR PRIMARY KEY,
            description VARCHAR,
            first_reported DATE,
            sessions_impacted INT DEFAULT 1,
            total_time_lost_minutes INT,
            priority VARCHAR,
            methodology_relevant BOOLEAN DEFAULT FALSE,
            status VARCHAR DEFAULT 'OPEN'
        );
        """
        
        for statement in schema.split(';'):
            if statement.strip():
                self.execute(statement)
        
        log("Database schema initialized (including AFML tables)", "success")
    
    def check_afml_data(self, ticker: str) -> Dict[str, Any]:
        """NEW: Check AFML-specific data availability."""
        afml_tables = ['labels', 'sample_weights', 'volatility', 'regime', 'cv_folds']
        availability = {}
        
        for table in afml_tables:
            query = f"SELECT COUNT(*) as cnt FROM {table} WHERE ticker = '{ticker}'"
            result = self.execute(query)
            
            if result["success"] and result["data"]:
                cnt = result["data"][0].get("cnt", 0)
                availability[table] = {
                    "available": cnt > 0,
                    "record_count": cnt,
                    "status": "OK" if cnt > 0 else "MISSING"
                }
            else:
                availability[table] = {
                    "available": False,
                    "record_count": 0,
                    "status": "TABLE_ERROR",
                    "error": result.get("error")
                }
        
        return availability


# =============================================================================
# ORCHESTRATOR
# =============================================================================

class ResearchOrchestrator:
    def __init__(self, api_key: Optional[str] = None, db_path: str = Config.DB_PATH, 
                 methodology: str = Config.DEFAULT_METHODOLOGY):
        self.executor = AgentExecutor(api_key, methodology)
        self.db = DatabaseManager(db_path)
        self.db_path = db_path
        self.methodology = methodology
    
    def run(self, ticker: str, company_name: str, 
            output_dir: Optional[str] = None,
            skip_db_check: bool = False) -> SessionContext:
        
        print_header(f"Multi-Agent Research: {ticker} ({company_name})")
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
            db_path=self.db_path
        )
        
        log(f"Session ID: {session_id}", "info")
        log(f"Output directory: {output_path}", "info")
        
        # Phase 0: Database + AFML Check
        print_header("Phase 0: Database & Methodology Assessment")
        
        db_context = ""
        afml_context = ""
        
        if not skip_db_check and self.db.connect():
            self.db.initialize_schema()
            
            # Standard data check
            standard_result = self.db.execute(f"""
                SELECT 'prices' as tbl, COUNT(*) as cnt FROM prices WHERE ticker = '{ticker}'
                UNION ALL
                SELECT 'fundamentals', COUNT(*) FROM fundamentals WHERE ticker = '{ticker}'
            """)
            
            # NEW: AFML data check
            afml_availability = self.db.check_afml_data(ticker)
            
            log("AFML Data Availability:", "header")
            for table, info in afml_availability.items():
                status_icon = "✓" if info["available"] else "✗"
                log(f"  {status_icon} {table}: {info['record_count']} records ({info['status']})", 
                    "success" if info["available"] else "warning")
            
            db_context = f"Standard data: {json.dumps(standard_result.get('data', []), indent=2)}"
            afml_context = f"AFML data availability:\n{json.dumps(afml_availability, indent=2)}"
            context.database_available = True
        else:
            log("Skipping database check", "warning")
            db_context = "Database not available."
            afml_context = "AFML data not checked."
            context.database_available = False
        
        combined_db_context = f"{db_context}\n\n{afml_context}"
        
        # Run agents with methodology injection
        dq_result = self.executor.execute("08-DATA-QUALITY-AGENT", context, combined_db_context)
        context.agent_results["08-DATA-QUALITY-AGENT"] = dq_result
        context.data_gaps.extend(dq_result.data_gaps)
        self._save_result(context, "data_availability.json", dq_result)
        
        print_header("Phase 1: Data Collection")
        data_result = self.executor.execute("01-DATA-AGENT", context, 
            f"Data Quality Assessment:\n{dq_result.response[:2000]}...")
        context.agent_results["01-DATA-AGENT"] = data_result
        context.data_gaps.extend(data_result.data_gaps)
        self._save_result(context, "coverage_log.json", data_result)
        
        print_header("Phase 2: Analysis")
        analysis_context = f"Coverage data:\n{data_result.response[:2000]}..."
        
        for agent_name in ["02-QUANT-AGENT", "03-RISK-AGENT", "04-COMPETITIVE-AGENT", "05-QUALITATIVE-AGENT"]:
            result = self.executor.execute(agent_name, context, analysis_context)
            context.agent_results[agent_name] = result
            context.data_gaps.extend(result.data_gaps)
            
            output_name = {
                "02-QUANT-AGENT": "valuation_package.json",
                "03-RISK-AGENT": "risk_assessment.json",
                "04-COMPETITIVE-AGENT": "competitive_analysis.json",
                "05-QUALITATIVE-AGENT": "qualitative_assessment.json"
            }[agent_name]
            self._save_result(context, output_name, result)
        
        print_header("Phase 3: Synthesis")
        all_results = {name: result.response[:3000] for name, result in context.agent_results.items()}
        synthesis_result = self.executor.execute("06-SYNTHESIS-AGENT", context,
            f"All agent results:\n{json.dumps(all_results, indent=2)}")
        context.agent_results["06-SYNTHESIS-AGENT"] = synthesis_result
        self._save_result(context, "final_memo.md", synthesis_result, is_markdown=True)
        
        print_header("Phase 4: Feedback")
        feedback = self._generate_feedback(context)
        self._save_feedback(context, feedback)
        self._print_summary(context, feedback)
        
        if self.db.connection:
            self.db.close()
        
        return context
    
    def _save_result(self, context: SessionContext, filename: str, result: AgentResult, is_markdown: bool = False):
        filepath = context.output_dir / filename
        if is_markdown:
            filepath.write_text(result.response)
        else:
            data = {
                "agent": result.agent,
                "status": result.status.value,
                "timestamp": datetime.now().isoformat(),
                "methodology": context.methodology,
                "response": result.response,
                "data_gaps": [asdict(g) for g in result.data_gaps],
                "duration_seconds": result.duration_seconds,
                "tokens_used": result.tokens_used
            }
            filepath.write_text(json.dumps(data, indent=2))
        log(f"Saved: {filename}", "info")
    
    def _generate_feedback(self, context: SessionContext) -> SessionFeedback:
        total_duration = (datetime.now() - context.start_time).total_seconds() / 60
        
        # Separate methodology gaps
        methodology_gaps = [g for g in context.data_gaps if g.methodology_relevant]
        standard_gaps = [g for g in context.data_gaps if not g.methodology_relevant]
        
        total_gaps = len(context.data_gaps)
        db_hit_rate = 1 - (total_gaps / max(total_gaps + 20, 1))
        
        return SessionFeedback(
            session_id=context.session_id,
            ticker=context.ticker,
            date=datetime.now().isoformat(),
            duration_minutes=total_duration,
            methodology=context.methodology,
            efficiency_metrics={
                "database_hit_rate": round(db_hit_rate, 2),
                "total_data_gaps": total_gaps,
                "methodology_gaps": len(methodology_gaps),
                "standard_gaps": len(standard_gaps),
            },
            data_gaps=[asdict(g) for g in standard_gaps],
            methodology_gaps=[asdict(g) for g in methodology_gaps],
            schema_improvements=[],
            system_health={
                "target_hit_rate": 0.80,
                "current_hit_rate": round(db_hit_rate, 2),
                "methodology_readiness": "LOW" if methodology_gaps else "OK"
            }
        )
    
    def _save_feedback(self, context: SessionContext, feedback: SessionFeedback):
        filepath = context.output_dir / "session_feedback.json"
        filepath.write_text(json.dumps(asdict(feedback), indent=2))
        log(f"Feedback saved", "success")
    
    def _print_summary(self, context: SessionContext, feedback: SessionFeedback):
        print_header("Session Summary")
        
        log(f"Session: {context.session_id}", "info")
        log(f"Methodology: {feedback.methodology}", "info")
        log(f"Duration: {feedback.duration_minutes:.1f} min", "info")
        log(f"Total gaps: {feedback.efficiency_metrics['total_data_gaps']}", "info")
        log(f"  - Methodology gaps: {feedback.efficiency_metrics['methodology_gaps']}", 
            "warning" if feedback.efficiency_metrics['methodology_gaps'] > 0 else "success")
        log(f"  - Standard gaps: {feedback.efficiency_metrics['standard_gaps']}", "info")
        log(f"Methodology readiness: {feedback.system_health['methodology_readiness']}", 
            "warning" if feedback.system_health['methodology_readiness'] == "LOW" else "success")
        
        log(f"\n✅ Output: {context.output_dir / 'final_memo.md'}", "success")


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Multi-Agent Research Orchestrator v2 (AFML-aware)")
    parser.add_argument("ticker", help="Stock ticker")
    parser.add_argument("company_name", help="Company name")
    parser.add_argument("--output-dir", "-o", help="Output directory")
    parser.add_argument("--db-path", "-d", default=Config.DB_PATH)
    parser.add_argument("--methodology", "-m", default="AFML", help="Methodology: AFML (default)")
    parser.add_argument("--skip-db-check", action="store_true")
    parser.add_argument("--api-key", "-k", help="Anthropic API key")
    
    args = parser.parse_args()
    
    api_key = args.api_key or os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY not set.")
        sys.exit(1)
    
    try:
        orchestrator = ResearchOrchestrator(
            api_key=api_key, 
            db_path=args.db_path,
            methodology=args.methodology
        )
        orchestrator.run(
            ticker=args.ticker.upper(),
            company_name=args.company_name,
            output_dir=args.output_dir,
            skip_db_check=args.skip_db_check
        )
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
