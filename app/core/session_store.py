"""
Simplified in-memory session store for small-scale deployments.

This module provides a thread-safe, TTL-aware session storage solution
that eliminates the need for Redis in small deployments (10 users).
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class SessionEntry:
    """Represents a stored session with TTL management."""
    data: Dict[str, Any]
    expires_at: datetime
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_accessed: datetime = field(default_factory=datetime.utcnow)
    access_count: int = 0


class InMemorySessionStore:
    """
    Thread-safe in-memory session store with TTL support.
    
    Designed for small-scale deployments (10 users) where Redis
    overhead is not justified. Includes automatic cleanup of expired sessions.
    """
    
    def __init__(self, 
                 max_sessions: int = 100,
                 default_ttl_seconds: int = 3600,
                 cleanup_interval_seconds: int = 300):
        """
        Initialize the in-memory session store.
        
        Args:
            max_sessions: Maximum number of sessions to store
            default_ttl_seconds: Default TTL for sessions
            cleanup_interval_seconds: Interval for cleanup task
        """
        self._sessions: Dict[str, SessionEntry] = {}
        self._lock = asyncio.Lock()
        self._max_sessions = max_sessions
        self._default_ttl = default_ttl_seconds
        self._cleanup_interval = cleanup_interval_seconds
        self._cleanup_task: Optional[asyncio.Task] = None
        self._stats = {
            'hits': 0,
            'misses': 0,
            'evictions': 0,
            'expirations': 0
        }
        
    async def start(self):
        """Start the background cleanup task."""
        if not self._cleanup_task:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.info("Session store cleanup task started")
    
    async def stop(self):
        """Stop the background cleanup task."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
            logger.info("Session store cleanup task stopped")
    
    async def store(self, 
                   session_id: str, 
                   session_type: str, 
                   data: Any, 
                   ttl: Optional[int] = None) -> None:
        """
        Store a session with optional TTL.
        
        Args:
            session_id: Unique session identifier
            session_type: Type of session (e.g., 'reasoning', 'troubleshooting')
            data: Session data to store
            ttl: Time-to-live in seconds (uses default if None)
        """
        key = f"{session_type}:{session_id}"
        ttl = ttl or self._default_ttl
        expires_at = datetime.utcnow() + timedelta(seconds=ttl)
        
        # Serialize data if needed
        if hasattr(data, 'model_dump'):
            serialized_data = data.model_dump()
        elif hasattr(data, 'dict'):
            serialized_data = data.dict()
        else:
            serialized_data = data
        
        async with self._lock:
            # Check capacity and evict if needed
            if len(self._sessions) >= self._max_sessions and key not in self._sessions:
                # Evict oldest without holding lock during async operation
                oldest_key = self._find_oldest_key()
                if oldest_key:
                    del self._sessions[oldest_key]
                    self._stats['evictions'] += 1
            
            # Store the session
            self._sessions[key] = SessionEntry(
                data=serialized_data,
                expires_at=expires_at
            )
            
        logger.debug(f"Stored session {key} with TTL {ttl}s")
    
    async def get(self, session_id: str, session_type: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a session by ID and type.
        
        Args:
            session_id: Session identifier
            session_type: Type of session
            
        Returns:
            Session data if found and not expired, None otherwise
        """
        key = f"{session_type}:{session_id}"
        
        async with self._lock:
            entry = self._sessions.get(key)
            
            if not entry:
                self._stats['misses'] += 1
                return None
            
            # Check if expired
            if datetime.utcnow() > entry.expires_at:
                del self._sessions[key]
                self._stats['expirations'] += 1
                self._stats['misses'] += 1
                logger.debug(f"Session {key} has expired")
                return None
            
            # Update access stats
            entry.last_accessed = datetime.utcnow()
            entry.access_count += 1
            self._stats['hits'] += 1
            
            return entry.data.copy()
    
    async def delete(self, session_id: str, session_type: str) -> bool:
        """
        Delete a session.
        
        Args:
            session_id: Session identifier
            session_type: Type of session
            
        Returns:
            True if deleted, False if not found
        """
        key = f"{session_type}:{session_id}"
        
        async with self._lock:
            if key in self._sessions:
                del self._sessions[key]
                logger.debug(f"Deleted session {key}")
                return True
            return False
    
    async def extend_ttl(self, session_id: str, session_type: str, additional_seconds: int) -> bool:
        """
        Extend the TTL of an existing session.
        
        Args:
            session_id: Session identifier
            session_type: Type of session
            additional_seconds: Seconds to add to current expiration
            
        Returns:
            True if extended, False if session not found
        """
        key = f"{session_type}:{session_id}"
        
        async with self._lock:
            if key in self._sessions:
                entry = self._sessions[key]
                entry.expires_at = max(
                    entry.expires_at,
                    datetime.utcnow()
                ) + timedelta(seconds=additional_seconds)
                logger.debug(f"Extended TTL for session {key} by {additional_seconds}s")
                return True
            return False
    
    def _find_oldest_key(self) -> Optional[str]:
        """Find the oldest session key by last access time (non-async helper)."""
        if not self._sessions:
            return None
        
        return min(
            self._sessions.keys(),
            key=lambda k: self._sessions[k].last_accessed
        )
    
    async def _cleanup_loop(self):
        """Background task to clean up expired sessions."""
        while True:
            try:
                await asyncio.sleep(self._cleanup_interval)
                await self._cleanup_expired()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")
    
    async def _cleanup_expired(self):
        """Remove all expired sessions."""
        now = datetime.utcnow()
        expired_keys = []
        
        async with self._lock:
            for key, entry in self._sessions.items():
                if now > entry.expires_at:
                    expired_keys.append(key)
            
            for key in expired_keys:
                del self._sessions[key]
                self._stats['expirations'] += 1
        
        if expired_keys:
            logger.info(f"Cleaned up {len(expired_keys)} expired sessions")
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get store statistics."""
        async with self._lock:
            return {
                'total_sessions': len(self._sessions),
                'max_sessions': self._max_sessions,
                'hits': self._stats['hits'],
                'misses': self._stats['misses'],
                'hit_rate': (
                    self._stats['hits'] / max(1, self._stats['hits'] + self._stats['misses'])
                ),
                'evictions': self._stats['evictions'],
                'expirations': self._stats['expirations']
            }
    
    async def clear(self):
        """Clear all sessions."""
        async with self._lock:
            self._sessions.clear()
            logger.info("Cleared all sessions from store")


# Global singleton instance
_session_store: Optional[InMemorySessionStore] = None


def get_session_store() -> InMemorySessionStore:
    """Get or create the global session store instance."""
    global _session_store
    if _session_store is None:
        from app.core.settings import get_settings
        settings = get_settings()
        
        # Configure based on settings
        _session_store = InMemorySessionStore(
            max_sessions=getattr(settings, 'session_store_max_sessions', 100),
            default_ttl_seconds=getattr(settings, 'session_store_default_ttl', 3600),
            cleanup_interval_seconds=getattr(settings, 'session_store_cleanup_interval', 300)
        )
    return _session_store


# Convenience functions that match the Redis interface
async def store_session(session_id: str, session_type: str, state: Any, ttl: int = 3600) -> None:
    """Store a session using the global store."""
    store = get_session_store()
    await store.store(session_id, session_type, state, ttl)


async def get_session(session_id: str, session_type: str) -> Optional[Dict[str, Any]]:
    """Retrieve a session using the global store."""
    store = get_session_store()
    return await store.get(session_id, session_type)


async def delete_session(session_id: str, session_type: str) -> bool:
    """Delete a session using the global store."""
    store = get_session_store()
    return await store.delete(session_id, session_type)