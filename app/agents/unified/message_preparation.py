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
from .multimodal_processor import MultimodalProcessor, get_multimodal_processor, ProcessedAttachments

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
        multimodal_processor: Optional[MultimodalProcessor] = None,
    ):
        """Initialize the preparer.

        Args:
            helper: GemmaHelper for summarization and rewriting.
            session_cache: Session cache for caching rewrites.
            attachment_processor: Attachment processor instance.
            multimodal_processor: Multimodal processor for images/PDFs.
        """
        self.helper = helper
        self.session_cache = session_cache or {}
        self.attachment_processor = attachment_processor or get_attachment_processor()
        self.multimodal_processor = multimodal_processor or get_multimodal_processor()

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

        # 4. Process attachments (multimodal for images/PDFs, text inline)
        if state.attachments:
            processed = self.multimodal_processor.process_attachments(state.attachments)

            if processed.has_multimodal:
                # Build multimodal HumanMessage with images/PDFs
                human_message_replaced = False
                for i in range(len(messages) - 1, -1, -1):
                    if isinstance(messages[i], HumanMessage):
                        user_text = self._coerce_message_text(messages[i])
                        messages[i] = self._build_multimodal_human_message(
                            user_text, processed
                        )
                        stats["multimodal_attachments"] = len(processed.multimodal_blocks)
                        human_message_replaced = True
                        break

                if not human_message_replaced:
                    fallback_text = (
                        self._coerce_message_text(messages[-1])
                        if messages
                        else "User provided attachments."
                    )
                    messages.append(
                        self._build_multimodal_human_message(
                            fallback_text, processed
                        )
                    )
                    stats["multimodal_attachments"] = len(processed.multimodal_blocks)

                stats["attachments_inlined"] = (
                    len(processed.multimodal_blocks)
                    + (1 if processed.text_content else 0)
                )
            elif processed.text_content:
                # Text-only: use existing SystemMessage approach
                messages.append(
                    SystemMessage(content=f"Attached files:\n{processed.text_content}")
                )
                stats["attachments_inlined"] = 1

            if processed.skipped:
                stats["attachments_skipped"] = len(processed.skipped)

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

    def _build_multimodal_human_message(
        self,
        user_text: str,
        processed: ProcessedAttachments,
    ) -> HumanMessage:
        """Build a multimodal HumanMessage with text and image/PDF content blocks.

        Args:
            user_text: The original user message text.
            processed: ProcessedAttachments with multimodal_blocks and text_content.

        Returns:
            HumanMessage with list-based content for Gemini vision API.
        """
        content: List[Dict[str, Any]] = []

        # Combine user text with any text attachments
        text_parts = [user_text]
        if processed.text_content:
            text_parts.append(f"\n\n--- Attached Files ---\n{processed.text_content}")

        combined_text = "".join(text_parts)
        content.append({"type": "text", "text": combined_text})

        # Add multimodal blocks (images, PDFs)
        content.extend(processed.multimodal_blocks)

        logger.info(
            "multimodal_message_built",
            text_length=len(combined_text),
            multimodal_blocks=len(processed.multimodal_blocks),
        )

        return HumanMessage(content=content)

    def _estimate_tokens(self, messages: List[BaseMessage]) -> int:
        """Rough token estimation (~4 chars per token, ~1000 tokens per image)."""
        total_tokens = 0

        for msg in messages:
            content = getattr(msg, "content", "")

            if isinstance(content, str):
                total_tokens += len(content) // 4
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict):
                        if part.get("type") == "text":
                            total_tokens += len(str(part.get("text", ""))) // 4
                        elif part.get("type") == "image_url":
                            # Conservative estimate: ~1000 tokens per image/PDF
                            total_tokens += 1000
                    else:
                        total_tokens += len(str(part)) // 4
            else:
                total_tokens += len(str(content)) // 4 if content else 0

        return total_tokens


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
