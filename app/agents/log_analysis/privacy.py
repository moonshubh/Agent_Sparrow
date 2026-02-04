"""Compatibility shim for log analysis privacy definitions.

Canonical import path: app.agents.log_analysis.privacy
"""

from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.agents.log_analysis.log_analysis_agent.privacy import (  # type: ignore[import-not-found]
        RedactionLevel as RedactionLevel,
    )
else:
    try:
        from app.agents.log_analysis.log_analysis_agent.privacy import (  # type: ignore[import-not-found]
            RedactionLevel as RedactionLevel,
        )
    except Exception:  # pragma: no cover

        class RedactionLevel(str, Enum):
            """Fallback redaction levels when the upstream module is unavailable."""

            LOW = "low"
            MEDIUM = "medium"
            HIGH = "high"


__all__ = ["RedactionLevel"]
