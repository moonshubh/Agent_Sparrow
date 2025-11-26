"""Tool result eviction middleware for context overflow prevention.

This middleware evicts large tool results to backend storage to prevent
context window overflow, following DeepAgents patterns.

Implements the LangChain AgentMiddleware interface for compatibility
with DeepAgents SubAgentMiddleware.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING, Union

from langchain_core.messages import ToolMessage
from loguru import logger

# Import AgentMiddleware interface for DeepAgents compatibility
try:
    from langchain.agents.middleware import AgentMiddleware, AgentState
    from langchain.agents.middleware.types import ModelRequest, ModelResponse, ToolCallRequest
    from langgraph.types import Command
    AGENT_MIDDLEWARE_AVAILABLE = True
except ImportError:
    AGENT_MIDDLEWARE_AVAILABLE = False
    AgentMiddleware = object  # Fallback for type hints
    AgentState = Dict[str, Any]
    ToolCallRequest = Any
    Command = Any

if TYPE_CHECKING:
    from langgraph.config import RunnableConfig
    from langgraph.runtime import Runtime


# Eviction configuration
DEFAULT_EVICTION_THRESHOLD = 20000  # tokens (~80k chars at 4 chars/token)
DEFAULT_CHAR_THRESHOLD = 80000  # characters
SUMMARY_LENGTH = 500  # characters for the summary in pointer message
TIMESTAMP_PATTERN = re.compile(r"_\d{14}$")


@dataclass
class EvictionStats:
    """Statistics from eviction operations."""

    total_tool_results: int = 0
    results_evicted: int = 0
    total_chars_evicted: int = 0
    evicted_paths: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for observability."""
        return {
            "total_tool_results": self.total_tool_results,
            "results_evicted": self.results_evicted,
            "total_chars_evicted": self.total_chars_evicted,
            "evicted_paths": self.evicted_paths,
        }


class EvictionBackend:
    """Simple in-memory backend for storing evicted results.

    In production, this would be replaced with SupabaseStoreBackend
    or another persistent storage solution.
    """

    def __init__(self):
        self._storage: Dict[str, str] = {}

    def write(self, path: str, content: str) -> bool:
        """Write content to storage.

        Args:
            path: Storage path.
            content: Content to store.

        Returns:
            True if successful.
        """
        self._storage[path] = content
        return True

    def read(self, path: str) -> Optional[str]:
        """Read content from storage.

        Args:
            path: Storage path.

        Returns:
            Content or None if not found.
        """
        return self._storage.get(path)

    def delete(self, path: str) -> bool:
        """Delete content from storage.

        Args:
            path: Storage path.

        Returns:
            True if deleted, False if not found.
        """
        return self._storage.pop(path, None) is not None

    def list_paths(self, prefix: str = "") -> List[str]:
        """List all paths with optional prefix filter.

        Args:
            prefix: Optional path prefix filter.

        Returns:
            List of matching paths.
        """
        return [p for p in self._storage.keys() if p.startswith(prefix)]


class ToolResultEvictionMiddleware(AgentMiddleware if AGENT_MIDDLEWARE_AVAILABLE else object):
    """Middleware for evicting large tool results to prevent context overflow.

    When a tool result exceeds the configured threshold:
    1. The full result is written to backend storage
    2. A pointer message replaces the original result
    3. The agent can later retrieve the full result if needed

    This follows the DeepAgents pattern for handling large outputs
    from tools like web scraping, file reading, or search results.

    Implements the LangChain AgentMiddleware interface for compatibility
    with DeepAgents SubAgentMiddleware.

    Usage:
        middleware = ToolResultEvictionMiddleware()
        # Middleware is then added to the agent's middleware stack

    Attributes:
        char_threshold: Character threshold for eviction.
        backend: Storage backend for evicted results.
    """

    def __init__(
        self,
        char_threshold: int = DEFAULT_CHAR_THRESHOLD,
        backend: Optional[EvictionBackend] = None,
    ):
        """Initialize the eviction middleware.

        Args:
            char_threshold: Character count threshold for eviction.
            backend: Optional storage backend (defaults to in-memory).
        """
        self.char_threshold = char_threshold
        self.backend = backend or self._build_backend()
        self._stats = EvictionStats()
        self._stats_lock = asyncio.Lock()  # Lock for thread-safe stat updates

    def _build_backend(self) -> Any:
        """Build an eviction backend, preferring Supabase when enabled."""
        if os.getenv("SPARROW_EVICTION_USE_SUPABASE", "").lower() in {"1", "true", "yes"}:
            try:
                from app.agents.harness.backends import SupabaseStoreBackend
                from app.db.supabase.client import get_supabase_client

                client = get_supabase_client()
                logger.info("eviction_backend_supabase_enabled")
                return SupabaseStoreBackend(client)
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("eviction_backend_supabase_failed", error=str(exc))
        return EvictionBackend()

    @property
    def name(self) -> str:
        """Middleware name for identification."""
        return "tool_result_eviction"

    # -------------------------------------------------------------------------
    # AgentMiddleware Interface Implementation
    # -------------------------------------------------------------------------

    def before_agent(self, state: Any, runtime: Any) -> Optional[Dict[str, Any]]:
        """Called before agent execution. No-op for eviction middleware."""
        return None

    async def abefore_agent(self, state: Any, runtime: Any) -> Optional[Dict[str, Any]]:
        """Async version of before_agent. No-op for eviction middleware."""
        return None

    def after_agent(self, state: Any, runtime: Any) -> Optional[Dict[str, Any]]:
        """Called after agent execution. No-op for eviction middleware."""
        return None

    async def aafter_agent(self, state: Any, runtime: Any) -> Optional[Dict[str, Any]]:
        """Async version of after_agent. No-op for eviction middleware."""
        return None

    def wrap_model_call(
        self,
        request: Any,
        handler: Callable[[Any], Any],
    ) -> Any:
        """Wrap model call. Pass-through for eviction middleware."""
        return handler(request)

    async def awrap_model_call(
        self,
        request: Any,
        handler: Callable[[Any], Any],
    ) -> Any:
        """Async wrap model call. Pass-through for eviction middleware."""
        return await handler(request)

    def wrap_tool_call(
        self,
        request: Any,
        handler: Callable[[Any], Union[ToolMessage, Any]],
    ) -> Union[ToolMessage, Any]:
        """Wrap tool call with eviction logic (sync version).

        Args:
            request: Tool call request from AgentMiddleware.
            handler: Original tool call handler.

        Returns:
            Tool result, potentially replaced with pointer message.
        """
        result = handler(request)
        return self._process_result_sync(result, request)

    async def awrap_tool_call(
        self,
        request: Any,
        handler: Callable[[Any], Any],
    ) -> Union[ToolMessage, Any]:
        """Async wrap tool call with eviction logic.

        This is the primary interface used by DeepAgents SubAgentMiddleware.

        Args:
            request: Tool call request from AgentMiddleware.
            handler: Original async tool call handler.

        Returns:
            Tool result, potentially replaced with pointer message.
        """
        result = await handler(request)
        return await self._process_result_async(result, request)

    def _process_result_sync(
        self,
        result: Any,
        request: Any,
    ) -> Union[ToolMessage, Any]:
        """Process tool result synchronously, evicting if needed.

        Args:
            result: Tool result.
            request: Original request for metadata.

        Returns:
            Original result or pointer message.
        """
        self._stats.total_tool_results += 1

        content = self._extract_content(result)
        if not self.should_evict(content):
            return result

        # Extract tool metadata from request
        tool_call_id = getattr(request, "tool_call_id", None) or "unknown"
        tool_name = getattr(request, "name", None) or getattr(request, "tool_name", None) or "unknown"

        return self._evict_and_pointer(result, tool_call_id, tool_name, content)

    async def _process_result_async(
        self,
        result: Any,
        request: Any,
    ) -> Union[ToolMessage, Any]:
        """Process tool result asynchronously, evicting if needed.

        Args:
            result: Tool result.
            request: Original request for metadata.

        Returns:
            Original result or pointer message.
        """
        async with self._stats_lock:
            self._stats.total_tool_results += 1

        content = self._extract_content(result)
        if not self.should_evict(content):
            return result

        # Extract tool metadata from request
        tool_call_id = getattr(request, "tool_call_id", None) or "unknown"
        tool_name = getattr(request, "name", None) or getattr(request, "tool_name", None) or "unknown"

        return await self._evict_and_pointer_async(result, tool_call_id, tool_name, content)

    # -------------------------------------------------------------------------
    # Legacy Interface (for direct usage without AgentMiddleware)
    # -------------------------------------------------------------------------

    def should_evict(self, content: str) -> bool:
        """Check if content should be evicted.

        Args:
            content: Tool result content.

        Returns:
            True if content exceeds threshold.
        """
        return len(content) > self.char_threshold

    def wrap_tool_handler(
        self,
        handler: Callable,
    ) -> Callable:
        """Wrap a tool call handler with eviction logic (decorator pattern).

        Legacy method for direct handler wrapping without AgentMiddleware.
        For AgentMiddleware usage, use wrap_tool_call/awrap_tool_call instead.

        Args:
            handler: Original tool call handler.

        Returns:
            Wrapped handler with eviction.
        """

        @wraps(handler)
        async def wrapped(
            tool_call_id: str,
            tool_name: str,
            *args,
            **kwargs,
        ) -> ToolMessage:
            # Execute original handler
            result = await handler(tool_call_id, tool_name, *args, **kwargs)

            # Thread-safe stat update
            async with self._stats_lock:
                self._stats.total_tool_results += 1

            # Check if eviction needed
            content = self._extract_content(result)
            if not self.should_evict(content):
                return result

            # Evict and create pointer (also needs thread-safe stat updates)
            return await self._evict_and_pointer_async(result, tool_call_id, tool_name, content)

        return wrapped

    def process_tool_result(
        self,
        result: ToolMessage,
        tool_call_id: str,
        tool_name: str,
    ) -> ToolMessage:
        """Process a tool result, evicting if necessary.

        Can be called directly instead of using wrap_tool_call.

        Args:
            result: Original tool result.
            tool_call_id: Tool call identifier.
            tool_name: Name of the tool.

        Returns:
            Original or pointer message.
        """
        self._stats.total_tool_results += 1

        content = self._extract_content(result)
        if not self.should_evict(content):
            return result

        return self._evict_and_pointer(result, tool_call_id, tool_name, content)

    def _evict_and_pointer(
        self,
        result: ToolMessage,
        tool_call_id: str,
        tool_name: str,
        content: str,
    ) -> ToolMessage:
        """Evict content and create pointer message (sync version).

        Note: This method is not thread-safe. For concurrent use, use
        _evict_and_pointer_async instead.

        Args:
            result: Original tool result.
            tool_call_id: Tool call identifier.
            tool_name: Name of the tool.
            content: Content to evict.

        Returns:
            Pointer message.
        """
        # Generate storage path
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        path = f"/large_results/{tool_call_id}_{timestamp}"

        # Write to backend
        write_result = self.backend.write(path, content)
        success = getattr(write_result, "success", write_result)
        if not success:
            logger.warning("eviction_write_failed", path=path, tool=tool_name)
            return result

        # Update stats (not thread-safe in sync version)
        self._stats.results_evicted += 1
        self._stats.total_chars_evicted += len(content)
        self._stats.evicted_paths.append(path)

        return self._create_pointer_message(
            tool_call_id, tool_name, content, path
        )

    async def _evict_and_pointer_async(
        self,
        result: ToolMessage,
        tool_call_id: str,
        tool_name: str,
        content: str,
    ) -> ToolMessage:
        """Evict content and create pointer message (async, thread-safe version).

        Args:
            result: Original tool result.
            tool_call_id: Tool call identifier.
            tool_name: Name of the tool.
            content: Content to evict.

        Returns:
            Pointer message.
        """
        # Generate storage path
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        path = f"/large_results/{tool_call_id}_{timestamp}"

        # Write to backend
        write_result = self.backend.write(path, content)
        success = getattr(write_result, "success", write_result)
        if not success:
            logger.warning("eviction_write_failed", path=path, tool=tool_name)
            return result

        # Thread-safe stat updates
        async with self._stats_lock:
            self._stats.results_evicted += 1
            self._stats.total_chars_evicted += len(content)
            self._stats.evicted_paths.append(path)

        return self._create_pointer_message(
            tool_call_id, tool_name, content, path
        )

    def _create_pointer_message(
        self,
        tool_call_id: str,
        tool_name: str,
        content: str,
        path: str,
    ) -> ToolMessage:
        """Create a pointer message for evicted content.

        Args:
            tool_call_id: Tool call identifier.
            tool_name: Name of the tool.
            content: Original content (for logging and summary).
            path: Storage path.

        Returns:
            Pointer ToolMessage.
        """
        logger.info(
            "tool_result_evicted",
            tool=tool_name,
            tool_call_id=tool_call_id,
            original_chars=len(content),
            path=path,
        )

        # Create summary
        summary = self._create_summary(content, tool_name)

        # Create pointer message
        pointer_content = (
            f"Result from {tool_name} was too large ({len(content):,} characters) "
            f"and has been saved to storage.\n\n"
            f"**Storage path:** `{path}`\n\n"
            f"**Summary:**\n{summary}\n\n"
            f"To access the full result, use the `read_evicted_result` tool with path: {path}"
        )

        return ToolMessage(
            content=pointer_content,
            tool_call_id=tool_call_id,
            additional_kwargs={
                "evicted": True,
                "evicted_path": path,
                "original_length": len(content),
                "tool_name": tool_name,
            },
        )

    def _extract_content(self, result: Any) -> str:
        """Extract string content from tool result.

        Args:
            result: Tool result (ToolMessage, dict, or str).

        Returns:
            String content.
        """
        if isinstance(result, ToolMessage):
            content = result.content
        elif isinstance(result, dict):
            content = result.get("content", "")
        else:
            content = str(result)

        if isinstance(content, (dict, list)):
            try:
                return json.dumps(content, indent=2)
            except (TypeError, ValueError):
                return str(content)

        return str(content)

    def _create_summary(self, content: str, tool_name: str) -> str:
        """Create a summary of evicted content.

        Args:
            content: Full content.
            tool_name: Name of the tool.

        Returns:
            Summary string.
        """
        # Try to parse as JSON and extract key info
        try:
            data = json.loads(content)
            if isinstance(data, dict):
                # Look for common summary fields
                for key in ("summary", "title", "description", "message"):
                    if key in data:
                        return str(data[key])[:SUMMARY_LENGTH]

                # Count items if it's a collection
                for key in ("results", "items", "data", "entries"):
                    if key in data and isinstance(data[key], list):
                        return f"Contains {len(data[key])} {key}"

                # Return keys overview
                keys = list(data.keys())[:10]
                return f"JSON object with keys: {', '.join(keys)}"

            elif isinstance(data, list):
                return f"JSON array with {len(data)} items"

        except (json.JSONDecodeError, TypeError):
            pass

        # Fall back to text truncation
        lines = content.strip().split("\n")
        if len(lines) > 3:
            preview = "\n".join(lines[:3]) + f"\n... ({len(lines) - 3} more lines)"
        else:
            preview = content[:SUMMARY_LENGTH]

        if len(preview) > SUMMARY_LENGTH:
            preview = preview[: SUMMARY_LENGTH - 3] + "..."

        return preview

    def read_evicted_result(self, path: str) -> Optional[str]:
        """Read an evicted result from storage.

        Args:
            path: Storage path.

        Returns:
            Original content or None if not found.
        """
        return self.backend.read(path)

    def cleanup_evicted_results(
        self,
        prefix: str = "/large_results/",
        max_age_seconds: Optional[int] = None,
    ) -> int:
        """Clean up evicted results from storage.

        Args:
            prefix: Path prefix to clean up.
            max_age_seconds: Optional age threshold; if provided, only results older than this are removed.

        Returns:
            Number of items deleted.
        """
        paths = self.backend.list_paths(prefix)
        deleted = 0
        for path in paths:
            if max_age_seconds is not None:
                # Expect path format: /large_results/{tool_call_id}_%Y%m%d%H%M%S
                suffix = path.rsplit("/", 1)[-1]
                if not TIMESTAMP_PATTERN.search(suffix):
                    continue
                try:
                    timestamp_part = suffix.split("_")[-1]
                    ts = datetime.strptime(timestamp_part, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
                    age = (datetime.now(timezone.utc) - ts).total_seconds()
                    if age < max_age_seconds:
                        continue
                except (ValueError, IndexError):
                    # Skip malformed timestamps instead of deleting
                    continue
            if self.backend.delete(path):
                deleted += 1
        return deleted

    def get_stats(self) -> Dict[str, Any]:
        """Get eviction statistics.

        Returns:
            Dict of stats for observability.
        """
        return self._stats.to_dict()

    def reset_stats(self) -> None:
        """Reset statistics for a new run."""
        self._stats = EvictionStats()
