"""
Pytest configuration and import shims for optional dependencies.

Provides a minimal shim for `langgraph.checkpoint.postgres.aio.AsyncPostgresSaver`
so tests that import it can run without requiring the optional Postgres module.

Also adjusts sys.path for internal test modules that expect to be run from the
log_analysis_agent package directory (so that `schemas`, `formatters`, and `tools`
can be imported directly during repository-level pytest runs).
"""
import sys
import types
from pathlib import Path


def _install_langgraph_postgres_shim() -> None:
    try:
        # If real module is importable, do nothing
        __import__("langgraph.checkpoint.postgres.aio")
        return
    except Exception:
        pass

    # Ensure a base 'langgraph' package exists or reuse the one already imported
    langgraph_pkg = sys.modules.get('langgraph')
    if langgraph_pkg is None:
        langgraph_pkg = types.ModuleType('langgraph')
        langgraph_pkg.__path__ = [""]  # type: ignore[attr-defined]
        sys.modules['langgraph'] = langgraph_pkg
    else:
        langgraph_pkg.__path__ = getattr(langgraph_pkg, '__path__', [""])  # type: ignore[attr-defined]

    # Reuse existing submodules when present to avoid duplicate module objects
    checkpoint_mod = sys.modules.get("langgraph.checkpoint")
    if checkpoint_mod is None:
        checkpoint_mod = types.ModuleType("langgraph.checkpoint")
        checkpoint_mod.__path__ = [""]  # type: ignore[attr-defined]
    else:
        checkpoint_mod.__path__ = getattr(checkpoint_mod, '__path__', [""])  # type: ignore[attr-defined]

    postgres_mod = sys.modules.get("langgraph.checkpoint.postgres")
    if postgres_mod is None:
        postgres_mod = types.ModuleType("langgraph.checkpoint.postgres")
        postgres_mod.__path__ = [""]  # type: ignore[attr-defined]
    else:
        postgres_mod.__path__ = getattr(postgres_mod, '__path__', [""])  # type: ignore[attr-defined]

    aio_mod = sys.modules.get("langgraph.checkpoint.postgres.aio")
    if aio_mod is None:
        aio_mod = types.ModuleType("langgraph.checkpoint.postgres.aio")

    if not hasattr(aio_mod, "AsyncPostgresSaver"):
        class AsyncPostgresSaver:  # type: ignore
            """Lightweight test stub used only for import compatibility."""
            pass

        aio_mod.AsyncPostgresSaver = AsyncPostgresSaver  # type: ignore[attr-defined]

    # Wire module hierarchy
    langgraph_pkg.checkpoint = checkpoint_mod  # type: ignore[attr-defined]
    checkpoint_mod.postgres = postgres_mod     # type: ignore[attr-defined]
    postgres_mod.aio = aio_mod                 # type: ignore[attr-defined]

    # Register modules in sys.modules for dotted imports
    sys.modules["langgraph.checkpoint"] = checkpoint_mod
    sys.modules["langgraph.checkpoint.postgres"] = postgres_mod
    sys.modules["langgraph.checkpoint.postgres.aio"] = aio_mod


_install_langgraph_postgres_shim()


def _install_log_agent_local_imports() -> None:
    """Allow tests under app/agents_v2/log_analysis_agent to import local modules.

    Some developer-oriented tests import `schemas`, `formatters`, and `tools`
    as if the current working directory is the log_analysis_agent package.
    To support running pytest from the repository root, we prepend that directory
    to sys.path when available.
    """
    try:
        repo_root = Path(__file__).resolve().parent
        pkg_dir = repo_root / "app" / "agents_v2" / "log_analysis_agent"
        if pkg_dir.exists() and str(pkg_dir) not in sys.path:
            sys.path.insert(0, str(pkg_dir))
    except Exception:
        pass


_install_log_agent_local_imports()
