"""Handoff Capture Middleware for Deep Agent context engineering.

This middleware implements the "handoff protocol" from Anthropic's
"Effective Harnesses for Long-Running Agents" - capturing session context
when summarization is about to occur to enable session continuity.

Key responsibilities:
1. Detect when context is approaching summarization threshold
2. Extract key information (todos, progress, decisions made)
3. Store handoff context for future session resumption
4. Optionally trigger progress note updates

Usage:
    from app.agents.harness.middleware import HandoffCaptureMiddleware

    middleware = HandoffCaptureMiddleware(
        workspace_store=SparrowWorkspaceStore(session_id),
        capture_threshold_fraction=0.6,  # Capture before summarization at 0.7
    )
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from langchain_core.messages import BaseMessage
from loguru import logger

# Import shared utilities from canonical location
from app.agents.harness._utils import estimate_tokens, extract_message_text

if TYPE_CHECKING:
    from app.agents.harness.store.workspace_store import SparrowWorkspaceStore

try:
    from langchain.agents.middleware import AgentMiddleware

    _MIDDLEWARE_AVAILABLE = True
except ImportError:
    _MIDDLEWARE_AVAILABLE = False

    class AgentMiddleware:  # type: ignore[no-redef]
        pass


class HandoffCaptureMiddleware(AgentMiddleware):
    """Middleware that captures handoff context before summarization.

    This middleware monitors context size and captures important session
    information before summarization occurs, enabling:
    - Session continuity after context compaction
    - Cross-session task resumption
    - Progress tracking for long-running tasks

    The captured handoff context includes:
    - Summary of conversation so far
    - Active todos and their status
    - Key decisions and findings
    - Suggested next steps

    Example:
        store = SparrowWorkspaceStore(session_id="session123")
        middleware = HandoffCaptureMiddleware(
            workspace_store=store,
            capture_threshold_fraction=0.6,  # Before summarization at 0.7
        )
    """

    name = "handoff_capture"

    def __init__(
        self,
        workspace_store: "SparrowWorkspaceStore",
        context_window: int = 128000,
        capture_threshold_fraction: float = 0.6,
        summarization_threshold_fraction: float = 0.7,
        max_summary_tokens: int = 2000,
    ) -> None:
        """Initialize the middleware.

        Args:
            workspace_store: SparrowWorkspaceStore instance for this session.
            context_window: Model's context window in tokens.
            capture_threshold_fraction: Fraction of context to trigger handoff capture.
            summarization_threshold_fraction: Fraction when summarization kicks in.
            max_summary_tokens: Maximum tokens for generated summary.
        """
        self.workspace_store = workspace_store
        self.context_window = context_window
        self.capture_threshold = int(context_window * capture_threshold_fraction)
        self.summarization_threshold = int(
            context_window * summarization_threshold_fraction
        )
        self.max_summary_tokens = max_summary_tokens

        self._capture_pending = False
        self._last_capture_tokens = 0
        self._capture_count = 0

    def before_agent(self, state: Any, runtime: Any) -> Optional[Dict[str, Any]]:
        """Check if handoff capture is needed before agent processes."""
        messages = self._extract_messages(state)
        if not messages:
            return None

        estimated_tokens = estimate_tokens(messages)

        # Check if we're approaching summarization threshold
        if estimated_tokens >= self.capture_threshold and not self._capture_pending:
            self._capture_pending = True
            logger.info(
                "handoff_capture_pending",
                estimated_tokens=estimated_tokens,
                threshold=self.capture_threshold,
                session_id=self.workspace_store.session_id,
            )

        return None

    async def abefore_agent(self, state: Any, runtime: Any) -> Optional[Dict[str, Any]]:
        """Async check if handoff capture is needed."""
        return self.before_agent(state, runtime)

    def after_agent(self, state: Any, runtime: Any) -> Optional[Dict[str, Any]]:
        """Capture handoff after agent completes if pending."""
        if not self._capture_pending:
            return None

        messages = self._extract_messages(state)
        scratchpad = self._extract_scratchpad(state)

        # Run async capture in event loop
        try:
            asyncio.get_running_loop()
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                pool.submit(
                    asyncio.run, self._capture_handoff(messages, scratchpad)
                ).result()
        except RuntimeError:
            asyncio.run(self._capture_handoff(messages, scratchpad))

        return None

    async def aafter_agent(self, state: Any, runtime: Any) -> Optional[Dict[str, Any]]:
        """Async capture handoff after agent completes."""
        if not self._capture_pending:
            return None

        messages = self._extract_messages(state)
        scratchpad = self._extract_scratchpad(state)

        await self._capture_handoff(messages, scratchpad)

        return None

    def wrap_model_call(self, request: Any, handler: Callable) -> Any:
        """Pass-through for model calls."""
        return handler(request)

    async def awrap_model_call(self, request: Any, handler: Callable) -> Any:
        """Async pass-through for model calls."""
        return await handler(request)

    def wrap_tool_call(self, request: Any, handler: Callable) -> Any:
        """Pass-through for tool calls."""
        return handler(request)

    async def awrap_tool_call(self, request: Any, handler: Callable) -> Any:
        """Async pass-through for tool calls."""
        return await handler(request)

    def _extract_messages(self, state: Any) -> List[BaseMessage]:
        """Extract messages from state."""
        if isinstance(state, dict):
            return state.get("messages", [])
        return getattr(state, "messages", [])

    def _extract_scratchpad(self, state: Any) -> Dict[str, Any]:
        """Extract scratchpad from state."""
        if isinstance(state, dict):
            return state.get("scratchpad", {}) or {}
        return getattr(state, "scratchpad", {}) or {}

    async def _capture_handoff(
        self,
        messages: List[BaseMessage],
        scratchpad: Dict[str, Any],
    ) -> None:
        """Capture handoff context and store it.

        Args:
            messages: Current message history.
            scratchpad: Current scratchpad state.
        """
        try:
            # Extract key information
            summary = self._generate_conversation_summary(messages)
            todos = self._extract_todos(scratchpad)
            next_steps = self._extract_next_steps(messages)
            decisions = self._extract_key_decisions(messages)

            handoff_context = {
                "summary": summary,
                "active_todos": todos,
                "next_steps": next_steps,
                "key_decisions": decisions,
                "message_count": len(messages),
                "estimated_tokens": estimate_tokens(messages),
                "capture_number": self._capture_count + 1,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            handoff_context.update(
                {
                    "tool_usage_summary": self._extract_tool_usage_summary(messages),
                    "subagent_deployments": self._extract_subagent_deployments(
                        messages
                    ),
                    "memory_ids": self._extract_memory_ids(scratchpad),
                    "evidence_trail": self._extract_evidence_trail(
                        messages, scratchpad
                    ),
                }
            )

            # Store handoff context
            await self.workspace_store.set_handoff_context(handoff_context)

            # Update progress notes
            progress_notes = self._format_progress_notes(handoff_context)
            await self.workspace_store.set_progress_notes(progress_notes)

            self._capture_pending = False
            self._last_capture_tokens = estimate_tokens(messages)
            self._capture_count += 1

            logger.info(
                "handoff_captured",
                session_id=self.workspace_store.session_id,
                capture_number=self._capture_count,
                summary_length=len(summary),
                todo_count=len(todos),
                next_steps_count=len(next_steps),
            )

        except Exception as exc:
            logger.warning("handoff_capture_failed", error=str(exc))
            self._capture_pending = False

    def _generate_conversation_summary(self, messages: List[BaseMessage]) -> str:
        """Generate a summary of the conversation.

        This extracts key points from the conversation without using an LLM.
        A simple heuristic approach that works well for most conversations.

        Args:
            messages: List of messages to summarize.

        Returns:
            Text summary of the conversation.
        """
        parts = []

        # Extract the initial user request
        for msg in messages:
            if getattr(msg, "type", "") == "human":
                content = self._get_message_text(msg)
                if content:
                    # Take first sentence/paragraph as the request
                    lines = content.split("\n")
                    request = lines[0][:200]
                    parts.append(f"User Request: {request}")
                    break

        # Extract key AI decisions/findings (from recent messages)
        ai_points = []
        for msg in reversed(messages[-20:]):  # Last 20 messages
            if getattr(msg, "type", "") == "ai":
                content = self._get_message_text(msg)
                if content:
                    # Look for conclusion-like statements
                    for sentence in re.split(r"[.!?]", content):
                        sentence = sentence.strip()
                        if len(sentence) > 50 and len(sentence) < 300:
                            # Prefer sentences with key phrases
                            key_phrases = [
                                "found",
                                "discovered",
                                "concluded",
                                "determined",
                                "the solution",
                                "fixed",
                                "implemented",
                                "completed",
                            ]
                            if any(
                                phrase in sentence.lower() for phrase in key_phrases
                            ):
                                if sentence not in ai_points:
                                    ai_points.append(sentence)
                                    if len(ai_points) >= 3:
                                        break
                if len(ai_points) >= 3:
                    break

        if ai_points:
            parts.append("Key Findings:")
            for point in ai_points:
                parts.append(f"- {point}")

        return "\n".join(parts) if parts else "Conversation in progress."

    def _extract_todos(self, scratchpad: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract active todos from scratchpad.

        Args:
            scratchpad: Current scratchpad state.

        Returns:
            List of todo items with status.
        """
        todos = []

        # Check for todos in scratchpad (from TodoListMiddleware)
        if "todos" in scratchpad:
            for todo in scratchpad["todos"]:
                if isinstance(todo, dict):
                    todos.append(
                        {
                            "content": todo.get("content", str(todo)),
                            "status": todo.get("status", "pending"),
                        }
                    )
                else:
                    todos.append({"content": str(todo), "status": "pending"})

        return todos

    def _extract_next_steps(self, messages: List[BaseMessage]) -> List[str]:
        """Extract suggested next steps from recent AI messages.

        Args:
            messages: Current message history.

        Returns:
            List of suggested next steps.
        """
        next_steps = []

        # Look in recent AI messages for next step suggestions
        for msg in reversed(messages[-10:]):
            if getattr(msg, "type", "") != "ai":
                continue

            content = self._get_message_text(msg)
            if not content:
                continue

            # Look for numbered steps or bullet points
            lines = content.split("\n")
            for line in lines:
                line = line.strip()
                # Match numbered steps like "1.", "1)", "Step 1:"
                if re.match(r"^(\d+[.)\]]|\*|-|•|Step \d)", line):
                    # Clean up the line
                    clean = re.sub(r"^(\d+[.)\]]|\*|-|•|Step \d+:?)\s*", "", line)
                    if clean and len(clean) < 200:
                        if clean not in next_steps:
                            next_steps.append(clean)
                            if len(next_steps) >= 5:
                                break
            if len(next_steps) >= 5:
                break

        return next_steps

    def _extract_key_decisions(self, messages: List[BaseMessage]) -> List[str]:
        """Extract key decisions made during the conversation.

        Args:
            messages: Current message history.

        Returns:
            List of key decisions/choices made.
        """
        decisions = []

        # Look for decision-related language
        # Use non-capturing groups (?:...) to avoid findall returning tuples
        decision_patterns = [
            r"I(?:'ve| have) decided to",
            r"I(?:'ll| will) (?:use|implement|create|build)",
            r"the best (?:approach|solution|way) is",
            r"I recommend",
            r"Let's go with",
            r"The decision is to",
        ]

        for msg in reversed(messages[-20:]):
            if getattr(msg, "type", "") != "ai":
                continue

            content = self._get_message_text(msg)
            if not content:
                continue

            for pattern in decision_patterns:
                matches = re.findall(f"{pattern}[^.!?]*[.!?]", content, re.IGNORECASE)
                for match in matches:
                    clean = match.strip()
                    if clean and len(clean) < 300 and clean not in decisions:
                        decisions.append(clean)
                        if len(decisions) >= 5:
                            break
                if len(decisions) >= 5:
                    break
            if len(decisions) >= 5:
                break

        return decisions

    def _extract_tool_usage_summary(self, messages: List[BaseMessage]) -> Dict[str, Any]:
        """Extract high-level requested/executed tool usage from message history."""
        requested: set[str] = set()
        executed: set[str] = set()

        for msg in messages:
            if getattr(msg, "type", "") == "ai":
                tool_calls = getattr(msg, "tool_calls", None) or (
                    (getattr(msg, "additional_kwargs", {}) or {}).get("tool_calls")
                )
                if isinstance(tool_calls, list):
                    for call in tool_calls:
                        if not isinstance(call, dict):
                            continue
                        name = call.get("name")
                        if isinstance(name, str) and name:
                            requested.add(name)
            elif getattr(msg, "type", "") == "tool":
                tool_name = getattr(msg, "name", None)
                if isinstance(tool_name, str) and tool_name:
                    executed.add(tool_name)

        return {
            "requested": sorted(requested),
            "requested_count": len(requested),
            "executed": sorted(executed),
            "executed_count": len(executed),
        }

    def _extract_subagent_deployments(self, messages: List[BaseMessage]) -> List[str]:
        """Extract subagent types requested via `task` tool calls."""
        deployed: set[str] = set()

        for msg in messages:
            if getattr(msg, "type", "") != "ai":
                continue
            tool_calls = getattr(msg, "tool_calls", None) or (
                (getattr(msg, "additional_kwargs", {}) or {}).get("tool_calls")
            )
            if not isinstance(tool_calls, list):
                continue
            for call in tool_calls:
                if not isinstance(call, dict) or call.get("name") != "task":
                    continue
                args = call.get("args") or call.get("arguments") or {}
                if not isinstance(args, dict):
                    continue
                subagent_type = args.get("subagent_type") or args.get("subagentType")
                if isinstance(subagent_type, str) and subagent_type.strip():
                    deployed.add(subagent_type.strip())

        return sorted(deployed)

    def _extract_memory_ids(self, scratchpad: Dict[str, Any]) -> List[str]:
        """Extract retrieved memory ids from scratchpad memory stats."""
        system_bucket = scratchpad.get("_system", {}) if isinstance(scratchpad, dict) else {}
        memory_stats = (
            system_bucket.get("memory_stats", {}) if isinstance(system_bucket, dict) else {}
        )
        ids = memory_stats.get("retrieved_memory_ids", []) if isinstance(memory_stats, dict) else []
        if not isinstance(ids, list):
            return []
        return [str(value) for value in ids if value is not None]

    def _extract_evidence_trail(
        self,
        messages: List[BaseMessage],
        scratchpad: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Extract a compact trail of recent tool evidence."""
        evidence: List[Dict[str, Any]] = []

        for msg in reversed(messages):
            if getattr(msg, "type", "") != "tool":
                continue
            content = self._get_message_text(msg)
            evidence.append(
                {
                    "tool_name": getattr(msg, "name", None),
                    "tool_call_id": getattr(msg, "tool_call_id", None),
                    "excerpt": content[:400] if content else "",
                }
            )
            if len(evidence) >= 5:
                break

        system_bucket = scratchpad.get("_system", {}) if isinstance(scratchpad, dict) else {}
        model_selection = (
            system_bucket.get("model_selection")
            if isinstance(system_bucket, dict)
            else None
        )
        if model_selection:
            evidence.append({"model_selection": model_selection})

        return list(reversed(evidence))

    def _format_progress_notes(self, handoff: Dict[str, Any]) -> str:
        """Format handoff context into progress notes.

        Args:
            handoff: Handoff context dictionary.

        Returns:
            Formatted markdown progress notes.
        """
        lines = [
            "# Session Progress Notes",
            f"_Last updated: {handoff.get('timestamp', 'Unknown')}_",
            f"_Capture #{handoff.get('capture_number', 1)}_",
            "",
            "## Summary",
            handoff.get("summary", "No summary available."),
            "",
        ]

        todos = handoff.get("active_todos", [])
        if todos:
            lines.append("## Active Tasks")
            for todo in todos:
                status = todo.get("status", "pending")
                emoji = "✅" if status == "completed" else "⏳"
                content = todo.get("content", str(todo))
                lines.append(f"- {emoji} [{status}] {content}")
            lines.append("")

        next_steps = handoff.get("next_steps", [])
        if next_steps:
            lines.append("## Suggested Next Steps")
            for i, step in enumerate(next_steps, 1):
                lines.append(f"{i}. {step}")
            lines.append("")

        decisions = handoff.get("key_decisions", [])
        if decisions:
            lines.append("## Key Decisions Made")
            for decision in decisions:
                lines.append(f"- {decision}")
            lines.append("")

        return "\n".join(lines)

    def _get_message_text(self, msg: BaseMessage) -> str:
        """Extract text content from a message.

        Args:
            msg: Message to extract text from.

        Returns:
            Text content of the message.
        """
        return extract_message_text(msg)

    def get_stats(self) -> Dict[str, Any]:
        """Get handoff capture statistics."""
        return {
            "capture_count": self._capture_count,
            "last_capture_tokens": self._last_capture_tokens,
            "capture_pending": self._capture_pending,
            "capture_threshold": self.capture_threshold,
        }
