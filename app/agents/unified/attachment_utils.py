"""Shared attachment helpers for MIME/text detection."""

from __future__ import annotations

from typing import Optional

TEXT_MIME_TYPES = {
    "text/plain",
    "text/csv",
    "text/html",
    "text/markdown",
    "text/xml",
    "application/json",
    "application/xml",
    "application/javascript",
}

# File extensions that indicate text content even with application/octet-stream
TEXT_EXTENSIONS = (".log", ".txt", ".csv", ".json", ".xml", ".md", ".yaml", ".yml")


def is_text_mime(mime: Optional[str], filename: Optional[str] = None) -> bool:
    """Check if MIME or filename indicates text content."""
    if mime:
        mime_lower = str(mime).lower()
        if mime_lower.startswith("text/"):
            return True
        if mime_lower in TEXT_MIME_TYPES:
            return True
        if mime_lower == "application/octet-stream" and filename:
            name_lower = str(filename).lower()
            if any(name_lower.endswith(ext) for ext in TEXT_EXTENSIONS):
                return True
    return False


__all__ = ["is_text_mime", "TEXT_MIME_TYPES", "TEXT_EXTENSIONS"]
