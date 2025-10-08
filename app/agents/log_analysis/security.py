"""Compatibility shim for log analysis security enums/types.

Canonical import path: app.agents.log_analysis.security
"""

try:
    from app.agents.log_analysis.log_analysis_agent.security import (
        ValidationStatus,  # noqa: F401
        ThreatLevel,  # noqa: F401
    )
except Exception:  # pragma: no cover
    pass

__all__ = ["ValidationStatus", "ThreatLevel"]
