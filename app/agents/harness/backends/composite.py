"""Composite backend that routes to appropriate storage based on path prefix.

This backend follows the DeepAgents pattern of using multiple backends
for different purposes, routing by path prefix.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from loguru import logger

from .supabase_store import (
    EditResult,
    FileInfo,
    GrepMatch,
    SupabaseStoreBackend,
    WriteResult,
)

if TYPE_CHECKING:
    from supabase import Client as SupabaseClient


class StateBackend:
    """Ephemeral in-memory backend for scratch data.

    Used for temporary storage during agent runs. Data is lost
    when the agent instance is garbage collected.
    """

    def __init__(self):
        """Initialize the backend."""
        self._storage: Dict[str, str] = {}
        self._metadata: Dict[str, Dict[str, Any]] = {}

    def read(
        self,
        file_path: str,
        offset: int = 0,
        limit: int = 2000,
    ) -> Optional[str]:
        """Read content from memory."""
        content = self._storage.get(file_path)
        if content is None:
            return None

        lines = content.split("\n")
        selected_lines = lines[offset : offset + limit]
        return "\n".join(selected_lines)

    def write(
        self,
        file_path: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> WriteResult:
        """Write content to memory."""
        self._storage[file_path] = content
        if metadata:
            self._metadata[file_path] = metadata

        return WriteResult(
            success=True,
            path=file_path,
            size=len(content),
        )

    def delete(self, file_path: str) -> bool:
        """Delete content from memory."""
        if file_path in self._storage:
            del self._storage[file_path]
            self._metadata.pop(file_path, None)
            return True
        return False

    def ls_info(self, path: str) -> List[FileInfo]:
        """List files at path.

        Args:
            path: Directory path to list.

        Returns:
            List of FileInfo for files in the directory.
        """
        from datetime import datetime, timezone

        files = []
        now = datetime.now(timezone.utc).isoformat()

        # Normalize path to ensure proper directory matching
        # This prevents "/scratch" from matching "/scratchpad"
        normalized_path = path.rstrip("/")
        if normalized_path and normalized_path != "/":
            normalized_path += "/"

        for stored_path, content in self._storage.items():
            # Match if: stored_path starts with normalized directory path
            # OR stored_path exactly equals the path (for root "/" or exact file match)
            is_match = (
                (normalized_path and stored_path.startswith(normalized_path))
                or stored_path == path
                or (path == "/" and True)  # Root lists everything
            )

            if is_match:
                files.append(
                    FileInfo(
                        path=stored_path,
                        size=len(content),
                        created_at=now,
                        updated_at=now,
                        metadata=self._metadata.get(stored_path, {}),
                    )
                )

        return files

    def glob_info(self, pattern: str, path: str = "/") -> List[FileInfo]:
        """Find files matching pattern."""
        import fnmatch

        all_files = self.ls_info(path)
        matched = []

        for file_info in all_files:
            relative_path = file_info.path
            if path and file_info.path.startswith(path):
                relative_path = file_info.path[len(path) :].lstrip("/")

            if fnmatch.fnmatch(relative_path, pattern):
                matched.append(file_info)

        return matched

    def grep_raw(
        self,
        pattern: str,
        path: Optional[str] = None,
        context_lines: int = 2,
    ) -> List[GrepMatch]:
        """Search for pattern in files."""
        import re

        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error:
            return []

        matches = []
        for file_path, content in self._storage.items():
            if path and not file_path.startswith(path):
                continue

            lines = content.split("\n")
            for idx, line in enumerate(lines):
                if regex.search(line):
                    start = max(0, idx - context_lines)
                    end = min(len(lines), idx + context_lines + 1)

                    matches.append(
                        GrepMatch(
                            path=file_path,
                            line_number=idx + 1,
                            content=line,
                            context_before=lines[start:idx],
                            context_after=lines[idx + 1 : end],
                        )
                    )

        return matches

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        """Edit a file by replacing strings."""
        content = self._storage.get(file_path)
        if content is None:
            return EditResult(
                success=False,
                replacements=0,
                error=f"File not found: {file_path}",
            )

        if old_string not in content:
            return EditResult(
                success=False,
                replacements=0,
                error="String not found",
            )

        if replace_all:
            new_content = content.replace(old_string, new_string)
            replacements = content.count(old_string)
        else:
            new_content = content.replace(old_string, new_string, 1)
            replacements = 1

        self._storage[file_path] = new_content
        return EditResult(success=True, replacements=replacements)

    def exists(self, file_path: str) -> bool:
        """Check if file exists."""
        return file_path in self._storage

    def clear(self) -> None:
        """Clear all stored data."""
        self._storage.clear()
        self._metadata.clear()


@dataclass
class RouteConfig:
    """Configuration for a backend route."""

    prefix: str
    backend: Any  # Backend instance
    description: str = ""


class SparrowCompositeBackend:
    """Composite backend that routes to appropriate storage based on path prefix.

    Routes:
    - /memories/* -> Persistent storage (Supabase) for cross-session memory
    - /scratch/* -> Ephemeral storage (in-memory) for temporary data
    - /large_results/* -> Ephemeral storage with auto-cleanup for tool results
    - /knowledge/* -> Persistent storage for knowledge base data

    This follows the DeepAgents pattern of composing multiple backends
    while providing a unified interface.

    Usage:
        backend = SparrowCompositeBackend(supabase_client)
        backend.write("/memories/user123/facts.txt", "...")  # Goes to Supabase
        backend.write("/scratch/temp.txt", "...")            # Goes to memory
    """

    def __init__(
        self,
        supabase_client: Optional["SupabaseClient"] = None,
        ephemeral_backend: Optional[StateBackend] = None,
    ):
        """Initialize the composite backend.

        Args:
            supabase_client: Optional Supabase client for persistent storage.
            ephemeral_backend: Optional ephemeral backend (defaults to StateBackend).
        """
        self._ephemeral = ephemeral_backend or StateBackend()

        # Initialize persistent backend if client provided
        self._persistent: Optional[SupabaseStoreBackend] = None
        if supabase_client:
            self._persistent = SupabaseStoreBackend(supabase_client)

        # Configure routes
        self._routes: List[RouteConfig] = [
            RouteConfig(
                prefix="/memories/",
                backend=self._persistent or self._ephemeral,
                description="Cross-session memory storage",
            ),
            RouteConfig(
                prefix="/knowledge/",
                backend=self._persistent or self._ephemeral,
                description="Knowledge base storage",
            ),
            RouteConfig(
                prefix="/scratch/",
                backend=self._ephemeral,
                description="Temporary scratch storage",
            ),
            RouteConfig(
                prefix="/large_results/",
                backend=self._ephemeral,
                description="Evicted tool results",
            ),
        ]

        # Default route for unmatched paths
        self._default_backend = self._ephemeral

    def _get_backend_for_path(self, path: str) -> Any:
        """Get the appropriate backend for a path.

        Args:
            path: File path.

        Returns:
            Backend instance to use.
        """
        for route in self._routes:
            if path.startswith(route.prefix):
                logger.debug(
                    "route_selected",
                    path=path,
                    route=route.prefix,
                    backend=type(route.backend).__name__,
                )
                return route.backend

        return self._default_backend

    def read(
        self,
        file_path: str,
        offset: int = 0,
        limit: int = 2000,
    ) -> Optional[str]:
        """Read content from the appropriate backend.

        Args:
            file_path: Path to read.
            offset: Line offset.
            limit: Line limit.

        Returns:
            Content or None.
        """
        backend = self._get_backend_for_path(file_path)
        return backend.read(file_path, offset=offset, limit=limit)

    def write(
        self,
        file_path: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> WriteResult:
        """Write content to the appropriate backend.

        Args:
            file_path: Path to write.
            content: Content to write.
            metadata: Optional metadata.

        Returns:
            WriteResult.
        """
        backend = self._get_backend_for_path(file_path)
        return backend.write(file_path, content, metadata=metadata)

    def delete(self, file_path: str) -> bool:
        """Delete from the appropriate backend.

        Args:
            file_path: Path to delete.

        Returns:
            True if deleted.
        """
        backend = self._get_backend_for_path(file_path)
        return backend.delete(file_path)

    def ls_info(self, path: str) -> List[FileInfo]:
        """List files from all matching backends.

        Args:
            path: Path to list.

        Returns:
            Combined list of FileInfo.
        """
        results = []
        seen_paths = set()

        for route in self._routes:
            if path.startswith(route.prefix) or route.prefix.startswith(path):
                files = route.backend.ls_info(path)
                for f in files:
                    if f.path not in seen_paths:
                        results.append(f)
                        seen_paths.add(f.path)

        return results

    def glob_info(self, pattern: str, path: str = "/") -> List[FileInfo]:
        """Find files matching pattern across backends.

        Args:
            pattern: Glob pattern.
            path: Base path.

        Returns:
            List of matching FileInfo.
        """
        results = []
        seen_paths = set()

        for route in self._routes:
            if path == "/" or path.startswith(route.prefix) or route.prefix.startswith(path):
                files = route.backend.glob_info(pattern, path)
                for f in files:
                    if f.path not in seen_paths:
                        results.append(f)
                        seen_paths.add(f.path)

        return results

    def grep_raw(
        self,
        pattern: str,
        path: Optional[str] = None,
    ) -> List[GrepMatch]:
        """Search for pattern across backends.

        Args:
            pattern: Search pattern.
            path: Optional path filter.

        Returns:
            List of GrepMatch (deduplicated).
        """
        results = []
        # Track seen matches by (path, line_number, content) to prevent duplicates
        seen_matches: set[tuple[str, int, str]] = set()

        for route in self._routes:
            if path is None or path.startswith(route.prefix) or route.prefix.startswith(path):
                matches = route.backend.grep_raw(pattern, path)
                for match in matches:
                    # Create uniqueness key from identifying attributes
                    match_key = (match.path, match.line_number, match.content)
                    if match_key not in seen_matches:
                        results.append(match)
                        seen_matches.add(match_key)

        return results

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        """Edit file in the appropriate backend.

        Args:
            file_path: Path to edit.
            old_string: String to find.
            new_string: Replacement string.
            replace_all: Replace all occurrences.

        Returns:
            EditResult.
        """
        backend = self._get_backend_for_path(file_path)
        return backend.edit(file_path, old_string, new_string, replace_all=replace_all)

    def exists(self, file_path: str) -> bool:
        """Check if file exists in appropriate backend.

        Args:
            file_path: Path to check.

        Returns:
            True if exists.
        """
        backend = self._get_backend_for_path(file_path)
        return backend.exists(file_path)

    def clear_ephemeral(self) -> None:
        """Clear all ephemeral storage.

        Call this after agent run to free memory.
        """
        self._ephemeral.clear()

    def get_route_info(self) -> List[Dict[str, str]]:
        """Get information about configured routes.

        Returns:
            List of route information dicts.
        """
        return [
            {
                "prefix": route.prefix,
                "backend": type(route.backend).__name__,
                "description": route.description,
            }
            for route in self._routes
        ]
