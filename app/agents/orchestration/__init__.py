"""Orchestration compatibility layer (Phase 1).

New canonical import path: app.agents.orchestration
Temporarily re-exports from app.agents_v2.orchestration.*
"""

try:
    from app.agents_v2.orchestration.graph import app as graph_app  # noqa: F401
    from app.agents_v2.orchestration.state import GraphState  # noqa: F401
except Exception:  # pragma: no cover
    pass

__all__ = ["graph_app", "GraphState"]
