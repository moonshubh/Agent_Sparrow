"""Composite backend that routes to appropriate storage based on path prefix.

This backend follows the DeepAgents pattern of using multiple backends
for different purposes, routing by path prefix.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from loguru import logger

# Import from protocol (canonical source for types and InMemoryBackend)
from .protocol import (
    EditResult,
    FileInfo,
    GrepMatch,
    InMemoryBackend,
    WriteResult,
)
from .supabase_store import SupabaseStoreBackend

if TYPE_CHECKING:
    from supabase import Client as SupabaseClient


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
        ephemeral_backend: Optional[InMemoryBackend] = None,
    ):
        """Initialize the composite backend.

        Args:
            supabase_client: Optional Supabase client for persistent storage.
            ephemeral_backend: Optional ephemeral backend (defaults to InMemoryBackend).
        """
        self._ephemeral = ephemeral_backend or InMemoryBackend()

        # Initialize persistent backend if client provided
        self._persistent: Optional[SupabaseStoreBackend] = None
        if supabase_client:
            self._persistent = SupabaseStoreBackend(supabase_client)

        # Configure routes
        # Persistent routes (survive across sessions):
        # - /memories/, /knowledge/: existing memory and KB storage
        # - /progress/, /goals/, /handoff/: deep agent workspace (NEW)
        #
        # Ephemeral routes (cleared per-session):
        # - /scratch/, /large_results/: temporary working data
        self._routes: List[RouteConfig] = [
            # === Persistent Storage Routes (Supabase-backed) ===
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
            # Deep Agent workspace routes (context engineering)
            RouteConfig(
                prefix="/progress/",
                backend=self._persistent or self._ephemeral,
                description="Session progress notes (persists across messages)",
            ),
            RouteConfig(
                prefix="/goals/",
                backend=self._persistent or self._ephemeral,
                description="Active goals and feature tracking (JSON)",
            ),
            RouteConfig(
                prefix="/handoff/",
                backend=self._persistent or self._ephemeral,
                description="Session handoff context for resumption",
            ),
            # === Ephemeral Storage Routes (in-memory) ===
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
