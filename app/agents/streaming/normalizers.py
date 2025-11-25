"""Normalizers for transforming raw tool outputs into typed event structures.

Extracted from agent_sparrow.py to provide a clean, testable interface for
normalizing various data formats emitted by tools and middleware.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from loguru import logger


def normalize_todos(
    raw: Any,
    root_operation_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Normalize various todo input formats to consistent structure.

    Accepts several shapes commonly emitted by tools/middleware:
    - List[dict]:     [{"title": ..., "status": ...}, ...]
    - Dict with list: {"todos": [...]} or {"items": [...]} or {"steps": [...]} etc.
    - Single dict:    {"title": ..., "status": ...} (treated as one-item list)
    - JSON string:    '{"todos": [...]}' or '[{...}]'
    - Noisy string:   'content={"todos": [...]}' (extracted from wrapper)

    Args:
        raw: The raw todo data in any supported format.
        root_operation_id: Optional prefix for generating todo IDs.

    Returns:
        List of normalized todo dicts with keys: id, title, status, metadata
    """
    normalized: List[Dict[str, Any]] = []
    prefix = root_operation_id or "todo"

    # Handle JSON-encoded payloads
    if isinstance(raw, str):
        parsed = _parse_json_string(raw)
        if parsed is not None:
            return normalize_todos(parsed, root_operation_id)
        # If parsing failed completely, return empty
        return normalized

    # Unwrap common container shapes emitted by tools/middleware
    items = _unwrap_container(raw)

    if not isinstance(items, list):
        return normalized

    # Normalize each item
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue

        normalized_item = _normalize_single_todo(item, idx, prefix)
        if normalized_item:
            normalized.append(normalized_item)

    return normalized


def _parse_json_string(raw: str) -> Optional[Any]:
    """Attempt to parse JSON from a string, handling various formats.

    Handles:
    - Clean JSON: '{"todos": [...]}' or '[...]'
    - Noisy JSON: 'content={"todos": [...]}' or 'ToolResult {...}'
    """
    trimmed = raw.strip()

    # Try direct JSON parse first
    if trimmed.startswith(("{", "[")) and trimmed.endswith(("}", "]")):
        try:
            return json.loads(trimmed)
        except json.JSONDecodeError:
            pass

    # Try to extract JSON from noisy strings
    json_candidate = _extract_json_from_string(trimmed)
    if json_candidate:
        try:
            return json.loads(json_candidate)
        except json.JSONDecodeError:
            pass

        # Fall back to ast.literal_eval for Python dict strings
        try:
            import ast
            return ast.literal_eval(json_candidate)
        except (ValueError, SyntaxError):
            pass

    return None


def _extract_json_from_string(text: str) -> Optional[str]:
    """Extract JSON object/array from a potentially noisy string."""
    brace_idx = text.find("{")
    bracket_idx = text.find("[")
    candidates = [i for i in (brace_idx, bracket_idx) if i >= 0]

    if not candidates:
        return None

    start_idx = min(candidates)
    return text[start_idx:]


def _unwrap_container(raw: Any) -> Any:
    """Unwrap common container shapes to get the items list."""
    # Handle non-dict inputs
    if not isinstance(raw, dict):
        if isinstance(raw, list):
            return raw
        # Non-list, non-dict - return empty list (can't unwrap)
        return []

    # raw is a dict - look for common container keys
    container_keys = ("todos", "items", "steps", "data", "value", "results")
    for key in container_keys:
        value = raw.get(key)
        if isinstance(value, list):
            return value

    # If no container key found, treat dict as single item
    return [raw]


def _normalize_single_todo(
    item: Dict[str, Any],
    idx: int,
    prefix: str,
) -> Optional[Dict[str, Any]]:
    """Normalize a single todo item dict."""
    # Extract title from various possible keys
    title = str(
        item.get("title")
        or item.get("content")
        or item.get("description")
        or item.get("name")
        or f"Step {idx + 1}"
    )

    # Normalize status
    raw_status = str(item.get("status") or "pending").lower()
    status = _normalize_status(raw_status)

    # Generate or use existing ID
    todo_id = str(item.get("id") or f"{prefix}-todo-{idx + 1}")

    # Preserve any additional metadata - create a shallow copy to avoid mutating caller's dict
    original_metadata = item.get("metadata") or {}
    metadata = dict(original_metadata)  # Shallow copy

    # Copy any extra fields as metadata
    known_keys = {"id", "title", "content", "description", "name", "status", "metadata"}
    for key, value in item.items():
        if key not in known_keys and value is not None:
            metadata[key] = value

    return {
        "id": todo_id,
        "title": title,
        "status": status,
        "metadata": metadata,
    }


def _normalize_status(raw: str) -> str:
    """Normalize status string to valid todo status."""
    status_map = {
        "pending": "pending",
        "todo": "pending",
        "not_started": "pending",
        "in_progress": "in_progress",
        "running": "in_progress",
        "active": "in_progress",
        "working": "in_progress",
        "done": "done",
        "completed": "done",
        "complete": "done",
        "finished": "done",
        "success": "done",
    }
    return status_map.get(raw.lower(), "pending")


def normalize_tool_output_preview(output: Any, max_length: int = 1000) -> str:
    """Create a preview string from tool output for timeline metadata."""
    if output is None:
        return ""

    if isinstance(output, str):
        return output[:max_length]

    try:
        json_str = json.dumps(output, ensure_ascii=False, default=str)
        return json_str[:max_length]
    except Exception:
        return str(output)[:max_length]


def extract_grounding_results(output: Any) -> Optional[List[Dict[str, Any]]]:
    """Extract results list from grounding search output."""
    if not isinstance(output, dict):
        return None

    results = output.get("results") or output.get("items")
    if isinstance(results, list):
        return results

    return None


def extract_snippet_texts(results: List[Dict[str, Any]]) -> List[str]:
    """Extract snippet/content text from grounding results."""
    texts = []
    for item in results:
        if isinstance(item, dict):
            text = str(item.get("snippet") or item.get("content") or item)
        else:
            text = str(item)
        texts.append(text)
    return texts
