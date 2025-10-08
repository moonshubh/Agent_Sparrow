"""Compatibility shim for comprehensive log analysis agent.

Canonical import path: app.agents.log_analysis.comprehensive_agent
"""

try:
    from app.agents_v2.log_analysis_agent.comprehensive_agent import (
        LogAnalysisAgent,  # noqa: F401
    )
except Exception:  # pragma: no cover
    pass

__all__ = ["LogAnalysisAgent"]
