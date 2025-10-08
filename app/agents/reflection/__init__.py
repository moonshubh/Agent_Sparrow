"""Reflection agent compatibility layer (Phase 1).

New canonical import path: app.agents.reflection
Temporarily re-exports from app.agents_v2.reflection.*
"""

try:
    from app.agents_v2.reflection.node import reflection_node as reflection_node  # noqa: F401
except Exception:  # pragma: no cover
    pass

__all__ = ["reflection_node"]
