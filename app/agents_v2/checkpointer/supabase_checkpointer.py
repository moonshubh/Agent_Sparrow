"""
PostgreSQL/Supabase Checkpointer for LangGraph.
Extends AsyncPostgresSaver with optimizations for production use.
"""

import asyncio
import json
import logging
import time
import zlib
from datetime import datetime, timezone, timedelta
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple
from uuid import uuid4

try:
    import psycopg
    from psycopg_pool import AsyncConnectionPool
    from psycopg.rows import dict_row
except ImportError:
    # For testing without actual psycopg
    psycopg = None
    AsyncConnectionPool = None
    dict_row = dict

from langgraph.checkpoint.base import (
    Checkpoint,
    CheckpointTuple,
    CheckpointMetadata,
    BaseCheckpointSaver,
)

try:
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
except ImportError:
    # Fallback base class for testing
    AsyncPostgresSaver = BaseCheckpointSaver

from .config import CheckpointerConfig

logger = logging.getLogger(__name__)


class CheckpointCache:
    """Thread-safe in-memory cache for recent checkpoints with proper eviction."""
    
    def __init__(self, ttl_seconds: int = 300, max_size: int = 100):
        self.ttl_seconds = ttl_seconds
        self.max_size = max_size
        self._cache: Dict[str, Tuple[CheckpointTuple, float]] = {}
        self._lock = asyncio.Lock()
        self._access_count: Dict[str, int] = {}  # Track access frequency
    
    async def get(self, key: str) -> Optional[CheckpointTuple]:
        """Get checkpoint from cache if not expired."""
        async with self._lock:
            if key in self._cache:
                checkpoint, timestamp = self._cache[key]
                current_time = time.time()
                
                # Check if expired
                if current_time - timestamp >= self.ttl_seconds:
                    del self._cache[key]
                    if key in self._access_count:
                        del self._access_count[key]
                    return None
                
                # Update access count for LRU
                self._access_count[key] = self._access_count.get(key, 0) + 1
                return checkpoint
        return None
    
    async def set(self, key: str, checkpoint: CheckpointTuple):
        """Add checkpoint to cache with LRU eviction."""
        async with self._lock:
            current_time = time.time()
            
            # Clean expired entries first
            expired_keys = [
                k for k, (_, ts) in self._cache.items()
                if current_time - ts >= self.ttl_seconds
            ]
            for k in expired_keys:
                del self._cache[k]
                if k in self._access_count:
                    del self._access_count[k]
            
            # Evict least recently used if cache is full
            if len(self._cache) >= self.max_size:
                # Find least frequently accessed key
                if self._access_count:
                    lru_key = min(self._access_count.keys(), 
                                key=lambda k: (self._access_count[k], self._cache[k][1]))
                else:
                    # Fallback to oldest timestamp
                    lru_key = min(self._cache.keys(), 
                                key=lambda k: self._cache[k][1])
                
                del self._cache[lru_key]
                if lru_key in self._access_count:
                    del self._access_count[lru_key]
            
            # Add new entry
            self._cache[key] = (checkpoint, current_time)
            self._access_count[key] = 1
    
    async def clear(self):
        """Clear all cached checkpoints."""
        async with self._lock:
            self._cache.clear()
            self._access_count.clear()
    
    async def cleanup_expired(self):
        """Remove expired entries from cache."""
        async with self._lock:
            current_time = time.time()
            expired_keys = [
                k for k, (_, ts) in self._cache.items()
                if current_time - ts >= self.ttl_seconds
            ]
            for k in expired_keys:
                del self._cache[k]
                if k in self._access_count:
                    del self._access_count[k]
            
            return len(expired_keys)


class SupabaseCheckpointer(AsyncPostgresSaver):
    """
    PostgreSQL checkpointer optimized for Supabase.
    Extends AsyncPostgresSaver with production optimizations.
    """
    
    def __init__(self, config: CheckpointerConfig):
        """Initialize the checkpointer with configuration."""
        # Initialize parent class first
        super().__init__()
        self.config = config
        self.pool: Optional[AsyncConnectionPool] = None
        self.cache = CheckpointCache(
            ttl_seconds=config.cache_ttl,
            max_size=config.cache_max_size
        ) if config.enable_cache else None
        self._metrics: Dict[str, Any] = {
            "saves": 0,
            "loads": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "total_save_time": 0,
            "total_load_time": 0,
        }
    
    async def setup(self) -> None:
        """Setup database connection pool and tables."""
        # Create connection pool
        self.pool = await self._create_connection_pool()
        
        # Initialize tables
        await self._ensure_tables()
        
        logger.info("SupabaseCheckpointer initialized successfully")
    
    async def _create_connection_pool(self) -> AsyncConnectionPool:
        """Create async connection pool with proper error handling."""
        if not AsyncConnectionPool:
            # Mock for testing
            from unittest.mock import AsyncMock
            return AsyncMock()
        
        pool_kwargs = self.config.to_pool_kwargs()
        conn_kwargs = self.config.to_connection_kwargs()
        
        try:
            pool = AsyncConnectionPool(
                self.config.db_url,
                **pool_kwargs,
                kwargs=conn_kwargs
            )
            
            # Wait for pool initialization with timeout
            await asyncio.wait_for(pool.wait(), timeout=10.0)
            
            # Test the connection
            async with pool.connection() as conn:
                await conn.execute("SELECT 1")
            
            return pool
        except asyncio.TimeoutError:
            logger.error("Connection pool initialization timed out")
            raise RuntimeError("Failed to initialize connection pool: timeout")
        except Exception as e:
            logger.error(f"Failed to create connection pool: {e}")
            raise RuntimeError(f"Failed to initialize connection pool: {e}")
    
    async def _ensure_tables(self) -> None:
        """Ensure checkpointer tables exist."""
        async with self.pool.connection() as conn:
            # Check if tables exist, migration should have created them
            table_exists = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'langgraph_threads'
                )
            """)
            
            if not table_exists:
                logger.warning("Checkpointer tables not found, run migration first")
    
    async def aput(
        self,
        config: Dict[str, Any],
        checkpoint: Checkpoint,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Save a checkpoint with optimization."""
        start_time = time.time()
        
        thread_id = config["configurable"].get("thread_id")
        if not thread_id:
            thread_id = str(uuid4())
            config["configurable"]["thread_id"] = thread_id
        
        try:
            async with self.pool.connection() as conn:
                async with conn.transaction():
                    # Ensure thread exists
                    await self._ensure_thread(conn, thread_id, metadata)
                    
                    # Determine checkpoint type
                    checkpoint_type = await self._determine_checkpoint_type(
                        conn, thread_id, checkpoint
                    )
                    
                    # Compress if needed
                    state_data = checkpoint.dict()
                    if self.config.enable_compression:
                        state_data = self._compress_if_needed(state_data)
                    
                    # Save checkpoint
                    checkpoint_id = await self._save_checkpoint(
                        conn, thread_id, state_data, 
                        checkpoint_type, metadata
                    )
                    
                    # Update cache for this thread instead of clearing all
                    if self.cache:
                        cache_key = f"{thread_id}:latest"
                        checkpoint_tuple = CheckpointTuple(
                            config=config,
                            checkpoint=checkpoint,
                            metadata=metadata or {},
                            parent_config=None
                        )
                        await self.cache.set(cache_key, checkpoint_tuple)
                    
                    # Update metrics
                    if self.config.enable_metrics:
                        elapsed = time.time() - start_time
                        self._metrics["saves"] += 1
                        self._metrics["total_save_time"] += elapsed
                        
                        if elapsed > self.config.slow_query_threshold:
                            logger.warning(f"Slow checkpoint save: {elapsed:.3f}s")
            
            return config
            
        except Exception as e:
            logger.error(f"Error saving checkpoint: {e}")
            raise
    
    async def aget(
        self,
        config: Dict[str, Any]
    ) -> Optional[CheckpointTuple]:
        """Get latest checkpoint with caching."""
        start_time = time.time()
        thread_id = config["configurable"].get("thread_id")
        
        if not thread_id:
            return None
        
        # Check cache first
        cache_key = f"{thread_id}:latest"
        if self.cache:
            cached = await self.cache.get(cache_key)
            if cached:
                if self.config.enable_metrics:
                    self._metrics["cache_hits"] += 1
                return cached
            else:
                if self.config.enable_metrics:
                    self._metrics["cache_misses"] += 1
        
        try:
            async with self.pool.connection() as conn:
                result = await conn.execute("""
                    SELECT * FROM get_latest_checkpoint(%s, %s)
                """, (thread_id, "main"))
                
                row = await result.fetchone()
                if not row:
                    return None
                
                # Decompress if needed
                state = row["state"]
                if isinstance(state, bytes):
                    state = self._decompress(state)
                elif isinstance(state, str):
                    state = json.loads(state)
                
                checkpoint = Checkpoint(**state)
                checkpoint_tuple = CheckpointTuple(
                    config=config,
                    checkpoint=checkpoint,
                    metadata=row.get("metadata", {}),
                    parent_config=None  # TODO: Handle parent
                )
                
                # Cache the result
                if self.cache:
                    await self.cache.set(cache_key, checkpoint_tuple)
                
                # Update metrics
                if self.config.enable_metrics:
                    elapsed = time.time() - start_time
                    self._metrics["loads"] += 1
                    self._metrics["total_load_time"] += elapsed
                
                return checkpoint_tuple
                
        except Exception as e:
            logger.error(f"Error loading checkpoint: {e}")
            return None
    
    async def alist(
        self,
        config: Dict[str, Any],
        limit: Optional[int] = None
    ) -> AsyncIterator[CheckpointTuple]:
        """List checkpoints for a thread."""
        thread_id = config["configurable"].get("thread_id")
        
        if not thread_id:
            return
        
        try:
            async with self.pool.connection() as conn:
                query = """
                    SELECT id, version, state, metadata, created_at
                    FROM langgraph_checkpoints
                    WHERE thread_id = %s
                    ORDER BY version DESC
                """
                
                params = [thread_id]
                if limit:
                    query += " LIMIT %s"
                    params.append(limit)
                
                result = await conn.execute(query, params)
                
                async for row in result:
                    # Decompress if needed
                    state = row["state"]
                    if isinstance(state, bytes):
                        state = self._decompress(state)
                    elif isinstance(state, str):
                        state = json.loads(state)
                    
                    checkpoint = Checkpoint(**state)
                    yield CheckpointTuple(
                        config=config,
                        checkpoint=checkpoint,
                        metadata=row.get("metadata", {}),
                        parent_config=None
                    )
                    
        except Exception as e:
            logger.error(f"Error listing checkpoints: {e}")
    
    async def _ensure_thread(
        self, 
        conn: Any,
        thread_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Ensure thread exists in database."""
        user_id = metadata.get("user_id") if metadata else "anonymous"
        session_id = metadata.get("session_id") if metadata else None
        
        await conn.execute("""
            INSERT INTO langgraph_threads (id, user_id, session_id, title)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE
            SET last_activity_at = NOW()
        """, (thread_id, user_id, session_id, "Conversation"))
    
    async def _determine_checkpoint_type(
        self,
        conn: Any,
        thread_id: str,
        checkpoint: Checkpoint
    ) -> str:
        """Determine if checkpoint should be full or delta."""
        # Get current version count
        result = await conn.execute("""
            SELECT COUNT(*) as count, MAX(version) as max_version
            FROM langgraph_checkpoints
            WHERE thread_id = %s AND channel = 'main'
        """, (thread_id,))
        
        row = await result.fetchone()
        count = row["count"] if row else 0
        
        # Check size
        state_size = len(json.dumps(checkpoint.dict()))
        
        # Determine type
        if count == 0:  # First checkpoint
            return "full"
        elif count % self.config.delta_threshold == 0:  # Every N checkpoints
            return "full"
        elif state_size > self.config.delta_size_threshold:  # Large checkpoint
            return "full"
        else:
            return "delta"
    
    async def _save_checkpoint(
        self,
        conn: Any,
        thread_id: str,
        state_data: Any,
        checkpoint_type: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Save checkpoint to database."""
        checkpoint_id = str(uuid4())
        
        # Convert state to JSON
        if isinstance(state_data, dict):
            state_json = json.dumps(state_data)
        else:
            state_json = state_data
        
        await conn.execute("""
            SELECT save_checkpoint(%s, %s, %s, %s)
        """, (thread_id, state_json, "main", json.dumps(metadata or {})))
        
        return checkpoint_id
    
    def _compress_if_needed(self, data: Dict[str, Any]) -> Any:
        """Compress data if larger than threshold."""
        json_data = json.dumps(data)
        
        if len(json_data) > self.config.compression_threshold:
            compressed = zlib.compress(json_data.encode())
            if len(compressed) < len(json_data) * 0.9:  # Only if >10% savings
                return compressed
        
        return data
    
    def _decompress(self, data: bytes) -> Dict[str, Any]:
        """Decompress data."""
        try:
            decompressed = zlib.decompress(data)
            return json.loads(decompressed)
        except (zlib.error, UnicodeDecodeError) as e:
            # Try as uncompressed JSON
            try:
                return json.loads(data)
            except json.JSONDecodeError:
                logger.error(f"Failed to decompress/decode checkpoint data: {e}")
                raise ValueError("Invalid checkpoint data format")
    
    async def cleanup_old_checkpoints(
        self,
        days: int = 30,
        dry_run: bool = True
    ) -> int:
        """Clean up old checkpoints."""
        async with self.pool.connection() as conn:
            if dry_run:
                result = await conn.execute("""
                    SELECT COUNT(*) as count
                    FROM langgraph_checkpoints
                    WHERE created_at < NOW() - (INTERVAL '1 day' * %s)
                """, (days,))
                row = await result.fetchone()
                return row["count"] if row else 0
            else:
                result = await conn.execute("""
                    DELETE FROM langgraph_checkpoints
                    WHERE created_at < NOW() - (INTERVAL '1 day' * %s)
                    RETURNING id
                """, (days,))
                return result.rowcount
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get performance metrics."""
        metrics = self._metrics.copy()
        
        if metrics["saves"] > 0:
            metrics["avg_save_time"] = metrics["total_save_time"] / metrics["saves"]
        
        if metrics["loads"] > 0:
            metrics["avg_load_time"] = metrics["total_load_time"] / metrics["loads"]
            
        cache_total = metrics["cache_hits"] + metrics["cache_misses"]
        if cache_total > 0:
            metrics["cache_hit_rate"] = metrics["cache_hits"] / cache_total
        
        return metrics
    
    async def close(self) -> None:
        """Close connection pool with proper cleanup."""
        if self.pool:
            try:
                # Clear cache first
                if self.cache:
                    await self.cache.clear()
                
                # Close all connections gracefully
                await asyncio.wait_for(self.pool.close(), timeout=5.0)
                logger.info("SupabaseCheckpointer connection pool closed")
            except asyncio.TimeoutError:
                logger.warning("Connection pool close timed out, forcing shutdown")
                # Force close if graceful close times out
                if hasattr(self.pool, 'terminate'):
                    self.pool.terminate()
            except Exception as e:
                logger.error(f"Error closing connection pool: {e}")
            finally:
                self.pool = None