"""Supabase-backed persistent storage following DeepAgents backend protocol.

This backend provides persistent storage for:
- Cross-session memory
- Large tool result eviction
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from loguru import logger

# Import data types from protocol (canonical source)
from .protocol import FileInfo, WriteResult, EditResult, GrepMatch

if TYPE_CHECKING:
    from supabase import Client as SupabaseClient


# Constants
DEFAULT_TABLE = "agent_files"
MAX_CONTENT_SIZE = 10_000_000  # 10MB limit
DEFAULT_READ_LIMIT = 500  # lines

# Re-export for backwards compatibility
__all__ = ["SupabaseStoreBackend", "FileInfo", "WriteResult", "EditResult", "GrepMatch"]


class SupabaseStoreBackend:
    """Supabase-backed persistent storage following DeepAgents backend protocol.

    Used for:
    - Cross-session memory
    - Large tool result eviction

    The backend uses a simple table structure:
    - path: VARCHAR (primary key, unique file path)
    - content: TEXT (file content)
    - metadata: JSONB (additional metadata)
    - created_at: TIMESTAMPTZ
    - updated_at: TIMESTAMPTZ

    Usage:
        backend = SupabaseStoreBackend(supabase_client)
        backend.write("/memories/user123/facts.txt", "Important facts...")
        content = backend.read("/memories/user123/facts.txt")
    """

    def __init__(
        self,
        client: "SupabaseClient",
        table: str = DEFAULT_TABLE,
    ):
        """Initialize the backend.

        Args:
            client: Supabase client instance.
            table: Table name for storage.
        """
        self.client = client
        self.table = table

    def read(
        self,
        file_path: str,
        offset: int = 0,
        limit: int = DEFAULT_READ_LIMIT,
    ) -> Optional[str]:
        """Read content from storage.

        Args:
            file_path: Path to the file.
            offset: Line offset to start reading from.
            limit: Maximum number of lines to read (defaults to 500).

        Returns:
            File content as string, or None if not found.
        """
        try:
            response = (
                self.client.table(self.table)
                .select("content")
                .eq("path", file_path)
                .single()
                .execute()
            )

            if not response.data:
                return None

            content = response.data.get("content", "")
            if not content:
                return ""

            # Apply offset and limit by lines
            lines = content.split("\n")
            start = max(offset, 0)
            end = start + max(limit, 0)
            selected_lines = lines[start:end]
            return "\n".join(selected_lines)

        except Exception as exc:
            logger.warning("supabase_read_failed", path=file_path, error=str(exc))
            return None

    def write(
        self,
        file_path: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> WriteResult:
        """Write content to storage.

        Args:
            file_path: Path for the file.
            content: Content to write.
            metadata: Optional metadata to store.

        Returns:
            WriteResult indicating success/failure.
        """
        # Check byte size (not character count) for proper UTF-8 handling
        byte_size = len(content.encode("utf-8"))
        if byte_size > MAX_CONTENT_SIZE:
            return WriteResult(
                success=False,
                path=file_path,
                size=byte_size,
                error=f"Content exceeds maximum size of {MAX_CONTENT_SIZE} bytes (actual: {byte_size})",
            )

        now = datetime.now(timezone.utc).isoformat()
        data = {
            "path": file_path,
            "content": content,
            "metadata": metadata or {},
            "updated_at": now,
        }

        try:
            # Try upsert (insert or update)
            response = (
                self.client.table(self.table)
                .upsert(data, on_conflict="path")
                .execute()
            )

            return WriteResult(
                success=True,
                path=file_path,
                size=len(content),
            )

        except Exception as exc:
            logger.error("supabase_write_failed", path=file_path, error=str(exc))
            return WriteResult(
                success=False,
                path=file_path,
                size=len(content),
                error=str(exc),
            )

    def delete(self, file_path: str) -> bool:
        """Delete a file from storage.

        Args:
            file_path: Path to delete.

        Returns:
            True if deleted, False otherwise.
        """
        try:
            self.client.table(self.table).delete().eq("path", file_path).execute()
            return True
        except Exception as exc:
            logger.warning("supabase_delete_failed", path=file_path, error=str(exc))
            return False

    def ls_info(self, path: str) -> List[FileInfo]:
        """List files at a path with info.

        Args:
            path: Directory path to list.

        Returns:
            List of FileInfo objects.
        """
        try:
            # Use LIKE to match path prefix
            pattern = f"{path}%"
            # Include content in the query to calculate size without N+1 queries
            response = (
                self.client.table(self.table)
                .select("path, content, metadata, created_at, updated_at")
                .like("path", pattern)
                .execute()
            )

            files = []
            for row in response.data or []:
                # Calculate size from content in the same row (no extra query)
                content = row.get("content", "")
                size = len(content) if content else 0

                files.append(
                    FileInfo(
                        path=row["path"],
                        size=size,
                        created_at=row.get("created_at", ""),
                        updated_at=row.get("updated_at", ""),
                        metadata=row.get("metadata", {}),
                    )
                )

            return files

        except Exception as exc:
            logger.warning("supabase_ls_failed", path=path, error=str(exc))
            return []

    def glob_info(self, pattern: str, path: str = "/") -> List[FileInfo]:
        """Find files matching a glob pattern.

        Args:
            pattern: Glob pattern (e.g., "*.txt", "**/*.json").
            path: Base path to search from.

        Returns:
            List of matching FileInfo objects.
        """
        import fnmatch

        # Get all files under path
        all_files = self.ls_info(path)

        # Filter by pattern
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
        """Search for pattern in files.

        Args:
            pattern: Regex pattern to search for.
            path: Optional path prefix to limit search.
            context_lines: Lines of context before/after match.

        Returns:
            List of GrepMatch objects.
        """
        import re

        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error as exc:
            logger.warning("invalid_grep_pattern", pattern=pattern, error=str(exc))
            return []

        # Get files to search
        if path:
            files = self.ls_info(path)
        else:
            files = self.ls_info("/")

        matches = []
        for file_info in files:
            # Read full file content (unlimited lines) for grep to work correctly
            content = self._read_full_content(file_info.path)
            if not content:
                continue

            lines = content.split("\n")
            for idx, line in enumerate(lines):
                if regex.search(line):
                    # Get context
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

    def _read_full_content(self, file_path: str) -> Optional[str]:
        """Read full file content without line limits.

        Used internally for grep operations where we need all lines.

        Args:
            file_path: Path to the file.

        Returns:
            Full file content or None if not found.
        """
        try:
            response = (
                self.client.table(self.table)
                .select("content")
                .eq("path", file_path)
                .single()
                .execute()
            )

            if not response.data:
                return None

            return response.data.get("content", "") or ""

        except Exception as exc:
            logger.warning("supabase_read_full_failed", path=file_path, error=str(exc))
            return None

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        """Edit a file by replacing strings.

        Args:
            file_path: Path to the file.
            old_string: String to find.
            new_string: String to replace with.
            replace_all: If True, replace all occurrences.

        Returns:
            EditResult indicating success/failure and replacement count.
        """
        content = self.read(file_path, limit=100000)
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
                error=f"String not found in file: {old_string[:50]}...",
            )

        if replace_all:
            new_content = content.replace(old_string, new_string)
            replacements = content.count(old_string)
        else:
            new_content = content.replace(old_string, new_string, 1)
            replacements = 1

        result = self.write(file_path, new_content)
        if not result.success:
            return EditResult(
                success=False,
                replacements=0,
                error=result.error,
            )

        return EditResult(
            success=True,
            replacements=replacements,
        )

    def exists(self, file_path: str) -> bool:
        """Check if a file exists.

        Args:
            file_path: Path to check.

        Returns:
            True if file exists.
        """
        try:
            response = (
                self.client.table(self.table)
                .select("path")
                .eq("path", file_path)
                .single()
                .execute()
            )
            return response.data is not None
        except Exception:
            return False

    def list_paths(self, prefix: str = "/") -> List[str]:
        """List paths with the given prefix."""
        files = self.ls_info(prefix or "/")
        return [f.path for f in files if f.path.startswith(prefix)]
