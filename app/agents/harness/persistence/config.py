"""Configuration for the async PostgreSQL checkpointer."""
from dataclasses import dataclass


@dataclass
class CheckpointerConfig:
    """Database connection and behavior settings for checkpointing.

    Attributes:
        db_url: PostgreSQL connection string.
        pool_size: Number of connections to maintain in the pool.
        max_overflow: Maximum connections beyond pool_size.
        enable_compression: Whether to compress large checkpoints.
        delta_threshold: Number of checkpoints before creating a snapshot.
        cleanup_after_days: Age threshold for checkpoint cleanup.
    """
    db_url: str
    pool_size: int = 5
    max_overflow: int = 10
    enable_compression: bool = True
    delta_threshold: int = 10
    cleanup_after_days: int = 30
