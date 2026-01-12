"""
Configuration for rate limiting system.
"""

from dataclasses import dataclass
import os

from app.core.settings import settings


def parse_boolean_env(value: str) -> bool:
    """
    Parse environment variable as boolean with support for multiple truthy values.

    Recognizes: 'true', '1', 'yes', 'on' (case insensitive) as True
    Everything else as False
    """
    return str(value).lower() in ("true", "1", "yes", "on")


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting infrastructure (provider-agnostic)."""

    # Redis configuration
    redis_url: str = settings.redis_url
    redis_key_prefix: str = "mb_sparrow_rl"
    redis_db: int = 3  # Dedicated database for rate limiting

    # Circuit breaker configuration
    circuit_breaker_enabled: bool = True
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_timeout_seconds: int = 60
    circuit_breaker_success_threshold: int = 3  # Successes needed to close in HALF_OPEN

    # Backpressure configuration
    enable_backpressure: bool = True
    backpressure_max_wait_seconds: int = 8
    backpressure_retry_attempts: int = 3
    backpressure_jitter_seconds: float = 0.35

    # Monitoring configuration
    monitoring_enabled: bool = True
    alert_threshold_percentage: float = 0.9

    # Performance configuration
    redis_connection_timeout: int = 5
    redis_operation_timeout: int = 1
    max_retry_attempts: int = 3
    retry_backoff_factor: float = 0.5

    def __post_init__(self):
        if self.circuit_breaker_failure_threshold <= 0:
            raise ValueError("Circuit breaker failure threshold must be positive")

    @classmethod
    def from_environment(cls) -> "RateLimitConfig":
        """Create configuration from environment variables."""
        return cls(
            redis_url=os.getenv("RATE_LIMIT_REDIS_URL", settings.redis_url),
            redis_key_prefix=os.getenv("RATE_LIMIT_REDIS_PREFIX", "mb_sparrow_rl"),
            redis_db=int(os.getenv("RATE_LIMIT_REDIS_DB", "3")),
            circuit_breaker_enabled=parse_boolean_env(
                os.getenv("CIRCUIT_BREAKER_ENABLED", "true")
            ),
            circuit_breaker_failure_threshold=int(
                os.getenv("CIRCUIT_BREAKER_FAILURE_THRESHOLD", "5")
            ),
            circuit_breaker_timeout_seconds=int(
                os.getenv("CIRCUIT_BREAKER_TIMEOUT", "60")
            ),
            circuit_breaker_success_threshold=int(
                os.getenv("CIRCUIT_BREAKER_SUCCESS_THRESHOLD", "3")
            ),
            enable_backpressure=parse_boolean_env(
                os.getenv("RATE_LIMIT_ENABLE_BACKPRESSURE", "true")
            ),
            backpressure_max_wait_seconds=int(
                os.getenv("RATE_LIMIT_BACKPRESSURE_MAX_WAIT", "8")
            ),
            backpressure_retry_attempts=int(
                os.getenv("RATE_LIMIT_BACKPRESSURE_RETRIES", "3")
            ),
            backpressure_jitter_seconds=float(
                os.getenv("RATE_LIMIT_BACKPRESSURE_JITTER", "0.35")
            ),
            monitoring_enabled=parse_boolean_env(
                os.getenv("RATE_LIMIT_MONITORING_ENABLED", "true")
            ),
            alert_threshold_percentage=float(
                os.getenv("RATE_LIMIT_ALERT_THRESHOLD", "0.9")
            ),
        )
