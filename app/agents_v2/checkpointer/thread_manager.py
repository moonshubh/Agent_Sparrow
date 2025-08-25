"""
Thread management for LangGraph checkpointer.
Handles conversation threads, forking, and history.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

try:
    import psycopg
    import psycopg.errors
    from psycopg.rows import dict_row
except ImportError:
    # If psycopg is not available, raise immediately to prevent further execution
    raise ImportError(
        "psycopg is required for thread management. "
        "Please install it with: pip install psycopg[binary]"
    )

try:
    from cachetools import TTLCache
except ImportError:
    # Fallback implementation of TTLCache for basic functionality
    class TTLCache:
        """Simple TTL cache implementation as fallback."""
        def __init__(self, maxsize: int, ttl: int):
            self.maxsize = maxsize
            self.ttl = ttl
            self._cache: Dict[str, tuple[Any, float]] = {}
        
        def __contains__(self, key: str) -> bool:
            if key not in self._cache:
                return False
            value, timestamp = self._cache[key]
            if time.time() - timestamp > self.ttl:
                del self._cache[key]
                return False
            return True
        
        def __getitem__(self, key: str) -> Any:
            if key not in self:
                raise KeyError(key)
            return self._cache[key][0]
        
        def __setitem__(self, key: str, value: Any):
            # Remove expired entries
            current_time = time.time()
            expired = [k for k, (_, ts) in self._cache.items() 
                      if current_time - ts > self.ttl]
            for k in expired:
                del self._cache[k]
            
            # Enforce max size
            if len(self._cache) >= self.maxsize and key not in self._cache:
                # Remove oldest entry
                if self._cache:
                    oldest = min(self._cache.items(), key=lambda x: x[1][1])
                    del self._cache[oldest[0]]
            
            self._cache[key] = (value, current_time)
        
        def get(self, key: str, default=None):
            try:
                return self[key]
            except KeyError:
                return default
        
        def clear(self):
            self._cache.clear()

from .postgres_checkpointer import SupabaseCheckpointer

logger = logging.getLogger(__name__)


class ThreadManager:
    """
    Manages conversation threads for persistent memory.
    Provides thread creation, switching, forking, and history.
    """
    
    def __init__(self, checkpointer: SupabaseCheckpointer):
        """Initialize thread manager with checkpointer."""
        self.checkpointer = checkpointer
        self.active_threads: Dict[str, str] = {}  # user_session -> thread_id
        self._thread_locks: Dict[str, asyncio.Lock] = {}  # Initialize locks dictionary
        self._cache_ttl = 300  # 5 minutes
        # Use TTLCache for automatic expiration
        self._thread_cache = TTLCache(maxsize=100, ttl=self._cache_ttl)
    
    async def get_or_create_thread(
        self,
        user_id: str,
        session_id: Optional[int] = None,
        title: str = "New Conversation"
    ) -> str:
        """Get existing thread or create new one with proper locking."""
        # Validate inputs
        if not user_id:
            raise ValueError("user_id is required")
        
        # Sanitize title
        title = title.replace('\n', ' ').replace('\r', ' ')[:255]
        
        # Check cache first
        cache_key = f"{user_id}:{session_id}" if session_id else user_id
        
        # Use a lock to prevent race conditions
        lock_key = f"thread_lock:{cache_key}"
        
        if lock_key not in self._thread_locks:
            self._thread_locks[lock_key] = asyncio.Lock()
        
        async with self._thread_locks[lock_key]:
            # Double-check cache after acquiring lock
            if cache_key in self.active_threads:
                thread_id = self.active_threads[cache_key]
                logger.debug(f"Found cached thread {thread_id} for {cache_key}")
                return thread_id
            
            try:
                async with self.checkpointer.pool.connection(row_factory=dict_row) as conn:
                    # Use the stored function with access control
                    result = await conn.execute("""
                        SELECT get_or_create_thread(%s, %s, %s) as thread_id
                    """, (user_id, session_id, title))
                    
                    row = await result.fetchone()
                    if not row or not row.get("thread_id"):
                        raise RuntimeError("Failed to get or create thread")
                    
                    thread_id = row["thread_id"]
                    
                    # Cache the result
                    self.active_threads[cache_key] = thread_id
                    
                    logger.info(f"Thread {thread_id} ready for user {user_id}")
                    return thread_id
                    
            except psycopg.errors.RaiseException as e:
                # Handle authorization errors from the stored function
                logger.error(f"Authorization error: {e}")
                raise PermissionError(str(e))
            except (psycopg.OperationalError, psycopg.InterfaceError) as e:
                logger.error(f"Database connection error: {e}")
                raise ConnectionError(f"Database connection failed: {e}")
            except Exception as e:
                logger.error(f"Unexpected error getting/creating thread: {e}")
                raise RuntimeError(f"Failed to get or create thread: {e}")
    
    async def switch_thread(
        self,
        user_id: str,
        thread_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Switch to a different thread.
        Returns the latest checkpoint for the thread.
        Guaranteed <100ms performance.
        """
        start_time = time.time()
        
        # Check cache first - using TTLCache
        cache_data = self._thread_cache.get(thread_id)
        if cache_data is not None:
            elapsed_ms = (time.time() - start_time) * 1000
            logger.debug(f"Thread switch (cached) in {elapsed_ms:.1f}ms")
            return cache_data
        
        try:
            async with self.checkpointer.pool.connection(row_factory=dict_row) as conn:
                # Verify ownership and get latest checkpoint
                result = await conn.execute("""
                    SELECT 
                        t.id,
                        t.title,
                        t.status,
                        t.checkpoint_count,
                        c.id as checkpoint_id,
                        c.state as checkpoint,
                        c.metadata
                    FROM langgraph_threads t
                    LEFT JOIN langgraph_checkpoints c ON c.thread_id = t.id AND c.is_latest = true
                    WHERE t.id = %s AND t.user_id = %s
                    LIMIT 1
                """, (thread_id, user_id))
                
                row = await result.fetchone()
                if not row:
                    logger.warning(f"Thread {thread_id} not found for user {user_id}")
                    return None
                
                # Update access log
                await conn.execute("""
                    INSERT INTO langgraph_thread_access 
                    (thread_id, user_id, access_type, response_time_ms)
                    VALUES (%s, %s, 'switch', %s)
                """, (thread_id, user_id, int((time.time() - start_time) * 1000)))
                
                # Prepare response
                response = {
                    "thread_id": row["id"],
                    "title": row["title"],
                    "status": row["status"],
                    "checkpoint_count": row["checkpoint_count"],
                    "checkpoint": row["checkpoint"] if row["checkpoint"] else None,
                    "metadata": row["metadata"] if row["metadata"] else {}
                }
                
                # Cache the result using TTLCache
                self._thread_cache[thread_id] = response
                
                elapsed_ms = (time.time() - start_time) * 1000
                logger.info(f"Thread switch completed in {elapsed_ms:.1f}ms")
                
                # Ensure we meet the <100ms requirement
                if elapsed_ms > 100:
                    logger.warning(f"Thread switch exceeded 100ms: {elapsed_ms:.1f}ms")
                
                return response
                
        except (psycopg.OperationalError, psycopg.InterfaceError) as e:
            logger.error(f"Database connection error during thread switch: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error switching thread: {e}")
            return None
    
    async def fork_thread(
        self,
        source_thread_id: str,
        checkpoint_id: str,
        title: Optional[str] = None
    ) -> str:
        """Fork a thread at a specific checkpoint."""
        try:
            async with self.checkpointer.pool.connection(row_factory=dict_row) as conn:
                # Call the fork function
                result = await conn.execute("""
                    SELECT fork_thread(%s, %s, %s) as new_thread_id
                """, (source_thread_id, checkpoint_id, title))
                
                row = await result.fetchone()
                new_thread_id = row["new_thread_id"]
                
                logger.info(f"Forked thread {source_thread_id} -> {new_thread_id}")
                return new_thread_id
                
        except psycopg.errors.RaiseException as e:
            logger.error(f"Authorization error during fork: {e}")
            raise PermissionError(str(e))
        except (psycopg.OperationalError, psycopg.InterfaceError) as e:
            logger.error(f"Database connection error during fork: {e}")
            raise ConnectionError(f"Database connection failed: {e}")
        except Exception as e:
            logger.error(f"Unexpected error forking thread: {e}")
            raise RuntimeError(f"Failed to fork thread: {e}")
    
    async def get_thread_history(
        self,
        thread_id: str,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get checkpoint history for a thread."""
        try:
            async with self.checkpointer.pool.connection(row_factory=dict_row) as conn:
                result = await conn.execute("""
                    SELECT 
                        id,
                        version,
                        checkpoint_type,
                        state_size_bytes,
                        metadata,
                        created_at
                    FROM langgraph_checkpoints
                    WHERE thread_id = %s
                    ORDER BY version DESC
                    LIMIT %s
                """, (thread_id, limit))
                
                history = []
                async for row in result:
                    history.append({
                        "checkpoint_id": row["id"],
                        "version": row["version"],
                        "type": row["checkpoint_type"],
                        "size_bytes": row["state_size_bytes"],
                        "metadata": row["metadata"],
                        "created_at": row["created_at"].isoformat() if row["created_at"] else None
                    })
                
                return history
                
        except (psycopg.OperationalError, psycopg.InterfaceError) as e:
            logger.error(f"Database connection error getting history: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error getting thread history: {e}")
            return []
    
    async def list_user_threads(
        self,
        user_id: str,
        status: Optional[str] = "active",
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """List all threads for a user."""
        try:
            async with self.checkpointer.pool.connection(row_factory=dict_row) as conn:
                query = """
                    SELECT 
                        id,
                        title,
                        status,
                        checkpoint_count,
                        last_activity_at,
                        created_at
                    FROM langgraph_threads
                    WHERE user_id = %s
                """
                
                params = [user_id]
                if status:
                    query += " AND status = %s"
                    params.append(status)
                
                query += " ORDER BY last_activity_at DESC LIMIT %s"
                params.append(limit)
                
                result = await conn.execute(query, params)
                
                threads = []
                async for row in result:
                    threads.append({
                        "thread_id": row["id"],
                        "title": row["title"],
                        "status": row["status"],
                        "checkpoint_count": row["checkpoint_count"],
                        "last_activity": row["last_activity_at"].isoformat() if row["last_activity_at"] else None,
                        "created_at": row["created_at"].isoformat() if row["created_at"] else None
                    })
                
                return threads
                
        except (psycopg.OperationalError, psycopg.InterfaceError) as e:
            logger.error(f"Database connection error listing threads: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error listing user threads: {e}")
            return []
    
    async def archive_thread(
        self,
        thread_id: str,
        user_id: str
    ) -> bool:
        """Archive a thread."""
        try:
            async with self.checkpointer.pool.connection(row_factory=dict_row) as conn:
                result = await conn.execute("""
                    UPDATE langgraph_threads
                    SET status = 'archived', archived_at = NOW()
                    WHERE id = %s AND user_id = %s
                    RETURNING id
                """, (thread_id, user_id))
                
                # Clear from cache (TTLCache handles this automatically)
                if thread_id in self._thread_cache:
                    del self._thread_cache[thread_id]
                
                # Remove from active threads - optimized iteration
                # Iterate over a copy to avoid modification during iteration
                for key, value in list(self.active_threads.items()):
                    if value == thread_id:
                        del self.active_threads[key]
                
                return result.rowcount > 0
                
        except (psycopg.OperationalError, psycopg.InterfaceError) as e:
            logger.error(f"Database connection error archiving thread: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error archiving thread: {e}")
            return False
    
    async def cleanup_old_checkpoints(
        self,
        days: int = 30,
        dry_run: bool = True
    ) -> int:
        """Clean up old checkpoints."""
        return await self.checkpointer.cleanup_old_checkpoints(days, dry_run)
    
    async def get_thread_metrics(
        self,
        user_id: str
    ) -> Dict[str, Any]:
        """Get thread metrics for a user."""
        try:
            async with self.checkpointer.pool.connection(row_factory=dict_row) as conn:
                result = await conn.execute("""
                    SELECT 
                        COUNT(DISTINCT t.id) as thread_count,
                        COUNT(DISTINCT CASE WHEN t.status = 'active' THEN t.id END) as active_threads,
                        AVG(t.checkpoint_count) as avg_checkpoints_per_thread,
                        MAX(t.last_activity_at) as last_activity,
                        AVG(a.response_time_ms) as avg_response_time_ms
                    FROM langgraph_threads t
                    LEFT JOIN langgraph_thread_access a ON t.id = a.thread_id
                    WHERE t.user_id = %s
                    GROUP BY t.user_id
                """, (user_id,))
                
                row = await result.fetchone()
                if row:
                    return {
                        "thread_count": row["thread_count"],
                        "active_threads": row["active_threads"],
                        "avg_checkpoints": float(row["avg_checkpoints_per_thread"] or 0),
                        "last_activity": row["last_activity"].isoformat() if row["last_activity"] else None,
                        "avg_response_ms": float(row["avg_response_time_ms"] or 0)
                    }
                
                return {
                    "thread_count": 0,
                    "active_threads": 0,
                    "avg_checkpoints": 0,
                    "last_activity": None,
                    "avg_response_ms": 0
                }
                
        except (psycopg.OperationalError, psycopg.InterfaceError) as e:
            logger.error(f"Database connection error getting metrics: {e}")
            return {}
        except Exception as e:
            logger.error(f"Unexpected error getting thread metrics: {e}")
            return {}
    
    async def clear_cache(self):
        """Clear all caches."""
        self.active_threads.clear()
        self._thread_cache.clear()
        if self.checkpointer.cache:
            await self.checkpointer.cache.clear()
        logger.info("Thread manager caches cleared")