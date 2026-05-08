"""
Scribe Agent - Event Logger

Records all events to disk for audit trail and debugging.
Clearance: Infrastructure
"""

import json
import logging
from datetime import datetime
from pathlib import Path

from agents.base import Agent, AgentConfig, Clearance
from agents.events import Event, EventBus, EventType

logger = logging.getLogger(__name__)


class Scribe(Agent):
    """
    The Scribe records all events in the system.
    
    Logs are written to:
    - agents/logs/{date}_{correlation_id}.jsonl (structured)
    - agents/logs/{date}_{correlation_id}.log (human readable)
    
    The Scribe has Infrastructure clearance - it can coordinate and log,
    but cannot modify the data pipeline.
    """
    
    def __init__(
        self,
        event_bus: EventBus,
        config: AgentConfig | None = None,
        log_dir: Path | None = None,
    ) -> None:
        super().__init__(event_bus, config)
        
        # Setup log directory
        if log_dir is None:
            log_dir = Path(__file__).parent / "logs"
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Create log files
        date_str = datetime.now().strftime("%Y-%m-%d")
        base_name = f"{date_str}_{self.config.correlation_id}"
        
        self.jsonl_path = self.log_dir / f"{base_name}.jsonl"
        self.log_path = self.log_dir / f"{base_name}.log"
        
        # Event counters
        self._event_counts: dict[str, int] = {}
        self._start_time: datetime | None = None
    
    @property
    def name(self) -> str:
        return "scribe"
    
    @property
    def clearance(self) -> Clearance:
        return Clearance.INFRASTRUCTURE
    
    def _subscribe_events(self) -> None:
        """Subscribe to ALL event types."""
        for event_type in EventType:
            self.event_bus.subscribe(event_type, self._handle_event)
    
    def start(self) -> None:
        """Start the Scribe and initialize log files."""
        super().start()
        self._start_time = datetime.now()
        
        # Write header to human-readable log
        with open(self.log_path, "w") as f:
            f.write("=" * 80 + "\n")
            f.write(f"ALPHA TESTING WORKFLOW LOG\n")
            f.write(f"Correlation ID: {self.config.correlation_id}\n")
            f.write(f"Started: {self._start_time.isoformat()}\n")
            f.write("=" * 80 + "\n\n")
        
        self.log(f"Logging to {self.log_path}")
    
    def stop(self) -> None:
        """Stop the Scribe and write summary."""
        # Write summary
        self._write_summary()
        super().stop()
    
    def _handle_event(self, event: Event) -> None:
        """Handle any event by logging it."""
        # Update counters
        event_name = event.event_type.value
        self._event_counts[event_name] = self._event_counts.get(event_name, 0) + 1
        
        # Write to JSONL
        with open(self.jsonl_path, "a") as f:
            f.write(event.to_json() + "\n")
        
        # Write to human-readable log
        self._write_human_readable(event)
    
    def _write_human_readable(self, event: Event) -> None:
        """Write event to human-readable log file."""
        timestamp = event.timestamp.strftime("%H:%M:%S.%f")[:-3]
        
        # Format based on event type
        if event.event_type == EventType.ALPHA_READY:
            msg = self._format_alpha_ready(event)
        elif event.event_type == EventType.BACKTEST_PASSED:
            msg = self._format_backtest_result(event, passed=True)
        elif event.event_type == EventType.BACKTEST_FAILED:
            msg = self._format_backtest_result(event, passed=False)
        elif event.event_type == EventType.ALPHA_SUCCESS:
            msg = self._format_alpha_result(event, success=True)
        elif event.event_type == EventType.ALPHA_REJECTED:
            msg = self._format_alpha_result(event, success=False)
        elif event.event_type == EventType.DATA_MISSING:
            msg = self._format_data_missing(event)
        elif event.event_type == EventType.SYSTEM_ERROR:
            msg = self._format_error(event)
        else:
            msg = f"{event.event_type.value}: {event.payload}"
        
        line = f"[{timestamp}] {event.source:20s} | {msg}\n"
        
        with open(self.log_path, "a") as f:
            f.write(line)
    
    def _format_alpha_ready(self, event: Event) -> str:
        """Format alpha.ready event."""
        p = event.payload
        strategy = p.get("strategy_name", "unknown")
        n_signals = p.get("n_signals", 0)
        return f"ALPHA READY: {strategy} ({n_signals} signals)"
    
    def _format_backtest_result(self, event: Event, passed: bool) -> str:
        """Format backtest result event."""
        p = event.payload
        status = "PASSED" if passed else "FAILED"
        folds = p.get("n_folds", "?")
        avg_return = p.get("avg_return", 0)
        return f"BACKTEST {status}: {folds} folds, avg return {avg_return:.2%}"
    
    def _format_alpha_result(self, event: Event, success: bool) -> str:
        """Format alpha result event."""
        p = event.payload
        status = "✅ SUCCESS" if success else "❌ REJECTED"
        psr = p.get("psr", 0)
        reason = p.get("reason", "")
        msg = f"ALPHA {status}: PSR={psr:.3f}"
        if reason:
            msg += f" ({reason})"
        return msg
    
    def _format_data_missing(self, event: Event) -> str:
        """Format data.missing event."""
        p = event.payload
        requester = p.get("requester", "unknown")
        request = p.get("request", {})
        return f"DATA REQUEST from {requester}: {request}"
    
    def _format_error(self, event: Event) -> str:
        """Format error event."""
        p = event.payload
        error = p.get("error", "unknown")
        return f"⚠️ ERROR: {error}"
    
    def _write_summary(self) -> None:
        """Write summary to log file."""
        end_time = datetime.now()
        duration = (end_time - self._start_time).total_seconds() if self._start_time else 0
        
        with open(self.log_path, "a") as f:
            f.write("\n" + "=" * 80 + "\n")
            f.write("SUMMARY\n")
            f.write("=" * 80 + "\n")
            f.write(f"Duration: {duration:.1f}s\n")
            f.write(f"Total events: {sum(self._event_counts.values())}\n")
            f.write("\nEvent counts:\n")
            for event_name, count in sorted(self._event_counts.items()):
                f.write(f"  {event_name}: {count}\n")
            f.write("=" * 80 + "\n")
    
    def get_stats(self) -> dict:
        """Get current statistics."""
        return {
            "total_events": sum(self._event_counts.values()),
            "event_counts": self._event_counts.copy(),
            "log_path": str(self.log_path),
            "jsonl_path": str(self.jsonl_path),
        }
