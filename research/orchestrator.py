#!/usr/bin/env python3
"""
Multi-Agent Equity Research Orchestrator
=========================================

Coordinates the research loop with database-first approach and continuous feedback.

Usage:
    python orchestrator.py AAPL "Apple Inc."
    python orchestrator.py MSFT "Microsoft Corporation" --output-dir ./research
    python orchestrator.py GOOGL "Alphabet Inc." --skip-db-check

Requirements:
    pip install anthropic duckdb pandas pyarrow rich

Environment:
    ANTHROPIC_API_KEY=your_api_key_here
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

# Add parent directory to path to import config
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import main config
try:
    from config import (
        RESEARCH_DB_PATH,
        RESEARCH_OUTPUT_PATH,
        RESEARCH_FEEDBACK_PATH,
        get_anthropic_api_key,
    )
    CONFIG_AVAILABLE = True
except ImportError:
    # Fallback if config not available
    CONFIG_AVAILABLE = False
    RESEARCH_DB_PATH = Path("data/research.duckdb")
    RESEARCH_OUTPUT_PATH = Path("outputs")
    RESEARCH_FEEDBACK_PATH = Path("feedback")

# Optional: Rich for better terminal output
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich.table import Table
    from rich.markdown import Markdown
    RICH_AVAILABLE = True
    console = Console()
except ImportError:
    RICH_AVAILABLE = False
    console = None


# =============================================================================
# CONFIGURATION
# =============================================================================

class Config:
    """Central configuration"""
    MODEL = "claude-sonnet-4-20250514"
    MAX_TOKENS = 8000
    DB_PATH = str(RESEARCH_DB_PATH)
    PROMPTS_DIR = str(Path(__file__).parent)  # Use research/ dir for prompt .md files
    OUTPUTS_DIR = str(RESEARCH_OUTPUT_PATH)
    FEEDBACK_DIR = str(RESEARCH_FEEDBACK_PATH)
    
    # Agent execution order
    AGENTS = [
        "08-DATA-QUALITY-AGENT",
        "01-DATA-AGENT", 
        "02-QUANT-AGENT",
        "03-RISK-AGENT",
        "04-COMPETITIVE-AGENT",
        "05-QUALITATIVE-AGENT",
        "06-SYNTHESIS-AGENT",
    ]
    
    @staticmethod
    def get_api_key():
        """Get Anthropic API key from environment or main config."""
        if CONFIG_AVAILABLE:
            try:
                return get_anthropic_api_key()
            except ValueError:
                pass
        
        # Fallback to environment variable
        key = os.getenv("ANTHROPIC_API_KEY")
        if not key:
            raise ValueError(
                "ANTHROPIC_API_KEY not set. "
                "Add it to .env file or set as environment variable."
            )
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
class DataGap:
    """Represents a data gap encountered during research"""
    gap_id: str
    timestamp: str
    agent: str
    data_needed: str
    table_checked: str
    result: str  # NOT_AVAILABLE, FIELD_NOT_EXISTS, STALE, etc.
    workaround: str
    time_cost_minutes: int
    priority: str  # P0, P1, P2, P3


@dataclass
class AgentResult:
    """Result from an agent execution"""
    agent: str
    status: AgentStatus
    response: str
    data_gaps: List[DataGap] = field(default_factory=list)
    duration_seconds: float = 0
    tokens_used: int = 0
    error: Optional[str] = None


@dataclass
class SessionContext:
    """Context maintained throughout a research session"""
    ticker: str
    company_name: str
    session_id: str
    output_dir: Path
    start_time: datetime
    data_gaps: List[DataGap] = field(default_factory=list)
    agent_results: Dict[str, AgentResult] = field(default_factory=dict)
    database_available: bool = True
    db_path: str = Config.DB_PATH


@dataclass 
class SessionFeedback:
    """End-of-session feedback for system improvement"""
    session_id: str
    ticker: str
    date: str
    duration_minutes: float
    efficiency_metrics: Dict[str, Any]
    data_gaps: List[Dict]
    schema_improvements: List[Dict]
    system_health: Dict[str, Any]


# =============================================================================
# LOGGING & OUTPUT
# =============================================================================

def log(message: str, style: str = "info"):
    """Log a message with optional styling"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    
    if RICH_AVAILABLE:
        styles = {
            "info": "blue",
            "success": "green",
            "warning": "yellow", 
            "error": "red",
            "header": "bold magenta"
        }
        console.print(f"[dim]{timestamp}[/dim] [{styles.get(style, 'white')}]{message}[/]")
    else:
        prefixes = {
            "info": "ℹ️ ",
            "success": "✅",
            "warning": "⚠️ ",
            "error": "❌",
            "header": "📋"
        }
        print(f"{timestamp} {prefixes.get(style, '')} {message}")


def print_header(title: str):
    """Print a section header"""
    if RICH_AVAILABLE:
        console.print(Panel(title, style="bold magenta"))
    else:
        print(f"\n{'='*60}\n{title}\n{'='*60}")


def print_table(title: str, data: Dict[str, Any]):
    """Print data as a table"""
    if RICH_AVAILABLE:
        table = Table(title=title)
        table.add_column("Field", style="cyan")
        table.add_column("Value", style="white")
        for k, v in data.items():
            table.add_row(str(k), str(v))
        console.print(table)
    else:
        print(f"\n{title}")
        print("-" * 40)
        for k, v in data.items():
            print(f"  {k}: {v}")


# =============================================================================
# DATABASE OPERATIONS
# =============================================================================

class DatabaseManager:
    """Handles all database operations"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.connection = None
    
    def connect(self) -> bool:
        """Establish database connection"""
        try:
            # Create directory if needed
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            self.connection = duckdb.connect(self.db_path)
            return True
        except Exception as e:
            log(f"Database connection failed: {e}", "error")
            return False
    
    def close(self):
        """Close database connection"""
        if self.connection:
            self.connection.close()
    
    def execute(self, query: str) -> Dict[str, Any]:
        """Execute a query and return results"""
        try:
            result = self.connection.execute(query).fetchdf()
            return {
                "success": True,
                "data": result.to_dict('records'),
                "columns": list(result.columns),
                "row_count": len(result)
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "data": [],
                "row_count": 0
            }
    
    def check_tables(self) -> List[str]:
        """Get list of available tables"""
        result = self.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'main'
        """)
        if result["success"]:
            return [row["table_name"] for row in result["data"]]
        return []
    
    def check_ticker_availability(self, ticker: str) -> Dict[str, Any]:
        """Check data availability for a specific ticker"""
        availability = {}
        tables = self.check_tables()
        
        for table in tables:
            # Get count and date range
            query = f"""
                SELECT 
                    COUNT(*) as record_count,
                    MIN(date) as earliest_date,
                    MAX(date) as latest_date
                FROM {table}
                WHERE ticker = '{ticker}'
            """
            result = self.execute(query)
            
            if result["success"] and result["data"]:
                row = result["data"][0]
                days_stale = None
                if row.get("latest_date"):
                    try:
                        latest = datetime.strptime(str(row["latest_date"])[:10], "%Y-%m-%d")
                        days_stale = (datetime.now() - latest).days
                    except:
                        pass
                
                availability[table] = {
                    "available": row["record_count"] > 0,
                    "record_count": row["record_count"],
                    "earliest_date": str(row.get("earliest_date", "N/A")),
                    "latest_date": str(row.get("latest_date", "N/A")),
                    "days_stale": days_stale
                }
            else:
                availability[table] = {
                    "available": False,
                    "record_count": 0,
                    "error": result.get("error")
                }
        
        return availability
    
    def initialize_schema(self):
        """Create tables if they don't exist"""
        schema = """
        -- Price data
        CREATE TABLE IF NOT EXISTS prices (
            ticker VARCHAR,
            date DATE,
            open DECIMAL,
            high DECIMAL,
            low DECIMAL,
            close DECIMAL,
            adj_close DECIMAL,
            volume BIGINT,
            PRIMARY KEY (ticker, date)
        );

        -- Fundamental data  
        CREATE TABLE IF NOT EXISTS fundamentals (
            ticker VARCHAR,
            period_end DATE,
            period_type VARCHAR,
            revenue DECIMAL,
            gross_profit DECIMAL,
            operating_income DECIMAL,
            net_income DECIMAL,
            eps DECIMAL,
            pe_ratio DECIMAL,
            market_cap DECIMAL,
            PRIMARY KEY (ticker, period_end, period_type)
        );

        -- Social metrics
        CREATE TABLE IF NOT EXISTS social_metrics (
            ticker VARCHAR,
            date DATE,
            source VARCHAR,
            mention_count INT,
            sentiment_score DECIMAL,
            bullish_count INT,
            bearish_count INT,
            PRIMARY KEY (ticker, date, source)
        );

        -- SEC filings metadata
        CREATE TABLE IF NOT EXISTS filings (
            ticker VARCHAR,
            filing_type VARCHAR,
            filing_date DATE,
            url VARCHAR,
            PRIMARY KEY (ticker, filing_type, filing_date)
        );

        -- Improvement backlog
        CREATE TABLE IF NOT EXISTS improvement_backlog (
            gap_id VARCHAR PRIMARY KEY,
            description VARCHAR,
            first_reported DATE,
            sessions_impacted INT DEFAULT 1,
            total_time_lost_minutes INT,
            priority VARCHAR,
            status VARCHAR DEFAULT 'OPEN',
            resolution_date DATE
        );
        """
        
        for statement in schema.split(';'):
            if statement.strip():
                self.execute(statement)
        
        log("Database schema initialized", "success")


# =============================================================================
# PROMPT MANAGEMENT
# =============================================================================

class PromptManager:
    """Manages agent prompts"""
    
    def __init__(self, prompts_dir: str = Config.PROMPTS_DIR):
        self.prompts_dir = Path(prompts_dir)
        self.prompts_cache: Dict[str, str] = {}
    
    def load_prompt(self, agent_name: str) -> str:
        """Load prompt for an agent"""
        
        # Check cache first
        if agent_name in self.prompts_cache:
            return self.prompts_cache[agent_name]
        
        # Try to load from file
        prompt_file = self.prompts_dir / f"{agent_name}.md"
        
        if prompt_file.exists():
            prompt = prompt_file.read_text()
            self.prompts_cache[agent_name] = prompt
            return prompt
        
        # Return embedded fallback prompt
        return self._get_fallback_prompt(agent_name)
    
    def _get_fallback_prompt(self, agent_name: str) -> str:
        """Return embedded fallback prompts if files not available"""
        
        fallbacks = {
            "08-DATA-QUALITY-AGENT": """
You are the DATA_QUALITY_AGENT responsible for:
1. Assessing data availability in the native database (Parquet/DuckDB)
2. Identifying data gaps and quality issues
3. Logging all data friction points
4. Generating feedback for system improvement

For each research session:
- First check what data exists in the database
- Assess freshness, completeness, accuracy
- Output a data_availability.json structure
- Track all gaps encountered for the feedback loop

Output JSON with: database_status, data_gaps, recommendations
""",
            "01-DATA-AGENT": """
You are the DATA_AGENT responsible for:
1. Gathering 60+ unique, verifiable sources
2. Filling gaps identified by DATA_QUALITY_AGENT
3. Validating coverage against thresholds

Requirements:
- ≥60 unique sources (by domain + title)
- ≥10 high-quality media sources
- ≥5 competitor primary sources  
- ≥5 academic/expert sources
- ≥60% dated within 24 months
- ≤10% from any single domain

Output JSON with: coverage_log, coverage_validator
""",
            "02-QUANT-AGENT": """
You are the QUANT_AGENT responsible for:
1. Building DCF models with explicit assumptions
2. Creating comparable company analysis
3. Calculating expected total return (E[TR])
4. Analyzing unit economics

Show all math. State all assumptions. Include sensitivities.

Output JSON with: fair_value_band, E_TR, margin_of_safety, skew_ratio, unit_economics
""",
            "03-RISK-AGENT": """
You are the RISK_AGENT responsible for:
1. Building the bear case scenario
2. Analyzing capital structure and covenants
3. Creating risk inventory with mitigants
4. Defining stop-loss triggers

Lead with downside. Quantify all risks.

Output JSON with: bear_case, downside_metrics, capital_structure, risk_inventory, stop_loss_trigger
""",
            "04-COMPETITIVE-AGENT": """
You are the COMPETITIVE_AGENT responsible for:
1. Sizing the market (TAM/SAM/SOM)
2. Mapping competitive landscape
3. Assessing moat strength
4. Analyzing pricing power

Output JSON with: market_structure, competitive_landscape, moat_assessment, pricing_power
""",
            "05-QUALITATIVE-AGENT": """
You are the QUALITATIVE_AGENT responsible for:
1. Assessing management track record
2. Evaluating execution quality
3. Analyzing customer sentiment
4. Identifying leadership gaps

Output JSON with: execution_quality, management_assessment, customer_sentiment, leadership_gaps
""",
            "06-SYNTHESIS-AGENT": """
You are the SYNTHESIS_AGENT responsible for:
1. Integrating all agent outputs into a coherent memo
2. Drafting the Executive Summary (MUST BE FIRST)
3. Writing all 21 sections with [Fact/Analysis/Inference] labels
4. Including the Data Infrastructure Feedback appendix

Output: Complete investment memo in markdown format
"""
        }
        
        return fallbacks.get(agent_name, f"You are {agent_name}. Complete your assigned analysis task.")


# =============================================================================
# AGENT EXECUTION
# =============================================================================

class AgentExecutor:
    """Executes individual agents via the Anthropic API"""
    
    def __init__(self, api_key: Optional[str] = None):
        # Use provided API key, or get from Config (which checks .env)
        if api_key:
            self.api_key = api_key
        else:
            try:
                self.api_key = Config.get_api_key()
            except ValueError as e:
                raise ValueError(f"ANTHROPIC_API_KEY not set. {e}")
        
        self.client = anthropic.Anthropic(api_key=self.api_key)
        self.prompt_manager = PromptManager()
    
    def execute(self, agent_name: str, context: SessionContext, additional_context: str = "") -> AgentResult:
        """Execute an agent and return results"""
        
        log(f"Running {agent_name}...", "info")
        start_time = datetime.now()
        
        try:
            # Load system prompt
            system_prompt = self.prompt_manager.load_prompt(agent_name)
            
            # Build user message
            user_message = self._build_user_message(agent_name, context, additional_context)
            
            # Call API
            response = self.client.messages.create(
                model=Config.MODEL,
                max_tokens=Config.MAX_TOKENS,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}]
            )
            
            duration = (datetime.now() - start_time).total_seconds()
            
            # Parse response for data gaps
            data_gaps = self._extract_data_gaps(response.content[0].text, agent_name)
            
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
    
    def _build_user_message(self, agent_name: str, context: SessionContext, additional_context: str) -> str:
        """Build the user message for an agent"""
        
        message = f"""
# Research Task

**Ticker**: {context.ticker}
**Company**: {context.company_name}
**Session ID**: {context.session_id}
**Timestamp**: {datetime.now().isoformat()}

## Previous Agent Outputs
{additional_context if additional_context else "This is the first agent in the sequence."}

## Instructions
1. Complete your assigned analysis tasks
2. Log any data gaps you encounter (missing data, stale data, quality issues)
3. Output your results in structured JSON format where applicable
4. Be explicit about assumptions and uncertainties

## Data Gap Logging Format
When you encounter missing or inadequate data, note it as:
```
DATA_GAP: {{
    "data_needed": "description",
    "table_checked": "table_name or N/A",
    "result": "NOT_AVAILABLE|STALE|INCOMPLETE",
    "workaround": "what you did instead",
    "time_cost_minutes": estimated_minutes,
    "priority": "P0|P1|P2|P3"
}}
```
"""
        return message
    
    def _extract_data_gaps(self, response: str, agent_name: str) -> List[DataGap]:
        """Extract data gaps from agent response"""
        gaps = []
        
        # Look for DATA_GAP markers in response
        import re
        pattern = r'DATA_GAP:\s*\{([^}]+)\}'
        matches = re.findall(pattern, response, re.DOTALL)
        
        for i, match in enumerate(matches):
            try:
                # Try to parse as JSON-like structure
                gap_data = json.loads('{' + match + '}')
                gap = DataGap(
                    gap_id=f"GAP-{context.session_id}-{agent_name}-{i:03d}",
                    timestamp=datetime.now().isoformat(),
                    agent=agent_name,
                    data_needed=gap_data.get("data_needed", "Unknown"),
                    table_checked=gap_data.get("table_checked", "N/A"),
                    result=gap_data.get("result", "NOT_AVAILABLE"),
                    workaround=gap_data.get("workaround", "None"),
                    time_cost_minutes=gap_data.get("time_cost_minutes", 5),
                    priority=gap_data.get("priority", "P2")
                )
                gaps.append(gap)
            except:
                pass  # Skip malformed gap entries
        
        return gaps


# =============================================================================
# MAIN ORCHESTRATOR
# =============================================================================

class ResearchOrchestrator:
    """Main orchestrator that coordinates the research loop"""
    
    def __init__(self, api_key: Optional[str] = None, db_path: str = Config.DB_PATH):
        self.executor = AgentExecutor(api_key)
        self.db = DatabaseManager(db_path)
        self.db_path = db_path
    
    def run(self, ticker: str, company_name: str, 
            output_dir: Optional[str] = None,
            skip_db_check: bool = False) -> SessionContext:
        """Execute the full research loop"""
        
        print_header(f"Multi-Agent Research: {ticker} ({company_name})")
        
        # Initialize session
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
        log(f"Output directory: {output_path}", "info")
        
        # =========================
        # PHASE 0: Database Check
        # =========================
        print_header("Phase 0: Database Assessment")
        
        db_context = ""
        if not skip_db_check and self.db.connect():
            self.db.initialize_schema()
            availability = self.db.check_ticker_availability(ticker)
            
            print_table("Database Availability", {
                table: f"{info.get('record_count', 0)} records, {info.get('days_stale', 'N/A')} days old"
                for table, info in availability.items()
            })
            
            db_context = f"Database availability:\n{json.dumps(availability, indent=2)}"
            context.database_available = True
        else:
            log("Skipping database check or database unavailable", "warning")
            db_context = "Database not available. Use external sources only."
            context.database_available = False
        
        # Run DATA_QUALITY_AGENT
        dq_result = self.executor.execute("08-DATA-QUALITY-AGENT", context, db_context)
        context.agent_results["08-DATA-QUALITY-AGENT"] = dq_result
        context.data_gaps.extend(dq_result.data_gaps)
        self._save_result(context, "data_availability.json", dq_result)
        
        # =========================
        # PHASE 1: Data Collection
        # =========================
        print_header("Phase 1: Data Collection")
        
        data_result = self.executor.execute(
            "01-DATA-AGENT", 
            context,
            f"Data Quality Assessment:\n{dq_result.response[:2000]}..."
        )
        context.agent_results["01-DATA-AGENT"] = data_result
        context.data_gaps.extend(data_result.data_gaps)
        self._save_result(context, "coverage_log.json", data_result)
        
        # =========================
        # PHASE 2: Analysis
        # =========================
        print_header("Phase 2: Parallel Analysis")
        
        analysis_context = f"Coverage data available:\n{data_result.response[:2000]}..."
        
        # Run analysis agents
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
        
        # =========================
        # PHASE 3: Synthesis
        # =========================
        print_header("Phase 3: Synthesis")
        
        # Compile all results for synthesis
        all_results = {
            name: result.response[:3000] 
            for name, result in context.agent_results.items()
        }
        
        synthesis_result = self.executor.execute(
            "06-SYNTHESIS-AGENT",
            context,
            f"All agent results:\n{json.dumps(all_results, indent=2)}"
        )
        context.agent_results["06-SYNTHESIS-AGENT"] = synthesis_result
        self._save_result(context, "final_memo.md", synthesis_result, is_markdown=True)
        
        # =========================
        # PHASE 4: Feedback Loop
        # =========================
        print_header("Phase 4: Feedback Generation")
        
        feedback = self._generate_feedback(context)
        self._save_feedback(context, feedback)
        self._update_backlog(feedback)
        
        # =========================
        # Summary
        # =========================
        self._print_summary(context, feedback)
        
        # Cleanup
        if self.db.connection:
            self.db.close()
        
        return context
    
    def _save_result(self, context: SessionContext, filename: str, result: AgentResult, is_markdown: bool = False):
        """Save agent result to file"""
        filepath = context.output_dir / filename
        
        if is_markdown:
            filepath.write_text(result.response)
        else:
            data = {
                "agent": result.agent,
                "status": result.status.value,
                "timestamp": datetime.now().isoformat(),
                "response": result.response,
                "data_gaps": [asdict(g) for g in result.data_gaps],
                "duration_seconds": result.duration_seconds,
                "tokens_used": result.tokens_used
            }
            filepath.write_text(json.dumps(data, indent=2))
        
        log(f"Saved: {filename}", "info")
    
    def _generate_feedback(self, context: SessionContext) -> SessionFeedback:
        """Generate session feedback"""
        
        total_duration = (datetime.now() - context.start_time).total_seconds() / 60
        total_gaps = len(context.data_gaps)
        total_workaround_time = sum(g.time_cost_minutes for g in context.data_gaps)
        
        # Calculate database hit rate (estimate)
        # In a real implementation, you'd track actual DB queries vs external fetches
        db_queries = sum(1 for g in context.data_gaps if g.result != "NOT_AVAILABLE")
        total_data_points = max(total_gaps + 20, 1)  # Estimate
        db_hit_rate = 1 - (total_gaps / total_data_points)
        
        # Group gaps by priority
        gaps_by_priority = {}
        for gap in context.data_gaps:
            gaps_by_priority.setdefault(gap.priority, []).append(gap)
        
        # Generate schema improvements
        schema_improvements = []
        seen_tables = set()
        for gap in context.data_gaps:
            if gap.table_checked not in seen_tables and gap.priority in ["P0", "P1"]:
                schema_improvements.append({
                    "table": gap.table_checked,
                    "gap": gap.data_needed,
                    "priority": gap.priority,
                    "time_impact": gap.time_cost_minutes
                })
                seen_tables.add(gap.table_checked)
        
        return SessionFeedback(
            session_id=context.session_id,
            ticker=context.ticker,
            date=datetime.now().isoformat(),
            duration_minutes=total_duration,
            efficiency_metrics={
                "database_hit_rate": round(db_hit_rate, 2),
                "workaround_time_minutes": total_workaround_time,
                "total_data_gaps": total_gaps,
                "gaps_by_priority": {k: len(v) for k, v in gaps_by_priority.items()}
            },
            data_gaps=[asdict(g) for g in context.data_gaps],
            schema_improvements=schema_improvements,
            system_health={
                "target_hit_rate": 0.80,
                "current_hit_rate": round(db_hit_rate, 2),
                "gap_to_target": round(0.80 - db_hit_rate, 2)
            }
        )
    
    def _save_feedback(self, context: SessionContext, feedback: SessionFeedback):
        """Save session feedback"""
        
        # Save to session output dir
        feedback_path = context.output_dir / "session_feedback.json"
        feedback_path.write_text(json.dumps(asdict(feedback), indent=2))
        
        # Also save to central feedback directory
        feedback_dir = Path(Config.FEEDBACK_DIR)
        feedback_dir.mkdir(parents=True, exist_ok=True)
        
        central_path = feedback_dir / f"{context.session_id}_feedback.json"
        central_path.write_text(json.dumps(asdict(feedback), indent=2))
        
        log(f"Feedback saved: {feedback_path}", "success")
    
    def _update_backlog(self, feedback: SessionFeedback):
        """Update the improvement backlog"""
        
        backlog_path = Path(Config.FEEDBACK_DIR) / "improvement_backlog.json"
        
        if backlog_path.exists():
            backlog = json.loads(backlog_path.read_text())
        else:
            backlog = {
                "improvements": [],
                "session_history": [],
                "metrics_over_time": []
            }
        
        # Add session to history
        backlog["session_history"].append({
            "session_id": feedback.session_id,
            "date": feedback.date,
            "ticker": feedback.ticker,
            "efficiency": feedback.efficiency_metrics
        })
        
        # Track metrics over time
        backlog["metrics_over_time"].append({
            "date": feedback.date,
            "database_hit_rate": feedback.efficiency_metrics["database_hit_rate"],
            "workaround_time": feedback.efficiency_metrics["workaround_time_minutes"]
        })
        
        # Add new improvements
        for improvement in feedback.schema_improvements:
            # Check if already in backlog
            existing = next(
                (i for i in backlog["improvements"] 
                 if i.get("table") == improvement["table"] and i.get("gap") == improvement["gap"]),
                None
            )
            
            if existing:
                existing["sessions_impacted"] = existing.get("sessions_impacted", 1) + 1
                existing["total_time_lost"] = existing.get("total_time_lost", 0) + improvement["time_impact"]
            else:
                backlog["improvements"].append({
                    "id": f"IMP-{len(backlog['improvements']):04d}",
                    "table": improvement["table"],
                    "gap": improvement["gap"],
                    "priority": improvement["priority"],
                    "first_reported": feedback.date,
                    "sessions_impacted": 1,
                    "total_time_lost": improvement["time_impact"],
                    "status": "OPEN"
                })
        
        # Save updated backlog
        backlog_path.parent.mkdir(parents=True, exist_ok=True)
        backlog_path.write_text(json.dumps(backlog, indent=2))
        
        log(f"Backlog updated: {len(backlog['improvements'])} open improvements", "info")
    
    def _print_summary(self, context: SessionContext, feedback: SessionFeedback):
        """Print session summary"""
        
        print_header("Session Summary")
        
        summary_data = {
            "Session ID": context.session_id,
            "Ticker": context.ticker,
            "Duration": f"{feedback.duration_minutes:.1f} minutes",
            "Agents Run": len(context.agent_results),
            "Data Gaps Found": feedback.efficiency_metrics["total_data_gaps"],
            "Database Hit Rate": f"{feedback.efficiency_metrics['database_hit_rate']:.0%}",
            "Workaround Time": f"{feedback.efficiency_metrics['workaround_time_minutes']} minutes",
            "Output Directory": str(context.output_dir)
        }
        
        print_table("Results", summary_data)
        
        if feedback.schema_improvements:
            log("\nRecommended Schema Improvements:", "header")
            for imp in feedback.schema_improvements[:5]:
                log(f"  [{imp['priority']}] {imp['table']}: {imp['gap']}", "warning")
        
        log(f"\n✅ Research complete! View memo at: {context.output_dir / 'final_memo.md'}", "success")


# =============================================================================
# CLI ENTRY POINT
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Multi-Agent Equity Research Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python orchestrator.py AAPL "Apple Inc."
    python orchestrator.py MSFT "Microsoft Corporation" --output-dir ./research
    python orchestrator.py GOOGL "Alphabet Inc." --skip-db-check
    
Environment Variables:
    ANTHROPIC_API_KEY    Your Anthropic API key (required)
        """
    )
    
    parser.add_argument("ticker", help="Stock ticker symbol (e.g., AAPL)")
    parser.add_argument("company_name", help="Company name (e.g., 'Apple Inc.')")
    parser.add_argument("--output-dir", "-o", help="Output directory for results")
    parser.add_argument("--db-path", "-d", default=Config.DB_PATH, help="Path to DuckDB database")
    parser.add_argument("--skip-db-check", action="store_true", help="Skip database availability check")
    parser.add_argument("--api-key", "-k", help="Anthropic API key (or set ANTHROPIC_API_KEY env var)")
    
    args = parser.parse_args()
    
    # Check for API key
    api_key = args.api_key or os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY not set.")
        print("Set it via: export ANTHROPIC_API_KEY=your_key_here")
        print("Or pass it via: --api-key your_key_here")
        sys.exit(1)
    
    try:
        orchestrator = ResearchOrchestrator(api_key=api_key, db_path=args.db_path)
        context = orchestrator.run(
            ticker=args.ticker.upper(),
            company_name=args.company_name,
            output_dir=args.output_dir,
            skip_db_check=args.skip_db_check
        )
        sys.exit(0)
        
    except KeyboardInterrupt:
        print("\n\nResearch interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        if os.getenv("DEBUG"):
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
