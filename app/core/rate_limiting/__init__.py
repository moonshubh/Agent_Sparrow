"""
Rate limiting module for MB-Sparrow.

Provides provider-agnostic, bucket-based rate limiting driven by models.yaml.
"""

from .token_bucket import TokenBucket
from .redis_limiter import RedisRateLimiter
from .circuit_breaker import CircuitBreaker
from .bucket_limiter import BucketRateLimiter
from .exceptions import (
    CircuitBreakerOpenException,
    GeminiQuotaExhaustedException,
    GeminiServiceUnavailableException,
    RateLimitExceededException,
)
from .schemas import (
    RateLimitResult,
    RateLimitMetadata,
    CircuitState,
    CircuitBreakerStatus,
    UsageStats,
)
from .config import RateLimitConfig

__all__ = [
    "TokenBucket",
    "RedisRateLimiter",
    "CircuitBreaker",
    "BucketRateLimiter",
    "CircuitState",
    "CircuitBreakerOpenException",
    "GeminiQuotaExhaustedException",
    "GeminiServiceUnavailableException",
    "RateLimitExceededException",
    "RateLimitResult",
    "RateLimitMetadata",
    "CircuitBreakerStatus",
    "UsageStats",
    "RateLimitConfig",
]
