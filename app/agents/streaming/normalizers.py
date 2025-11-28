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


# --- Evidence card builders ---

from datetime import datetime
from urllib.parse import urlparse


def _shorten(text: str, width: int = 220) -> str:
    """Shorten text to specified width with ellipsis."""
    if not isinstance(text, str):
        text = str(text)
    text = " ".join(text.split())  # collapse whitespace
    return (text[: width - 1] + "…") if len(text) > width else text


def _host(u: Optional[str]) -> Optional[str]:
    """Extract hostname from URL."""
    if not u:
        return None
    try:
        return urlparse(u).netloc or None
    except Exception:
        return None


def _coerce_entries(data: Any) -> List[Dict[str, Any]]:
    """Coerce various data shapes to a list of entry dicts."""
    # Accept {results|items|documents|entries|data}: [...]
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for k in ("results", "items", "documents", "entries", "data"):
            v = data.get(k)
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
        # single flat dict as one entry
        if all(not isinstance(v, (dict, list)) for v in data.values()):
            return [data]
        # nested dicts
        return [v for v in data.values() if isinstance(v, dict)]
    return []


def _infer_type(tool_name: str, output: Any) -> str:
    """Infer card type from tool name."""
    name = (tool_name or "").lower()
    if "ground" in name or "web" in name or "search" in name:
        return "research"
    if "kb" in name or "knowledge" in name or "vector" in name or "rag" in name:
        return "knowledge"
    if "log" in name or "trace" in name or "observe" in name or "monitor" in name:
        return "log_analysis"
    return "grounding" if isinstance(output, dict) and output.get("results") else "knowledge"


def _score(v: Any) -> Optional[int]:
    """Normalize score to 0-100 int."""
    try:
        f = float(v)
        # normalize 0-1 to 0-100 if needed
        if 0.0 <= f <= 1.0:
            f *= 100.0
        return max(0, min(100, int(round(f))))
    except Exception:
        return None


def _to_card(
    entry: Dict[str, Any],
    card_type: str,
    *,
    default_title: str,
    fallback_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Convert a single entry dict to an evidence card."""
    title = (
        entry.get("title")
        or entry.get("name")
        or entry.get("id")
        or default_title
    )
    url = entry.get("url") or entry.get("link") or fallback_url
    source = entry.get("source") or entry.get("path") or _host(url)
    snippet = (
        entry.get("snippet")
        or entry.get("summary")
        or entry.get("content")
        or entry.get("text")
        or ""
    )
    snippet = _shorten(str(snippet)) if snippet else ""
    rel = (
        _score(entry.get("relevance"))
        or _score(entry.get("score"))
        or _score(entry.get("rank"))
    )
    conf = _score(entry.get("confidence"))
    ts = entry.get("published_at") or entry.get("date") or entry.get("updated_at") or None
    if isinstance(ts, (int, float)):
        try:
            ts = datetime.utcfromtimestamp(ts).isoformat() + "Z"
        except Exception:
            ts = None

    keep_keys = (
        "host", "collection", "path", "doctype", "author", "tags", "severity",
        "count", "window", "lang", "provider"
    )
    metadata: Dict[str, Any] = {}
    if url:
        metadata["host"] = _host(url)
    for k in keep_keys:
        if k in entry and entry[k] is not None:
            metadata[k] = entry[k]
    for k in ("errors", "warnings", "info", "total"):
        if k in entry and isinstance(entry[k], (int, float)):
            metadata[k] = entry[k]

    return {
        "type": card_type,
        "title": str(title),
        "source": source,
        "url": url,
        "snippet": snippet or _shorten(str(entry)[:500]),
        "fullContent": None,
        "relevanceScore": rel,
        "confidence": conf,
        "metadata": metadata or None,
        "timestamp": ts,
        "status": "success",
    }


def build_tool_evidence_cards(
    output: Any,
    tool_name: str,
    *,
    user_query: Optional[str] = None,
    max_items: int = 3,
) -> List[Dict[str, Any]]:
    """Normalize raw tool output into a small list of 'evidence cards' the UI can render.

    Args:
        output: Raw tool output in any format.
        tool_name: Name of the tool that produced the output.
        user_query: Optional user query for context.
        max_items: Maximum number of cards to return.

    Returns:
        List of evidence card dicts with keys: type, title, source, url, snippet,
        fullContent, relevanceScore, confidence, metadata, timestamp, status.
    """
    card_type = _infer_type(tool_name, output)

    # Try to parse JSON-like strings to get real entries/cards
    if isinstance(output, str):
        parsed_str: Any = None
        trimmed = output.strip()
        if trimmed.startswith(("content=", "data=")):
            trimmed = trimmed.split("=", 1)[1].strip()
        if (trimmed.startswith("{") and trimmed.endswith("}")) or (trimmed.startswith("[") and trimmed.endswith("]")):
            try:
                parsed_str = json.loads(trimmed)
            except Exception:
                # Try a looser parse (handles single quotes from some tool outputs)
                try:
                    import ast
                    parsed_str = ast.literal_eval(trimmed)
                except Exception:
                    parsed_str = None

        if parsed_str is not None:
            entries = _coerce_entries(parsed_str)
            if entries:
                cards = []
                for idx, e in enumerate(entries[:max_items], start=1):
                    cards.append(_to_card(e, card_type, default_title=f"Result {idx}"))
                return cards
            # If no entries but we have a query, produce a friendly summary card
            if isinstance(parsed_str, dict):
                query_val = parsed_str.get("query") or parsed_str.get("q") or None
                return [{
                    "type": card_type,
                    "title": tool_name,
                    "source": None,
                    "url": None,
                    "snippet": _shorten(f"Search results for '{query_val}'" if query_val else output, 220),
                    "fullContent": output,
                    "relevanceScore": None,
                    "confidence": None,
                    "metadata": None,
                    "timestamp": None,
                    "status": "success",
                }]

        return [{
            "type": card_type,
            "title": tool_name,
            "source": None,
            "url": None,
            "snippet": _shorten(output, 220),
            "fullContent": output,
            "relevanceScore": None,
            "confidence": None,
            "metadata": None,
            "timestamp": None,
            "status": "success",
        }]

    entries = _coerce_entries(output)
    if entries:
        cards = []
        for idx, e in enumerate(entries[:max_items], start=1):
            cards.append(_to_card(e, card_type, default_title=f"Result {idx}"))
        return cards

    try:
        preview = json.dumps(output, ensure_ascii=False, default=str)
    except Exception:
        preview = str(output)
    return [{
        "type": card_type,
        "title": tool_name,
        "source": None,
        "url": None,
        "snippet": _shorten(preview, 500),
        "fullContent": None,
        "relevanceScore": None,
        "confidence": None,
        "metadata": None,
        "timestamp": None,
        "status": "success",
    }]
