"""Compat wrapper for Supabase client.

Canonical path: app.db.supabase.client
This module re-exports symbols from app.db.supabase_client to avoid breaking
changes while we migrate imports across the codebase.
"""
from __future__ import annotations

# Dynamic forwarding to allow tests to monkeypatch app.db.supabase_client
def SupabaseClient(*args, **kwargs):  # type: ignore[override]
    from app.db import supabase_client as _sb
    return _sb.SupabaseClient(*args, **kwargs)


def get_supabase_client():
    from app.db import supabase_client as _sb
    return _sb.get_supabase_client()


def supabase_transaction():
    from app.db import supabase_client as _sb
    return _sb.supabase_transaction()


class SupabaseConfig:  # pragma: no cover - alias for type hints
    from app.db.supabase_client import SupabaseConfig as _Cfg

    def __new__(cls, *args, **kwargs):
        from app.db import supabase_client as _sb
        return _sb.SupabaseConfig(*args, **kwargs)


__all__ = ["SupabaseClient", "SupabaseConfig", "get_supabase_client", "supabase_transaction"]
