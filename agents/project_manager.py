"""
Project Manager Agent

Evaluates data requests and coordinates between agents.
Clearance: Infrastructure
"""

import logging

from agents.base import Agent, AgentConfig, Clearance
from agents.events import Event, EventBus, EventType

logger = logging.getLogger(__name__)


class ProjectManager(Agent):
    """
    Project Manager evaluates data requests and coordinates workflow.

    Responsibilities:
    - Evaluate data.missing requests
    - Approve/reject based on feasibility
    - Propose alternatives when data unavailable
    """

    def __init__(
        self,
        event_bus: EventBus,
        config: AgentConfig | None = None,
    ) -> None:
        super().__init__(event_bus, config)

        # Track pending requests
        self._pending_requests: list[Event] = []

        # Known data sources
        self._available_sources = [
            "yahoo_finance",
            "stocktwits",
            "house_clerk",
            "openbb",
        ]

    @property
    def name(self) -> str:
        return "ProjectManager"

    @property
    def clearance(self) -> Clearance:
        return Clearance.INFRASTRUCTURE

    def _subscribe_events(self) -> None:
        """Subscribe to data requests."""
        self.event_bus.subscribe(EventType.DATA_MISSING, self._on_data_missing)
        self.event_bus.subscribe(EventType.DATA_AVAILABLE, self._on_data_available)

    def _on_data_missing(self, event: Event) -> None:
        """Evaluate a data request."""
        request = event.payload.get("request", {})
        requester = event.payload.get("requester", "unknown")

        self.log(f"Evaluating data request from {requester}: {request}")

        # Check if request is feasible
        data_type = request.get("type", "")
        source = request.get("source", "")

        if self._can_fulfill(request):
            # Approve and forward to data pipeline
            self.log(f"Approving data request: {data_type}")
            self.emit(
                EventType.PM_APPROVED,
                {
                    "original_request": request,
                    "requester": requester,
                    "source": source or self._suggest_source(data_type),
                },
            )
        else:
            # Reject and propose alternative
            self.log(f"Rejecting data request: {data_type} (not available)")
            alternative = self._propose_alternative(request)

            if alternative:
                self.emit(
                    EventType.PM_REJECTED,
                    {
                        "original_request": request,
                        "requester": requester,
                        "reason": "Data source not available",
                    },
                )
                # Propose alternative for human review
                self.emit(
                    EventType.ALTERNATIVE_PROPOSED,
                    {
                        "original_request": request,
                        "proposal": alternative,
                        "requester": requester,
                    },
                )
            else:
                self.emit(
                    EventType.PM_REJECTED,
                    {
                        "original_request": request,
                        "requester": requester,
                        "reason": "No alternative available",
                    },
                )

    def _on_data_available(self, event: Event) -> None:
        """Handle data becoming available."""
        self.log(f"Data now available: {event.payload.get('type')}")

    def _can_fulfill(self, request: dict) -> bool:
        """Check if a data request can be fulfilled."""
        data_type = request.get("type", "")

        # Check what we can provide
        fulfillable_types = [
            "prices",
            "ohlcv",
            "fundamentals",
            "sentiment",
            "social",
        ]

        return data_type.lower() in fulfillable_types

    def _suggest_source(self, data_type: str) -> str:
        """Suggest a data source for a type."""
        source_map = {
            "prices": "yahoo_finance",
            "ohlcv": "yahoo_finance",
            "fundamentals": "yahoo_finance",
            "sentiment": "stocktwits",
            "social": "stocktwits",
        }
        return source_map.get(data_type.lower(), "yahoo_finance")

    def _propose_alternative(self, request: dict) -> dict | None:
        """Propose an alternative approach when data unavailable."""
        data_type = request.get("type", "")

        alternatives = {
            "realtime": {
                "proposal": "Use EOD data with 1-day lag",
                "tradeoff": "Signals delayed by 1 day",
            },
            "options": {
                "proposal": "Use implied volatility proxies from price action",
                "tradeoff": "Less accurate than actual options data",
            },
            "insider": {
                "proposal": "Use SEC filings (delayed)",
                "tradeoff": "Data is 2+ days old",
            },
        }

        return alternatives.get(data_type.lower())
