"""Message preparation module for Agent Sparrow.

Extracted from agent_sparrow.py to provide a clean, testable interface
for all pre-agent message transformations.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from loguru import logger

from .attachment_processor import AttachmentProcessor, get_attachment_processor

if TYPE_CHECKING:
    from app.agents.helpers.gemma_helper import GemmaHelper
    from app.agents.orchestration.orchestration.state import GraphState


# Constants
HELPER_TIMEOUT_SECONDS = 8.0
LONG_HISTORY_THRESHOLD = 8  # Number of messages before summarization
TOKEN_LIMIT_BEFORE_COMPACT = 9000  # Estimated tokens before compaction


class MessagePreparer:
    """Handles all pre-agent message transformations.

    This class is responsible for preparing messages before they're sent
    to the agent, including:
    - Memory context injection
    - Query rewriting for retrieval optimization
    - History summarization for long conversations
    - Attachment processing and inlining
    - Context compaction when approaching token limits

    Usage:
        preparer = MessagePreparer(
            helper=GemmaHelper(),
            session_cache=session_cache,
        )

        prepared_messages, stats = await preparer.prepare_messages(
            state=graph_state,
            memory_context="Relevant memories...",
        )
    """

    def __init__(
        self,
        helper: Optional["GemmaHelper"] = None,
        session_cache: Optional[Dict[str, Dict[str, Any]]] = None,
        attachment_processor: Optional[AttachmentProcessor] = None,
    ):
        """Initialize the preparer.

        Args:
            helper: GemmaHelper for summarization and rewriting.
            session_cache: Session cache for caching rewrites.
            attachment_processor: Attachment processor instance.
        """
        self.helper = helper
        self.session_cache = session_cache or {}
        self.attachment_processor = attachment_processor or get_attachment_processor()

    async def prepare_messages(
        self,
        state: "GraphState",
        memory_context: Optional[str] = None,
    ) -> Tuple[List[BaseMessage], Dict[str, Any]]:
        """Prepare messages for agent invocation.

        Args:
            state: Current graph state.
            memory_context: Optional memory context to prepend.

        Returns:
            Tuple of (prepared_messages, stats_dict).
        """
        stats: Dict[str, Any] = {
            "original_message_count": len(state.messages),
            "memory_prepended": False,
            "query_rewritten": False,
            "history_summarized": False,
            "attachments_inlined": 0,
            "context_compacted": False,
        }

        messages = list(state.messages)

        # 1. Prepend memory context if provided
        if memory_context:
            memory_msg = SystemMessage(
                content=memory_context,
                name="server_memory_context",
            )
            messages = [memory_msg, *messages]
            stats["memory_prepended"] = True

        # 2. Extract and rewrite user query
        last_user_query = self._extract_last_user_query(messages)
        if last_user_query and self.helper:
            rewritten = await self._rewrite_query(last_user_query, state.scratchpad)
            if rewritten and rewritten != last_user_query:
                messages.append(
                    SystemMessage(content=f"Rewritten query for retrieval: {rewritten}")
                )
                stats["query_rewritten"] = True
                stats["rewritten_query"] = rewritten

        # 3. Summarize long history
        if len(messages) > LONG_HISTORY_THRESHOLD and self.helper:
            messages = await self._summarize_history(messages)
            stats["history_summarized"] = True

        # 4. Inline attachments
        if state.attachments:
            summarizer = self.helper.summarize if self.helper else None
            inline_text = await self.attachment_processor.inline_attachments(
                state.attachments,
                summarizer=summarizer,
            )
            if inline_text:
                messages.append(
                    SystemMessage(content=f"Attached logs/content:\n{inline_text}")
                )
                stats["attachments_inlined"] = len(state.attachments)

        # 5. Compact context if too large
        estimated_tokens = self._estimate_tokens(messages)
        if estimated_tokens > TOKEN_LIMIT_BEFORE_COMPACT and self.helper:
            messages = await self._compact_context(messages)
            stats["context_compacted"] = True

        stats["final_message_count"] = len(messages)
        stats["estimated_tokens"] = self._estimate_tokens(messages)

        return messages, stats

    async def _rewrite_query(
        self,
        query: str,
        scratchpad: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Rewrite user query for improved retrieval.

        Args:
            query: Original user query.
            scratchpad: State scratchpad for storing rewritten query.

        Returns:
            Rewritten query, or None if rewriting failed.
        """
        # Check cache first
        rewrite_key = f"rewrite:{query.lower().strip()}"
        cached = self.session_cache.get(rewrite_key, {}).get("value")
        if cached:
            return cached

        # Rewrite with timeout
        rewritten = await self._with_timeout(
            self.helper.rewrite_query(query),
            "gemma_rewrite_query",
        )

        if rewritten:
            # Cache the result
            self.session_cache[rewrite_key] = {"value": rewritten, "ts": time.time()}

            # Store in scratchpad
            if scratchpad is not None:
                system_bucket = scratchpad.setdefault("_system", {})
                system_bucket["rewritten_query"] = rewritten

        return rewritten

    async def _summarize_history(
        self,
        messages: List[BaseMessage],
    ) -> List[BaseMessage]:
        """Summarize older history messages.

        Keeps the most recent messages and summarizes the rest.

        Args:
            messages: Full message list.

        Returns:
            Message list with older messages summarized.
        """
        # Keep last 4 messages, summarize the rest
        keep_count = 4
        to_summarize = messages[:-keep_count]
        to_keep = messages[-keep_count:]

        history_text = "\n\n".join(
            self._coerce_message_text(msg) for msg in to_summarize
        )

        if not history_text:
            return messages

        summary = await self._with_timeout(
            self.helper.summarize(history_text, budget_tokens=800),
            "gemma_history_summarize",
        )

        if summary:
            return [
                SystemMessage(content=f"Conversation so far (summarized):\n{summary}"),
                *to_keep,
            ]

        return messages

    async def _compact_context(
        self,
        messages: List[BaseMessage],
    ) -> List[BaseMessage]:
        """Compact context when approaching token limits.

        Args:
            messages: Message list to compact.

        Returns:
            Compacted message list.
        """
        # Keep last 3 messages, summarize everything else
        keep_count = 3
        combined = "\n\n".join(
            f"{getattr(m, 'type', 'message')}: {self._coerce_message_text(m)}"
            for m in messages
        )

        summary = await self._with_timeout(
            self.helper.summarize(combined, budget_tokens=1200),
            "gemma_context_compact",
        )

        if summary:
            return [
                SystemMessage(content=f"Conversation summary (compacted):\n{summary}"),
                *messages[-keep_count:],
            ]

        return messages

    async def _with_timeout(
        self,
        coro: Any,
        label: str,
        timeout: float = HELPER_TIMEOUT_SECONDS,
    ) -> Optional[Any]:
        """Apply a timeout to helper calls."""
        try:
            return await asyncio.wait_for(coro, timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning(f"{label}_timeout", timeout=timeout)
        except Exception as exc:
            logger.warning(f"{label}_failed", error=str(exc))
        return None

    def _extract_last_user_query(self, messages: List[BaseMessage]) -> str:
        """Extract the last human message text."""
        for message in reversed(messages or []):
            if isinstance(message, HumanMessage):
                text = self._coerce_message_text(message).strip()
                if text:
                    return text
        return ""

    def _coerce_message_text(self, message: BaseMessage) -> str:
        """Convert message content to plain text."""
        content = getattr(message, "content", "")

        if isinstance(content, str):
            return content

        if isinstance(content, list):
            parts = []
            for chunk in content:
                if isinstance(chunk, dict) and chunk.get("type") == "text":
                    parts.append(str(chunk.get("text") or ""))
                else:
                    parts.append(str(chunk))
            return "".join(parts)

        return str(content) if content is not None else ""

    def _estimate_tokens(self, messages: List[BaseMessage]) -> int:
        """Rough token estimation (~4 chars per token)."""
        total_chars = sum(len(self._coerce_message_text(m)) for m in messages)
        return int(total_chars / 4)


# Module-level instance for convenience
_default_preparer: Optional[MessagePreparer] = None


def get_message_preparer(
    helper: Optional["GemmaHelper"] = None,
    session_cache: Optional[Dict[str, Dict[str, Any]]] = None,
) -> MessagePreparer:
    """Get a message preparer instance."""
    if helper is None and session_cache is None:
        global _default_preparer
        if _default_preparer is None:
            _default_preparer = MessagePreparer()
        return _default_preparer

    return MessagePreparer(helper=helper, session_cache=session_cache)
