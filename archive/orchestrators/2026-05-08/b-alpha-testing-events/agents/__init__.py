"""
Multi-Agent Orchestration System for Alpha Testing

Event-driven workflow for testing alpha generation strategies using AFML techniques.
See CLAUDE.md for complete workflow documentation.
"""

from agents.base import Agent, Clearance
from agents.backtest_unit import BacktestUnit
from agents.data_pipeline import DataPipelineAgent
from agents.events import Event, EventBus, EventType
from agents.momentum_researcher import MomentumResearcher
from agents.orchestrator import Orchestrator
from agents.project_manager import ProjectManager
from agents.scribe import Scribe
from agents.statistical_agent import StatisticalAgent

__all__ = [
    # Base
    "Agent",
    "Clearance",
    "Event",
    "EventBus",
    "EventType",
    # Agents
    "MomentumResearcher",
    "BacktestUnit",
    "StatisticalAgent",
    "ProjectManager",
    "DataPipelineAgent",
    "Scribe",
    "Orchestrator",
]
