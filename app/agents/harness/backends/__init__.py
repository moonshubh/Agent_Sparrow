"""Backend abstractions for Agent Sparrow.

Backend components following DeepAgents patterns:
- BackendProtocol: Interface contract for storage backends
- SupabaseStoreBackend: Persistent storage via Supabase
- InMemoryBackend: In-memory storage for testing
- SparrowCompositeBackend: Routes to appropriate backend based on path prefix

Data types (FileInfo, WriteResult, EditResult, GrepMatch) are defined in
protocol.py as the canonical source.
"""

from __future__ import annotations

# Data types and protocol from canonical source
from .protocol import (
    BackendProtocol,
    InMemoryBackend,
    FileInfo,
    WriteResult,
    EditResult,
    GrepMatch,
)

# Backend implementations
from .supabase_store import SupabaseStoreBackend
from .composite import SparrowCompositeBackend

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
