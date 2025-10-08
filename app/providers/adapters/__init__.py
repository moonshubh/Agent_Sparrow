"""Unified provider adapter access layer.

This module centralizes adapter registration and exposes a stable API for
loading models and accessing defaults. Provider-specific adapters continue to
live under app.providers.<Provider>/<Model>/adapter.py but are imported here
to trigger registration with the registry.
"""

from __future__ import annotations

def _bootstrap_known_adapters() -> None:
    """Best-effort load of common adapters to register them eagerly.

    Uses the registry's dynamic loader to handle hyphenated module paths.
    Failures are non-fatal; unknown providers/models can still be
    dynamically loaded later on demand.
    """
    try:
        # Import here to avoid import cycles at module import time
        from app.providers.registry import get_adapter as _get
    except Exception:
        return

    combos = [
        ("google", "gemini-2.5-flash"),
        ("google", "gemini-2.5-flash-preview-09-2025"),
        ("google", "gemini-2.5-pro"),
        ("openai", "gpt-5-mini-2025-08-07"),
        ("openai", "gpt5-mini"),
        ("openai", "gpt-5-mini"),
    ]
    for prov, model in combos:
        try:
            _get(prov, model)
        except Exception:
            # Adapter may be unavailable in environment; ignore
            continue

# Public API re-exports
from app.providers.registry import (  # noqa: E402
    get_adapter as get_adapter,
    load_model as load_model,
)

# Defaults re-exported here for a single, stable import path
from app.providers.registry import (  # noqa: E402
    default_provider as default_provider,
    default_model_for_provider as default_model_for_provider,
)

__all__ = [
    "get_adapter",
    "load_model",
    "default_provider",
    "default_model_for_provider",
]

# Eagerly attempt to load common adapters
_bootstrap_known_adapters()

