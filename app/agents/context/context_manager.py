"""
Agent Context Manager - Claude-style context flow management.

This module ensures context flows smoothly between agent and tools,
preserving conversation history, tool results, and recovery hints.

Key patterns from Claude Agent SDK:
1. Tools receive rich context (not just args)
2. Tool results flow back to context
3. Failed tools generate recovery hints
4. Session state is preserved across turns
"""

import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage

from app.core.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class ToolContext:
    """Rich context prepared for tool execution.

    This gives tools more information to work with than just their arguments,
    enabling smarter tool behavior based on conversation context.
    """

    session_id: str
    tool_name: Optional[str]
    user_intent: str
    conversation_summary: str
    previous_tool_results: list[dict]
    recovery_hints: list[str]
    scratchpad: dict
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class ToolExecutionRecord:
    """Record of a single tool execution for context tracking."""

    tool_name: str
    success: bool
    duration_ms: int
    timestamp: str
    error: Optional[str] = None
    summary: Optional[str] = None


class AgentContextManager:
    """Manages context flow through agent execution.

    Key responsibilities:
    1. Prepare rich context for tool execution
    2. Integrate tool results back into agent context
    3. Track tool execution history
    4. Generate recovery hints for failed tools
    5. Summarize conversation for context efficiency

    Example:
        context_manager = AgentContextManager()

        # Before tool execution
        tool_context = context_manager.prepare_tool_context(state, tool_call)

        # After tool execution
        state = context_manager.integrate_tool_result(state, result)

        # Get summary for agent
        summary = context_manager.get_execution_summary(state)
    """

    def __init__(self, max_context_tokens: int = 128000, max_history_items: int = 20):
        """Initialize the context manager.

        Args:
            max_context_tokens: Maximum tokens for context (for future optimization)
            max_history_items: Maximum tool execution records to keep in history
        """
        self.max_context_tokens = max_context_tokens
        self.max_history_items = max_history_items

    def prepare_tool_context(
        self,
        state: Any,  # GraphState
        tool_name: str,
    ) -> ToolContext:
        """Prepare rich context for tool execution.

        Args:
            state: Current graph state
            tool_name: Name of the tool being executed

        Returns:
            ToolContext with conversation summary, user intent, etc.
        """
        messages = getattr(state, "messages", []) or []
        scratchpad = getattr(state, "scratchpad", {}) or {}
        session_id = getattr(state, "session_id", "unknown")

        return ToolContext(
            session_id=session_id,
            tool_name=tool_name,
            user_intent=self._extract_user_intent(messages),
            conversation_summary=self._summarize_recent_messages(messages),
            previous_tool_results=self._get_tool_history(scratchpad),
            recovery_hints=self._get_recovery_hints(scratchpad),
            scratchpad=scratchpad,
        )

    def integrate_tool_result(
        self,
        state: Any,  # GraphState
        tool_name: str,
        success: bool,
        duration_ms: int,
        error: Optional[str] = None,
        result_summary: Optional[str] = None,
    ) -> dict:
        """Integrate tool result back into context.

        Updates the scratchpad with:
        - Tool execution history
        - Recovery hints for failed tools
        - Execution metadata for observability

        Args:
            state: Current graph state
            tool_name: Name of the executed tool
            success: Whether execution succeeded
            duration_ms: Execution duration
            error: Error message if failed
            result_summary: Brief summary of result

        Returns:
            Updated scratchpad dict to merge into state
        """
        scratchpad = dict(getattr(state, "scratchpad", {}) or {})
        system_bucket = dict(scratchpad.get("_system", {}))

        # Update tool history
        tool_history = list(system_bucket.get("_tool_history", []))
        tool_history.append(
            {
                "tool": tool_name,
                "success": success,
                "duration_ms": duration_ms,
                "timestamp": datetime.now().isoformat(),
                "error": error,
                "summary": result_summary,
            }
        )
        # Keep only recent history
        if len(tool_history) > self.max_history_items:
            tool_history = tool_history[-self.max_history_items :]
        system_bucket["_tool_history"] = tool_history

        # Update recovery hints for failed tools
        if not success and error:
            recovery_hints = list(system_bucket.get("_recovery_hints", []))
            recovery_hints.append(
                f"Tool '{tool_name}' failed: {error[:100]}... Consider alternative approaches."
            )
            # Keep only last 5 hints
            system_bucket["_recovery_hints"] = recovery_hints[-5:]

        scratchpad["_system"] = system_bucket
        return {"scratchpad": scratchpad}

    def get_execution_summary(self, state: Any) -> dict:
        """Get a summary of tool executions for observability.

        Args:
            state: Current graph state

        Returns:
            Summary dict with execution stats
        """
        scratchpad = getattr(state, "scratchpad", {}) or {}
        system_bucket = scratchpad.get("_system", {})
        tool_history = system_bucket.get("_tool_history", [])

        total = len(tool_history)
        successes = sum(1 for t in tool_history if t.get("success"))
        failures = total - successes
        total_duration = sum(t.get("duration_ms", 0) for t in tool_history)

        return {
            "total_tool_calls": total,
            "successful": successes,
            "failed": failures,
            "total_duration_ms": total_duration,
            "average_duration_ms": total_duration // total if total > 0 else 0,
            "recovery_hints": system_bucket.get("_recovery_hints", []),
        }

    def clear_recovery_hints(self, state: Any) -> dict:
        """Clear recovery hints after they've been used.

        Args:
            state: Current graph state

        Returns:
            Updated scratchpad dict to merge into state
        """
        scratchpad = dict(getattr(state, "scratchpad", {}) or {})
        system_bucket = dict(scratchpad.get("_system", {}))
        system_bucket["_recovery_hints"] = []
        scratchpad["_system"] = system_bucket
        return {"scratchpad": scratchpad}

    def _extract_user_intent(self, messages: list[BaseMessage], max_length: int = 200) -> str:
        """Extract the user's intent from recent messages.

        Looks for the most recent human message and extracts the intent.

        Args:
            messages: List of conversation messages
            max_length: Maximum length of intent string

        Returns:
            Brief description of user intent
        """
        # Find most recent human message
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage):
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                # Truncate if too long
                if len(content) > max_length:
                    return content[:max_length] + "..."
                return content

        return "No user intent available"

    def _summarize_recent_messages(
        self,
        messages: list[BaseMessage],
        max_messages: int = 5,
        max_per_message: int = 200,
    ) -> str:
        """Create concise summary of recent conversation for tool context.

        Args:
            messages: List of conversation messages
            max_messages: Maximum number of recent messages to include
            max_per_message: Maximum characters per message

        Returns:
            Formatted summary of recent conversation
        """
        recent = messages[-max_messages:] if len(messages) > max_messages else messages

        summaries = []
        for msg in recent:
            msg_type = getattr(msg, "type", "unknown")
            content = msg.content if isinstance(msg.content, str) else str(msg.content)

            if len(content) > max_per_message:
                content = content[:max_per_message] + "..."

            summaries.append(f"{msg_type}: {content}")

        return "\n".join(summaries) if summaries else "No conversation history"

    def _get_tool_history(self, scratchpad: dict) -> list[dict]:
        """Get recent tool execution history from scratchpad.

        Args:
            scratchpad: Current scratchpad state

        Returns:
            List of recent tool execution records
        """
        system_bucket = scratchpad.get("_system", {})
        return list(system_bucket.get("_tool_history", []))

    def _get_recovery_hints(self, scratchpad: dict) -> list[str]:
        """Get recovery hints from failed tool executions.

        Args:
            scratchpad: Current scratchpad state

        Returns:
            List of recovery hints
        """
        system_bucket = scratchpad.get("_system", {})
        return list(system_bucket.get("_recovery_hints", []))


# Global instance for convenience
_context_manager: Optional[AgentContextManager] = None
_context_manager_lock = threading.Lock()


def get_context_manager() -> AgentContextManager:
    """Get the global context manager instance."""
    global _context_manager
    if _context_manager is None:
        with _context_manager_lock:
            if _context_manager is None:
                _context_manager = AgentContextManager()
    return _context_manager
