"""Log analysis agent compatibility layer.

Legacy agent router removed - use unified agent's log_diagnoser_tool instead.
This module provides access to:
- simplified_agent: Simplified log analysis (used by unified agent)
- simplified_schemas: Schema definitions
- privacy: Log sanitization utilities
- security: Security validation
- comprehensive_agent: Full-featured log analysis (used by secure endpoints)
"""

try:
    from app.agents.log_analysis.log_analysis_agent.simplified_schemas import (
        SimplifiedLogAnalysisOutput,  # noqa: F401
        SimplifiedAgentState,  # noqa: F401
    )
    # Re-export sanitizer for SSE defense-in-depth usage
    from app.agents.log_analysis.log_analysis_agent.privacy import (
        LogSanitizer,  # noqa: F401
    )
except Exception:  # pragma: no cover
    pass

__all__ = [
    "SimplifiedLogAnalysisOutput",
    "SimplifiedAgentState",
    "LogSanitizer",
]
