"""Checkpointer module for LangGraph state persistence.

DEPRECATED: This module has been relocated to app.agents.harness.persistence.
These re-exports are maintained for backward compatibility.
Import from app.agents.harness.persistence for new code.
"""

import warnings

# Backward-compatible re-exports
from app.agents.harness.persistence import (
    CheckpointerConfig,
    CheckpointResult,
    SupabaseCheckpointer,
    ThreadManager,
)

__all__ = [
    "CheckpointerConfig",
    "CheckpointResult",
    "SupabaseCheckpointer",
    "ThreadManager",
]


def _emit_deprecation_warning() -> None:
    import os

    if os.environ.get("SPARROW_ENV", "").lower() != "production":
        warnings.warn(
            "app.agents.checkpointer is deprecated. "
            "Import from app.agents.harness.persistence instead.",
            DeprecationWarning,
            stacklevel=3,
        )


_emit_deprecation_warning()
