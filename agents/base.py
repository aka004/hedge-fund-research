"""
Base Agent Class

All agents inherit from this class. Provides:
- Event emission and subscription
- Clearance level enforcement
- Common logging patterns
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
import logging
import uuid

from agents.events import Event, EventBus, EventType


class Clearance(Enum):
    """
    Agent clearance levels define what agents can do.
    
    From CLAUDE.md:
    - Research: Read data, compute signals, propose alphas
    - Validation: Read data/signals, run validation
    - Infrastructure: Coordinate, log events  
    - Pipeline: Add provider methods, add Parquet columns
    - Admin: Approve alternatives, final decisions (human)
    """
    
    RESEARCH = "research"
    VALIDATION = "validation"
    INFRASTRUCTURE = "infrastructure"
    PIPELINE = "pipeline"
    ADMIN = "admin"


@dataclass
class AgentConfig:
    """Configuration for an agent."""
    
    verbose: bool = False
    correlation_id: str = ""
    
    def __post_init__(self):
        if not self.correlation_id:
            self.correlation_id = str(uuid.uuid4())[:8]


class Agent(ABC):
    """
    Base class for all agents in the system.
    
    Agents must:
    1. Define their name and clearance level
    2. Subscribe to relevant events
    3. Emit events for other agents
    4. Use AFML functions where required (see CLAUDE.md)
    """
    
    def __init__(
        self,
        event_bus: EventBus,
        config: AgentConfig | None = None,
    ) -> None:
        self.event_bus = event_bus
        self.config = config or AgentConfig()
        self._logger = logging.getLogger(f"agents.{self.name}")
        self._is_running = False
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Return the agent's name."""
        pass
    
    @property
    @abstractmethod
    def clearance(self) -> Clearance:
        """Return the agent's clearance level."""
        pass
    
    @abstractmethod
    def _subscribe_events(self) -> None:
        """Subscribe to relevant events. Called on start()."""
        pass
    
    def start(self) -> None:
        """Start the agent and subscribe to events."""
        self._subscribe_events()
        self._is_running = True
        self._logger.info(f"{self.name} started (clearance: {self.clearance.value})")
        self.emit(EventType.AGENT_STARTED, {"agent": self.name})
    
    def stop(self) -> None:
        """Stop the agent."""
        self._is_running = False
        self._logger.info(f"{self.name} stopped")
        self.emit(EventType.AGENT_STOPPED, {"agent": self.name})
    
    def emit(
        self,
        event_type: EventType,
        payload: dict | None = None,
    ) -> Event:
        """Emit an event from this agent."""
        event = Event(
            event_type=event_type,
            source=self.name,
            payload=payload or {},
            correlation_id=self.config.correlation_id,
        )
        self.event_bus.emit(event)
        return event
    
    def log(self, message: str, level: str = "info") -> None:
        """Log a message with the agent's context."""
        log_func = getattr(self._logger, level.lower(), self._logger.info)
        log_func(f"[{self.config.correlation_id}] {message}")
    
    def can_perform(self, required_clearance: Clearance) -> bool:
        """Check if agent has sufficient clearance."""
        clearance_hierarchy = [
            Clearance.RESEARCH,
            Clearance.VALIDATION,
            Clearance.INFRASTRUCTURE,
            Clearance.PIPELINE,
            Clearance.ADMIN,
        ]
        
        agent_level = clearance_hierarchy.index(self.clearance)
        required_level = clearance_hierarchy.index(required_clearance)
        
        return agent_level >= required_level
    
    def request_data(self, data_request: dict) -> None:
        """
        Request data from the data pipeline.
        
        Emits a DATA_MISSING event that triggers the PM -> Pipeline flow.
        """
        self.emit(EventType.DATA_MISSING, {
            "requester": self.name,
            "request": data_request,
        })
