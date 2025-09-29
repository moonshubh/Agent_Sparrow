"""
Pytest configuration and import shims for optional dependencies.

Provides a minimal shim for `langgraph.checkpoint.postgres.aio.AsyncPostgresSaver`
so tests that import it can run without requiring the optional Postgres module.
"""
import sys
import types


def _install_langgraph_postgres_shim() -> None:
    try:
        # If real module is importable, do nothing
        __import__("langgraph.checkpoint.postgres.aio")
        return
    except Exception:
        pass

    # Ensure a base 'langgraph' package exists
    if 'langgraph' in sys.modules:
        langgraph_pkg = sys.modules['langgraph']
    else:
        langgraph_pkg = types.ModuleType('langgraph')
        # Mark as package
        langgraph_pkg.__path__ = [""]  # type: ignore[attr-defined]
        sys.modules['langgraph'] = langgraph_pkg

    # Create nested modules
    checkpoint_mod = types.ModuleType("langgraph.checkpoint")
    postgres_mod = types.ModuleType("langgraph.checkpoint.postgres")
    aio_mod = types.ModuleType("langgraph.checkpoint.postgres.aio")

    # Set __path__ to behave like packages
    checkpoint_mod.__path__ = [""]  # type: ignore[attr-defined]
    postgres_mod.__path__ = [""]  # type: ignore[attr-defined]

    class AsyncPostgresSaver:  # type: ignore
        """Lightweight test stub used only for import compatibility."""
        pass

    aio_mod.AsyncPostgresSaver = AsyncPostgresSaver  # type: ignore[attr-defined]

    # Wire module hierarchy
    langgraph_pkg.checkpoint = checkpoint_mod  # type: ignore[attr-defined]
    checkpoint_mod.postgres = postgres_mod     # type: ignore[attr-defined]
    postgres_mod.aio = aio_mod                 # type: ignore[attr-defined]

    # Register modules in sys.modules for dotted imports
    sys.modules.setdefault("langgraph.checkpoint", checkpoint_mod)
    sys.modules.setdefault("langgraph.checkpoint.postgres", postgres_mod)
    sys.modules.setdefault("langgraph.checkpoint.postgres.aio", aio_mod)


_install_langgraph_postgres_shim()
