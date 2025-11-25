"""Summarization middleware for conversation context management.

This middleware monitors message token counts and automatically summarizes older
messages when a threshold is reached, preserving recent context and maintaining
coherent conversation history.

Following DeepAgents middleware patterns and LangChain's SummarizationMiddleware
design, adapted for Agent Sparrow's Gemini-first architecture.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, TYPE_CHECKING

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    RemoveMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.messages.utils import count_tokens_approximately
from loguru import logger

if TYPE_CHECKING:
    from langgraph.config import RunnableConfig


# Default configuration
DEFAULT_MAX_TOKENS = 100_000  # Trigger summarization at 100k tokens
DEFAULT_MESSAGES_TO_KEEP = 20  # Preserve last 20 messages
DEFAULT_TIMEOUT = 30.0  # 30 second timeout for summarization

# Summary prompt designed for Gemini models
DEFAULT_SUMMARY_PROMPT = """You are a context extraction assistant. Your task is to extract the most important and relevant information from the following conversation history.

This summary will replace the full conversation history to free up context space. Focus on:
1. Key decisions and conclusions made
2. Important facts and data points discussed
3. Ongoing tasks and their current status
4. User preferences and requirements mentioned
5. Technical details relevant to the current work

Be concise but comprehensive. The summary should enable continuation of the conversation without losing critical context.

Conversation to summarize:
{messages}

Provide only the extracted context summary, no additional commentary."""

SUMMARY_PREFIX = "## Previous Conversation Summary\n\n"


@dataclass
class SummarizationStats:
    """Statistics from summarization operations for observability."""

    summarization_triggered: bool = False
    tokens_before: int = 0
    tokens_after: int = 0
    messages_summarized: int = 0
    messages_kept: int = 0
    summarization_success: bool = False
    summarization_error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for scratchpad storage."""
        return {
            "summarization_triggered": self.summarization_triggered,
            "tokens_before": self.tokens_before,
            "tokens_after": self.tokens_after,
            "messages_summarized": self.messages_summarized,
            "messages_kept": self.messages_kept,
            "summarization_success": self.summarization_success,
            "summarization_error": self.summarization_error,
        }


class SparrowSummarizationMiddleware:
    """Middleware for automatic conversation summarization.

    This middleware monitors conversation token counts and triggers automatic
    summarization when approaching context limits. It preserves recent messages
    while condensing older conversation history into a summary.

    Key features:
    - Token-based threshold triggering
    - Safe cutoff to preserve AI/Tool message pairs
    - Async-first with Gemini model integration
    - Statistics tracking for observability
    - Non-blocking: conversation continues if summarization fails

    Usage:
        middleware = SparrowSummarizationMiddleware(
            model=gemini_model,
            max_tokens_before_summary=100_000,
            messages_to_keep=20,
        )

        # In agent workflow
        messages = await middleware.before_agent(messages, config, state)

    Attributes:
        model: Language model for generating summaries.
        max_tokens_before_summary: Token threshold to trigger summarization.
        messages_to_keep: Number of recent messages to preserve.
        token_counter: Function to count tokens in messages.
        summary_prompt: Prompt template for generating summaries.
        timeout: Timeout for summarization operations.
    """

    name: str = "sparrow_summarization"

    def __init__(
        self,
        model: Optional[Any] = None,
        max_tokens_before_summary: int = DEFAULT_MAX_TOKENS,
        messages_to_keep: int = DEFAULT_MESSAGES_TO_KEEP,
        token_counter: Callable[[Iterable[BaseMessage]], int] = count_tokens_approximately,
        summary_prompt: str = DEFAULT_SUMMARY_PROMPT,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        """Initialize the summarization middleware.

        Args:
            model: Language model for generating summaries. If None, uses default Gemini.
            max_tokens_before_summary: Token threshold to trigger summarization.
            messages_to_keep: Number of recent messages to preserve after summarization.
            token_counter: Function to count tokens in messages.
            summary_prompt: Prompt template for generating summaries.
            timeout: Timeout for summarization operations in seconds.
        """
        self.model = model
        self.max_tokens_before_summary = max_tokens_before_summary
        self.messages_to_keep = messages_to_keep
        self.token_counter = token_counter
        self.summary_prompt = summary_prompt
        self.timeout = timeout
        self._stats = SummarizationStats()
        self._model_initialized = False

    def _ensure_model(self) -> Any:
        """Lazy-load the summarization model.

        Returns:
            Configured language model for summarization.
        """
        if self.model is not None:
            return self.model

        if self._model_initialized:
            return self.model

        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            from app.core.settings import settings

            self.model = ChatGoogleGenerativeAI(
                model=settings.primary_agent_model or "gemini-2.5-flash",
                google_api_key=settings.gemini_api_key,
                temperature=0.1,  # Low temperature for consistent summaries
            )
            self._model_initialized = True
            return self.model
        except Exception as exc:
            logger.warning("summarization_model_init_failed", error=str(exc))
            self._model_initialized = True
            return None

    async def before_agent(
        self,
        messages: List[BaseMessage],
        config: "RunnableConfig",
        state: Optional[Dict[str, Any]] = None,
    ) -> List[BaseMessage]:
        """Process messages before agent invocation, potentially triggering summarization.

        Called before the agent processes messages. Checks if summarization is needed
        based on token count and, if so, creates a summary of older messages.

        Args:
            messages: Current message list.
            config: Runnable configuration.
            state: Optional state dict.

        Returns:
            Modified message list, potentially with older messages summarized.
        """
        self._stats = SummarizationStats()  # Reset stats for this run

        if not messages:
            return messages

        # Ensure all messages have IDs
        self._ensure_message_ids(messages)

        # Count tokens
        total_tokens = self.token_counter(messages)
        self._stats.tokens_before = total_tokens

        # Check if summarization is needed
        if total_tokens < self.max_tokens_before_summary:
            return messages

        logger.info(
            "summarization_triggered",
            tokens=total_tokens,
            threshold=self.max_tokens_before_summary,
            message_count=len(messages),
        )
        self._stats.summarization_triggered = True

        # Find safe cutoff point
        cutoff_index = self._find_safe_cutoff(messages)
        if cutoff_index <= 0:
            logger.info("summarization_skipped", reason="no_safe_cutoff")
            return messages

        # Partition messages
        messages_to_summarize = messages[:cutoff_index]
        preserved_messages = messages[cutoff_index:]

        self._stats.messages_summarized = len(messages_to_summarize)
        self._stats.messages_kept = len(preserved_messages)

        # Generate summary
        try:
            summary = await asyncio.wait_for(
                self._create_summary(messages_to_summarize),
                timeout=self.timeout,
            )

            # Build new message list
            summary_message = HumanMessage(
                content=f"{SUMMARY_PREFIX}{summary}",
                id=str(uuid.uuid4()),
            )

            new_messages = [summary_message, *preserved_messages]
            self._stats.tokens_after = self.token_counter(new_messages)
            self._stats.summarization_success = True

            logger.info(
                "summarization_complete",
                tokens_before=self._stats.tokens_before,
                tokens_after=self._stats.tokens_after,
                messages_summarized=self._stats.messages_summarized,
            )

            return new_messages

        except asyncio.TimeoutError:
            logger.warning("summarization_timeout", timeout=self.timeout)
            self._stats.summarization_error = "timeout"
            return messages

        except Exception as exc:
            logger.warning("summarization_failed", error=str(exc))
            self._stats.summarization_error = str(exc)
            return messages

    async def after_agent(
        self,
        response: BaseMessage,
        messages: List[BaseMessage],
        config: "RunnableConfig",
        state: Optional[Dict[str, Any]] = None,
    ) -> BaseMessage:
        """Pass-through after agent invocation.

        Summarization is only done before agent invocation, so this method
        simply returns the response unchanged.

        Args:
            response: Agent's response message.
            messages: Full message history.
            config: Runnable configuration.
            state: Optional state dict.

        Returns:
            Unchanged response message.
        """
        return response

    def get_stats(self) -> Dict[str, Any]:
        """Get summarization operation statistics.

        Returns:
            Dict of summarization stats for observability.
        """
        return self._stats.to_dict()

    def reset_stats(self) -> None:
        """Reset statistics for a new run."""
        self._stats = SummarizationStats()

    def _ensure_message_ids(self, messages: List[BaseMessage]) -> None:
        """Ensure all messages have unique IDs for proper tracking."""
        for msg in messages:
            if msg.id is None:
                msg.id = str(uuid.uuid4())

    def _find_safe_cutoff(self, messages: List[BaseMessage]) -> int:
        """Find safe cutoff point that preserves AI/Tool message pairs.

        Returns the index where messages can be safely cut without separating
        related AI and Tool messages. Returns 0 if no safe cutoff is found.

        Args:
            messages: List of messages to find cutoff for.

        Returns:
            Index of safe cutoff point, or 0 if none found.
        """
        if len(messages) <= self.messages_to_keep:
            return 0

        target_cutoff = len(messages) - self.messages_to_keep

        # Search backward from target for safe cutoff
        for i in range(target_cutoff, -1, -1):
            if self._is_safe_cutoff_point(messages, i):
                return i

        return 0

    def _is_safe_cutoff_point(self, messages: List[BaseMessage], cutoff_index: int) -> bool:
        """Check if cutting at index would separate AI/Tool message pairs.

        Args:
            messages: Message list.
            cutoff_index: Proposed cutoff index.

        Returns:
            True if cutoff is safe, False if it would separate AI/Tool pairs.
        """
        if cutoff_index >= len(messages):
            return True

        # Check messages around the cutoff point
        search_range = 5
        search_start = max(0, cutoff_index - search_range)
        search_end = min(len(messages), cutoff_index + search_range)

        for i in range(search_start, search_end):
            msg = messages[i]
            if not isinstance(msg, AIMessage):
                continue

            # Check if this AI message has tool calls
            tool_calls = getattr(msg, "tool_calls", None)
            if not tool_calls:
                continue

            tool_call_ids = {
                tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)
                for tc in tool_calls
            }
            tool_call_ids.discard(None)

            # Check if cutoff separates AI from its tool responses
            for j in range(i + 1, len(messages)):
                if isinstance(messages[j], ToolMessage):
                    if messages[j].tool_call_id in tool_call_ids:
                        ai_before = i < cutoff_index
                        tool_before = j < cutoff_index
                        if ai_before != tool_before:
                            return False

        return True

    async def _create_summary(self, messages_to_summarize: List[BaseMessage]) -> str:
        """Generate summary for the given messages.

        Args:
            messages_to_summarize: Messages to summarize.

        Returns:
            Generated summary string.
        """
        if not messages_to_summarize:
            return "No previous conversation history."

        model = self._ensure_model()
        if model is None:
            return self._fallback_summary(messages_to_summarize)

        # Format messages for summary
        formatted_messages = self._format_messages_for_summary(messages_to_summarize)

        try:
            prompt = self.summary_prompt.format(messages=formatted_messages)
            response = await model.ainvoke(prompt)
            return str(response.content).strip()
        except Exception as exc:
            logger.warning("summary_generation_failed", error=str(exc))
            return self._fallback_summary(messages_to_summarize)

    def _format_messages_for_summary(self, messages: List[BaseMessage]) -> str:
        """Format messages into a string for summarization.

        Args:
            messages: Messages to format.

        Returns:
            Formatted string representation of messages.
        """
        lines = []
        for msg in messages:
            role = msg.type if hasattr(msg, "type") else "unknown"
            content = msg.content if isinstance(msg.content, str) else str(msg.content)

            # Truncate very long content
            if len(content) > 500:
                content = content[:500] + "..."

            lines.append(f"[{role}]: {content}")

        return "\n\n".join(lines)

    def _fallback_summary(self, messages: List[BaseMessage]) -> str:
        """Create a basic fallback summary when model is unavailable.

        Args:
            messages: Messages to summarize.

        Returns:
            Basic summary string.
        """
        human_count = sum(1 for m in messages if isinstance(m, HumanMessage))
        ai_count = sum(1 for m in messages if isinstance(m, AIMessage))
        tool_count = sum(1 for m in messages if isinstance(m, ToolMessage))

        parts = [
            f"Previous conversation: {len(messages)} messages",
            f"({human_count} user, {ai_count} assistant, {tool_count} tool responses)",
        ]

        # Extract key topics from user messages
        topics = []
        for msg in messages:
            if isinstance(msg, HumanMessage):
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                if len(content) > 100:
                    content = content[:100] + "..."
                topics.append(f"- {content}")
                if len(topics) >= 5:
                    break

        if topics:
            parts.append("\nKey user queries:")
            parts.extend(topics)

        return "\n".join(parts)
