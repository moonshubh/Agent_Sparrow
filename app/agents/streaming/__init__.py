"""AG-UI streaming event types and utilities for Agent Sparrow."""

from .event_types import (
    TraceStep,
    TimelineOperation,
    AgentThinkingTraceEvent,
    AgentTimelineUpdateEvent,
    ToolEvidenceUpdateEvent,
    AgentTodosUpdateEvent,
    TodoItem,
)
from .emitter import StreamEventEmitter
from .handler import StreamEventHandler
from .normalizers import normalize_todos

__all__ = [
    # Event types
    "TraceStep",
    "TimelineOperation",
    "AgentThinkingTraceEvent",
    "AgentTimelineUpdateEvent",
    "ToolEvidenceUpdateEvent",
    "AgentTodosUpdateEvent",
    "TodoItem",
    # Classes
    "StreamEventEmitter",
    "StreamEventHandler",
    # Utilities
    "normalize_todos",
]
