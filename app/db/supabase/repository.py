"""Light repository façade for Supabase-backed operations.

Use get_repo_client() to obtain the shared Supabase client. This layer exists
to provide a stable import path for future repository methods without changing
behavior now.
"""

from __future__ import annotations

from .client import get_supabase_client, SupabaseClient


def get_repo_client() -> SupabaseClient:
    """Return the shared Supabase client instance."""
    return get_supabase_client()


__all__ = ["get_repo_client", "SupabaseClient"]
