"""Backend abstractions for Agent Sparrow.

Backend components following DeepAgents patterns:
- SupabaseStoreBackend: Persistent storage via Supabase
- SparrowCompositeBackend: Routes to appropriate backend based on path prefix
"""

from __future__ import annotations

from .supabase_store import SupabaseStoreBackend
from .composite import SparrowCompositeBackend

__all__ = [
    "SupabaseStoreBackend",
    "SparrowCompositeBackend",
]
