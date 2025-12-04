"""State Tracking Middleware for agent loop observability.

This middleware automatically tracks agent loop state transitions,
converting the imperative LoopStateTracker into the DeepAgents middleware pattern.

Key state transitions tracked:
- before_agent: IDLE -> PROCESSING_INPUT
- wrap_model_call: PROCESSING_INPUT -> AWAITING_MODEL
- wrap_tool_call: AWAITING_MODEL -> EXECUTING_TOOLS -> PROCESSING_RESULTS
- after_agent: -> STREAMING_RESPONSE -> COMPLETED

Usage:
    from app.agents.harness.middleware import StateTrackingMiddleware

    middleware_stack = [
        StateTrackingMiddleware(),
        # ... other middleware
    ]
"""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from langchain_core.messages import ToolMessage
from loguru import logger

# Import from new canonical location
from app.agents.harness.observability import (
    AgentLoopState,
    LoopStateTracker,
    get_or_create_tracker,
    clear_tracker,
)

# Try to import DeepAgents middleware base
try:
    from langchain.agents.middleware.types import AgentMiddleware

    _MIDDLEWARE_AVAILABLE = True
except ImportError:
    _MIDDLEWARE_AVAILABLE = False
    AgentMiddleware = object  # type: ignore[misc, assignment]


@dataclass
class StateTrackingStats:
    """Statistics for state tracking middleware."""

    transitions_tracked: int = 0
    model_calls_tracked: int = 0
    tool_calls_tracked: int = 0
    completions: int = 0
    errors: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            "transitions_tracked": self.transitions_tracked,
            "model_calls_tracked": self.model_calls_tracked,
            "tool_calls_tracked": self.tool_calls_tracked,
            "completions": self.completions,
            "errors": self.errors,
        }


class StateTrackingMiddleware(AgentMiddleware if _MIDDLEWARE_AVAILABLE else object):  # type: ignore[misc]
    """Middleware that automatically tracks agent loop state.

    Implements DeepAgents middleware hooks to:
    1. Initialize/transition state at the start of each agent call
    2. Track model and tool invocations
    3. Record timing and capture metrics at completion
    4. Emit LangSmith-compatible metadata via scratchpad

    This replaces manual tracker.transition_to() calls with automatic tracking.

    Note:
        Error handling (tracker.set_error()) should still be done manually
        in exception handlers for proper error categorization.
    """

    name = "state_tracking"

    def __init__(self) -> None:
        """Initialize the state tracking middleware."""
        self._stats = StateTrackingStats()
        self._stats_lock = asyncio.Lock()
        self._trackers_lock = asyncio.Lock()
        self._active_trackers: Dict[str, LoopStateTracker] = {}

    def _get_session_id(self, state: Any, config: Optional[Dict[str, Any]] = None) -> str:
        """Extract session ID from state or config."""
        session_id = (
            getattr(state, "session_id", None)
            or getattr(state, "trace_id", None)
            or (config or {}).get("configurable", {}).get("thread_id")
            or "unknown"
        )
        return str(session_id)

    async def _get_tracker_async(self, session_id: str) -> LoopStateTracker:
        """Get or create tracker for session (async, thread-safe)."""
        async with self._trackers_lock:
            if session_id not in self._active_trackers:
                self._active_trackers[session_id] = get_or_create_tracker(session_id)
            return self._active_trackers[session_id]

    def _get_tracker(self, session_id: str) -> LoopStateTracker:
        """Get or create tracker for session (sync, for use in sync contexts).

        Note: This method is not thread-safe for concurrent async access.
        Use _get_tracker_async for async contexts.
        """
        if session_id not in self._active_trackers:
            self._active_trackers[session_id] = get_or_create_tracker(session_id)
        return self._active_trackers[session_id]

    async def abefore_agent(
        self,
        state: Any,
        runtime: Any,
    ) -> Optional[Dict[str, Any]]:
        """Initialize state tracking before agent processes messages.

        Transitions: IDLE -> PROCESSING_INPUT
        """
        if not _MIDDLEWARE_AVAILABLE:
            return None

        session_id = self._get_session_id(state)
        tracker = await self._get_tracker_async(session_id)

        # Transition to processing input
        message_count = len(getattr(state, "messages", []) or [])
        tracker.transition_to(
            AgentLoopState.PROCESSING_INPUT,
            metadata={"session_id": session_id, "message_count": message_count},
        )

        async with self._stats_lock:
            self._stats.transitions_tracked += 1

        logger.debug(
            "state_tracking_before_agent",
            session_id=session_id,
            state=AgentLoopState.PROCESSING_INPUT.value,
        )

        return None

    async def aafter_agent(
        self,
        state: Any,
        runtime: Any,
    ) -> Optional[Dict[str, Any]]:
        """Finalize state tracking and store summary after agent completes.

        Transitions: -> STREAMING_RESPONSE -> COMPLETED
        Stores loop_state summary in scratchpad["_system"]["loop_state"]
        """
        if not _MIDDLEWARE_AVAILABLE:
            return None

        session_id = self._get_session_id(state)
        tracker = await self._get_tracker_async(session_id)

        # Transition to streaming/completed if not already in error state
        if tracker.current_state not in (AgentLoopState.ERRORED, AgentLoopState.COMPLETED):
            tracker.transition_to(AgentLoopState.STREAMING_RESPONSE)
            tracker.complete()

        # Get summary for LangSmith observability
        loop_summary = tracker.get_summary()

        async with self._stats_lock:
            self._stats.completions += 1

        logger.debug(
            "state_tracking_after_agent",
            session_id=session_id,
            summary=loop_summary,
        )

        # Return scratchpad update
        return {
            "scratchpad": {
                "_system": {
                    "loop_state": loop_summary,
                }
            }
        }

    async def awrap_model_call(
        self,
        request: Any,
        handler: Callable[..., Any],
    ) -> Any:
        """Track model call state transitions.

        Transitions: -> AWAITING_MODEL
        """
        # Extract session context from request if available
        session_id = "unknown"
        model_name = "unknown"

        if hasattr(request, "config"):
            config = request.config
            session_id = (config or {}).get("configurable", {}).get("thread_id", "unknown")

        if hasattr(request, "model"):
            model_name = str(request.model)

        tracker = await self._get_tracker_async(session_id)

        # Transition to awaiting model
        tracker.transition_to(
            AgentLoopState.AWAITING_MODEL,
            metadata={"model": model_name},
        )

        async with self._stats_lock:
            self._stats.model_calls_tracked += 1

        # Call the actual handler
        return await handler(request)

    async def awrap_tool_call(
        self,
        request: Any,
        handler: Callable[..., Any],
    ) -> ToolMessage:
        """Track tool execution state transitions.

        Transitions: -> EXECUTING_TOOLS -> PROCESSING_RESULTS
        """
        session_id = "unknown"
        tool_name = "unknown"

        if hasattr(request, "config"):
            config = request.config
            session_id = (config or {}).get("configurable", {}).get("thread_id", "unknown")

        if hasattr(request, "tool_name"):
            tool_name = str(request.tool_name)

        tracker = await self._get_tracker_async(session_id)

        # Transition to executing tools
        tracker.transition_to(
            AgentLoopState.EXECUTING_TOOLS,
            metadata={"tool": tool_name},
        )

        async with self._stats_lock:
            self._stats.tool_calls_tracked += 1

        # Execute the tool
        result = await handler(request)

        # Transition to processing results
        tracker.transition_to(
            AgentLoopState.PROCESSING_RESULTS,
            metadata={"tool": tool_name, "success": not getattr(result, "is_error", False)},
        )

        return result

    def set_error(self, session_id: str, error_message: str) -> None:
        """Manually set error state for a session.

        This is exposed for exception handlers that need to record errors.

        Args:
            session_id: The session identifier
            error_message: Error message to record

        Note:
            The stats increment is not async-lock protected as this is typically
            called from exception handlers in a single execution context.
        """
        tracker = self._get_tracker(session_id)
        tracker.set_error(error_message)
        self._stats.errors += 1

    def get_tracker(self, session_id: str) -> LoopStateTracker:
        """Get tracker for a session (for manual operations like set_error).

        Args:
            session_id: The session identifier

        Returns:
            LoopStateTracker for the session
        """
        return self._get_tracker(session_id)

    def get_summary(self, session_id: str) -> Dict[str, Any]:
        """Get execution summary for a session.

        Args:
            session_id: The session identifier

        Returns:
            Summary dict with execution statistics
        """
        tracker = self._get_tracker(session_id)
        return tracker.get_summary()

    async def get_stats(self) -> Dict[str, Any]:
        """Get middleware statistics."""
        async with self._stats_lock:
            return self._stats.to_dict()

    async def reset_stats(self) -> None:
        """Reset middleware statistics."""
        async with self._stats_lock:
            self._stats = StateTrackingStats()

    async def cleanup_session_async(self, session_id: str) -> None:
        """Cleanup tracker for a completed session (async, thread-safe).

        Args:
            session_id: The session identifier
        """
        async with self._trackers_lock:
            self._active_trackers.pop(session_id, None)
        clear_tracker(session_id)

    def cleanup_session(self, session_id: str) -> None:
        """Cleanup tracker for a completed session (sync).

        Note: This method is not thread-safe for concurrent async access.
        Use cleanup_session_async for async contexts.

        Args:
            session_id: The session identifier
        """
        self._active_trackers.pop(session_id, None)
        clear_tracker(session_id)


# Convenience function for getting middleware instance (thread-safe singleton)
_middleware_instance: Optional[StateTrackingMiddleware] = None
_middleware_lock = threading.Lock()


def get_state_tracking_middleware() -> StateTrackingMiddleware:
    """Get the global state tracking middleware instance.

    Uses double-checked locking for thread-safe lazy initialization.
    """
    global _middleware_instance
    if _middleware_instance is None:
        with _middleware_lock:
            if _middleware_instance is None:
                _middleware_instance = StateTrackingMiddleware()
    return _middleware_instance
