from dataclasses import dataclass


@dataclass
class CheckpointerConfig:
    db_url: str
    pool_size: int = 5
    max_overflow: int = 10
    enable_compression: bool = True
    delta_threshold: int = 10
    cleanup_after_days: int = 30
