"""
Database Analytics Cache Layer

Provides Redis-backed caching for expensive analytics queries.
Uses the new RPC aggregation functions for efficient database-side processing.
Integrates with database-side invalidation tracking via cache_invalidation_tracker table.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from functools import wraps
import inspect
from typing import Any, Callable, Optional

from app.cache.redis_cache import RedisCache

logger = logging.getLogger(__name__)

# Cache TTL configurations (in seconds)
CACHE_TTL = {
    "conversation_analytics": 300,  # 5 minutes
    "approval_workflow_stats": 300,  # 5 minutes
    "feedme_summary": 120,  # 2 minutes
    "folders_with_stats": 180,  # 3 minutes
    "chat_session_stats": 300,  # 5 minutes
    "conversation_processing_stats": 60,  # 1 minute (per-conversation)
    "embedding": 3600,  # 1 hour (embeddings are expensive)
}


class AnalyticsCache:
    """
    Redis-backed cache for analytics queries.

    Wraps expensive analytics operations with automatic caching.
    Uses cache keys based on operation name and optional parameters.
    Integrates with database-side invalidation tracking.
    """

    def __init__(self, default_ttl: int = 300):
        """
        Initialize the analytics cache.

        Args:
            default_ttl: Default cache TTL in seconds (default: 5 minutes)
        """
        self._redis = RedisCache(ttl=default_ttl)
        self._enabled = True
        self._supabase_client = None  # Lazy loaded

    def disable(self) -> None:
        """Disable caching (useful for testing)."""
        self._enabled = False

    def enable(self) -> None:
        """Enable caching."""
        self._enabled = True

    def _make_key(self, operation: str, *args: Any, **kwargs: Any) -> str:
        """Generate a cache key from operation name and parameters."""
        key_parts = [f"analytics:{operation}"]
        if args:
            key_parts.append(":".join(str(a) for a in args))
        if kwargs:
            sorted_kwargs = sorted(kwargs.items())
            key_parts.append(":".join(f"{k}={v}" for k, v in sorted_kwargs))
        return ":".join(key_parts)

    def get(self, operation: str, *args: Any, **kwargs: Any) -> Optional[Any]:
        """
        Get cached result for an operation.

        Args:
            operation: The operation name (e.g., 'conversation_analytics')
            *args: Positional arguments used to generate cache key
            **kwargs: Keyword arguments used to generate cache key

        Returns:
            Cached result or None if not found
        """
        if not self._enabled:
            return None

        key = self._make_key(operation, *args, **kwargs)
        result = self._redis.get(key)

        if result is not None:
            logger.debug(f"Cache hit for {operation}")
        else:
            logger.debug(f"Cache miss for {operation}")

        return result

    def set(
        self,
        operation: str,
        value: Any,
        *args: Any,
        ttl: Optional[int] = None,
        **kwargs: Any,
    ) -> None:
        """
        Cache a result for an operation.

        Args:
            operation: The operation name
            value: The value to cache
            *args: Positional arguments used to generate cache key
            ttl: Optional TTL override (uses CACHE_TTL config if not provided)
            **kwargs: Keyword arguments used to generate cache key
        """
        if not self._enabled:
            return

        key = self._make_key(operation, *args, **kwargs)
        cache_ttl = ttl or CACHE_TTL.get(operation, 300)
        self._redis.set(key, value, ttl=cache_ttl)
        logger.debug(f"Cached {operation} with TTL {cache_ttl}s")

    def invalidate(self, operation: str, *args: Any, **kwargs: Any) -> None:
        """
        Invalidate cached result for an operation.

        Args:
            operation: The operation name
            *args: Positional arguments used to generate cache key
            **kwargs: Keyword arguments used to generate cache key
        """
        if not self._enabled:
            return

        key = self._make_key(operation, *args, **kwargs)
        try:
            self._redis.client.delete(key)
            logger.debug(f"Invalidated cache for {operation}")
        except Exception as e:
            logger.warning(f"Failed to invalidate cache for {operation}: {e}")

    def _get_supabase(self):
        """Lazy load Supabase client to avoid circular imports."""
        if self._supabase_client is None:
            try:
                from supabase import create_client
                from app.core.settings import settings

                self._supabase_client = create_client(
                    settings.supabase_url, settings.supabase_anon_key
                )
            except Exception as e:
                logger.warning(f"Failed to initialize Supabase client for cache: {e}")
                return None
        return self._supabase_client

    def check_db_invalidation(self, operation: str, cached_at: datetime) -> bool:
        """
        Check if cache is still valid against database invalidation tracker.

        Args:
            operation: The cache operation name (e.g., 'conversation_analytics')
            cached_at: When the cache entry was created

        Returns:
            True if cache is valid, False if it should be invalidated
        """
        try:
            client = self._get_supabase()
            if client is None:
                return True  # Assume valid if can't check

            result = client.rpc(
                "is_cache_valid",
                {"p_cache_key": operation, "p_cached_at": cached_at.isoformat()},
            ).execute()

            if result.data is not None:
                return bool(result.data)
            return True
        except Exception as e:
            logger.warning(f"Failed to check DB invalidation for {operation}: {e}")
            return True  # Assume valid on error

    def get_with_db_validation(
        self, operation: str, *args: Any, **kwargs: Any
    ) -> tuple[Optional[Any], bool]:
        """
        Get cached result with database invalidation validation.

        Args:
            operation: The operation name
            *args: Positional arguments used to generate cache key
            **kwargs: Keyword arguments used to generate cache key

        Returns:
            Tuple of (cached_value, is_valid). If is_valid is False,
            the cache was invalidated by database triggers.
        """
        if not self._enabled:
            return None, False

        key = self._make_key(operation, *args, **kwargs)
        meta_key = f"{key}:meta"

        try:
            # Get both value and metadata
            value = self._redis.get(key)
            if value is None:
                return None, False

            # Get metadata with cached_at timestamp
            meta = self._redis.get(meta_key)
            if meta is None:
                # No metadata, assume valid (backward compatibility)
                return value, True

            cached_at_raw = meta.get("cached_at") if isinstance(meta, dict) else None
            if not cached_at_raw:
                # Missing/invalid metadata: treat as valid to avoid cache stampedes.
                return value, True
            try:
                cached_at = datetime.fromisoformat(str(cached_at_raw))
            except ValueError:
                # Treat unparseable timestamps as valid (best-effort compatibility).
                return value, True

            # Check database invalidation
            if not self.check_db_invalidation(operation, cached_at):
                # Cache was invalidated, delete it
                self._redis.client.delete(key)
                self._redis.client.delete(meta_key)
                logger.debug(f"Cache invalidated by DB trigger for {operation}")
                return None, False

            return value, True
        except Exception as e:
            logger.warning(f"Error in get_with_db_validation for {operation}: {e}")
            return None, False

    def set_with_metadata(
        self,
        operation: str,
        value: Any,
        *args: Any,
        ttl: Optional[int] = None,
        **kwargs: Any,
    ) -> None:
        """
        Cache a result with metadata for database invalidation tracking.

        Args:
            operation: The operation name
            value: The value to cache
            *args: Positional arguments used to generate cache key
            ttl: Optional TTL override
            **kwargs: Keyword arguments used to generate cache key
        """
        if not self._enabled:
            return

        key = self._make_key(operation, *args, **kwargs)
        meta_key = f"{key}:meta"
        cache_ttl = ttl or CACHE_TTL.get(operation, 300)

        try:
            # Store value
            self._redis.set(key, value, ttl=cache_ttl)

            # Store metadata with timestamp
            meta = {
                "cached_at": datetime.now(timezone.utc).isoformat(),
                "operation": operation,
            }
            self._redis.set(meta_key, meta, ttl=cache_ttl)

            logger.debug(f"Cached {operation} with metadata, TTL {cache_ttl}s")
        except Exception as e:
            logger.warning(f"Failed to cache {operation} with metadata: {e}")


def cached_analytics(
    operation: str,
    ttl: Optional[int] = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Decorator for caching analytics method results.

    Usage:
        @cached_analytics("conversation_analytics", ttl=300)
        async def get_conversation_analytics(self) -> Dict[str, Any]:
            ...

    Args:
        operation: The operation name for cache key generation
        ttl: Optional TTL override

    Returns:
        Decorated function with caching
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        signature = inspect.signature(func)
        param_names = list(signature.parameters.keys())
        skip_first_arg = bool(param_names and param_names[0] in {"self", "cls"})

        def _args_for_cache_key(args: tuple[Any, ...]) -> tuple[Any, ...]:
            # Avoid including instance/class references in cache keys.
            if skip_first_arg and len(args) > 0:
                return tuple(args[1:])
            return tuple(args)

        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            # Get or create cache instance
            cache = _get_analytics_cache()

            # Check cache first
            key_args = _args_for_cache_key(args)
            cached = cache.get(operation, *key_args, **kwargs)
            if cached is not None:
                return cached

            # Execute function
            result = await func(*args, **kwargs)

            # Cache result
            cache.set(operation, result, *key_args, ttl=ttl, **kwargs)

            return result

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            cache = _get_analytics_cache()

            key_args = _args_for_cache_key(args)
            cached = cache.get(operation, *key_args, **kwargs)
            if cached is not None:
                return cached

            result = func(*args, **kwargs)
            cache.set(operation, result, *key_args, ttl=ttl, **kwargs)

            return result

        # Return appropriate wrapper based on function type
        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


# Singleton cache instance
_analytics_cache: Optional[AnalyticsCache] = None


def _get_analytics_cache() -> AnalyticsCache:
    """Get or create the singleton analytics cache instance."""
    global _analytics_cache
    if _analytics_cache is None:
        _analytics_cache = AnalyticsCache()
    return _analytics_cache


def get_analytics_cache() -> AnalyticsCache:
    """Public function to get the analytics cache instance."""
    return _get_analytics_cache()


class EmbeddingCache:
    """
    Cache for query embeddings to avoid repeated API calls.

    Embeddings are cached by query text hash with a longer TTL
    since they don't change for the same input.
    """

    def __init__(self, ttl: int = 3600):
        """
        Initialize embedding cache.

        Args:
            ttl: Cache TTL in seconds (default: 1 hour)
        """
        self._redis = RedisCache(ttl=ttl)

    def get_embedding(self, query: str) -> Optional[list[float]]:
        """
        Get cached embedding for a query.

        Args:
            query: The query text

        Returns:
            Cached embedding vector or None
        """
        key = f"embedding:{query}"
        result = self._redis.get(key)
        return result

    def set_embedding(self, query: str, embedding: list[float]) -> None:
        """
        Cache an embedding for a query.

        Args:
            query: The query text
            embedding: The embedding vector
        """
        key = f"embedding:{query}"
        self._redis.set(key, embedding, ttl=CACHE_TTL["embedding"])


# Singleton embedding cache
_embedding_cache: Optional[EmbeddingCache] = None


def get_embedding_cache() -> EmbeddingCache:
    """Get or create the singleton embedding cache instance."""
    global _embedding_cache
    if _embedding_cache is None:
        _embedding_cache = EmbeddingCache()
    return _embedding_cache
