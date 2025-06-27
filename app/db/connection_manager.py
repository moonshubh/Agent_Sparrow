"""
Unified Database Connection Manager for FeedMe v2.0
Phase 1: DB Unification - Centralized connection handling for Supabase

This module provides:
- Unified connection pooling for all database operations
- Automatic connection retry with exponential backoff
- Connection health monitoring and auto-recovery
- Support for both sync and async database operations
- Environment-based configuration with Supabase optimization
"""

import os
import logging
import asyncio
from typing import Optional, Dict, Any, List
from contextlib import contextmanager, asynccontextmanager
import psycopg2
import psycopg2.pool
from psycopg2.extras import RealDictCursor, NamedTupleCursor
from pgvector.psycopg2 import register_vector
from dataclasses import dataclass
import time
from functools import wraps

from app.core.settings import settings

logger = logging.getLogger(__name__)

@dataclass
class ConnectionConfig:
    """Configuration for database connections"""
    database_url: str
    min_connections: int = 2
    max_connections: int = 20
    connection_timeout: int = 30
    retry_attempts: int = 3
    retry_delay: float = 1.0
    health_check_interval: int = 300  # 5 minutes
    enable_vector_extension: bool = True


class DatabaseConnectionManager:
    """
    Unified database connection manager for FeedMe v2.0
    
    Provides centralized connection pooling, health monitoring, and
    automatic recovery for all database operations.
    """
    
    def __init__(self, config: Optional[ConnectionConfig] = None):
        self.config = config or self._get_default_config()
        self._pool: Optional[psycopg2.pool.ThreadedConnectionPool] = None
        self._is_healthy = False
        self._last_health_check = 0
        self._connection_stats = {
            "total_connections": 0,
            "active_connections": 0,
            "failed_connections": 0,
            "health_checks": 0,
            "last_error": None
        }
        
        # Initialize connection pool
        self._initialize_pool()
    
    def _get_default_config(self) -> ConnectionConfig:
        """Create default configuration from settings"""
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise ValueError("DATABASE_URL environment variable not set")
        
        return ConnectionConfig(
            database_url=database_url,
            min_connections=getattr(settings, 'feedme_min_db_connections', 2),
            max_connections=getattr(settings, 'feedme_max_db_connections', 20),
            connection_timeout=getattr(settings, 'feedme_db_timeout', 30),
            retry_attempts=getattr(settings, 'feedme_db_retry_attempts', 3),
            retry_delay=getattr(settings, 'feedme_db_retry_delay', 1.0)
        )
    
    def get_raw_connection(self):
        """
        Get a raw connection from the connection pool
        
        Returns:
            A database connection from the pool
            
        Raises:
            RuntimeError: If the connection pool is not initialized
        """
        if not self._pool:
            raise RuntimeError("Database connection pool is not initialized")
        return self._pool.getconn()
        
    def _initialize_pool(self):
        """Initialize the connection pool with retry logic"""
        for attempt in range(self.config.retry_attempts):
            try:
                logger.info(f"Initializing database connection pool (attempt {attempt + 1})")
                
                self._pool = psycopg2.pool.ThreadedConnectionPool(
                    minconn=self.config.min_connections,
                    maxconn=self.config.max_connections,
                    dsn=self.config.database_url,
                    connection_factory=None,
                    cursor_factory=RealDictCursor
                )
                
                # Test connection and register vector extension (avoid recursion)
                conn = self.get_raw_connection()
                try:
                    if self.config.enable_vector_extension:
                        register_vector(conn)
                        logger.info("Registered pgvector extension")
                    
                    # Test basic query
                    with conn.cursor() as cur:
                        cur.execute("SELECT 1 as test_val")
                        result = cur.fetchone()
                        if not result or result['test_val'] != 1:
                            raise Exception("Connection test failed")
                finally:
                    self._pool.putconn(conn)
                
                self._is_healthy = True
                self._last_health_check = time.time()
                logger.info(f"Database connection pool initialized successfully with {self.config.min_connections}-{self.config.max_connections} connections")
                return
                
            except Exception as e:
                self._connection_stats["failed_connections"] += 1
                self._connection_stats["last_error"] = str(e)
                logger.error(f"Failed to initialize connection pool (attempt {attempt + 1}): {e}")
                
                if attempt < self.config.retry_attempts - 1:
                    wait_time = self.config.retry_delay * (2 ** attempt)  # Exponential backoff
                    logger.info(f"Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                else:
                    raise Exception(f"Failed to initialize database connection pool after {self.config.retry_attempts} attempts")
    
    @contextmanager
    def get_connection(self, cursor_factory=None):
        """
        Get a database connection from the pool
        
        Args:
            cursor_factory: Optional cursor factory (RealDictCursor, NamedTupleCursor, etc.)
        
        Yields:
            psycopg2.connection: Database connection
        """
        if not self._pool:
            raise Exception("Connection pool not initialized")
        
        conn = None
        try:
            # Skip health check during initialization to avoid recursion
            if self._is_healthy or self._last_health_check == 0:
                conn = self._pool.getconn()
            else:
                # Check health before getting connection (but not during initialization)
                self._check_health()
                conn = self._pool.getconn()
            if not conn:
                raise Exception("Unable to get connection from pool")
            
            # Set cursor factory if specified
            if cursor_factory:
                conn.cursor_factory = cursor_factory
            
            # Register vector extension for this connection
            if self.config.enable_vector_extension:
                register_vector(conn)
            
            self._connection_stats["total_connections"] += 1
            self._connection_stats["active_connections"] += 1
            
            yield conn
            
        except Exception as e:
            self._connection_stats["failed_connections"] += 1
            self._connection_stats["last_error"] = str(e)
            logger.error(f"Database connection error: {e}")
            
            if conn:
                try:
                    conn.rollback()
                except:
                    pass
            raise
        finally:
            if conn:
                try:
                    self._connection_stats["active_connections"] -= 1
                    self._pool.putconn(conn)
                except Exception as e:
                    logger.error(f"Error returning connection to pool: {e}")
    
    def _check_health(self):
        """Check connection pool health and reconnect if needed"""
        current_time = time.time()
        
        # Only check health periodically
        if current_time - self._last_health_check < self.config.health_check_interval:
            return
        
        try:
            self._connection_stats["health_checks"] += 1
            
            # Test connection with a simple query (avoid recursion)
            conn = self._pool.getconn()
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1 as test_val")
                    result = cur.fetchone()
                    if not result or result['test_val'] != 1:
                        raise Exception("Health check query failed")
            finally:
                self._pool.putconn(conn)
            
            self._is_healthy = True
            self._last_health_check = current_time
            logger.debug("Database health check passed")
            
        except Exception as e:
            self._is_healthy = False
            self._connection_stats["last_error"] = str(e)
            logger.warning(f"Database health check failed: {e}")
            
            # Try to reinitialize pool
            try:
                self._pool.closeall()
                self._initialize_pool()
            except Exception as reinit_error:
                logger.error(f"Failed to reinitialize connection pool: {reinit_error}")
    
    def execute_query(self, query: str, params: tuple = None, fetch_one: bool = False, fetch_all: bool = True) -> Any:
        """
        Execute a query with automatic connection management
        
        Args:
            query: SQL query to execute
            params: Query parameters
            fetch_one: Whether to fetch only one result
            fetch_all: Whether to fetch all results
            
        Returns:
            Query results or None
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params or ())
                
                if fetch_one:
                    return cur.fetchone()
                elif fetch_all:
                    return cur.fetchall()
                else:
                    return None
    
    def execute_transaction(self, queries: List[tuple]) -> bool:
        """
        Execute multiple queries in a transaction
        
        Args:
            queries: List of (query, params) tuples
            
        Returns:
            bool: True if transaction successful, False otherwise
        """
        with self.get_connection() as conn:
            try:
                with conn.cursor() as cur:
                    for query, params in queries:
                        cur.execute(query, params or ())
                
                conn.commit()
                return True
                
            except Exception as e:
                conn.rollback()
                logger.error(f"Transaction failed: {e}")
                return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get connection pool statistics"""
        pool_stats = {}
        if self._pool:
            try:
                # Safe way to get pool statistics without accessing private attributes
                pool_stats = {
                    "pool_minconn": getattr(self._pool, 'minconn', 0),
                    "pool_maxconn": getattr(self._pool, 'maxconn', 0),
                    "is_healthy": self._is_healthy,
                    "last_health_check": self._last_health_check
                }
            except Exception as e:
                logger.warning(f"Could not retrieve pool stats: {e}")
                pool_stats = {
                    "is_healthy": self._is_healthy,
                    "last_health_check": self._last_health_check
                }
        return {**self._connection_stats, **pool_stats}
    
    def close(self):
        """Close all connections in the pool"""
        if self._pool:
            self._pool.closeall()
            logger.info("Database connection pool closed")


# Global connection manager instance
_connection_manager: Optional[DatabaseConnectionManager] = None


def get_connection_manager() -> DatabaseConnectionManager:
    """Get the global connection manager instance"""
    global _connection_manager
    
    if _connection_manager is None:
        _connection_manager = DatabaseConnectionManager()
    
    return _connection_manager


def with_db_connection(cursor_factory=None):
    """
    Decorator for functions that need database connections
    
    Args:
        cursor_factory: Optional cursor factory for the connection
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            manager = get_connection_manager()
            with manager.get_connection(cursor_factory=cursor_factory) as conn:
                return func(conn, *args, **kwargs)
        return wrapper
    return decorator


# Backward compatibility functions
def get_db_connection():
    """Legacy function for backward compatibility"""
    manager = get_connection_manager()
    # Return a context manager for legacy usage
    return manager.get_connection()


# Health check endpoint
def health_check() -> Dict[str, Any]:
    """
    Perform a comprehensive health check of the database connection
    
    Returns:
        Dict containing health status and statistics
    """
    try:
        manager = get_connection_manager()
        stats = manager.get_stats()
        
        # Test basic operations (avoid recursion in health check)
        conn = None
        try:
            conn = manager.get_raw_connection()
            with conn.cursor() as cur:
                # Test basic query
                cur.execute("SELECT 1 as test")
                basic_test = cur.fetchone()["test"] == 1
                
                # Test vector extension
                vector_test = False
                try:
                    cur.execute("SELECT '[1,2,3]'::vector(3)")
                    vector_test = True
                except Exception as e:
                    logger.warning(f"Vector extension test failed: {e}")
                
                # Test FeedMe tables existence
                cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_schema = 'public' 
                        AND table_name = 'feedme_conversations'
                    ) as conversations_exist,
                    EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_schema = 'public' 
                        AND table_name = 'feedme_examples'
                    ) as examples_exist
                """)
                table_check = cur.fetchone()
        finally:
            if conn:
                manager.close_connection(conn)
        
        return {
            "status": "healthy" if all([basic_test, stats["is_healthy"]]) else "unhealthy",
            "basic_query_test": basic_test,
            "vector_extension_test": vector_test,
            "feedme_tables": {
                "conversations_exist": table_check["conversations_exist"],
                "examples_exist": table_check["examples_exist"]
            },
            "connection_stats": stats,
            "timestamp": time.time()
        }
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": time.time()
        }


if __name__ == "__main__":
    # Test the connection manager
    logging.basicConfig(level=logging.INFO)
    
    print("Testing Database Connection Manager...")
    manager = get_connection_manager()
    
    # Test basic connection
    with manager.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT version()")
            version = cur.fetchone()
            print(f"Database version: {version}")
    
    # Test health check
    health = health_check()
    print(f"Health check: {health}")
    
    # Test stats
    stats = manager.get_stats()
    print(f"Connection stats: {stats}")
    
    print("Connection manager test completed successfully!")