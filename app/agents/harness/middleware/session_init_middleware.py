"""Session Initialization Middleware for Deep Agent context engineering.

This middleware implements the "initializer agent" pattern from Anthropic's
"Effective Harnesses for Long-Running Agents" - loading handoff context from
previous sessions and injecting it at the start of new sessions.

Key responsibilities:
1. Detect first message in a session
2. Load handoff context from previous sessions (if any)
3. Load active goals and progress notes
4. Inject context as system messages for the coordinator

Usage:
    from app.agents.harness.middleware import SessionInitMiddleware

    middleware = [
        SessionInitMiddleware(workspace_store),
        # ... other middleware
    ]
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple, TYPE_CHECKING

from langchain_core.messages import BaseMessage, SystemMessage
from loguru import logger

if TYPE_CHECKING:
    from app.agents.harness.store.workspace_store import SparrowWorkspaceStore

try:
    from langchain.agents.middleware.types import AgentMiddleware

    _MIDDLEWARE_AVAILABLE = True
except ImportError:
    _MIDDLEWARE_AVAILABLE = False
    AgentMiddleware = object  # type: ignore


# System message name for handoff context (used for filtering)
HANDOFF_SYSTEM_NAME = "session_handoff_context"
GOALS_SYSTEM_NAME = "session_active_goals"
PROGRESS_SYSTEM_NAME = "session_progress_notes"


class SessionInitMiddleware(AgentMiddleware if _MIDDLEWARE_AVAILABLE else object):
    """Middleware that initializes sessions with context from previous runs.

    On the first message of a session:
    1. Loads handoff context (summary, next_steps, active_todos)
    2. Loads active goals from /goals/active.json
    3. Loads progress notes from /progress/session_notes.md
    4. Injects relevant context as system messages

    This enables session continuity without losing context when:
    - Context window is exhausted and summarization occurs
    - User returns to a conversation after a break
    - Agent needs to resume work on a complex task

    Example:
        store = SparrowWorkspaceStore(session_id="session123")
        middleware = SessionInitMiddleware(store)

        # On first message, the middleware will inject:
        # - Previous handoff summary (if exists)
        # - Active goals and their status
        # - Progress notes from previous work
    """

    name = "session_init"

    def __init__(
        self,
        workspace_store: "SparrowWorkspaceStore",
        max_context_chars: int = 4000,
    ) -> None:
        """Initialize the middleware.

        Args:
            workspace_store: SparrowWorkspaceStore instance for this session.
            max_context_chars: Maximum characters to inject from handoff context.
        """
        self.workspace_store = workspace_store
        self.max_context_chars = max_context_chars
        self._initialized = False
        self._context_injected = False

    def _is_first_message(self, messages: List[BaseMessage]) -> bool:
        """Check if this is the first user message in the session.

        We detect first message by:
        1. No previous AI messages in the history
        2. Only has initial human message(s)

        Note: This is heuristic-based since we don't have direct access
        to session metadata here.
        """
        if self._initialized:
            return False

        # Count message types
        ai_count = sum(1 for m in messages if getattr(m, "type", "") == "ai")
        human_count = sum(1 for m in messages if getattr(m, "type", "") == "human")

        # First message: no AI responses yet, at most 1-2 human messages
        return ai_count == 0 and human_count <= 2

    async def _load_handoff_context(self) -> Optional[Dict[str, Any]]:
        """Load handoff context from previous session."""
        try:
            return await self.workspace_store.get_handoff_context()
        except Exception as exc:
            logger.debug("handoff_context_load_failed", error=str(exc))
            return None

    async def _load_active_goals(self) -> Optional[Dict[str, Any]]:
        """Load active goals from workspace."""
        try:
            return await self.workspace_store.get_active_goals()
        except Exception as exc:
            logger.debug("active_goals_load_failed", error=str(exc))
            return None

    async def _load_progress_notes(self) -> Optional[str]:
        """Load progress notes from workspace."""
        try:
            return await self.workspace_store.get_progress_notes()
        except Exception as exc:
            logger.debug("progress_notes_load_failed", error=str(exc))
            return None

    def _format_handoff_message(self, handoff: Dict[str, Any]) -> str:
        """Format handoff context into a readable system message."""
        parts = []

        summary = handoff.get("summary", "")
        if summary:
            parts.append(f"**Previous Session Summary:**\n{summary}")

        next_steps = handoff.get("next_steps", [])
        if next_steps:
            steps_text = "\n".join(f"- {step}" for step in next_steps)
            parts.append(f"**Suggested Next Steps:**\n{steps_text}")

        active_todos = handoff.get("active_todos", [])
        if active_todos:
            # Format todos with status
            todo_lines = []
            for todo in active_todos:
                if isinstance(todo, dict):
                    content = todo.get("content", "")
                    status = todo.get("status", "pending")
                    todo_lines.append(f"- [{status}] {content}")
                else:
                    todo_lines.append(f"- {todo}")
            parts.append(f"**Pending Tasks:**\n" + "\n".join(todo_lines))

        timestamp = handoff.get("timestamp") or handoff.get("captured_at", "")
        if timestamp:
            parts.append(f"_Captured: {timestamp}_")

        content = "\n\n".join(parts)

        # Truncate if too long
        if len(content) > self.max_context_chars:
            content = content[: self.max_context_chars - 50] + "\n\n_[Truncated for context limit]_"

        return content

    def _format_goals_message(self, goals: Dict[str, Any]) -> str:
        """Format active goals into a system message."""
        parts = []

        features = goals.get("features", [])
        if features:
            feature_lines = []
            for feature in features:
                if isinstance(feature, dict):
                    name = feature.get("name", "Unknown")
                    status = feature.get("status", "pending")
                    emoji = "✅" if status == "pass" else "❌" if status == "fail" else "⏳"
                    feature_lines.append(f"- {emoji} {name}: {status}")
                else:
                    feature_lines.append(f"- {feature}")
            parts.append("**Active Goals:**\n" + "\n".join(feature_lines))

        description = goals.get("description", "")
        if description:
            parts.append(f"**Goal Description:**\n{description}")

        return "\n\n".join(parts)

    async def before_agent(
        self,
        messages: List[BaseMessage],
        config: Dict[str, Any],
        state: Any,
    ) -> List[BaseMessage]:
        """Inject handoff context before agent processes messages.

        This method is called before each agent invocation. On the first
        message of a session, it loads and injects handoff context.

        Args:
            messages: Current message list.
            config: Agent configuration.
            state: Current graph state.

        Returns:
            Modified message list with injected context.
        """
        if not _MIDDLEWARE_AVAILABLE:
            return messages

        # Skip if not first message or already injected
        if not self._is_first_message(messages) or self._context_injected:
            self._initialized = True
            return messages

        self._initialized = True
        injected_messages: List[BaseMessage] = []

        # Load handoff context
        handoff = await self._load_handoff_context()
        if handoff:
            handoff_content = self._format_handoff_message(handoff)
            if handoff_content:
                injected_messages.append(
                    SystemMessage(
                        content=f"[Session Handoff Context]\n\n{handoff_content}",
                        name=HANDOFF_SYSTEM_NAME,
                    )
                )
                logger.info(
                    "session_handoff_injected",
                    session_id=self.workspace_store.session_id,
                    handoff_chars=len(handoff_content),
                )

        # Load active goals
        goals = await self._load_active_goals()
        if goals:
            goals_content = self._format_goals_message(goals)
            if goals_content:
                injected_messages.append(
                    SystemMessage(
                        content=f"[Active Goals]\n\n{goals_content}",
                        name=GOALS_SYSTEM_NAME,
                    )
                )
                logger.debug(
                    "session_goals_injected",
                    session_id=self.workspace_store.session_id,
                    goal_count=len(goals.get("features", [])),
                )

        # Load progress notes (only if short enough)
        progress = await self._load_progress_notes()
        if progress and len(progress) < 2000:
            injected_messages.append(
                SystemMessage(
                    content=f"[Session Progress Notes]\n\n{progress}",
                    name=PROGRESS_SYSTEM_NAME,
                )
            )
            logger.debug(
                "session_progress_injected",
                session_id=self.workspace_store.session_id,
                progress_chars=len(progress),
            )

        if injected_messages:
            self._context_injected = True
            # Inject at the beginning, before user messages
            return injected_messages + list(messages)

        return messages

    async def after_agent(
        self,
        messages: List[BaseMessage],
        output: BaseMessage,
        config: Dict[str, Any],
        state: Any,
    ) -> Tuple[List[BaseMessage], BaseMessage]:
        """Post-process after agent completes.

        Currently a no-op, but could be extended to:
        - Track session progress
        - Update goals based on agent output
        - Prepare handoff context for summarization

        Args:
            messages: Message list used.
            output: Agent's output message.
            config: Agent configuration.
            state: Current graph state.

        Returns:
            Tuple of (messages, output) unchanged.
        """
        return messages, output


def strip_session_context_messages(messages: List[BaseMessage]) -> List[BaseMessage]:
    """Remove session context system messages from message list.

    Call this before persisting messages to avoid duplicate context injection.

    Args:
        messages: List of messages to filter.

    Returns:
        Filtered message list without session context messages.
    """
    context_names = {HANDOFF_SYSTEM_NAME, GOALS_SYSTEM_NAME, PROGRESS_SYSTEM_NAME}
    return [
        msg
        for msg in messages
        if not (isinstance(msg, SystemMessage) and getattr(msg, "name", "") in context_names)
    ]
