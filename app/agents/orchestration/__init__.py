"""Orchestration compatibility layer - Phase 1 Complete.

Now using unified agent system. Re-exports from app.agents.orchestration.orchestration
for backward compatibility during transition.
"""

try:
    from app.agents.orchestration.orchestration.graph import (
        app as graph_app,
    )  # noqa: F401
    from app.agents.orchestration.orchestration.state import GraphState  # noqa: F401
except Exception:  # pragma: no cover
    pass

__all__ = ["graph_app", "GraphState"]
