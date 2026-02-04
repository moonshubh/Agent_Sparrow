"""Tracing/observability helpers (LangSmith + OpenTelemetry)."""

from __future__ import annotations

import logging
import os
from typing import Optional

from app.core.settings import settings

logger = logging.getLogger(__name__)

_LANGSMITH_READY: Optional[bool] = None


def configure_langsmith() -> bool:
    """Set LangSmith/LangChain environment variables when tracing is enabled."""

    global _LANGSMITH_READY
    if _LANGSMITH_READY is not None:
        return _LANGSMITH_READY

    if not settings.langsmith_tracing_enabled:
        logger.debug("LangSmith tracing disabled; skipping configuration")
        _LANGSMITH_READY = False
        return False

    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    os.environ.setdefault("LANGSMITH_TRACING", "true")

    if settings.langsmith_api_key:
        os.environ.setdefault("LANGCHAIN_API_KEY", settings.langsmith_api_key)
        os.environ.setdefault("LANGSMITH_API_KEY", settings.langsmith_api_key)
    if settings.langsmith_endpoint:
        os.environ.setdefault("LANGCHAIN_ENDPOINT", settings.langsmith_endpoint)
        os.environ.setdefault("LANGSMITH_ENDPOINT", settings.langsmith_endpoint)
    if settings.langsmith_project:
        os.environ.setdefault("LANGCHAIN_PROJECT", settings.langsmith_project)
        os.environ.setdefault("LANGSMITH_PROJECT", settings.langsmith_project)

    try:  # Optional dependency
        from langsmith import Client

        Client()  # Prime the SDK so misconfigurations fail fast
        logger.info(
            "LangSmith client initialized for project '%s'",
            os.environ.get("LANGSMITH_PROJECT"),
        )
        _LANGSMITH_READY = True
    except Exception as exc:  # pragma: no cover - best effort
        logger.warning("LangSmith client not available: %s", exc)
        _LANGSMITH_READY = False

    return _LANGSMITH_READY


__all__ = ["configure_langsmith", "logger"]

# Note: For long-running workers (FastAPI, Celery), configure_langsmith() should be
# called explicitly during application startup (app/main.py, celery app init).
# Avoid import-time side effects for better testability and startup control.
