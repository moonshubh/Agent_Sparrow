"""Agent execution state tracking infrastructure.

DEPRECATED: This module has been relocated to app.agents.harness.observability.
These re-exports are maintained for backward compatibility.
Import from app.agents.harness.observability for new code.
"""

import warnings

# Backward-compatible re-exports
from app.agents.harness.observability import (
    AgentLoopState,
    LoopStateTracker,
    StateTransition,
    VALID_TRANSITIONS,
    create_loop_tracker,
    get_or_create_tracker,
    clear_tracker,
)

__all__ = [
    "AgentLoopState",
    "LoopStateTracker",
    "StateTransition",
    "VALID_TRANSITIONS",
    "create_loop_tracker",
    "get_or_create_tracker",
    "clear_tracker",
]


def _emit_deprecation_warning() -> None:
    import os

    if os.environ.get("SPARROW_ENV", "").lower() != "production":
        warnings.warn(
            "app.agents.execution is deprecated. "
            "Import from app.agents.harness.observability instead.",
            DeprecationWarning,
            stacklevel=3,
        )


_emit_deprecation_warning()
