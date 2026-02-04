"""Shared utilities for Agent Sparrow harness.

Following DeepAgents patterns for:
- Path normalization and validation
- Content extraction from messages
- Token estimation
- Search operations (grep, glob)

These utilities are extracted from multiple files to eliminate duplication
and provide a single source of truth.
"""

from __future__ import annotations

import fnmatch
import re
from typing import Any, Callable, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from langchain_core.messages import BaseMessage

# Sentinel value to indicate failed import (distinct from None)
# Used by lazy-loading patterns across middleware and stores
IMPORT_FAILED = object()


def normalize_directory_path(path: str) -> str:
    """Normalize path for proper directory matching.

    This prevents false positives like "/scratch" matching "/scratchpad"
    by ensuring directory paths end with a trailing slash.

    Args:
        path: Directory path to normalize.

    Returns:
        Normalized path with trailing slash (or "/" for root).

    Examples:
        >>> normalize_directory_path("/scratch")
        '/scratch/'
        >>> normalize_directory_path("/")
        '/'
        >>> normalize_directory_path("/memories/")
        '/memories/'
    """
    if path == "/":
        return "/"
    return path.rstrip("/") + "/"


def is_path_under_directory(file_path: str, directory_path: str) -> bool:
    """Check if file_path is under directory_path.

    Args:
        file_path: Full path to the file.
        directory_path: Directory to check against.

    Returns:
        True if file is in or under the directory.

    Examples:
        >>> is_path_under_directory("/scratch/foo.txt", "/scratch")
        True
        >>> is_path_under_directory("/scratchpad/foo.txt", "/scratch")
        False
    """
    normalized = normalize_directory_path(directory_path)
    return file_path == directory_path or file_path.startswith(normalized)


def extract_message_text(msg: "BaseMessage") -> str:
    """Extract text content from a LangChain message.

    Handles both string content and multimodal content lists
    (e.g., messages with images and text parts).

    Args:
        msg: LangChain message object.

    Returns:
        Extracted text content as a string.
    """
    content = getattr(msg, "content", "")

    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict):
                if part.get("type") == "text":
                    parts.append(part.get("text", ""))
            elif isinstance(part, str):
                parts.append(part)
        return " ".join(parts).strip()

    return str(content) if content else ""


def estimate_tokens(messages: List["BaseMessage"]) -> int:
    """Estimate token count using ~4 chars/token heuristic.

    This is a rough approximation for context window management.
    Image content is estimated at a fixed token count.

    Args:
        messages: List of LangChain messages.

    Returns:
        Estimated token count.
    """
    total_chars = 0
    image_token_estimate = 3060  # Approximate tokens for an image

    for msg in messages:
        content = getattr(msg, "content", "")

        if isinstance(content, str):
            total_chars += len(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict):
                    part_type = part.get("type", "")
                    if part_type == "text":
                        total_chars += len(part.get("text", ""))
                    elif part_type == "image_url":
                        total_chars += image_token_estimate * 4  # Convert back to chars
                else:
                    total_chars += len(str(part))
        else:
            total_chars += len(str(content))

    return total_chars // 4


def glob_match_files(
    files: List[Any],
    pattern: str,
    base_path: str = "/",
    path_extractor: Optional[Callable[[Any], str]] = None,
) -> List[Any]:
    """Filter files matching a glob pattern.

    Args:
        files: List of file objects to filter.
        pattern: Glob pattern (e.g., "*.txt", "**/*.json").
        base_path: Base path for relative matching.
        path_extractor: Function to extract path from file object.
            Defaults to accessing .path attribute.

    Returns:
        List of matching file objects.
    """
    if path_extractor is None:

        def path_extractor(f: Any) -> str:
            return getattr(f, "path", str(f))

    matched = []
    for file_info in files:
        file_path = path_extractor(file_info)
        relative_path = file_path

        if base_path and file_path.startswith(base_path):
            relative_path = file_path[len(base_path) :].lstrip("/")

        if fnmatch.fnmatch(relative_path, pattern):
            matched.append(file_info)

    return matched


def grep_content(
    content: str,
    pattern: str,
    file_path: str,
    context_lines: int = 2,
    match_factory: Optional[Callable[..., Any]] = None,
) -> List[Any]:
    """Search content for regex pattern and return matches with context.

    Args:
        content: Text content to search.
        pattern: Regex pattern to match.
        file_path: Path for match attribution.
        context_lines: Lines of context before/after each match.
        match_factory: Factory function to create match objects.
            Should accept (path, line_number, content, context_before, context_after).
            If None, returns dicts.

    Returns:
        List of match objects (type depends on match_factory).
    """
    context_lines = max(0, context_lines)

    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error:
        return []

    lines = content.split("\n")
    matches = []

    for idx, line in enumerate(lines):
        if regex.search(line):
            start = max(0, idx - context_lines)
            end = min(len(lines), idx + context_lines + 1)

            match_data = {
                "path": file_path,
                "line_number": idx + 1,
                "content": line,
                "context_before": lines[start:idx],
                "context_after": lines[idx + 1 : end],
            }

            if match_factory:
                matches.append(
                    match_factory(
                        path=file_path,
                        line_number=idx + 1,
                        content=line,
                        context_before=lines[start:idx],
                        context_after=lines[idx + 1 : end],
                    )
                )
            else:
                matches.append(match_data)

    return matches


def truncate_content(
    content: str,
    max_chars: int,
    suffix: str = "... [truncated]",
) -> str:
    """Truncate content to maximum character length.

    Args:
        content: Content to truncate.
        max_chars: Maximum characters allowed.
        suffix: Suffix to append when truncating.

    Returns:
        Original content or truncated with suffix.
    """
    if len(content) <= max_chars:
        return content

    truncate_at = max(0, max_chars - len(suffix))
    suffix_to_use = suffix if truncate_at > 0 else ""
    return content[:truncate_at] + suffix_to_use
