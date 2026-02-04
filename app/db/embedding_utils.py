"""Compatibility shim for legacy embedding imports.

The canonical module is now `app.db.embedding.utils`. This file re-exports all
symbols to avoid breaking older import paths during the migration.
"""

from app.db.embedding.utils import *  # noqa: F401,F403
