"""Orchestration compatibility layer (Phase 1).

New canonical import path: app.agents.orchestration
Temporarily re-exports from app.agents.orchestration.*
"""

try:
    from app.agents.orchestration.orchestration.graph import app as graph_app  # noqa: F401
    from app.agents.orchestration.orchestration.state import GraphState  # noqa: F401
except Exception:  # pragma: no cover
    pass

__all__ = ["graph_app", "GraphState"]
