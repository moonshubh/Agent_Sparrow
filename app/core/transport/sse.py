"""Unified SSE helpers (Phase 1 skeleton).

Minimal helpers to format Server-Sent Events consistently.
Safe to adopt incrementally without behavior changes.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any


def _sanitize_comment_text(comment: str) -> str:
    """Ensure heartbeat comments are single-line to avoid breaking SSE frames."""
    return comment.replace("\n", " ").strip() or "keep-alive"

def _default_serializer(obj: Any):
    if isinstance(obj, datetime):
        return obj.isoformat()
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "dict"):
        return obj.dict()
    return str(obj)

def format_sse_data(payload: Any) -> str:
    """Return a properly formatted SSE data line for a JSON-serializable payload."""
    try:
        data = json.dumps(payload, ensure_ascii=False, default=_default_serializer)
    except Exception:
        data = json.dumps({"type": "error", "errorText": "serialization_failed"})
    return f"data: {data}\n\n"


def format_sse_comment(comment: str = "keep-alive") -> str:
    """Return a correctly formatted SSE comment frame (useful for heartbeat pings)."""
    return f": {_sanitize_comment_text(comment)}\n\n"
