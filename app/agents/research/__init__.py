"""Research agent compatibility layer (Phase 1).

New canonical import path: app.agents.research
Temporarily re-exports from app.agents.research.research_agent.*
"""

try:
    from app.agents.research.research_agent.research_agent import (
        get_research_graph,  # noqa: F401
        ResearchState,  # noqa: F401
    )
except Exception:  # pragma: no cover
    pass

__all__ = ["get_research_graph", "ResearchState"]
