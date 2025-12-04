"""Observability components for Agent Sparrow.

Includes state tracking, metrics, and LangSmith integration.

Usage:
    from app.agents.harness.observability import (
        AgentLoopState,
        LoopStateTracker,
        get_or_create_tracker,
    )

    tracker = get_or_create_tracker(session_id="abc123")
    tracker.transition_to(AgentLoopState.PROCESSING_INPUT)
"""

from .loop_state import (
    AgentLoopState,
    LoopStateTracker,
    StateTransition,
    VALID_TRANSITIONS,
    create_loop_tracker,
    get_or_create_tracker,
    clear_tracker,
)

__all__ = [
    "AgentLoopState",
    "LoopStateTracker",
    "StateTransition",
    "VALID_TRANSITIONS",
    "create_loop_tracker",
    "get_or_create_tracker",
    "clear_tracker",
]
