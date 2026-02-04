"""Row-parsing utilities for database result normalization.

These utilities handle the polymorphic nature of database rows
from various sources (raw tuples, dicts, ORM objects, mocks).
"""

from __future__ import annotations

import json
import logging
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def decode_json(value: Any, default: T) -> T | dict[str, Any] | list[Any]:
    """Decode a JSON string or return the value if already decoded.

    Args:
        value: Raw value that may be JSON string, dict, list, or None.
        default: Fallback value when decoding fails or value is None.

    Returns:
        Decoded value or default.
    """
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            logger.warning("Failed to decode JSON payload: %.100s", value)
            return default
    return default


def ensure_dict(value: Any) -> dict[str, Any]:
    """Coerce a value to a dictionary.

    Handles JSON strings, dict-like objects, and gracefully degrades
    to an empty dict for unrecognized types.

    Args:
        value: Raw value to convert.

    Returns:
        Dictionary representation of the value.
    """
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            result = json.loads(value)
            return result if isinstance(result, dict) else {}
        except json.JSONDecodeError:
            logger.warning("Failed to decode JSON field: %.100s", value)
            return {}
    # Handle dict-like objects (e.g., database rows with .items())
    if hasattr(value, "items"):
        try:
            return dict(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return {}
    return {}


def get_row_value(row: Any, key: str, index: int) -> Any:
    """Extract a value from a polymorphic database row.

    Handles dict rows, named tuple rows, and positional tuple rows.

    Args:
        row: Database row (dict, tuple, or object with attributes).
        key: Column name for dict/attribute access.
        index: Positional index for tuple access.

    Returns:
        Extracted value or None if row is None.
    """
    if row is None:
        return None
    if isinstance(row, dict):
        return row.get(key)
    if hasattr(row, key):
        return getattr(row, key)
    try:
        return row[index]
    except (IndexError, TypeError, KeyError):
        return None


def rows_to_dicts(cursor: Any, rows: list[Any]) -> list[dict[str, Any]]:
    """Convert database rows to list of dictionaries.

    Handles various row formats (dicts, tuples, named tuples) and
    automatically decodes JSON fields named 'state' or 'metadata'.

    Args:
        cursor: Database cursor with optional description attribute.
        rows: List of database rows.

    Returns:
        List of normalized dictionaries.
    """
    if not rows:
        return []

    columns: list[str] = []
    if hasattr(cursor, "description") and cursor.description:
        columns = [getattr(col, "name", col[0]) for col in cursor.description]

    results: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, dict):
            item = dict(row)
        elif columns:
            item = {
                columns[idx]: row[idx] for idx in range(min(len(columns), len(row)))
            }
        else:
            item = {"value": row}

        # Decode JSON fields (applied consistently for all row types)
        if "state" in item:
            item["state"] = decode_json(item["state"], {})
        if "metadata" in item:
            item["metadata"] = decode_json(item["metadata"], {})
        results.append(item)

    return results
