"""Log analysis agent compatibility layer (Phase 1).

New canonical import path: app.agents.log_analysis
Temporarily re-exports from app.agents.log_analysis.log_analysis_agent.*
"""

try:
    from app.agents.log_analysis.log_analysis_agent.agent import run_log_analysis_agent  # noqa: F401
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
    "run_log_analysis_agent",
    "SimplifiedLogAnalysisOutput",
    "SimplifiedAgentState",
    "LogSanitizer",
]
