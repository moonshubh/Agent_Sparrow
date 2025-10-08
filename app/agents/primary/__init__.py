"""Primary agent compatibility layer (Phase 1).

New canonical import path: app.agents.primary
Temporarily re-exports from app.agents_v2.primary_agent.*
"""

try:
    from app.agents_v2.primary_agent.agent import run_primary_agent  # noqa: F401
    from app.agents_v2.primary_agent.schemas import PrimaryAgentState  # noqa: F401
except Exception:  # pragma: no cover
    pass

__all__ = ["run_primary_agent", "PrimaryAgentState"]
