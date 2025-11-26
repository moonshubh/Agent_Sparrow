"""
Backend Protocol for Agent Harness Storage.

Defines the interface contract for storage backends following
the DeepAgents middleware-first architecture pattern.

This protocol enables:
- Type-safe backend implementations
- Interchangeable storage backends (Supabase, memory, file system)
- Consistent API across all storage operations
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from .supabase_store import FileInfo, WriteResult, EditResult, GrepMatch


@runtime_checkable
class BackendProtocol(Protocol):
    """Protocol defining the storage backend interface.

    Backends implementing this protocol provide consistent storage
    operations for:
    - Global knowledge persistence
    - Cross-session memory
    - Large tool result eviction
    - Scratchpad operations

    All implementations must support:
    - CRUD operations (read, write, delete)
    - Directory listing (ls_info)
    - Pattern matching (glob_info)
    - Content search (grep_raw)
    - In-place editing (edit)

    Example:
        def process_with_backend(backend: BackendProtocol):
            content = backend.read("/data/facts.txt")
            result = backend.write("/data/output.txt", "new content")
            matches = backend.grep_raw("error", path="/logs")
    """

    def read(
        self,
        file_path: str,
        offset: int = 0,
        limit: int = 500,
    ) -> Optional[str]:
        """Read content from storage with pagination support.

        Args:
            file_path: Path to the file to read.
            offset: Line offset to start reading from (0-indexed).
            limit: Maximum number of lines to return.

        Returns:
            File content as string, or None if file not found.
            Content is line-limited based on offset and limit.
        """
        ...

    def write(
        self,
        file_path: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> WriteResult:
        """Write content to storage (creates or overwrites).

        Args:
            file_path: Path for the file (will be created if needed).
            content: Content to write.
            metadata: Optional metadata to associate with the file.

        Returns:
            WriteResult with success status, path, size, and error if any.
        """
        ...

    def delete(self, file_path: str) -> bool:
        """Delete a file from storage.

        Args:
            file_path: Path to the file to delete.

        Returns:
            True if file was deleted, False if not found or error.
        """
        ...

    def ls_info(self, path: str) -> List[FileInfo]:
        """List files at a path with detailed information.

        Args:
            path: Directory path to list (prefix match).

        Returns:
            List of FileInfo objects with path, size, timestamps, metadata.
        """
        ...

    def glob_info(self, pattern: str, path: str = "/") -> List[FileInfo]:
        """Find files matching a glob pattern.

        Args:
            pattern: Glob pattern (e.g., "*.txt", "**/*.json").
            path: Base path to search from.

        Returns:
            List of matching FileInfo objects.
        """
        ...

    def grep_raw(
        self,
        pattern: str,
        path: Optional[str] = None,
        context_lines: int = 2,
    ) -> List[GrepMatch]:
        """Search for pattern in file contents.

        Args:
            pattern: Regex pattern to search for.
            path: Optional path prefix to limit search scope.
            context_lines: Number of lines to include before/after match.

        Returns:
            List of GrepMatch objects with path, line number, content, and context.
        """
        ...

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        """Edit a file by replacing strings.

        Args:
            file_path: Path to the file to edit.
            old_string: String to find and replace.
            new_string: Replacement string.
            replace_all: If True, replace all occurrences; otherwise replace first only.

        Returns:
            EditResult with success status, replacement count, and error if any.
        """
        ...


class InMemoryBackend:
    """In-memory implementation of BackendProtocol for testing.

    Provides a simple dict-based storage that implements the full
    protocol without any external dependencies.
    """

    def __init__(self) -> None:
        self._storage: Dict[str, Dict[str, Any]] = {}

    def read(
        self,
        file_path: str,
        offset: int = 0,
        limit: int = 500,
    ) -> Optional[str]:
        # Validate offset and limit are non-negative
        offset = max(0, offset)
        limit = max(0, limit)

        entry = self._storage.get(file_path)
        if entry is None:
            return None

        content = entry.get("content", "")
        lines = content.split("\n")
        selected = lines[offset : offset + limit]
        return "\n".join(selected)

    def write(
        self,
        file_path: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> WriteResult:
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        self._storage[file_path] = {
            "content": content,
            "metadata": metadata or {},
            "created_at": self._storage.get(file_path, {}).get("created_at", now),
            "updated_at": now,
        }
        return WriteResult(success=True, path=file_path, size=len(content))

    def delete(self, file_path: str) -> bool:
        if file_path in self._storage:
            del self._storage[file_path]
            return True
        return False

    def ls_info(self, path: str) -> List[FileInfo]:
        results = []
        # Normalize path for proper prefix matching (prevent /scratch matching /scratchpad)
        normalized_path = path.rstrip("/") + "/" if path != "/" else "/"
        for file_path, entry in self._storage.items():
            # Match if: exact file, or file is in directory (starts with path/)
            if file_path == path or file_path.startswith(normalized_path):
                results.append(
                    FileInfo(
                        path=file_path,
                        size=len(entry.get("content", "")),
                        created_at=entry.get("created_at", ""),
                        updated_at=entry.get("updated_at", ""),
                        metadata=entry.get("metadata", {}),
                    )
                )
        return results

    def glob_info(self, pattern: str, path: str = "/") -> List[FileInfo]:
        import fnmatch

        all_files = self.ls_info(path)
        matched = []
        for file_info in all_files:
            relative = file_info.path
            if path and file_info.path.startswith(path):
                relative = file_info.path[len(path) :].lstrip("/")
            if fnmatch.fnmatch(relative, pattern):
                matched.append(file_info)
        return matched

    def grep_raw(
        self,
        pattern: str,
        path: Optional[str] = None,
        context_lines: int = 2,
    ) -> List[GrepMatch]:
        import re

        # Validate context_lines is non-negative
        context_lines = max(0, context_lines)

        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error:
            return []

        files = self.ls_info(path or "/")
        matches = []

        for file_info in files:
            content = self.read(file_info.path, limit=100000)
            if not content:
                continue

            lines = content.split("\n")
            for idx, line in enumerate(lines):
                if regex.search(line):
                    start = max(0, idx - context_lines)
                    end = min(len(lines), idx + context_lines + 1)
                    matches.append(
                        GrepMatch(
                            path=file_info.path,
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
        content = self.read(file_path, limit=100000)
        if content is None:
            return EditResult(success=False, replacements=0, error="File not found")

        if old_string not in content:
            return EditResult(success=False, replacements=0, error="String not found")

        if replace_all:
            replacements = content.count(old_string)
            new_content = content.replace(old_string, new_string)
        else:
            replacements = 1
            new_content = content.replace(old_string, new_string, 1)

        self.write(file_path, new_content)
        return EditResult(success=True, replacements=replacements)
