"""Compatibility shim for log analysis privacy definitions.

Canonical import path: app.agents.log_analysis.privacy
"""

try:
    from app.agents_v2.log_analysis_agent.privacy import (
        RedactionLevel,  # noqa: F401
    )
except Exception:  # pragma: no cover
    pass

__all__ = ["RedactionLevel"]
