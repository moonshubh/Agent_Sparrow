"""LangGraph Store implementations for Agent Sparrow.

This package provides LangGraph-compatible BaseStore implementations
that integrate with Sparrow's existing infrastructure.

Components:
- SparrowMemoryStore: BaseStore adapter wrapping mem0-based MemoryService
- sparrow_memory_store: Global singleton instance
- SparrowWorkspaceStore: BaseStore for Deep Agent workspace files (progress, goals, handoff)

Usage:
    from app.agents.harness.store import sparrow_memory_store, SparrowWorkspaceStore

    # Memory store - for cross-session facts
    await sparrow_memory_store.aput(
        ("sparrow", "user_123"),
        "preference",
        {"text": "User prefers dark mode"}
    )

    # Workspace store - for session progress and handoff
    workspace = SparrowWorkspaceStore(session_id="session_123")
    await workspace.set_progress_notes("Made progress on feature X...")
    await workspace.set_active_goals({"features": [{"name": "Auth", "status": "pass"}]})
"""

from .memory_store import SparrowMemoryStore, sparrow_memory_store
from .workspace_store import SparrowWorkspaceStore

__all__ = [
    "SparrowMemoryStore",
    "sparrow_memory_store",
    "SparrowWorkspaceStore",
]
