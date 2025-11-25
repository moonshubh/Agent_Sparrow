"""LangGraph Store implementations for Agent Sparrow.

This package provides LangGraph-compatible BaseStore implementations
that integrate with Sparrow's existing infrastructure.

Components:
- SparrowMemoryStore: BaseStore adapter wrapping mem0-based MemoryService
- sparrow_memory_store: Global singleton instance

Usage:
    from app.agents.harness.store import sparrow_memory_store

    # Store a fact
    await sparrow_memory_store.aput(
        ("sparrow", "user_123"),
        "preference",
        {"text": "User prefers dark mode"}
    )

    # Search memories
    results = await sparrow_memory_store.asearch(
        ("sparrow",),
        query="user preferences"
    )
"""

from .memory_store import SparrowMemoryStore, sparrow_memory_store

__all__ = [
    "SparrowMemoryStore",
    "sparrow_memory_store",
]
