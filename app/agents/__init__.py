"""
Compatibility package for the agents layer.

Phase 1 re-organization: expose stable imports while the codebase migrates
from app.agents.* to app.agents.*. No behavior changes.
"""

# Legacy agent exports removed - all endpoints now use unified agent
# Keeping simplified schemas for backward compatibility with unified agent tools
try:
    from app.agents.log_analysis.log_analysis_agent.simplified_schemas import (
        SimplifiedLogAnalysisOutput as SimplifiedLogAnalysisOutput,  # noqa: F401
        SimplifiedAgentState as SimplifiedAgentState,  # noqa: F401
    )
except Exception:  # pragma: no cover
    pass

# Orchestration - replaced by unified agent system
try:
    from app.agents.orchestration.orchestration.graph import (
        app as agent_graph,
    )  # noqa: F401
    from app.agents.orchestration.orchestration.state import (
        GraphState as GraphState,
    )  # noqa: F401
except Exception:  # pragma: no cover
    # Do not raise at import time: this package is imported in many contexts
    # (tests, tooling) where agent dependencies may be intentionally absent.
    import logging

    logging.error("Failed to import agent_graph", exc_info=True)
    agent_graph = None  # type: ignore[assignment]
    GraphState = None  # type: ignore[misc,assignment]

__all__ = [
    # Legacy exports removed - use unified agent via app/agents/unified/
    "SimplifiedLogAnalysisOutput",
    "SimplifiedAgentState",
    "agent_graph",
    "GraphState",
]
