"""Compatibility shim for primary adapter bridge.

Canonical import path: app.agents.primary.adapter_bridge
"""

try:
    from app.agents.primary.primary_agent.adapter_bridge import (
        get_primary_agent_model,  # noqa: F401
    )
except Exception:  # pragma: no cover
    pass

__all__ = ["get_primary_agent_model"]
