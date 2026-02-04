"""Memory middleware for mem0-based memory integration.

This middleware handles automatic memory retrieval before agent invocation
and memory recording after response, following DeepAgents middleware patterns.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from loguru import logger

# Import shared modules from canonical locations
from app.agents.harness._utils import IMPORT_FAILED, extract_message_text
from app.agents.harness._stats import MemoryStats

if TYPE_CHECKING:
    from langgraph.config import RunnableConfig

# Memory configuration
MEMORY_AGENT_ID = "sparrow"
MEMORY_SYSTEM_NAME = "server_memory_context"
DEFAULT_TOP_K = 5
DEFAULT_TIMEOUT = 8.0


class SparrowMemoryMiddleware:
    """Middleware for mem0-based memory integration.

    This middleware integrates with the memory service to:
    1. Retrieve relevant memories before agent invocation
    2. Record facts from the response after agent completion

    The middleware is designed to be non-blocking - if memory operations
    fail or timeout, the agent continues without them.

    Usage:
        middleware = SparrowMemoryMiddleware(enabled=True)
        # Middleware is then added to the agent's middleware stack

    Attributes:
        enabled: Whether memory operations are active.
        agent_id: Agent ID for memory service.
        top_k: Number of memories to retrieve.
        timeout: Timeout for memory operations.
    """

    name: str = "sparrow_memory"

    def __init__(
        self,
        enabled: bool = True,
        agent_id: str = MEMORY_AGENT_ID,
        top_k: int = DEFAULT_TOP_K,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        """Initialize the memory middleware.

        Args:
            enabled: Whether memory operations are active.
            agent_id: Agent ID for memory service operations.
            top_k: Number of memories to retrieve.
            timeout: Timeout for memory operations in seconds.
        """
        self.enabled = enabled
        self.agent_id = agent_id
        self.top_k = top_k
        self.timeout = timeout
        self._memory_service = None
        self._stats = MemoryStats()
        self._stats_lock = asyncio.Lock()

    @property
    def memory_service(self):
        """Lazy-load memory service to avoid circular imports.

        Uses a sentinel value to prevent repeated import attempts after failure.
        Returns None if import failed or service unavailable.
        """
        # Return None if we already tried and failed
        if self._memory_service is IMPORT_FAILED:
            return None

        # First access - try to import
        if self._memory_service is None:
            try:
                from app.memory import memory_service

                self._memory_service = memory_service
            except ImportError:
                logger.warning("Memory service not available - will not retry import")
                self._memory_service = IMPORT_FAILED
                return None

        return self._memory_service

    async def before_agent(
        self,
        messages: List[BaseMessage],
        config: "RunnableConfig",
        state: Optional[Dict[str, Any]] = None,
    ) -> List[BaseMessage]:
        """Retrieve relevant memories and prepend to messages.

        Called before the agent processes messages. Retrieves memories
        relevant to the user's query and injects them as a system message.

        Args:
            messages: Current message list.
            config: Runnable configuration.
            state: Optional state dict.

        Returns:
            Modified message list with memory context prepended.
        """
        if not self.enabled or not self.memory_service:
            return messages

        # Check if memory is configured
        state = state or {}
        use_memory = state.get("use_server_memory", False)
        if not use_memory:
            return messages

        # Extract user query
        query = self._extract_user_query(messages)
        if not query:
            return messages

        # Retrieve memories
        async with self._stats_lock:
            self._stats.retrieval_attempted = True

        try:
            memories = await asyncio.wait_for(
                self.memory_service.retrieve(
                    agent_id=self.agent_id,
                    query=query,
                    top_k=self.top_k,
                ),
                timeout=self.timeout,
            )

            if memories:
                async with self._stats_lock:
                    self._stats.retrieval_success = True
                    self._stats.facts_retrieved = len(memories)
                    self._stats.relevance_scores = [
                        m.get("score", 0.0)
                        for m in memories
                        if isinstance(m, dict) and "score" in m
                    ]

                memory_message = self._build_memory_message(memories)
                if memory_message:
                    return [memory_message, *messages]

        except asyncio.TimeoutError:
            logger.warning("memory_retrieval_timeout", timeout=self.timeout)
            async with self._stats_lock:
                self._stats.retrieval_error = "timeout"
        except Exception as exc:
            logger.warning("memory_retrieval_failed", error=str(exc))
            async with self._stats_lock:
                self._stats.retrieval_error = str(exc)

        return messages

    async def after_agent(
        self,
        response: BaseMessage,
        messages: List[BaseMessage],
        config: "RunnableConfig",
        state: Optional[Dict[str, Any]] = None,
    ) -> BaseMessage:
        """Extract facts from response and store in memory.

        Called after the agent generates a response. Extracts key facts
        and stores them for future retrieval.

        Args:
            response: Agent's response message.
            messages: Full message history.
            config: Runnable configuration.
            state: Optional state dict.

        Returns:
            Unchanged response message.
        """
        if not self.enabled or not self.memory_service:
            return response

        state = state or {}
        use_memory = state.get("use_server_memory", False)
        if not use_memory:
            return response

        # Extract facts from response
        facts = self._extract_facts(response)
        if not facts:
            return response

        async with self._stats_lock:
            self._stats.write_attempted = True

        # Build metadata
        meta: Dict[str, Any] = {"source": "unified_agent"}
        if state.get("user_id"):
            meta["user_id"] = state["user_id"]
        if state.get("session_id"):
            meta["session_id"] = state["session_id"]

        try:
            await asyncio.wait_for(
                self.memory_service.add_facts(
                    agent_id=self.agent_id,
                    facts=facts,
                    meta=meta,
                ),
                timeout=self.timeout,
            )
            async with self._stats_lock:
                self._stats.write_success = True
                self._stats.facts_written = len(facts)

        except asyncio.TimeoutError:
            logger.warning("memory_write_timeout", timeout=self.timeout)
            async with self._stats_lock:
                self._stats.write_error = "timeout"
        except Exception as exc:
            logger.warning("memory_write_failed", error=str(exc))
            async with self._stats_lock:
                self._stats.write_error = str(exc)

        return response

    async def get_stats(self) -> Dict[str, Any]:
        """Get memory operation statistics.

        Returns:
            Dict of memory stats for observability.
        """
        async with self._stats_lock:
            return self._stats.to_dict()

    async def reset_stats(self) -> None:
        """Reset statistics for a new run."""
        async with self._stats_lock:
            self._stats = MemoryStats()

    def _extract_user_query(self, messages: List[BaseMessage]) -> str:
        """Extract the last user query from messages."""
        for message in reversed(messages):
            if isinstance(message, HumanMessage):
                return extract_message_text(message)
        return ""

    def _build_memory_message(
        self, memories: List[Dict[str, Any]]
    ) -> Optional[SystemMessage]:
        """Build a system message from retrieved memories."""
        lines = []
        for item in memories:
            text = (item.get("memory") or "").strip()
            if not text:
                continue
            score = item.get("score")
            if isinstance(score, (int, float)):
                lines.append(f"- {text} (score={score:.2f})")
            else:
                lines.append(f"- {text}")

        if not lines:
            return None

        header = (
            "Server memory retrieved for this session/user. Use only if relevant:\n"
        )
        return SystemMessage(content=header + "\n".join(lines), name=MEMORY_SYSTEM_NAME)

    def _extract_facts(self, response: BaseMessage, max_facts: int = 3) -> List[str]:
        """Extract key facts from a response for memory storage."""
        import re
        import textwrap

        content = getattr(response, "content", "")
        if isinstance(content, list):
            parts = [
                str(chunk.get("text", ""))
                for chunk in content
                if isinstance(chunk, dict) and chunk.get("type") == "text"
            ]
            content = " ".join(parts)

        text = (content or "").strip()
        if not text:
            return []

        # Extract bullet points or sentences
        bullet_pattern = re.compile(r"^[-*\u2022]\s+")
        lines = [line.strip() for line in text.splitlines() if line.strip()]

        bullet_candidates = [
            bullet_pattern.sub("", line).strip()
            for line in lines
            if bullet_pattern.match(line)
        ]

        if bullet_candidates:
            candidates = bullet_candidates
        else:
            # Fall back to sentences
            sentence_pattern = re.compile(r"(?<=[.!?])\s+")
            candidates = [
                s.strip() for s in sentence_pattern.split(text) if len(s.strip()) >= 20
            ]

        # Deduplicate and limit
        seen = set()
        facts = []
        for candidate in candidates:
            clean = re.sub(r"\s+", " ", candidate).strip()
            if not clean:
                continue
            key = clean.lower()
            if key in seen:
                continue
            seen.add(key)
            facts.append(textwrap.shorten(clean, width=280, placeholder="..."))
            if len(facts) >= max_facts:
                break

        return facts
