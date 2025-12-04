"""Persistence layer for LangGraph state checkpointing.

This module provides PostgreSQL-backed checkpointing for LangGraph workflows:
- SupabaseCheckpointer: Async checkpointer using Supabase/PostgreSQL
- ThreadManager: Thread lifecycle management (create, fork, switch)
- CheckpointerConfig: Configuration dataclass

Usage:
    from app.agents.harness.persistence import (
        SupabaseCheckpointer,
        ThreadManager,
        CheckpointerConfig,
    )

    config = CheckpointerConfig(db_url="postgresql://...")
    checkpointer = SupabaseCheckpointer(config)
    await checkpointer.setup()
"""

from .config import CheckpointerConfig
from .postgres_checkpointer import CheckpointResult, SupabaseCheckpointer
from .thread_manager import ThreadManager
from .utils import decode_json, ensure_dict, get_row_value, rows_to_dicts

__all__ = [
    "CheckpointerConfig",
    "CheckpointResult",
    "SupabaseCheckpointer",
    "ThreadManager",
    # Utilities
    "decode_json",
    "ensure_dict",
    "get_row_value",
    "rows_to_dicts",
]
