"""Router compatibility layer (Phase 1).

New canonical import path: app.agents.router
Temporarily re-exports from app.agents.router.router
"""

try:
    from app.agents.router.router import query_router, get_user_query  # noqa: F401
except Exception:  # pragma: no cover
    pass

__all__ = ["query_router", "get_user_query"]
