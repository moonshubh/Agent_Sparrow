"""
Compatibility package for the agents layer.

Phase 1 re-organization: expose stable imports while the codebase migrates
from app.agents.* to app.agents.*. No behavior changes.
"""

# Primary agent
try:
    from app.agents.primary.primary_agent.agent import run_primary_agent as run_primary_agent  # noqa: F401
    from app.agents.primary.primary_agent.schemas import PrimaryAgentState as PrimaryAgentState  # noqa: F401
except Exception:  # pragma: no cover
    pass

# Log analysis agent
try:
    from app.agents.log_analysis.log_analysis_agent.agent import run_log_analysis_agent as run_log_analysis_agent  # noqa: F401
    from app.agents.log_analysis.log_analysis_agent.simplified_schemas import (
        SimplifiedLogAnalysisOutput as SimplifiedLogAnalysisOutput,  # noqa: F401
        SimplifiedAgentState as SimplifiedAgentState,  # noqa: F401
    )
except Exception:  # pragma: no cover
    pass

# Research agent
try:
    from app.agents.research.research_agent.research_agent import (
        get_research_graph as get_research_graph,  # noqa: F401
        ResearchState as ResearchState,  # noqa: F401
    )
except Exception:  # pragma: no cover
    pass

# Orchestration - replaced by unified agent system
try:
    from app.agents.orchestration.orchestration.graph import app as agent_graph  # noqa: F401
    from app.agents.orchestration.orchestration.state import GraphState as GraphState  # noqa: F401
except Exception:  # pragma: no cover
    pass

__all__ = [
    "run_primary_agent",
    "PrimaryAgentState",
    "run_log_analysis_agent",
    "SimplifiedLogAnalysisOutput",
    "SimplifiedAgentState",
    "get_research_graph",
    "ResearchState",
    "agent_graph",
    "GraphState",
]
