"""Shared model context window metadata and helpers."""

from __future__ import annotations

from typing import Optional

from app.core.config import find_model_config, get_models_config, resolve_coordinator_config

DEFAULT_CONTEXT_WINDOW = 128_000


def get_model_context_window(model: str, provider: Optional[str] = None) -> int:
    """Get the context window size for a model from models.yaml."""
    if model:
        config = get_models_config()
        match = find_model_config(config, model)
        if match is not None:
            return match.context_window

    if provider:
        config = get_models_config()
        coordinator = resolve_coordinator_config(config, provider)
        return coordinator.context_window

    raise ValueError(f"Unknown model context window for: {model}")


__all__ = ["DEFAULT_CONTEXT_WINDOW", "get_model_context_window"]
