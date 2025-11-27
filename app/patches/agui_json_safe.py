"""
Runtime monkey patch for ag_ui_langgraph.utils.make_json_safe to handle circular references.

The original make_json_safe function recursively processes objects but doesn't track
seen objects, causing RecursionError when circular references exist in the state
(e.g., LangChain messages with complex additional_kwargs).

This patch adds a seen-object tracking mechanism to prevent infinite recursion.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Set

_PATCH_FLAG = "_agui_json_safe_patch_applied"
_PATCH_LOCK = threading.Lock()
logger = logging.getLogger(__name__)


def make_json_safe_with_cycle_detection(value: Any, _seen: Set[int] | None = None) -> Any:
    """
    Recursively convert a value into a JSON-serializable structure with circular reference detection.

    - Handles Pydantic models via `model_dump`.
    - Handles LangChain messages via `to_dict`.
    - Recursively walks dicts, lists, and tuples.
    - Tracks seen object IDs to prevent infinite recursion on circular references.
    - For arbitrary objects, falls back to `__dict__` if available, else `repr()`.
    """
    if _seen is None:
        _seen = set()

    # Check for circular reference using object id
    obj_id = id(value)
    if obj_id in _seen:
        return f"<circular ref: {type(value).__name__}>"

    # Don't track primitive types (they can't have circular refs)
    is_primitive = isinstance(value, (str, int, float, bool, type(None)))

    if not is_primitive:
        _seen = _seen | {obj_id}  # Create new set to avoid mutation issues

    # Pydantic models
    if hasattr(value, "model_dump"):
        try:
            return make_json_safe_with_cycle_detection(
                value.model_dump(by_alias=True, exclude_none=True),
                _seen
            )
        except Exception:
            pass

    # LangChain messages or other chat message types
    try:
        from langchain_core.messages import BaseMessage  # type: ignore
        if isinstance(value, BaseMessage):
            try:
                return make_json_safe_with_cycle_detection(value.to_dict(), _seen)
            except Exception:
                # Fallback: serialize minimal shape
                return {
                    "__type__": type(value).__name__,
                    "role": getattr(value, "role", None),
                    "content": getattr(value, "content", None),
                    "additional_kwargs": getattr(value, "additional_kwargs", None),
                }
    except Exception:
        # If langchain_core not available, continue with other handlers
        pass

    # LangChain-style objects
    if hasattr(value, "to_dict"):
        try:
            return make_json_safe_with_cycle_detection(value.to_dict(), _seen)
        except Exception:
            pass

    # Dict
    if isinstance(value, dict):
        return {
            key: make_json_safe_with_cycle_detection(sub_value, _seen)
            for key, sub_value in value.items()
        }

    # List / tuple
    if isinstance(value, (list, tuple)):
        return [make_json_safe_with_cycle_detection(sub_value, _seen) for sub_value in value]

    # Already JSON safe
    if is_primitive:
        return value

    # Arbitrary object: try __dict__ first, fallback to repr
    if hasattr(value, "__dict__"):
        try:
            sanitized = make_json_safe_with_cycle_detection(value.__dict__, _seen)
            if isinstance(sanitized, dict):
                return {"__type__": type(value).__name__, **sanitized}
            # Fallback when __dict__ yields a non-mapping (avoid TypeError when splatting)
            return {"__type__": type(value).__name__, "__value__": sanitized}
        except Exception:
            # Best-effort fallback to repr to keep the stream alive
            return repr(value)

    return repr(value)


def apply_patch() -> None:
    """Idempotent patch application for make_json_safe."""
    try:
        import ag_ui_langgraph.utils as agui_utils
    except ImportError:
        logger.warning("ag_ui_langgraph.utils not found - skipping make_json_safe patch")
        return

    if getattr(agui_utils, _PATCH_FLAG, False):
        return

    with _PATCH_LOCK:
        if getattr(agui_utils, _PATCH_FLAG, False):
            return
        try:
            # Store original for reference
            agui_utils._original_make_json_safe = agui_utils.make_json_safe
            # Replace with patched version
            agui_utils.make_json_safe = make_json_safe_with_cycle_detection
        except Exception:
            logger.exception("Failed to apply AG-UI make_json_safe patch")
            raise
        setattr(agui_utils, _PATCH_FLAG, True)
        logger.info("AG-UI make_json_safe circular reference patch applied")


# Apply eagerly on import
apply_patch()
