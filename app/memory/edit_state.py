"""Shared helpers for memory edited-state and cleanup protection logic."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

EDITOR_METADATA_KEYS: tuple[str, ...] = (
    "edited_by_email",
    "updated_by_email",
    "editor_email",
    "edited_by",
    "updated_by",
    "edited_by_name",
    "updated_by_name",
)

# Safety guard threshold selected by product requirement.
CLEANUP_PROTECTED_MIN_CONFIDENCE = 0.6


def _metadata_text(metadata: Any, key: str) -> str:
    if not isinstance(metadata, dict):
        return ""
    value = metadata.get(key)
    if isinstance(value, str):
        return value.strip()
    return ""


def memory_has_editor_identity(memory_row: dict[str, Any]) -> bool:
    reviewed_by = memory_row.get("reviewed_by")
    if isinstance(reviewed_by, str) and reviewed_by.strip():
        return True

    metadata = memory_row.get("metadata")
    return any(_metadata_text(metadata, key) for key in EDITOR_METADATA_KEYS)


def _coerce_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def is_memory_edited(memory_row: dict[str, Any]) -> bool:
    """
    Canonical edited-memory rule shared by API, service, and cleanup tooling.

    A memory is considered edited when:
    1) `updated_at > created_at`, and
    2) editor identity is present (`reviewed_by` or known metadata keys).
    """
    created_dt = _coerce_datetime(memory_row.get("created_at"))
    updated_dt = _coerce_datetime(memory_row.get("updated_at"))
    if created_dt is None or updated_dt is None:
        return False
    if updated_dt <= created_dt:
        return False
    return memory_has_editor_identity(memory_row)


def is_cleanup_protected_memory(
    memory_row: dict[str, Any],
    *,
    min_confidence: float = CLEANUP_PROTECTED_MIN_CONFIDENCE,
) -> bool:
    """
    Cleanup guard for critical memories.

    Protected class:
    - edited memory
    - confidence >= min_confidence
    """
    try:
        confidence = float(memory_row.get("confidence_score") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    return is_memory_edited(memory_row) and confidence >= float(min_confidence)


def partition_cleanup_candidates(
    memories: Iterable[dict[str, Any]],
    *,
    min_confidence: float = CLEANUP_PROTECTED_MIN_CONFIDENCE,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split cleanup candidates into (`deletable`, `protected`)."""
    deletable: list[dict[str, Any]] = []
    protected: list[dict[str, Any]] = []
    for memory_row in memories:
        if is_cleanup_protected_memory(
            memory_row, min_confidence=min_confidence
        ):
            protected.append(memory_row)
        else:
            deletable.append(memory_row)
    return deletable, protected

