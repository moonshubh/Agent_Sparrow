"""Agent Harness package following DeepAgents patterns.

This package provides the harness adapter for creating Agent Sparrow
instances with proper middleware composition and backend abstractions.

Subpackages:
    middleware/     - DeepAgents middleware stack (memory, rate limiting, eviction, state tracking)
    backends/       - Storage backend implementations (protocol, composite, supabase)
    store/          - LangGraph BaseStore implementations (workspace, memory)
    observability/  - State tracking and metrics (LoopStateTracker, AgentLoopState)
    persistence/    - LangGraph checkpointing (SupabaseCheckpointer, ThreadManager)

Usage:
    from app.agents.harness import create_sparrow_agent, SparrowAgentConfig
    from app.agents.harness.middleware import StateTrackingMiddleware
    from app.agents.harness.observability import AgentLoopState
    from app.agents.harness.persistence import SupabaseCheckpointer
"""

from __future__ import annotations

try:  # pragma: no cover - import-time guard for optional deps
    from .sparrow_harness import create_sparrow_agent, SparrowAgentConfig
except Exception:  # pragma: no cover
    import logging
    from typing import Any, NoReturn

    logging.error("Failed to import sparrow_harness", exc_info=True)

    def _missing_sparrow_harness(*_args: Any, **_kwargs: Any) -> NoReturn:
        raise ImportError(
            "sparrow_harness is unavailable; install optional dependencies."
        )

    class _MissingSparrowAgentConfig:
        def __init__(self, *_: Any, **__: Any) -> None:
            _missing_sparrow_harness()

    create_sparrow_agent = _missing_sparrow_harness  # type: ignore[assignment]
    SparrowAgentConfig = _MissingSparrowAgentConfig  # type: ignore[misc,assignment]

__all__ = [
    "create_sparrow_agent",
    "SparrowAgentConfig",
]
