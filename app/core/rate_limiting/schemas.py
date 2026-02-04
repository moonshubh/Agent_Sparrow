"""
Schemas for rate limiting data structures.
"""

from datetime import datetime
from enum import Enum
from typing import Dict, Optional
from pydantic import BaseModel, Field, ConfigDict


class CircuitState(str, Enum):
    """Circuit breaker states."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class RateLimitMetadata(BaseModel):
    """Metadata about rate limit status."""

    bucket: str = Field(description="Rate limiting bucket name")
    model: str = Field(description="Model identifier for the bucket")
    provider: str = Field(description="Model provider")

    rpm_limit: int = Field(description="Requests per minute limit")
    rpm_used: int = Field(description="Requests used in current minute")
    rpm_remaining: int = Field(description="Requests remaining in current minute")

    rpd_limit: int = Field(description="Requests per day limit")
    rpd_used: int = Field(description="Requests used in current day")
    rpd_remaining: int = Field(description="Requests remaining in current day")

    tpm_limit: Optional[int] = Field(
        default=None, description="Tokens per minute limit"
    )
    tpm_used: int = Field(default=0, description="Tokens used in current minute")
    tpm_remaining: Optional[int] = Field(
        default=None, description="Tokens remaining in current minute"
    )

    reset_time_rpm: datetime = Field(description="When RPM counter resets")
    reset_time_rpd: datetime = Field(description="When RPD counter resets")
    reset_time_tpm: Optional[datetime] = Field(
        default=None, description="When TPM counter resets"
    )

    safety_margin: float = Field(default=0.0, description="Safety margin applied")

    model_config = ConfigDict(from_attributes=True)


class RateLimitResult(BaseModel):
    """Result of rate limit check."""

    allowed: bool = Field(description="Whether request is allowed")
    metadata: RateLimitMetadata = Field(description="Rate limit metadata")
    retry_after: Optional[int] = Field(
        default=None, description="Seconds to wait before retry"
    )
    blocked_by: Optional[str] = Field(
        default=None, description="Which limit blocked the request"
    )
    token_identifier: Optional[str] = Field(
        default=None,
        description="Identifier for the reserved slot used for optional release/rollback.",
    )

    model_config = ConfigDict(from_attributes=True)


class CircuitBreakerStatus(BaseModel):
    """Circuit breaker status information."""

    state: CircuitState = Field(description="Current circuit breaker state")
    failure_count: int = Field(description="Number of consecutive failures")
    success_count: int = Field(
        description="Number of consecutive successes in HALF_OPEN"
    )
    last_failure_time: Optional[datetime] = Field(
        default=None, description="Time of last failure"
    )
    next_attempt_time: Optional[datetime] = Field(
        default=None, description="When next attempt is allowed"
    )

    model_config = ConfigDict(from_attributes=True)


class UsageStats(BaseModel):
    """Current usage statistics for all buckets."""

    buckets: Dict[str, RateLimitMetadata] = Field(description="Per-bucket usage stats")
    circuits: Dict[str, CircuitBreakerStatus] = Field(
        description="Per-bucket circuit breaker status"
    )
    total_requests_today: int = Field(
        description="Total requests across all buckets today"
    )
    total_requests_this_minute: int = Field(
        description="Total requests across all buckets this minute"
    )
    uptime_percentage: float = Field(description="Service uptime percentage")
    last_updated: datetime = Field(
        default_factory=datetime.utcnow, description="When stats were last updated"
    )

    model_config = ConfigDict(from_attributes=True)
