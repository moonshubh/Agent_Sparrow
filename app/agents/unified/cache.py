"""LLM caching configuration for cost/latency savings."""

from __future__ import annotations

import os

from loguru import logger

from app.core.settings import settings


def configure_llm_cache(ttl_seconds: int = 1800) -> bool:
    """Configure a Redis-backed LangChain LLM cache (best effort).

    Returns:
        True if cache was configured, False otherwise.
    """
    if os.getenv("DISABLE_LLM_CACHE") in {"1", "true", "True"}:
        logger.info("llm_cache_disabled_via_env")
        return False

    redis_url_env = os.getenv("REDIS_URL")
    redis_url = redis_url_env or getattr(settings, "redis_url", None)
    if not redis_url_env and settings.is_production_mode():
        logger.info("llm_cache_not_configured", reason="missing_redis_url_env")
        return False
    if not redis_url:
        logger.info("llm_cache_not_configured", reason="missing_redis_url")
        return False

    try:
        from langchain.globals import set_llm_cache  # type: ignore[import-not-found]

        try:
            from langchain_community.cache import RedisCache  # type: ignore[import-not-found]
        except ImportError:
            try:
                from langchain.cache import RedisCache  # type: ignore[import-not-found, assignment]
            except ImportError as exc:
                logger.info(
                    "llm_cache_not_configured",
                    reason="missing_langchain_cache",
                    error=str(exc),
                )
                return False

        set_llm_cache(RedisCache(redis_url=redis_url, ttl=ttl_seconds))
        logger.info("llm_cache_configured", backend="redis", ttl_seconds=ttl_seconds)
        return True
    except Exception as exc:  # pragma: no cover - best effort
        logger.warning("llm_cache_configuration_failed", error=str(exc))
        return False


__all__ = ["configure_llm_cache"]
