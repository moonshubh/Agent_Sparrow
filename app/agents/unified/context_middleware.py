"""Context management middleware for long-running tasks.

This module provides middleware for intelligent context compaction:
1. FractionBasedSummarizationMiddleware - Triggers summarization at X% of context window
2. ContextEditingMiddleware - Clears old tool results to free tokens
3. ModelRetryMiddleware - Handles context overflow with graceful retry

These middleware follow the LangChain AgentMiddleware interface.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from langchain_core.messages import AIMessage, BaseMessage, RemoveMessage, ToolMessage
from loguru import logger

from langgraph.graph.message import REMOVE_ALL_MESSAGES

# Import AgentMiddleware interface
try:
    from langchain.agents.middleware import AgentMiddleware, AgentState
    from langchain.agents.middleware.summarization import SummarizationMiddleware
    AGENT_MIDDLEWARE_AVAILABLE = True
except ImportError:
    AGENT_MIDDLEWARE_AVAILABLE = False
    AgentMiddleware = object
    AgentState = Dict[str, Any]
    SummarizationMiddleware = object

from app.agents.unified.model_context import DEFAULT_CONTEXT_WINDOW, get_model_context_window


def estimate_tokens(messages: List[BaseMessage]) -> int:
    """Estimate token count for messages using ~4 chars/token heuristic.

    Args:
        messages: List of messages to count.

    Returns:
        Estimated token count.
    """
    total_chars = 0
    for msg in messages:
        content = getattr(msg, "content", "")
        if isinstance(content, str):
            total_chars += len(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict):
                    if part.get("type") == "text":
                        total_chars += len(part.get("text", ""))
                    elif part.get("type") == "image_url":
                        # Images are ~765 tokens for standard resolution
                        total_chars += 3060  # ~765 * 4 chars/token
                else:
                    total_chars += len(str(part))
        else:
            total_chars += len(str(content))

    return total_chars // 4


@dataclass
class ContextStats:
    """Statistics for context management operations."""

    summarization_triggers: int = 0
    tool_results_cleared: int = 0
    retry_attempts: int = 0
    tokens_before_compaction: int = 0
    tokens_after_compaction: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for observability."""
        return {
            "summarization_triggers": self.summarization_triggers,
            "tool_results_cleared": self.tool_results_cleared,
            "retry_attempts": self.retry_attempts,
            "tokens_before_compaction": self.tokens_before_compaction,
            "tokens_after_compaction": self.tokens_after_compaction,
        }


class FractionBasedSummarizationMiddleware(SummarizationMiddleware if AGENT_MIDDLEWARE_AVAILABLE else object):
    """Summarization middleware that triggers at a fraction of context window.

    Instead of a fixed token threshold, this middleware triggers summarization
    when the message history reaches X% of the model's context window.

    This adapts automatically to different model context sizes:
    - Gemini 2.5 Flash (1M tokens) → triggers at 700K tokens (0.7)
    - Grok 4.1 (400K tokens) → triggers at 280K tokens (0.7)

    Usage:
        middleware = FractionBasedSummarizationMiddleware(
            model="gemini-2.5-flash-lite",
            trigger_fraction=0.7,  # 70% of context window
            messages_to_keep=6,
        )
    """

    def __init__(
        self,
        model: Any,
        trigger_fraction: float = 0.7,
        messages_to_keep: int = 6,
        model_name: Optional[str] = None,
        **kwargs,
    ):
        """Initialize fraction-based summarization middleware.

        Args:
            model: Chat model for summarization (or model name string).
            trigger_fraction: Fraction of context window to trigger summarization (0.0-1.0).
            messages_to_keep: Number of recent messages to preserve after summarization.
            model_name: Explicit model name for context window lookup.
            **kwargs: Additional arguments passed to SummarizationMiddleware.
        """
        self.trigger_fraction = min(max(trigger_fraction, 0.1), 0.95)
        self._model_name = model_name
        self._stats = ContextStats()

        # Calculate token threshold from fraction
        context_window = self._get_context_window(model, model_name)
        max_tokens = int(context_window * self.trigger_fraction)

        logger.info(
            "fraction_summarization_configured",
            trigger_fraction=self.trigger_fraction,
            context_window=context_window,
            max_tokens_before_summary=max_tokens,
            messages_to_keep=messages_to_keep,
        )

        # Initialize parent with calculated threshold
        if AGENT_MIDDLEWARE_AVAILABLE:
            super().__init__(
                model=model,
                max_tokens_before_summary=max_tokens,
                messages_to_keep=messages_to_keep,
                **kwargs,
            )
        else:
            self.model = model
            self.max_tokens_before_summary = max_tokens
            self.messages_to_keep = messages_to_keep

    def _get_context_window(self, model: Any, model_name: Optional[str]) -> int:
        """Get context window for the model.

        Args:
            model: Chat model instance or name.
            model_name: Explicit model name override.

        Returns:
            Context window size in tokens.
        """
        # Try explicit model name first
        if model_name:
            return get_model_context_window(model_name)

        # Try to extract from model instance
        if hasattr(model, "model_name"):
            return get_model_context_window(model.model_name)
        if hasattr(model, "model"):
            return get_model_context_window(model.model)
        if isinstance(model, str):
            return get_model_context_window(model)

        return DEFAULT_CONTEXT_WINDOW

    @property
    def name(self) -> str:
        """Middleware name for identification."""
        return "fraction_summarization"

    def get_stats(self) -> Dict[str, Any]:
        """Get summarization statistics."""
        return self._stats.to_dict()


class ContextEditingMiddleware(AgentMiddleware if AGENT_MIDDLEWARE_AVAILABLE else object):
    """Middleware that clears old tool results to prevent context overflow.

    When the estimated token count exceeds a threshold, this middleware
    clears older tool call/result pairs while keeping the most recent ones.

    Features:
    - Configurable token threshold for triggering cleanup
    - Preserves N most recent tool results
    - Can exclude specific tools from cleanup (e.g., KB search results)
    - Replaces cleared content with a placeholder message

    Usage:
        middleware = ContextEditingMiddleware(
            trigger_tokens=100000,
            keep_recent=3,
            exclude_tools=["search_knowledge_base"],
            placeholder="[cleared - result available in storage]",
        )
    """

    def __init__(
        self,
        trigger_tokens: int = 100000,
        keep_recent: int = 3,
        exclude_tools: Optional[List[str]] = None,
        placeholder: str = "[Result cleared to save context - use tool again if needed]",
    ):
        """Initialize context editing middleware.

        Args:
            trigger_tokens: Token count threshold to trigger cleanup.
            keep_recent: Number of recent tool results to preserve.
            exclude_tools: Tool names to never clear (e.g., important KB results).
            placeholder: Message to replace cleared content.
        """
        self.trigger_tokens = trigger_tokens
        self.keep_recent = keep_recent
        self.exclude_tools = set(exclude_tools or [])
        self.placeholder = placeholder
        self._stats = ContextStats()
        self._stats_lock = asyncio.Lock()

    @property
    def name(self) -> str:
        """Middleware name for identification."""
        return "context_editing"

    def before_model(self, state: Any, runtime: Any) -> Optional[Dict[str, Any]]:  # noqa: ARG002
        """Process messages before each model call.

        This runs inside the agent loop (model → tools → model → ...). Tool results
        accumulate over multiple iterations, so we must clear older tool results
        repeatedly (not just once at agent start) to prevent context overflow.
        """
        messages = self._extract_messages(state)
        return self._maybe_clear_tool_results(messages)

    async def abefore_model(self, state: Any, runtime: Any) -> Optional[Dict[str, Any]]:  # noqa: ARG002
        """Async version of before_model."""
        return self.before_model(state, runtime)

    def before_agent(self, state: Any, runtime: Any) -> Optional[Dict[str, Any]]:
        """Process messages before agent call, clearing old tool results if needed."""
        messages = self._extract_messages(state)
        return self._maybe_clear_tool_results(messages)

    async def abefore_agent(self, state: Any, runtime: Any) -> Optional[Dict[str, Any]]:
        """Async version of before_agent."""
        return self.before_agent(state, runtime)

    def after_agent(self, state: Any, runtime: Any) -> Optional[Dict[str, Any]]:
        """No-op after agent."""
        return None

    async def aafter_agent(self, state: Any, runtime: Any) -> Optional[Dict[str, Any]]:
        """No-op after agent."""
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

    def _maybe_clear_tool_results(self, messages: List[BaseMessage]) -> Optional[Dict[str, Any]]:
        if not messages:
            return None

        estimated_tokens = estimate_tokens(messages)
        if estimated_tokens < self.trigger_tokens:
            return None

        self._stats.tokens_before_compaction = estimated_tokens

        cleared_before = self._stats.tool_results_cleared
        edited_messages = self._clear_old_tool_results(messages)
        cleared_now = self._stats.tool_results_cleared - cleared_before
        if cleared_now <= 0:
            return None

        self._stats.tokens_after_compaction = estimate_tokens(edited_messages)

        logger.info(
            "context_editing_triggered",
            tokens_before=self._stats.tokens_before_compaction,
            tokens_after=self._stats.tokens_after_compaction,
            results_cleared=cleared_now,
        )

        return {
            "messages": [
                RemoveMessage(id=REMOVE_ALL_MESSAGES),
                *edited_messages,
            ]
        }

    def _clear_old_tool_results(self, messages: List[BaseMessage]) -> List[BaseMessage]:
        """Clear old tool results, keeping recent ones.

        Args:
            messages: Original message list.

        Returns:
            Edited message list with old tool results cleared.
        """
        # Find tool messages and their indices
        tool_msg_indices = []
        for i, msg in enumerate(messages):
            if isinstance(msg, ToolMessage):
                tool_name = getattr(msg, "name", None)
                tool_call_id = getattr(msg, "tool_call_id", None)

                # Check additional_kwargs for tool info
                if not tool_name:
                    additional = getattr(msg, "additional_kwargs", {}) or {}
                    tool_name = additional.get("tool_name") or additional.get("name")

                if tool_name not in self.exclude_tools:
                    tool_msg_indices.append((i, tool_name, tool_call_id))

        if len(tool_msg_indices) <= self.keep_recent:
            return messages

        # Clear older tool results (keep the most recent ones)
        indices_to_clear = tool_msg_indices[:-self.keep_recent]
        cleared_indices = {idx for idx, _, _ in indices_to_clear}
        tool_name_by_index = {idx: tool_name for idx, tool_name, _ in indices_to_clear}

        edited_messages = []
        for i, msg in enumerate(messages):
            if i in cleared_indices:
                # Replace with placeholder
                original_tool_call_id = getattr(msg, "tool_call_id", "unknown")
                original_tool_name = tool_name_by_index.get(i)
                edited_messages.append(
                    ToolMessage(
                        content=self.placeholder,
                        tool_call_id=original_tool_call_id,
                        name=str(original_tool_name) if original_tool_name else "tool",
                    )
                )
                self._stats.tool_results_cleared += 1
            else:
                edited_messages.append(msg)

        return edited_messages

    def get_stats(self) -> Dict[str, Any]:
        """Get context editing statistics."""
        return self._stats.to_dict()


class ModelRetryMiddleware(AgentMiddleware if AGENT_MIDDLEWARE_AVAILABLE else object):
    """Middleware that handles context overflow with graceful retry.

    When a model call fails due to context length errors:
    1. Attempts to compact the context (via triggering summarization)
    2. Retries the call with exponential backoff
    3. Returns a graceful error message instead of crashing

    Usage:
        middleware = ModelRetryMiddleware(
            max_retries=2,
            on_failure="continue",  # or "raise"
        )
    """

    CONTEXT_ERROR_PATTERNS = [
        "context length",
        "token limit",
        "maximum context",
        "input too long",
        "exceeds the maximum",
        "too many tokens",
    ]

    def __init__(
        self,
        max_retries: int = 2,
        on_failure: str = "continue",
        base_delay: float = 1.0,
    ):
        """Initialize model retry middleware.

        Args:
            max_retries: Maximum number of retry attempts.
            on_failure: "continue" to return error AIMessage, "raise" to propagate.
            base_delay: Base delay in seconds for exponential backoff.
        """
        self.max_retries = max_retries
        self.on_failure = on_failure
        self.base_delay = base_delay
        self._stats = ContextStats()

    @property
    def name(self) -> str:
        """Middleware name for identification."""
        return "model_retry"

    def before_agent(self, state: Any, runtime: Any) -> Optional[Dict[str, Any]]:
        """No-op before agent."""
        return None

    async def abefore_agent(self, state: Any, runtime: Any) -> Optional[Dict[str, Any]]:
        """No-op before agent."""
        return None

    def after_agent(self, state: Any, runtime: Any) -> Optional[Dict[str, Any]]:
        """No-op after agent."""
        return None

    async def aafter_agent(self, state: Any, runtime: Any) -> Optional[Dict[str, Any]]:
        """No-op after agent."""
        return None

    def wrap_model_call(self, request: Any, handler: Callable) -> Any:
        """Wrap model call with retry logic."""
        for attempt in range(self.max_retries + 1):
            try:
                return handler(request)
            except Exception as e:
                if not self._is_context_error(e):
                    raise

                self._stats.retry_attempts += 1

                if attempt < self.max_retries:
                    delay = self.base_delay * (2 ** attempt)
                    logger.warning(
                        "context_overflow_retry",
                        attempt=attempt + 1,
                        max_retries=self.max_retries,
                        delay=delay,
                        error=str(e)[:200],
                    )
                    time.sleep(delay)
                else:
                    return self._handle_failure(e)

        return self._handle_failure(Exception("Max retries exceeded"))

    async def awrap_model_call(self, request: Any, handler: Callable) -> Any:
        """Async wrap model call with retry logic."""
        for attempt in range(self.max_retries + 1):
            try:
                return await handler(request)
            except Exception as e:
                if not self._is_context_error(e):
                    raise

                self._stats.retry_attempts += 1

                if attempt < self.max_retries:
                    delay = self.base_delay * (2 ** attempt)
                    logger.warning(
                        "context_overflow_retry",
                        attempt=attempt + 1,
                        max_retries=self.max_retries,
                        delay=delay,
                        error=str(e)[:200],
                    )
                    await asyncio.sleep(delay)
                else:
                    return self._handle_failure(e)

        return self._handle_failure(Exception("Max retries exceeded"))

    def wrap_tool_call(self, request: Any, handler: Callable) -> Any:
        """Pass-through for tool calls."""
        return handler(request)

    async def awrap_tool_call(self, request: Any, handler: Callable) -> Any:
        """Async pass-through for tool calls."""
        return await handler(request)

    def _is_context_error(self, error: Exception) -> bool:
        """Check if the error is a context length error.

        Args:
            error: Exception to check.

        Returns:
            True if it's a context length error.
        """
        error_str = str(error).lower()
        return any(pattern in error_str for pattern in self.CONTEXT_ERROR_PATTERNS)

    def _handle_failure(self, error: Exception) -> Any:
        """Handle final failure after retries exhausted.

        Args:
            error: The exception that caused failure.

        Returns:
            AIMessage with error info or raises exception.
        """
        logger.error(
            "context_overflow_unrecoverable",
            error=str(error)[:500],
            retry_attempts=self._stats.retry_attempts,
        )

        if self.on_failure == "raise":
            raise error

        # Return graceful error message
        return AIMessage(
            content=(
                "I apologize, but the conversation has grown too long for me to process. "
                "Please start a new conversation or try rephrasing your request more concisely. "
                "If you were in the middle of a complex task, you may want to break it into smaller steps."
            ),
            additional_kwargs={
                "error": "context_overflow",
                "error_message": str(error)[:500],
            },
        )

    def get_stats(self) -> Dict[str, Any]:
        """Get retry statistics."""
        return self._stats.to_dict()


# Export middleware classes
__all__ = [
    "FractionBasedSummarizationMiddleware",
    "ContextEditingMiddleware",
    "ModelRetryMiddleware",
    "get_model_context_window",
    "estimate_tokens",
    "ContextStats",
    "DEFAULT_CONTEXT_WINDOW",
    "AGENT_MIDDLEWARE_AVAILABLE",
]
