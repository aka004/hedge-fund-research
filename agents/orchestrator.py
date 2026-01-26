"""
Orchestrator - Main event loop coordinator

Manages agent lifecycle and coordinates the alpha testing workflow.
"""

import logging
from datetime import datetime
from pathlib import Path

from agents.base import Agent, AgentConfig, Clearance
from agents.events import Event, EventBus, EventType
from agents.momentum_researcher import MomentumResearcher
from agents.backtest_unit import BacktestUnit
from agents.statistical_agent import StatisticalAgent
from agents.scribe import Scribe

logger = logging.getLogger(__name__)


class Orchestrator:
    """
    Main coordinator for the multi-agent alpha testing system.
    
    Manages:
    - Agent lifecycle (start/stop)
    - Event routing
    - Workflow state
    - Human approval gates
    """
    
    def __init__(
        self,
        verbose: bool = False,
        log_dir: Path | None = None,
    ) -> None:
        self.verbose = verbose
        self.log_dir = log_dir or Path("agents/logs")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Create event bus
        self.event_bus = EventBus()
        
        # Create config
        self.config = AgentConfig(verbose=verbose)
        
        # Workflow state
        self._workflow_complete = False
        self._final_result: dict | None = None
        self._pending_human_review: list[Event] = []
        
        # Create agents
        self.scribe = Scribe(
            event_bus=self.event_bus,
            config=self.config,
            log_dir=self.log_dir,
        )
        
        self.momentum_researcher = MomentumResearcher(
            event_bus=self.event_bus,
            config=self.config,
        )
        
        self.backtest_unit = BacktestUnit(
            event_bus=self.event_bus,
            config=self.config,
        )
        
        self.statistical_agent = StatisticalAgent(
            event_bus=self.event_bus,
            config=self.config,
        )
        
        self.agents = [
            self.scribe,
            self.momentum_researcher,
            self.backtest_unit,
            self.statistical_agent,
        ]
        
        # Subscribe to workflow events
        self._subscribe_workflow_events()
    
    def _subscribe_workflow_events(self) -> None:
        """Subscribe to events that affect workflow state."""
        self.event_bus.subscribe(EventType.ALPHA_SUCCESS, self._on_alpha_success)
        self.event_bus.subscribe(EventType.ALPHA_REJECTED, self._on_alpha_rejected)
        self.event_bus.subscribe(EventType.ALTERNATIVE_PROPOSED, self._on_alternative_proposed)
        self.event_bus.subscribe(EventType.SYSTEM_ERROR, self._on_system_error)
    
    def _on_alpha_success(self, event: Event) -> None:
        """Handle successful alpha validation."""
        self._workflow_complete = True
        self._final_result = {
            "status": "success",
            "psr": event.payload.get("psr"),
            "sharpe": event.payload.get("sharpe"),
            "message": "Alpha passed all validation gates",
        }
        logger.info("✅ WORKFLOW COMPLETE: Alpha validated successfully!")
    
    def _on_alpha_rejected(self, event: Event) -> None:
        """Handle rejected alpha - researcher will retry."""
        logger.warning(f"Alpha rejected: {event.payload.get('reason')}")
        # Momentum researcher should handle retry
    
    def _on_alternative_proposed(self, event: Event) -> None:
        """Handle proposal requiring human review."""
        self._pending_human_review.append(event)
        logger.info(f"⚠️ HUMAN REVIEW REQUIRED: {event.payload.get('proposal')}")
    
    def _on_system_error(self, event: Event) -> None:
        """Handle system errors."""
        logger.error(f"System error: {event.payload.get('error')}")
    
    def start(self) -> None:
        """Start all agents."""
        logger.info("=" * 60)
        logger.info("STARTING MULTI-AGENT ORCHESTRATION")
        logger.info("=" * 60)
        
        for agent in self.agents:
            agent.start()
        
        self.event_bus.emit(Event(
            event_type=EventType.SYSTEM_START,
            source="orchestrator",
            correlation_id=self.config.correlation_id,
        ))
    
    def stop(self) -> None:
        """Stop all agents."""
        for agent in self.agents:
            agent.stop()
        
        self.event_bus.emit(Event(
            event_type=EventType.SYSTEM_STOP,
            source="orchestrator",
            correlation_id=self.config.correlation_id,
        ))
        
        logger.info("All agents stopped")
    
    def run_data_test(self, symbols: list[str] | None = None) -> dict:
        """
        Test mode: Verify agents can fetch all required data.
        
        Returns dict with status and any issues found.
        """
        logger.info("Running data availability test...")
        
        self.start()
        
        try:
            # Ask momentum researcher to verify data
            result = self.momentum_researcher.test_data_availability(symbols)
            
            return {
                "status": "pass" if result["all_available"] else "fail",
                "symbols_tested": result["symbols_tested"],
                "symbols_ok": result["symbols_ok"],
                "symbols_failed": result["symbols_failed"],
                "issues": result.get("issues", []),
            }
        finally:
            self.stop()
    
    def run_alpha_workflow(
        self,
        symbols: list[str] | None = None,
        max_iterations: int = 3,
    ) -> dict:
        """
        Run the full alpha testing workflow.
        
        Main flow:
        1. Momentum Researcher generates alpha signals
        2. Backtest Unit validates with purged k-fold
        3. Statistical Agent checks PSR >= 0.95
        4. If rejected, researcher adjusts and retries
        
        Returns final result dict.
        """
        logger.info("Running alpha testing workflow...")
        
        self.start()
        
        try:
            # Trigger alpha generation
            self.momentum_researcher.generate_alpha(symbols)
            
            # Wait for workflow to complete (in real async this would be event-driven)
            # For now, we run synchronously through the chain
            
            if self._workflow_complete:
                return self._final_result
            else:
                return {
                    "status": "incomplete",
                    "message": "Workflow did not complete",
                    "pending_review": len(self._pending_human_review),
                }
        finally:
            self.stop()
    
    def get_pending_reviews(self) -> list[Event]:
        """Get events pending human review."""
        return self._pending_human_review
    
    def approve_alternative(self, event: Event) -> None:
        """Human approves a proposed alternative."""
        self.event_bus.emit(Event(
            event_type=EventType.ALTERNATIVE_APPROVED,
            source="human",
            payload=event.payload,
            correlation_id=event.correlation_id,
        ))
        self._pending_human_review.remove(event)
    
    def reject_alternative(self, event: Event, reason: str = "") -> None:
        """Human rejects a proposed alternative."""
        self.event_bus.emit(Event(
            event_type=EventType.ALTERNATIVE_REJECTED,
            source="human",
            payload={**event.payload, "rejection_reason": reason},
            correlation_id=event.correlation_id,
        ))
        self._pending_human_review.remove(event)
    
    def get_event_history(self) -> list[Event]:
        """Get full event history for this session."""
        return self.event_bus.get_history(
            correlation_id=self.config.correlation_id
        )
    
    def print_summary(self) -> None:
        """Print a summary of the workflow."""
        history = self.get_event_history()
        
        print("\n" + "=" * 60)
        print("WORKFLOW SUMMARY")
        print("=" * 60)
        print(f"Correlation ID: {self.config.correlation_id}")
        print(f"Total events: {len(history)}")
        print("-" * 60)
        
        for event in history:
            ts = event.timestamp.strftime("%H:%M:%S")
            print(f"[{ts}] {event.source:20} → {event.event_type.value}")
        
        print("=" * 60)
        
        if self._final_result:
            print(f"\nFinal Result: {self._final_result['status'].upper()}")
            if self._final_result.get("psr"):
                print(f"PSR: {self._final_result['psr']:.3f}")
