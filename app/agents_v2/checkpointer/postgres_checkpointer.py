"""Compat shim for Postgres checkpointer location change.

Ensures tests patching this module's ``create_connection_pool`` affect the
actual implementation before instantiation of SupabaseCheckpointer.
"""
from __future__ import annotations

# Import real module under a name
from app.agents.checkpointer import postgres_checkpointer as _real

# Re-export public API
SupabaseCheckpointerBase = _real.SupabaseCheckpointer
CheckpointerConfig = _real.CheckpointerConfig

# Expose create_connection_pool symbol here so tests can patch it
create_connection_pool = _real.create_connection_pool


class SupabaseCheckpointer(SupabaseCheckpointerBase):  # type: ignore[misc]
    def __init__(self, *args, **kwargs):
        # Propagate any patched function from this shim to the real module
        try:
            _real.create_connection_pool = globals().get("create_connection_pool", _real.create_connection_pool)
        except Exception:
            pass
        super().__init__(*args, **kwargs)

__all__ = [
    "SupabaseCheckpointer",
    "CheckpointerConfig",
    "create_connection_pool",
]
