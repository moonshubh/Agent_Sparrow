"""Compatibility shim for legacy imports.

The canonical Supabase client now lives at `app.db.supabase.client`. This
module re-exports the same symbols so existing imports continue to work
while the codebase migrates.
"""

from app.db.supabase.client import (  # noqa: F401
    SupabaseClient,
    SupabaseConfig,
    get_supabase_client,
    supabase_transaction,
)

__all__ = [
    "SupabaseClient",
    "SupabaseConfig",
    "get_supabase_client",
    "supabase_transaction",
]
