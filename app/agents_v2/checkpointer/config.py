"""
Configuration for LangGraph PostgreSQL Checkpointer.
"""

from dataclasses import dataclass, field
from typing import Dict, Any
import os

# Import dict_row at module level for use in methods
try:
    from psycopg.rows import dict_row
except ImportError:
    # Fallback for testing without psycopg - create a proper row factory
    def dict_row(cursor):
        """Fallback row factory that converts rows to dictionaries."""
        def make_row(values):
            if cursor.description is None:
                return values
            columns = [desc.name for desc in cursor.description]
            return dict(zip(columns, values))
        return make_row


def parse_bool_env(value: str, default: bool = False) -> bool:
    """
    Parse boolean environment variable with support for multiple truthy values.
    
    Args:
        value: The string value to parse
        default: Default value if parsing fails
        
    Returns:
        Boolean value
    """
    if not value:
        return default
    
    # Normalize and check for truthy values
    normalized = value.strip().lower()
    truthy_values = {'true', '1', 'yes', 'on', 'enabled'}
    falsy_values = {'false', '0', 'no', 'off', 'disabled'}
    
    if normalized in truthy_values:
        return True
    elif normalized in falsy_values:
        return False
    else:
        return default


@dataclass
class CheckpointerConfig:
    """Configuration for the Supabase/PostgreSQL checkpointer."""
    
    # Database connection
    db_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", ""))
    
    # Connection pool settings
    pool_size: int = 5  # Number of persistent connections
    max_overflow: int = 10  # Maximum overflow connections
    pool_timeout: float = 30.0  # Timeout for getting connection from pool
    pool_recycle: int = 3600  # Recycle connections after 1 hour
    pool_pre_ping: bool = True  # Test connections before using
    
    # Checkpoint optimization
    enable_compression: bool = True  # Compress large checkpoints
    compression_threshold: int = 10240  # Compress if larger than 10KB
    delta_threshold: int = 10  # Create full checkpoint every N versions
    delta_size_threshold: int = 102400  # Force full checkpoint if > 100KB
    
    # Cache settings
    enable_cache: bool = True  # Enable in-memory cache
    cache_ttl: int = 300  # Cache TTL in seconds (5 minutes)
    cache_max_size: int = 100  # Maximum cached checkpoints
    
    # Performance tuning
    batch_size: int = 100  # Batch size for bulk operations
    enable_prepared_statements: bool = True  # Use prepared statements
    statement_cache_size: int = 20  # Number of prepared statements to cache
    
    # Cleanup and maintenance
    cleanup_after_days: int = 30  # Delete checkpoints older than N days
    archive_after_days: int = 7  # Archive threads inactive for N days
    max_checkpoints_per_thread: int = 1000  # Maximum checkpoints per thread
    
    # Monitoring
    enable_metrics: bool = True  # Enable performance metrics
    metrics_sample_rate: float = 0.1  # Sample 10% of operations
    slow_query_threshold: float = 0.1  # Log queries slower than 100ms
    
    # Thread management
    max_active_threads_per_user: int = 10  # Max concurrent threads per user
    thread_timeout_minutes: int = 30  # Auto-pause threads after N minutes
    enable_thread_forking: bool = True  # Allow thread forking
    
    # Security
    enable_ssl: bool = True  # Use SSL for database connection
    ssl_mode: str = "require"  # SSL mode (require, prefer, allow, disable)
    
    # Advanced features
    enable_versioning: bool = True  # Enable checkpoint versioning
    enable_metadata_tracking: bool = True  # Track checkpoint metadata
    enable_access_logging: bool = True  # Log thread access
    
    def to_connection_kwargs(self) -> Dict[str, Any]:
        """Convert config to psycopg connection kwargs."""
        kwargs = {
            "autocommit": False,  # Use transactions
            "row_factory": dict_row,  # Return rows as dicts
        }
        
        # Only include prepare_threshold if prepared statements are enabled
        if self.enable_prepared_statements:
            kwargs["prepare_threshold"] = 5
        
        # Add SSL settings
        if self.enable_ssl:
            kwargs["sslmode"] = self.ssl_mode
        
        return kwargs
    
    def to_pool_kwargs(self) -> Dict[str, Any]:
        """Convert config to connection pool kwargs."""
        pool_kwargs = {
            "min_size": self.pool_size,
            "max_size": self.pool_size + self.max_overflow,
            "timeout": self.pool_timeout,
            "max_idle": self.pool_recycle,
        }
        
        # Only include check if pool_pre_ping is enabled
        if self.pool_pre_ping:
            pool_kwargs["check"] = self._check_connection
        
        return pool_kwargs
    
    @staticmethod
    def _check_connection(conn) -> bool:
        """Check if connection is alive."""
        try:
            conn.execute("SELECT 1")
            return True
        except (Exception,) as e:
            # Log the error for debugging
            import logging
            logging.getLogger(__name__).debug(f"Connection check failed: {e}")
            return False
    
    @classmethod
    def from_env(cls) -> "CheckpointerConfig":
        """Create config from environment variables."""
        return cls(
            db_url=os.getenv("DATABASE_URL", ""),
            pool_size=int(os.getenv("CHECKPOINT_POOL_SIZE", "5")),
            max_overflow=int(os.getenv("CHECKPOINT_POOL_OVERFLOW", "10")),
            enable_compression=parse_bool_env(os.getenv("CHECKPOINT_COMPRESSION", "true"), True),
            delta_threshold=int(os.getenv("CHECKPOINT_DELTA_THRESHOLD", "10")),
            cleanup_after_days=int(os.getenv("CHECKPOINT_CLEANUP_DAYS", "30")),
            enable_cache=parse_bool_env(os.getenv("CHECKPOINT_CACHE", "true"), True),
            cache_ttl=int(os.getenv("CHECKPOINT_CACHE_TTL", "300")),
            enable_metrics=parse_bool_env(os.getenv("CHECKPOINT_METRICS", "true"), True),
            enable_ssl=parse_bool_env(os.getenv("DATABASE_SSL", "true"), True),
        )