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

    logging.error("Failed to import sparrow_harness", exc_info=True)
    create_sparrow_agent = None  # type: ignore[assignment]
    SparrowAgentConfig = None  # type: ignore[assignment]

__all__ = [
    "create_sparrow_agent",
    "SparrowAgentConfig",
]
