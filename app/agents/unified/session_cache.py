"""Thread-safe session cache with TTL.

This module provides a thread-safe cache for per-session data such as:
- Rewritten queries (to avoid re-calling Gemma helper)
- Reranked search results
- Other session-specific computations

The cache automatically expires entries after the configured TTL.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Generic, Optional, TypeVar

from loguru import logger


# Type variable for cached values
V = TypeVar("V")

# Default configuration
DEFAULT_MAX_SIZE = 1000
DEFAULT_TTL_SECONDS = 3600  # 1 hour
SESSION_CACHE_TTL = 600  # 10 minutes for session-specific data


@dataclass
class CacheEntry(Generic[V]):
    """A single cache entry with timestamp."""

    value: V
    timestamp: float
    hits: int = 0


class ThreadSafeCache(Generic[V]):
    """Thread-safe LRU-like cache with TTL.

    Provides a simple in-memory cache that:
    - Is thread-safe via locking
    - Automatically expires entries after TTL
    - Limits total entries (oldest removed first)

    Usage:
        cache = ThreadSafeCache[str](maxsize=100, ttl=3600)
        cache.set("key", "value")
        value = cache.get("key")  # Returns "value" or None if expired
    """

    def __init__(
        self,
        maxsize: int = DEFAULT_MAX_SIZE,
        ttl: float = DEFAULT_TTL_SECONDS,
    ):
        """Initialize the cache.

        Args:
            maxsize: Maximum number of entries.
            ttl: Time-to-live in seconds.
        """
        self.maxsize = maxsize
        self.ttl = ttl
        self._cache: Dict[str, CacheEntry[V]] = {}
        self._lock = threading.Lock()
        self._stats = CacheStats()

    def get(self, key: str) -> Optional[V]:
        """Get a value from the cache.

        Args:
            key: Cache key.

        Returns:
            Cached value or None if not found/expired.
        """
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._stats.misses += 1
                return None

            # Check expiration
            if time.time() - entry.timestamp > self.ttl:
                del self._cache[key]
                self._stats.misses += 1
                self._stats.expirations += 1
                return None

            entry.hits += 1
            self._stats.hits += 1
            return entry.value

    def set(self, key: str, value: V) -> None:
        """Set a value in the cache.

        Args:
            key: Cache key.
            value: Value to cache.
        """
        with self._lock:
            # Evict if at capacity
            if len(self._cache) >= self.maxsize and key not in self._cache:
                self._evict_oldest()

            self._cache[key] = CacheEntry(value=value, timestamp=time.time())

    def delete(self, key: str) -> bool:
        """Delete a key from the cache.

        Args:
            key: Cache key.

        Returns:
            True if key was present.
        """
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def clear(self) -> None:
        """Clear all entries from the cache."""
        with self._lock:
            self._cache.clear()

    def _evict_oldest(self) -> None:
        """Evict the oldest entry (by timestamp)."""
        if not self._cache:
            return

        oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k].timestamp)
        del self._cache[oldest_key]
        self._stats.evictions += 1

    def prune_expired(self) -> int:
        """Remove all expired entries.

        Returns:
            Number of entries removed.
        """
        with self._lock:
            now = time.time()
            expired = [
                key
                for key, entry in self._cache.items()
                if now - entry.timestamp > self.ttl
            ]
            for key in expired:
                del self._cache[key]
            self._stats.expirations += len(expired)
            return len(expired)

    def get_stats(self) -> "CacheStats":
        """Get cache statistics.

        Returns:
            CacheStats object.
        """
        with self._lock:
            self._stats.size = len(self._cache)
            return self._stats.copy()

    def size(self) -> int:
        """Get the number of entries in the cache (thread-safe).

        Returns:
            Number of cache entries.
        """
        with self._lock:
            return len(self._cache)

    def export_entries(self) -> Dict[str, Dict[str, Any]]:
        """Export all cache entries as a dict (thread-safe).

        Returns:
            Dict of key -> {value, ts} entries.
        """
        with self._lock:
            return {
                key: {"value": entry.value, "ts": entry.timestamp}
                for key, entry in self._cache.items()
            }


@dataclass
class CacheStats:
    """Statistics for cache performance monitoring."""

    hits: int = 0
    misses: int = 0
    evictions: int = 0
    expirations: int = 0
    size: int = 0

    def copy(self) -> "CacheStats":
        """Create a copy of stats."""
        return CacheStats(
            hits=self.hits,
            misses=self.misses,
            evictions=self.evictions,
            expirations=self.expirations,
            size=self.size,
        )

    @property
    def hit_rate(self) -> float:
        """Calculate hit rate."""
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for observability."""
        return {
            "hits": self.hits,
            "misses": self.misses,
            "evictions": self.evictions,
            "expirations": self.expirations,
            "size": self.size,
            "hit_rate": round(self.hit_rate, 3),
        }


class SessionCache:
    """Per-session cache with automatic cleanup.

    Manages separate caches for each session, with automatic
    expiration of inactive sessions.

    Usage:
        cache = SessionCache()
        cache.set("session-123", "rewrite:query", "rewritten query")
        value = cache.get("session-123", "rewrite:query")
    """

    def __init__(
        self,
        session_ttl: float = SESSION_CACHE_TTL,
        max_sessions: int = 1000,
        entries_per_session: int = 100,
    ):
        """Initialize the session cache.

        Args:
            session_ttl: TTL for session data.
            max_sessions: Maximum number of sessions to track.
            entries_per_session: Maximum entries per session.
        """
        self.session_ttl = session_ttl
        self.max_sessions = max_sessions
        self.entries_per_session = entries_per_session
        self._sessions: Dict[str, ThreadSafeCache[Any]] = {}
        self._session_timestamps: Dict[str, float] = {}
        self._lock = threading.Lock()

    def get(self, session_id: str, key: str) -> Optional[Any]:
        """Get a value from a session cache.

        Args:
            session_id: Session identifier.
            key: Cache key within the session.

        Returns:
            Cached value or None.
        """
        with self._lock:
            session_cache = self._sessions.get(session_id)
            if session_cache is None:
                return None
            self._session_timestamps[session_id] = time.time()
            return session_cache.get(key)

    def set(self, session_id: str, key: str, value: Any) -> None:
        """Set a value in a session cache.

        Args:
            session_id: Session identifier.
            key: Cache key within the session.
            value: Value to cache.
        """
        with self._lock:
            # Evict old sessions if at capacity
            if session_id not in self._sessions and len(self._sessions) >= self.max_sessions:
                self._evict_oldest_session()

            # Create session cache if needed
            if session_id not in self._sessions:
                self._sessions[session_id] = ThreadSafeCache(
                    maxsize=self.entries_per_session,
                    ttl=self.session_ttl,
                )

            self._sessions[session_id].set(key, value)
            self._session_timestamps[session_id] = time.time()

    def get_session_data(self, session_id: str) -> Dict[str, Dict[str, Any]]:
        """Get all data for a session (for backwards compatibility).

        Args:
            session_id: Session identifier.

        Returns:
            Dict of key -> {value, ts} for the session.
        """
        with self._lock:
            session_cache = self._sessions.get(session_id)
            if session_cache is None:
                return {}

            # Use thread-safe export method to access cache entries
            return session_cache.export_entries()

    def clear_session(self, session_id: str) -> None:
        """Clear all data for a session.

        Args:
            session_id: Session identifier.
        """
        with self._lock:
            self._sessions.pop(session_id, None)
            self._session_timestamps.pop(session_id, None)

    def _evict_oldest_session(self) -> None:
        """Evict the oldest session."""
        if not self._session_timestamps:
            return

        oldest_session = min(
            self._session_timestamps.keys(),
            key=lambda s: self._session_timestamps[s],
        )
        self._sessions.pop(oldest_session, None)
        self._session_timestamps.pop(oldest_session, None)
        logger.debug("session_cache_evicted", session_id=oldest_session)

    def prune_expired_sessions(self) -> int:
        """Remove all expired sessions.

        Returns:
            Number of sessions removed.
        """
        with self._lock:
            now = time.time()
            expired = [
                session_id
                for session_id, timestamp in self._session_timestamps.items()
                if now - timestamp > self.session_ttl
            ]
            for session_id in expired:
                self._sessions.pop(session_id, None)
                self._session_timestamps.pop(session_id, None)
            return len(expired)

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dict of stats for observability.
        """
        with self._lock:
            # Use thread-safe size() method instead of accessing _cache directly
            total_entries = sum(
                cache.size() for cache in self._sessions.values()
            )
            return {
                "active_sessions": len(self._sessions),
                "total_entries": total_entries,
                "max_sessions": self.max_sessions,
                "entries_per_session": self.entries_per_session,
            }


# Global session cache instance with thread-safe initialization
_session_cache: Optional[SessionCache] = None
_session_cache_lock = threading.Lock()


def get_session_cache() -> SessionCache:
    """Get the global session cache instance (thread-safe singleton).

    Uses double-checked locking to ensure thread-safe initialization
    while minimizing lock contention after initialization.

    Returns:
        SessionCache instance.
    """
    global _session_cache
    # First check without lock (fast path)
    if _session_cache is not None:
        return _session_cache

    # Double-checked locking for thread-safe initialization
    with _session_cache_lock:
        # Check again under lock
        if _session_cache is None:
            _session_cache = SessionCache()
        return _session_cache


def get_session_data(session_id: Optional[str]) -> Dict[str, Dict[str, Any]]:
    """Get session data (backwards compatible helper).

    Args:
        session_id: Session identifier.

    Returns:
        Session data dict.
    """
    if not session_id:
        return {}
    return get_session_cache().get_session_data(session_id)
