"""LangGraph Store implementations for Agent Sparrow.

This package provides LangGraph-compatible BaseStore implementations
that integrate with Sparrow's existing infrastructure.

Components:
- SparrowMemoryStore: BaseStore adapter wrapping mem0-based MemoryService
- sparrow_memory_store: Global singleton instance
- SparrowWorkspaceStore: BaseStore for Deep Agent workspace files (progress, goals, handoff)
- IssueResolutionStore: Store for tracking resolved issues with vector similarity search

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

    # Issue resolution store - for finding similar past resolutions
    from app.agents.harness.store import IssueResolutionStore

    resolution_store = IssueResolutionStore()
    await resolution_store.store_resolution(
        ticket_id="12345",
        category="account_setup",
        problem_summary="User cannot login",
        solution_summary="Reset session tokens",
    )
    similar = await resolution_store.find_similar_resolutions(
        query="Login issues after password change",
        limit=5,
    )
"""

from .issue_resolution_store import IssueResolution, IssueResolutionStore
from .memory_store import SparrowMemoryStore, sparrow_memory_store
from .workspace_store import SparrowWorkspaceStore

__all__ = [
    "SparrowMemoryStore",
    "sparrow_memory_store",
    "SparrowWorkspaceStore",
    "IssueResolutionStore",
    "IssueResolution",
]
