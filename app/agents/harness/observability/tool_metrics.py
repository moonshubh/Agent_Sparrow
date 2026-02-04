"""Lightweight tool execution metrics sink.

Records recent tool executions for observability without coupling ToolExecutor
to any specific backend. A contextvar carries the current session ID so
orchestration layers can attribute tool runs to sessions.
"""

from __future__ import annotations

from collections import deque
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from typing import Any, Deque, Iterable

from app.agents.tools.tool_executor import ToolExecutionResult
from app.core.settings import settings

# Track the active session for attribution; orchestration layer should set/reset.
_current_session: ContextVar[str | None] = ContextVar("tool_session_id", default=None)

# Bounded in-memory buffer to avoid unbounded growth.
_BUFFER_SIZE = 200


@dataclass
class ToolRunRecord:
    """Immutable record of a tool execution."""

    session_id: str | None
    tool_name: str
    tool_call_id: str
    success: bool
    status: str | None
    duration_ms: int
    retries_used: int
    is_retryable_error: bool
    error_type: str | None
    error: str | None
    args_summary: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_records: Deque[ToolRunRecord] = deque(maxlen=_BUFFER_SIZE)


def set_current_session(session_id: str | None):
    """Bind the current session for subsequent tool result recording."""
    return _current_session.set(session_id)


def reset_current_session(token) -> None:
    """Reset the current session binding."""
    _current_session.reset(token)


def record_tool_result(result: ToolExecutionResult) -> None:
    """Record a tool execution result into the in-memory buffer."""
    record = ToolRunRecord(
        session_id=_current_session.get(),
        tool_name=result.tool_name,
        tool_call_id=result.tool_call_id,
        success=result.success,
        status=result.status,
        duration_ms=result.duration_ms,
        retries_used=result.retries_used,
        is_retryable_error=result.is_retryable_error,
        error_type=result.error_type,
        error=result.error,
        args_summary=result.args_summary,
    )
    _records.append(record)


def get_recent_results(limit: int = 50) -> list[dict[str, Any]]:
    """Return recent tool execution records (most recent last)."""
    return [rec.to_dict() for rec in list(_records)[-limit:]]


def iter_results() -> Iterable[ToolRunRecord]:
    """Iterate over recorded results for diagnostic tooling."""
    return tuple(_records)


def get_recent_results_for_session(
    session_id: str, limit: int = 20
) -> list[dict[str, Any]]:
    """Return recent tool runs for a session."""
    if not session_id:
        return []
    filtered = [rec for rec in _records if rec.session_id == session_id]
    return [rec.to_dict() for rec in filtered[-limit:]]


def publish_tool_batch_to_langsmith(session_id: str | None, limit: int = 20) -> None:
    """Attach a batch of recent tool runs to the active LangSmith run."""
    if not settings.langsmith_tracing_enabled or not session_id:
        return
    try:
        from langsmith.run_helpers import get_current_run_tree

        tree = get_current_run_tree()
        if not tree:
            return
        batch = get_recent_results_for_session(session_id, limit=limit)
        if not batch:
            return
        tree.add_metadata({"tool_runs": batch})
    except Exception:
        # Best effort only; never disrupt execution
        return
