"""Workspace file tools for Deep Agent context engineering.

This module provides file-system-like tools for agents to organize their context:
- read_workspace_file: Read files with safe defaults
- write_workspace_file: Write files with size limits
- list_workspace_files: List files with depth limit
- search_workspace: Content search using GIN index
- append_workspace_file: Thread-safe append for history files
- grep_workspace_files: Pattern matching in file contents

Usage:
    from app.agents.unified.workspace_tools import (
        read_workspace_file,
        write_workspace_file,
        list_workspace_files,
        search_workspace,
        append_workspace_file,
        get_workspace_tools,
    )

    # Get all tools for tool registry
    tools = get_workspace_tools(workspace_store)
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Annotated, Dict, List, Optional, TYPE_CHECKING

from langchain_core.tools import tool, InjectedToolArg
from pydantic import BaseModel, Field

from app.core.logging_config import get_logger

if TYPE_CHECKING:
    from app.agents.harness.store.workspace_store import (
        PersistenceScope,
        SparrowWorkspaceStore,
    )

logger = get_logger(__name__)


# =============================================================================
# Safe Default Constants
# =============================================================================

DEFAULT_READ_LIMIT_CHARS = 2048     # ~500 tokens, safe default
MAX_READ_LIMIT_CHARS = 50000        # ~12k tokens, requires explicit opt-in
DEFAULT_WRITE_MAX_BYTES = 100_000   # 100KB max per file
MAX_WRITE_BYTES = 500_000           # 500KB absolute maximum
DEFAULT_LIST_DEPTH = 2              # Default directory listing depth
MAX_LIST_DEPTH = 5                  # Maximum directory listing depth
DEFAULT_SEARCH_LIMIT = 10           # Default search results
MAX_SEARCH_LIMIT = 50               # Maximum search results
ATTACHMENT_TTL_HOURS = 24           # TTL for cached attachments
ATTACHMENT_MAX_SIZE_BYTES = 50_000  # 50KB per attachment summary


# =============================================================================
# Rate Limiting
# =============================================================================

# Rate limits per scope/identifier (per 60 second window)
RATE_LIMITS = {
    "global": {"reads": 10, "writes": 0, "window_seconds": 60},    # Read-only
    "customer": {"reads": 20, "writes": 5, "window_seconds": 60},
    "session": {"reads": 100, "writes": 50, "window_seconds": 60},
}


class WorkspaceRateLimiter:
    """Per-scope rate limiter for workspace operations.

    Prevents runaway tool calls that could exhaust context or cause
    excessive database load.
    """

    def __init__(self) -> None:
        # Structure: {"{scope}:{id}": {"reads": [timestamps], "writes": [timestamps]}}
        self._counters: Dict[str, Dict[str, List[datetime]]] = defaultdict(
            lambda: {"reads": [], "writes": []}
        )

    def check_and_record(
        self,
        scope: str,
        operation: str,
        identifier: Optional[str] = None,
    ) -> bool:
        """Check rate limit and record operation.

        Args:
            scope: Persistence scope ("global", "customer", "session")
            operation: Operation type ("reads" or "writes")
            identifier: Unique identifier per scope (e.g., session_id, customer_id)

        Returns:
            True if operation is allowed, False if rate limited.
        """
        limits = RATE_LIMITS.get(scope, RATE_LIMITS["session"])
        window = timedelta(seconds=limits["window_seconds"])
        cutoff = datetime.now(timezone.utc) - window
        key = f"{scope}:{identifier or 'unknown'}"

        # Clean old entries
        self._counters[key][operation] = [
            t for t in self._counters[key][operation] if t > cutoff
        ]

        # Check limit
        if len(self._counters[key][operation]) >= limits[operation]:
            logger.warning(
                "workspace_rate_limited",
                scope=scope,
                identifier=identifier,
                operation=operation,
                limit=limits[operation],
                window_seconds=limits["window_seconds"],
            )
            return False

        # Record this operation
        self._counters[key][operation].append(datetime.now(timezone.utc))
        return True

    def reset(self) -> None:
        """Reset all rate limit counters."""
        self._counters.clear()


# Global rate limiter instance
_rate_limiter = WorkspaceRateLimiter()


def get_rate_limiter() -> WorkspaceRateLimiter:
    """Get the global rate limiter instance."""
    return _rate_limiter


def _get_rate_limit_identifier(
    scope: "PersistenceScope",
    path: str,
    store: "SparrowWorkspaceStore",
) -> str:
    """Build a rate-limit key using scope and session/customer identifier."""
    scope_value = getattr(scope, "value", str(scope))
    if scope_value == "session":
        return getattr(store, "session_id", "") or "unknown-session"
    if scope_value == "customer":
        parts = path.strip("/").split("/")
        if len(parts) >= 2 and parts[1]:
            return parts[1]
        return getattr(store, "customer_id", "") or "unknown-customer"
    return "global"


# =============================================================================
# Tool Schemas
# =============================================================================

class ReadWorkspaceFileInput(BaseModel):
    """Input schema for read_workspace_file."""
    path: str = Field(
        description="Virtual path to read (e.g., '/scratch/notes.md', '/customer/{id}/history/ticket_123.md')"
    )
    offset: int = Field(
        default=0,
        ge=0,
        description="Character offset to start reading from"
    )
    limit: int = Field(
        default=DEFAULT_READ_LIMIT_CHARS,
        ge=1,
        le=MAX_READ_LIMIT_CHARS,
        description=f"Maximum characters to read (default: {DEFAULT_READ_LIMIT_CHARS}, max: {MAX_READ_LIMIT_CHARS})"
    )


class WriteWorkspaceFileInput(BaseModel):
    """Input schema for write_workspace_file."""
    path: str = Field(
        description="Virtual path to write (e.g., '/scratch/notes.md')"
    )
    content: str = Field(
        description="Content to write"
    )
    max_size_bytes: int = Field(
        default=DEFAULT_WRITE_MAX_BYTES,
        ge=1,
        le=MAX_WRITE_BYTES,
        description=f"Maximum file size in bytes (default: {DEFAULT_WRITE_MAX_BYTES})"
    )


class ListWorkspaceFilesInput(BaseModel):
    """Input schema for list_workspace_files."""
    path: str = Field(
        default="/",
        description="Virtual directory path to list (e.g., '/scratch', '/customer/{id}')"
    )
    depth: int = Field(
        default=DEFAULT_LIST_DEPTH,
        ge=1,
        le=MAX_LIST_DEPTH,
        description=f"Maximum depth to traverse (default: {DEFAULT_LIST_DEPTH}, max: {MAX_LIST_DEPTH})"
    )


class SearchWorkspaceInput(BaseModel):
    """Input schema for search_workspace."""
    query: str = Field(
        description="Search query to find in file contents"
    )
    path: str = Field(
        default="/",
        description="Virtual path prefix to search within"
    )
    limit: int = Field(
        default=DEFAULT_SEARCH_LIMIT,
        ge=1,
        le=MAX_SEARCH_LIMIT,
        description=f"Maximum results to return (default: {DEFAULT_SEARCH_LIMIT}, max: {MAX_SEARCH_LIMIT})"
    )


class AppendWorkspaceFileInput(BaseModel):
    """Input schema for append_workspace_file."""
    path: str = Field(
        description="Virtual path to append to (e.g., '/customer/{id}/history/ticket_123.md')"
    )
    content: str = Field(
        description="Content to append (will be timestamped)"
    )
    max_size_bytes: int = Field(
        default=DEFAULT_WRITE_MAX_BYTES,
        ge=1,
        le=MAX_WRITE_BYTES,
        description=f"Maximum file size in bytes (default: {DEFAULT_WRITE_MAX_BYTES})"
    )


class GrepWorkspaceFilesInput(BaseModel):
    """Input schema for grep_workspace_files."""
    pattern: str = Field(
        description="Regex pattern to search for"
    )
    path: str = Field(
        default="/",
        description="Virtual path prefix to search within"
    )
    limit: int = Field(
        default=20,
        ge=1,
        le=50,
        description="Maximum matching files to return"
    )


# =============================================================================
# Tool Implementations
# =============================================================================

def create_read_workspace_file(store: "SparrowWorkspaceStore"):
    """Create read_workspace_file tool bound to a workspace store."""

    @tool(args_schema=ReadWorkspaceFileInput)
    async def read_workspace_file(
        path: str,
        offset: int = 0,
        limit: int = DEFAULT_READ_LIMIT_CHARS,
    ) -> str:
        """Read content from a workspace file.

        Use this to read files from your virtual workspace:
        - /scratch/ - Your working notes (ephemeral)
        - /customer/{id}/ - Customer history (persistent)
        - /knowledge/ - Cached search results
        - /playbooks/ - Solution playbooks (read-only)

        Args:
            path: Virtual path (e.g., "/scratch/notes.md")
            offset: Character offset to start reading from
            limit: Maximum characters to read (default: 2048, max: 50000)

        Returns:
            File content, or error message if not found.
        """
        try:
            # Validate path and get scope
            scope = store._get_scope_for_path(path)
            identifier = _get_rate_limit_identifier(scope, path, store)

            # Check rate limit
            if not _rate_limiter.check_and_record(scope.value, "reads", identifier):
                return f"Rate limit exceeded for {scope.value} scope. Try again in 60 seconds."

            # Enforce max limit
            limit = min(limit, MAX_READ_LIMIT_CHARS)

            # Read the file
            content = await store.read_file(path)

            if content is None:
                return f"File not found: {path}"

            # Apply offset and limit
            if offset > 0:
                content = content[offset:]

            if len(content) > limit:
                truncated = content[:limit]
                return f"{truncated}\n\n[...truncated at {limit} chars. Use offset={offset + limit} to continue reading]"

            return content

        except ValueError as e:
            return f"Invalid path: {e}"
        except Exception as e:
            logger.error("read_workspace_file_error", path=path, error=str(e))
            return f"Error reading file: {e}"

    return read_workspace_file


def create_write_workspace_file(store: "SparrowWorkspaceStore"):
    """Create write_workspace_file tool bound to a workspace store."""

    @tool(args_schema=WriteWorkspaceFileInput)
    async def write_workspace_file(
        path: str,
        content: str,
        max_size_bytes: int = DEFAULT_WRITE_MAX_BYTES,
    ) -> str:
        """Write content to a workspace file.

        Use this to save your working notes and findings:
        - /scratch/notes.md - Investigation notes
        - /scratch/hypothesis.md - Current hypothesis
        - /knowledge/kb_results.md - Cached KB search results

        Note: /playbooks/ is read-only and cannot be written to.

        Args:
            path: Virtual path (e.g., "/scratch/notes.md")
            content: Content to write
            max_size_bytes: Maximum file size (default: 100KB)

        Returns:
            Success message with file size, or error message.
        """
        try:
            # Validate path and get scope
            scope = store._get_scope_for_path(path)
            identifier = _get_rate_limit_identifier(scope, path, store)

            # Check if this is a read-only scope
            if scope.value == "global":
                return "Error: /playbooks/ is read-only. Cannot write to global scope."

            # Check rate limit
            if not _rate_limiter.check_and_record(scope.value, "writes", identifier):
                return f"Rate limit exceeded for {scope.value} scope. Try again in 60 seconds."

            # Check content size
            content_bytes = len(content.encode('utf-8'))
            if content_bytes > max_size_bytes:
                return f"Content too large: {content_bytes} bytes exceeds limit of {max_size_bytes} bytes."

            # Write the file
            await store.write_file(path, content)

            logger.info(
                "workspace_file_written",
                path=path,
                size_bytes=content_bytes,
                scope=scope.value,
            )

            return f"Successfully wrote {content_bytes} bytes to {path}"

        except ValueError as e:
            return f"Invalid path: {e}"
        except Exception as e:
            logger.error("write_workspace_file_error", path=path, error=str(e))
            return f"Error writing file: {e}"

    return write_workspace_file


def create_list_workspace_files(store: "SparrowWorkspaceStore"):
    """Create list_workspace_files tool bound to a workspace store."""

    @tool(args_schema=ListWorkspaceFilesInput)
    async def list_workspace_files(
        path: str = "/",
        depth: int = DEFAULT_LIST_DEPTH,
    ) -> str:
        """List files in a workspace directory.

        Use this to see what files exist in your workspace.

        Args:
            path: Virtual directory path (e.g., "/scratch", "/customer/{id}")
            depth: Maximum depth to traverse (default: 2, max: 5)

        Returns:
            List of files with paths and metadata.
        """
        try:
            # Validate path and get scope
            scope = store._get_scope_for_path(path)
            identifier = _get_rate_limit_identifier(scope, path, store)

            # Check rate limit
            if not _rate_limiter.check_and_record(scope.value, "reads", identifier):
                return f"Rate limit exceeded for {scope.value} scope. Try again in 60 seconds."

            # Enforce max depth
            depth = min(depth, MAX_LIST_DEPTH)

            # List files
            files = await store.list_files(path, depth)

            if not files:
                return f"No files found in {path}"

            # Format output
            lines = [f"Files in {path}:"]
            for f in files:
                lines.append(f"  - {f['path']} (updated: {f.get('updated_at', 'unknown')})")

            return "\n".join(lines)

        except ValueError as e:
            return f"Invalid path: {e}"
        except Exception as e:
            logger.error("list_workspace_files_error", path=path, error=str(e))
            return f"Error listing files: {e}"

    return list_workspace_files


def create_search_workspace(store: "SparrowWorkspaceStore"):
    """Create search_workspace tool bound to a workspace store."""

    @tool(args_schema=SearchWorkspaceInput)
    async def search_workspace(
        query: str,
        path: str = "/",
        limit: int = DEFAULT_SEARCH_LIMIT,
    ) -> str:
        """Search for content in workspace files.

        Uses content indexing for fast search. Good for finding specific
        information across your workspace files.

        Args:
            query: Search query to find in file contents
            path: Virtual path prefix to search within
            limit: Maximum results to return (default: 10, max: 50)

        Returns:
            List of matching files with snippets.
        """
        try:
            # Validate path and get scope
            scope = store._get_scope_for_path(path)
            identifier = _get_rate_limit_identifier(scope, path, store)

            # Check rate limit
            if not _rate_limiter.check_and_record(scope.value, "reads", identifier):
                return f"Rate limit exceeded for {scope.value} scope. Try again in 60 seconds."

            # Enforce max limit
            limit = min(limit, MAX_SEARCH_LIMIT)

            # Convert path to namespace prefix
            normalized = path.strip("/")
            if normalized:
                namespace_prefix = tuple(normalized.split("/"))
            else:
                namespace_prefix = ()

            # Search with content query
            items = await store.asearch(namespace_prefix, query=query, limit=limit)

            if not items:
                return f"No results found for '{query}' in {path}"

            # Format output with snippets
            lines = [f"Search results for '{query}' in {path}:"]
            for item in items:
                file_path = "/" + "/".join(item.namespace) + "/" + item.key
                content = item.value.get("content", "")

                # Extract snippet around match
                snippet = _extract_snippet(content, query, context_chars=100)

                lines.append(f"\n  {file_path}:")
                lines.append(f"    ...{snippet}...")

            return "\n".join(lines)

        except ValueError as e:
            return f"Invalid path: {e}"
        except Exception as e:
            logger.error("search_workspace_error", query=query, path=path, error=str(e))
            return f"Error searching: {e}"

    return search_workspace


def create_append_workspace_file(store: "SparrowWorkspaceStore"):
    """Create append_workspace_file tool bound to a workspace store."""

    @tool(args_schema=AppendWorkspaceFileInput)
    async def append_workspace_file(
        path: str,
        content: str,
        max_size_bytes: int = DEFAULT_WRITE_MAX_BYTES,
    ) -> str:
        """Append content to a workspace file with timestamp.

        Use this for building up history files or logs:
        - /customer/{id}/history/ticket_123.md - Ticket summaries
        - /scratch/findings.md - Accumulated findings

        Content is automatically timestamped. Thread-safe via per-path locked append.

        Args:
            path: Virtual path to append to
            content: Content to append (will be prefixed with timestamp)
            max_size_bytes: Maximum file size (default: 100KB)

        Returns:
            Success message with new file size, or error if exceeds limit.
        """
        try:
            # Validate path and get scope
            scope = store._get_scope_for_path(path)
            identifier = _get_rate_limit_identifier(scope, path, store)

            # Check if this is a read-only scope
            if scope.value == "global":
                return "Error: /playbooks/ is read-only. Cannot append to global scope."

            # Check rate limit
            if not _rate_limiter.check_and_record(scope.value, "writes", identifier):
                return f"Rate limit exceeded for {scope.value} scope. Try again in 60 seconds."

            # Create timestamped entry
            timestamp = datetime.now(timezone.utc).isoformat()
            entry = f"\n---\n[{timestamp}]\n{content}"

            appended_bytes = len(entry.encode("utf-8"))
            try:
                new_size = await store.append_file(path, entry, max_size_bytes)
            except ValueError as e:
                message = str(e)
                if "Append would exceed" in message:
                    return message
                raise

            logger.info(
                "workspace_file_appended",
                path=path,
                appended_bytes=appended_bytes,
                total_bytes=new_size,
                scope=scope.value,
            )

            return f"Appended {len(content)} chars to {path} (total size: {new_size} bytes)"

        except ValueError as e:
            return f"Invalid path: {e}"
        except Exception as e:
            logger.error("append_workspace_file_error", path=path, error=str(e))
            return f"Error appending: {e}"

    return append_workspace_file


def create_grep_workspace_files(store: "SparrowWorkspaceStore"):
    """Create grep_workspace_files tool bound to a workspace store."""

    @tool(args_schema=GrepWorkspaceFilesInput)
    async def grep_workspace_files(
        pattern: str,
        path: str = "/",
        limit: int = 20,
    ) -> str:
        """Search for a regex pattern in workspace files.

        Similar to grep, finds files containing the pattern with
        line numbers and context.

        Args:
            pattern: Regex pattern to search for
            path: Virtual path prefix to search within
            limit: Maximum matching files to return

        Returns:
            List of matches with file paths and line numbers.
        """
        try:
            # Validate regex
            try:
                regex = re.compile(pattern, re.IGNORECASE)
            except re.error as e:
                return f"Invalid regex pattern: {e}"

            # Validate path and get scope
            scope = store._get_scope_for_path(path)
            identifier = _get_rate_limit_identifier(scope, path, store)

            # Check rate limit
            if not _rate_limiter.check_and_record(scope.value, "reads", identifier):
                return f"Rate limit exceeded for {scope.value} scope. Try again in 60 seconds."

            # List all files in path
            files = await store.list_files(path, depth=MAX_LIST_DEPTH)

            matches = []
            for f in files:
                if len(matches) >= limit:
                    break

                # Read file content
                content = await store.read_file(f["path"])
                if not content:
                    continue

                # Find matches
                file_matches = []
                for i, line in enumerate(content.split("\n"), 1):
                    if regex.search(line):
                        file_matches.append((i, line.strip()[:100]))  # Line num, truncated line

                if file_matches:
                    matches.append({
                        "path": f["path"],
                        "matches": file_matches[:5],  # Max 5 matches per file
                    })

            if not matches:
                return f"No matches for pattern '{pattern}' in {path}"

            # Format output
            lines = [f"Grep results for '{pattern}' in {path}:"]
            for m in matches:
                lines.append(f"\n  {m['path']}:")
                for line_num, line_text in m["matches"]:
                    lines.append(f"    {line_num}: {line_text}")

            return "\n".join(lines)

        except ValueError as e:
            return f"Invalid path: {e}"
        except Exception as e:
            logger.error("grep_workspace_files_error", pattern=pattern, path=path, error=str(e))
            return f"Error searching: {e}"

    return grep_workspace_files


# =============================================================================
# Helper Functions
# =============================================================================

def _extract_snippet(content: str, query: str, context_chars: int = 100) -> str:
    """Extract a snippet around the first match of query in content."""
    query_lower = query.lower()
    content_lower = content.lower()

    pos = content_lower.find(query_lower)
    if pos == -1:
        # Return start of content if no match found
        return content[:context_chars * 2]

    start = max(0, pos - context_chars)
    end = min(len(content), pos + len(query) + context_chars)

    snippet = content[start:end].strip()
    return snippet


# =============================================================================
# Tool Registry
# =============================================================================

def get_workspace_tools(store: "SparrowWorkspaceStore") -> List:
    """Get all workspace tools bound to a workspace store.

    Args:
        store: SparrowWorkspaceStore instance to bind tools to.

    Returns:
        List of LangChain tools ready for use in agent.

    Example:
        from app.agents.harness.store import SparrowWorkspaceStore
        from app.agents.unified.workspace_tools import get_workspace_tools

        store = SparrowWorkspaceStore(session_id="sess123", customer_id="cust456")
        tools = get_workspace_tools(store)
    """
    return [
        create_read_workspace_file(store),
        create_write_workspace_file(store),
        create_list_workspace_files(store),
        create_search_workspace(store),
        create_append_workspace_file(store),
        create_grep_workspace_files(store),
    ]


# =============================================================================
# Attachment Caching
# =============================================================================

async def cache_attachment_summary(
    store: "SparrowWorkspaceStore",
    attachment_id: str,
    summary: str,
) -> str:
    """Cache a processed attachment summary with TTL metadata.

    Args:
        store: Workspace store instance.
        attachment_id: Unique attachment identifier.
        summary: Processed attachment summary text.

    Returns:
        Success message with path.
    """
    path = f"/knowledge/attachments/{attachment_id}.md"

    # Enforce size limit
    if len(summary.encode('utf-8')) > ATTACHMENT_MAX_SIZE_BYTES:
        summary = summary[:ATTACHMENT_MAX_SIZE_BYTES] + "\n\n[...truncated]"

    await store.write_file(path, summary, metadata={
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=ATTACHMENT_TTL_HOURS)).isoformat(),
        "attachment_id": attachment_id,
    })

    logger.info(
        "attachment_cached",
        attachment_id=attachment_id,
        path=path,
        size_bytes=len(summary.encode('utf-8')),
    )

    return f"Cached attachment summary to {path}"


async def get_cached_attachment(
    store: "SparrowWorkspaceStore",
    attachment_id: str,
) -> Optional[str]:
    """Retrieve a cached attachment summary if not expired.

    Checks the TTL metadata and returns None if the cache has expired.

    Args:
        store: Workspace store instance.
        attachment_id: Unique attachment identifier.

    Returns:
        Cached summary if valid and not expired, None otherwise.
    """
    path = f"/knowledge/attachments/{attachment_id}.md"

    try:
        # Read the file (includes metadata)
        content = await store.read_file(path)
        if not content:
            return None

        # Check if we can get metadata
        namespace, key = store._path_to_namespace_key(path)
        item = await store.aget(namespace, key)

        if item and item.value.get("metadata"):
            metadata = item.value["metadata"]
            expires_at_str = metadata.get("expires_at")

            if expires_at_str:
                expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
                if datetime.now(timezone.utc) > expires_at:
                    logger.debug(
                        "attachment_cache_expired",
                        attachment_id=attachment_id,
                        expires_at=expires_at_str,
                    )
                    return None

        logger.debug(
            "attachment_cache_hit",
            attachment_id=attachment_id,
            path=path,
        )
        return content

    except Exception as e:
        logger.debug(
            "attachment_cache_miss",
            attachment_id=attachment_id,
            error=str(e),
        )
        return None


async def cleanup_expired_attachments(
    store: "SparrowWorkspaceStore",
) -> int:
    """Clean up expired attachment caches.

    Scans /knowledge/attachments/ and removes files past their TTL.

    Args:
        store: Workspace store instance.

    Returns:
        Number of expired attachments removed.
    """
    try:
        # List all attachment files
        files = await store.list_files("/knowledge/attachments", depth=1)
        now = datetime.now(timezone.utc)
        deleted_count = 0

        for f in files:
            path = f["path"]
            namespace, key = store._path_to_namespace_key(path)
            item = await store.aget(namespace, key)

            if item and item.value.get("metadata"):
                expires_at_str = item.value["metadata"].get("expires_at")
                if expires_at_str:
                    expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
                    if now > expires_at:
                        # Delete expired attachment
                        await store.adelete(namespace, key)
                        deleted_count += 1
                        logger.debug(
                            "expired_attachment_deleted",
                            path=path,
                            expires_at=expires_at_str,
                        )

        if deleted_count > 0:
            logger.info(
                "attachment_cleanup_complete",
                deleted_count=deleted_count,
            )

        return deleted_count

    except Exception as e:
        logger.warning(
            "attachment_cleanup_error",
            error=str(e),
        )
        return 0
