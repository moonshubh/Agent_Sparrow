"""Compat wrapper for Supabase client (Phase 1).

Canonical path moving to app.db.supabase.client; currently re-exports
from app.db.supabase_client to avoid breaking changes.
"""
from __future__ import annotations

try:
    # Re-export public client helpers
    from app.db.supabase_client import (
        get_supabase_client,  # noqa: F401
        SupabaseServiceClient,  # noqa: F401
    )
except Exception:  # pragma: no cover
    pass

__all__ = ["get_supabase_client", "SupabaseServiceClient"]
