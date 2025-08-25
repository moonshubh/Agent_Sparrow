"""
LangGraph Checkpointer with PostgreSQL/Supabase integration.

This module re-exports key checkpointer primitives for persistent memory and state management:
- CheckpointerConfig: Configuration for the checkpointer
- SupabaseCheckpointer: PostgreSQL/Supabase-backed checkpointer implementation
- ThreadManager: Manages conversation threads and sessions

Usage:
    from app.agents_v2.checkpointer import CheckpointerConfig, SupabaseCheckpointer
    
    config = CheckpointerConfig(connection_string="postgresql://...")
    checkpointer = SupabaseCheckpointer(config)
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Import for type checking only, doesn't execute at runtime
    from .config import CheckpointerConfig
    from .supabase_checkpointer import SupabaseCheckpointer
    from .thread_manager import ThreadManager

__all__ = (
    "CheckpointerConfig",
    "SupabaseCheckpointer",
    "ThreadManager",
)

# Lazy loading implementation (PEP 562)
def __getattr__(name: str):
    """Lazy load modules on first access."""
    if name == "CheckpointerConfig":
        from .config import CheckpointerConfig
        return CheckpointerConfig
    elif name == "SupabaseCheckpointer":
        from .supabase_checkpointer import SupabaseCheckpointer
        return SupabaseCheckpointer
    elif name == "ThreadManager":
        from .thread_manager import ThreadManager
        return ThreadManager
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

def __dir__():
    """List available attributes for module introspection."""
    return list(__all__)