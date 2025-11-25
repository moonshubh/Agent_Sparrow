"""Backend abstractions for Agent Sparrow.

Backend components following DeepAgents patterns:
- BackendProtocol: Interface contract for storage backends
- SupabaseStoreBackend: Persistent storage via Supabase
- InMemoryBackend: In-memory storage for testing
- SparrowCompositeBackend: Routes to appropriate backend based on path prefix
"""

from __future__ import annotations

from .supabase_store import (
    SupabaseStoreBackend,
    FileInfo,
    WriteResult,
    EditResult,
    GrepMatch,
)
from .composite import SparrowCompositeBackend
from .protocol import BackendProtocol, InMemoryBackend

__all__ = [
    # Protocol and types
    "BackendProtocol",
    "FileInfo",
    "WriteResult",
    "EditResult",
    "GrepMatch",
    # Implementations
    "SupabaseStoreBackend",
    "InMemoryBackend",
    "SparrowCompositeBackend",
]
