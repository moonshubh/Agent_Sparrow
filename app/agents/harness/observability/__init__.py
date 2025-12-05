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
from .tool_metrics import (
    record_tool_result,
    get_recent_results as get_recent_tool_results,
    set_current_session as set_current_tool_session,
    reset_current_session as reset_current_tool_session,
    get_recent_results_for_session,
    publish_tool_batch_to_langsmith,
)

__all__ = [
    "AgentLoopState",
    "LoopStateTracker",
    "StateTransition",
    "VALID_TRANSITIONS",
    "create_loop_tracker",
    "get_or_create_tracker",
    "clear_tracker",
    # Tool metrics
    "record_tool_result",
    "get_recent_tool_results",
    "set_current_tool_session",
    "reset_current_tool_session",
    "get_recent_results_for_session",
    "publish_tool_batch_to_langsmith",
]
