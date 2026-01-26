"""
Event System for Multi-Agent Communication

Defines event types and the event bus for agent coordination.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable
import json
import logging

logger = logging.getLogger(__name__)


class EventType(Enum):
    """All possible event types in the system."""
    
    # Main alpha workflow
    ALPHA_READY = "alpha.ready"
    BACKTEST_PASSED = "backtest.passed"
    BACKTEST_FAILED = "backtest.failed"
    ALPHA_SUCCESS = "alpha.success"
    ALPHA_REJECTED = "alpha.rejected"
    
    # Data flow
    DATA_MISSING = "data.missing"
    DATA_AVAILABLE = "data.available"
    
    # Project manager decisions
    PM_APPROVED = "pm.approved"
    PM_REJECTED = "pm.rejected"
    
    # Human review
    ALTERNATIVE_PROPOSED = "alternative.proposed"
    ALTERNATIVE_APPROVED = "alternative.approved"
    ALTERNATIVE_REJECTED = "alternative.rejected"
    
    # System events
    SYSTEM_ERROR = "system.error"
    SYSTEM_START = "system.start"
    SYSTEM_STOP = "system.stop"
    WORKFLOW_COMPLETE = "workflow.complete"
    
    # Agent lifecycle
    AGENT_STARTED = "agent.started"
    AGENT_STOPPED = "agent.stopped"


@dataclass
class Event:
    """
    Represents an event in the system.
    
    Attributes
    ----------
    event_type : EventType
        Type of event
    source : str
        Name of the agent that emitted this event
    timestamp : datetime
        When the event was created
    payload : dict
        Event data (varies by event type)
    correlation_id : str
        ID to track related events across the workflow
    """
    
    event_type: EventType
    source: str
    payload: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    correlation_id: str = ""
    
    def to_dict(self) -> dict:
        """Convert event to dictionary for serialization."""
        return {
            "event_type": self.event_type.value,
            "source": self.source,
            "timestamp": self.timestamp.isoformat(),
            "payload": self.payload,
            "correlation_id": self.correlation_id,
        }
    
    def to_json(self) -> str:
        """Convert event to JSON string."""
        return json.dumps(self.to_dict(), default=str)
    
    @classmethod
    def from_dict(cls, data: dict) -> "Event":
        """Create event from dictionary."""
        return cls(
            event_type=EventType(data["event_type"]),
            source=data["source"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            payload=data.get("payload", {}),
            correlation_id=data.get("correlation_id", ""),
        )


EventHandler = Callable[[Event], None]


class EventBus:
    """
    Central event bus for agent communication.
    
    Agents subscribe to event types and receive notifications when
    those events are emitted by other agents.
    """
    
    def __init__(self) -> None:
        self._handlers: dict[EventType, list[EventHandler]] = {}
        self._event_history: list[Event] = []
        self._max_history: int = 1000
    
    def subscribe(self, event_type: EventType, handler: EventHandler) -> None:
        """Subscribe a handler to an event type."""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)
        logger.debug(f"Handler subscribed to {event_type.value}")
    
    def unsubscribe(self, event_type: EventType, handler: EventHandler) -> None:
        """Unsubscribe a handler from an event type."""
        if event_type in self._handlers:
            self._handlers[event_type].remove(handler)
    
    def emit(self, event: Event) -> None:
        """Emit an event to all subscribed handlers."""
        # Store in history
        self._event_history.append(event)
        if len(self._event_history) > self._max_history:
            self._event_history = self._event_history[-self._max_history:]
        
        logger.info(f"Event emitted: {event.event_type.value} from {event.source}")
        
        # Notify handlers
        handlers = self._handlers.get(event.event_type, [])
        for handler in handlers:
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Handler error for {event.event_type.value}: {e}")
                # Emit error event (but don't recurse infinitely)
                if event.event_type != EventType.SYSTEM_ERROR:
                    self.emit(Event(
                        event_type=EventType.SYSTEM_ERROR,
                        source="event_bus",
                        payload={
                            "error": str(e),
                            "original_event": event.to_dict(),
                        },
                        correlation_id=event.correlation_id,
                    ))
    
    def get_history(
        self,
        event_type: EventType | None = None,
        correlation_id: str | None = None,
        limit: int = 100,
    ) -> list[Event]:
        """Get event history, optionally filtered."""
        events = self._event_history
        
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        
        if correlation_id:
            events = [e for e in events if e.correlation_id == correlation_id]
        
        return events[-limit:]
    
    def clear_history(self) -> None:
        """Clear event history."""
        self._event_history = []
