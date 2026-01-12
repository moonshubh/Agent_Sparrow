"""Utilities for generating human-readable memory titles.

The Memory UI benefits from short, scan-friendly titles that can be used in
lists and cluster previews. Titles are stored in `memories.metadata.title`.
"""

from __future__ import annotations

import re
from typing import Any, Mapping


_WHITESPACE_RE = re.compile(r"\s+")
_LEADING_BULLET_RE = re.compile(r"^[-*•]+\s*")
_LABEL_LINE_PREFIXES: tuple[str, ...] = (
    "title:",
    "problem:",
    "issue:",
    "error:",
    "summary:",
    "solution:",
)


def derive_memory_title(content: str, *, max_length: int = 80) -> str:
    """Derive a short title from memory content."""

    raw = (content or "").strip()
    if not raw:
        return "Untitled memory"

    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if not lines:
        return "Untitled memory"

    preferred: str | None = None
    for line in lines[:6]:
        lowered = line.lower()
        for prefix in _LABEL_LINE_PREFIXES:
            if lowered.startswith(prefix):
                preferred = line[len(prefix) :].strip(" -\t")
                break
        if preferred:
            break

    candidate = preferred or lines[0]
    candidate = _LEADING_BULLET_RE.sub("", candidate).strip()
    candidate = _WHITESPACE_RE.sub(" ", candidate).strip()

    if not candidate:
        candidate = _WHITESPACE_RE.sub(" ", raw).strip()

    if len(candidate) <= max_length:
        return candidate

    trimmed = candidate[: max_length + 1].rstrip()
    # Prefer to cut at a word boundary when possible.
    cut = trimmed.rfind(" ")
    if cut >= max(12, max_length - 24):
        trimmed = trimmed[:cut].rstrip()
    return f"{trimmed}…"


def ensure_memory_title(
    metadata: Mapping[str, Any] | None,
    *,
    content: str,
    max_length: int = 80,
) -> dict[str, Any]:
    """Return a metadata dict with a non-empty `title` field."""

    base: dict[str, Any] = dict(metadata or {})
    existing = base.get("title")
    if isinstance(existing, str) and existing.strip():
        return base

    base["title"] = derive_memory_title(content, max_length=max_length)
    return base
