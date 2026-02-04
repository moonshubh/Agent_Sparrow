"""
Agent Loop State Machine - Explicit state tracking for agent execution.

This module makes agent loop state explicit and trackable, similar to Claude's
approach. Every state transition is observable, making debugging and
monitoring straightforward.

Key states:
- IDLE: Agent ready for input
- PROCESSING_INPUT: Analyzing user message
- AWAITING_MODEL: Waiting for LLM response
- EXECUTING_TOOLS: Running tool calls
- PROCESSING_RESULTS: Integrating tool results
- STREAMING_RESPONSE: Sending response chunks
- COMPLETED: Turn finished successfully
- ERRORED: Turn finished with error
"""

import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from app.core.logging_config import get_logger

logger = get_logger(__name__)


class AgentLoopState(Enum):
    """Explicit states for agent loop execution.

    State machine flow:

    IDLE → PROCESSING_INPUT → AWAITING_MODEL → EXECUTING_TOOLS →
    PROCESSING_RESULTS → (loop back to AWAITING_MODEL or →)
    STREAMING_RESPONSE → COMPLETED

    Any state can transition to ERRORED on failure.
    """

    IDLE = "idle"
    PROCESSING_INPUT = "processing_input"
    AWAITING_MODEL = "awaiting_model"
    EXECUTING_TOOLS = "executing_tools"
    PROCESSING_RESULTS = "processing_results"
    STREAMING_RESPONSE = "streaming_response"
    COMPLETED = "completed"
    ERRORED = "errored"


# Valid state transitions for validation
VALID_TRANSITIONS: dict[AgentLoopState, set[AgentLoopState]] = {
    AgentLoopState.IDLE: {AgentLoopState.PROCESSING_INPUT, AgentLoopState.ERRORED},
    AgentLoopState.PROCESSING_INPUT: {
        AgentLoopState.AWAITING_MODEL,
        AgentLoopState.ERRORED,
    },
    AgentLoopState.AWAITING_MODEL: {
        AgentLoopState.EXECUTING_TOOLS,
        AgentLoopState.STREAMING_RESPONSE,
        AgentLoopState.ERRORED,
    },
    AgentLoopState.EXECUTING_TOOLS: {
        AgentLoopState.PROCESSING_RESULTS,
        AgentLoopState.ERRORED,
    },
    AgentLoopState.PROCESSING_RESULTS: {
        AgentLoopState.AWAITING_MODEL,  # More tools needed
        AgentLoopState.STREAMING_RESPONSE,  # Done with tools
        AgentLoopState.ERRORED,
    },
    AgentLoopState.STREAMING_RESPONSE: {
        AgentLoopState.COMPLETED,
        AgentLoopState.ERRORED,
    },
    AgentLoopState.COMPLETED: {AgentLoopState.IDLE},  # Ready for next turn
    AgentLoopState.ERRORED: {AgentLoopState.IDLE},  # Can recover
}


@dataclass
class StateTransition:
    """Record of a single state transition for observability."""

    from_state: AgentLoopState
    to_state: AgentLoopState
    timestamp: str
    duration_ms: int  # Time spent in from_state
    metadata: dict = field(default_factory=dict)


@dataclass
class LoopStateTracker:
    """Tracks agent loop state through execution.

    This is the key observability component for understanding agent behavior.
    Every state transition is recorded with timing information, making it
    easy to identify bottlenecks and debug issues.

    Example:
        tracker = LoopStateTracker(session_id="abc123")

        # Start processing
        tracker.transition_to(AgentLoopState.PROCESSING_INPUT)

        # Wait for model
        tracker.transition_to(AgentLoopState.AWAITING_MODEL)

        # Execute tools
        tracker.transition_to(
            AgentLoopState.EXECUTING_TOOLS,
            metadata={"tools": ["web_search", "kb_search"]}
        )

        # Get summary for LangSmith
        summary = tracker.get_summary()
    """

    session_id: str
    current_state: AgentLoopState = AgentLoopState.IDLE
    transitions: list[StateTransition] = field(default_factory=list)
    start_time: float = field(default_factory=time.monotonic)
    state_start_time: float = field(default_factory=time.monotonic)
    tool_execution_count: int = 0
    model_call_count: int = 0
    error: Optional[str] = None
    error_state: Optional[AgentLoopState] = None

    def transition_to(
        self,
        new_state: AgentLoopState,
        metadata: Optional[dict] = None,
        validate: bool = True,
    ) -> bool:
        """Transition to a new state.

        Args:
            new_state: The state to transition to
            metadata: Optional metadata to record with transition
            validate: Whether to validate the transition is allowed

        Returns:
            True if transition succeeded, False if invalid
        """
        if validate and new_state not in VALID_TRANSITIONS.get(
            self.current_state, set()
        ):
            logger.warning(
                "invalid_state_transition",
                session_id=self.session_id,
                from_state=self.current_state.value,
                to_state=new_state.value,
                valid_transitions=[
                    s.value for s in VALID_TRANSITIONS.get(self.current_state, set())
                ],
            )
            return False

        now = time.monotonic()
        duration_ms = int((now - self.state_start_time) * 1000)

        transition = StateTransition(
            from_state=self.current_state,
            to_state=new_state,
            timestamp=datetime.now().isoformat(),
            duration_ms=duration_ms,
            metadata=metadata or {},
        )
        self.transitions.append(transition)

        # Update counters
        if new_state == AgentLoopState.EXECUTING_TOOLS:
            self.tool_execution_count += 1
        elif new_state == AgentLoopState.AWAITING_MODEL:
            self.model_call_count += 1

        logger.debug(
            "state_transition",
            session_id=self.session_id,
            from_state=self.current_state.value,
            to_state=new_state.value,
            duration_ms=duration_ms,
            metadata=metadata,
        )

        self.current_state = new_state
        self.state_start_time = now
        return True

    def set_error(self, error: str) -> None:
        """Record an error and transition to ERRORED state.

        Args:
            error: Error message to record
        """
        self.error = error
        self.error_state = self.current_state
        self.transition_to(
            AgentLoopState.ERRORED,
            metadata={"error": error, "error_state": self.current_state.value},
            validate=False,  # Always allow error transition
        )

    def complete(self) -> None:
        """Mark execution as completed."""
        if self.current_state == AgentLoopState.STREAMING_RESPONSE:
            self.transition_to(AgentLoopState.COMPLETED)
        elif self.current_state != AgentLoopState.ERRORED:
            # Skip to completed if we didn't stream (e.g., tool-only response)
            self.transition_to(AgentLoopState.COMPLETED, validate=False)

    def reset(self) -> None:
        """Reset tracker for a new turn."""
        self.transition_to(AgentLoopState.IDLE, validate=False)
        self.error = None
        self.error_state = None

    def get_total_duration_ms(self) -> int:
        """Get total execution time in milliseconds."""
        return int((time.monotonic() - self.start_time) * 1000)

    def get_state_durations(self) -> dict[str, int]:
        """Get time spent in each state.

        Returns:
            Dict mapping state names to duration in ms
        """
        durations: dict[str, int] = {}
        for transition in self.transitions:
            state_name = transition.from_state.value
            durations[state_name] = (
                durations.get(state_name, 0) + transition.duration_ms
            )
        return durations

    def get_summary(self) -> dict:
        """Get execution summary for LangSmith metadata.

        Returns:
            Dict with execution statistics suitable for observability
        """
        state_durations = self.get_state_durations()

        return {
            "session_id": self.session_id,
            "current_state": self.current_state.value,
            "total_duration_ms": self.get_total_duration_ms(),
            "tool_execution_count": self.tool_execution_count,
            "model_call_count": self.model_call_count,
            "transition_count": len(self.transitions),
            "state_durations": state_durations,
            "had_error": self.error is not None,
            "error": self.error,
            "error_state": self.error_state.value if self.error_state else None,
            # Key timing metrics for monitoring
            "model_wait_time_ms": state_durations.get("awaiting_model", 0),
            "tool_execution_time_ms": state_durations.get("executing_tools", 0),
            "processing_time_ms": (
                state_durations.get("processing_input", 0)
                + state_durations.get("processing_results", 0)
            ),
        }

    def get_langsmith_tags(self) -> list[str]:
        """Get tags for LangSmith tracing.

        Returns:
            List of tags describing the execution
        """
        tags = [f"state:{self.current_state.value}"]

        if self.tool_execution_count > 0:
            tags.append(f"tools_used:{self.tool_execution_count}")

        if self.model_call_count > 1:
            tags.append(f"model_calls:{self.model_call_count}")

        if self.error:
            tags.append("had_error")
            if self.error_state:
                tags.append(f"error_in:{self.error_state.value}")

        return tags

    def to_scratchpad_update(self) -> dict:
        """Convert state to scratchpad update dict.

        Returns:
            Dict with _system bucket update for scratchpad
        """
        return {
            "scratchpad": {
                "_system": {
                    "_loop_state": {
                        "current": self.current_state.value,
                        "tool_count": self.tool_execution_count,
                        "model_count": self.model_call_count,
                        "duration_ms": self.get_total_duration_ms(),
                        "had_error": self.error is not None,
                    }
                }
            }
        }


# Factory function for creating trackers
def create_loop_tracker(session_id: str) -> LoopStateTracker:
    """Create a new LoopStateTracker for a session.

    Args:
        session_id: The session identifier

    Returns:
        Initialized LoopStateTracker ready for use
    """
    return LoopStateTracker(session_id=session_id)


# Session-scoped tracker cache
_session_trackers: OrderedDict[str, LoopStateTracker] = OrderedDict()
_session_trackers_lock = threading.Lock()
MAX_CACHED_TRACKERS = 1000


def get_or_create_tracker(session_id: str) -> LoopStateTracker:
    """Get existing tracker or create new one for session.

    Args:
        session_id: The session identifier

    Returns:
        LoopStateTracker for the session
    """
    with _session_trackers_lock:
        tracker = _session_trackers.get(session_id)
        if tracker is None:
            tracker = create_loop_tracker(session_id)
            _session_trackers[session_id] = tracker
        _session_trackers.move_to_end(session_id)
        while len(_session_trackers) > MAX_CACHED_TRACKERS:
            _session_trackers.popitem(last=False)
        return tracker


def clear_tracker(session_id: str) -> None:
    """Clear tracker for a session.

    Args:
        session_id: The session identifier
    """
    with _session_trackers_lock:
        _session_trackers.pop(session_id, None)
