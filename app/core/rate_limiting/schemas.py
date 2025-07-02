"""
Schemas for rate limiting data structures.
"""

from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field


class CircuitState(str, Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Blocking requests
    HALF_OPEN = "half_open"  # Testing if service recovered


class RateLimitMetadata(BaseModel):
    """Metadata about rate limit status."""
    
    rpm_limit: int = Field(description="Requests per minute limit")
    rpm_used: int = Field(description="Requests used in current minute")
    rpm_remaining: int = Field(description="Requests remaining in current minute")
    
    rpd_limit: int = Field(description="Requests per day limit")
    rpd_used: int = Field(description="Requests used in current day")
    rpd_remaining: int = Field(description="Requests remaining in current day")
    
    reset_time_rpm: datetime = Field(description="When RPM counter resets")
    reset_time_rpd: datetime = Field(description="When RPD counter resets")
    
    model: str = Field(description="Gemini model name")
    safety_margin: float = Field(default=0.2, description="Safety margin applied")
    
    class Config:
        orm_mode = True


class RateLimitResult(BaseModel):
    """Result of rate limit check."""
    
    allowed: bool = Field(description="Whether request is allowed")
    metadata: RateLimitMetadata = Field(description="Rate limit metadata")
    retry_after: Optional[int] = Field(default=None, description="Seconds to wait before retry")
    blocked_by: Optional[str] = Field(default=None, description="Which limit blocked the request")
    
    class Config:
        orm_mode = True


class CircuitBreakerStatus(BaseModel):
    """Circuit breaker status information."""
    
    state: CircuitState = Field(description="Current circuit breaker state")
    failure_count: int = Field(description="Number of consecutive failures")
    success_count: int = Field(description="Number of consecutive successes in HALF_OPEN")
    last_failure_time: Optional[datetime] = Field(default=None, description="Time of last failure")
    next_attempt_time: Optional[datetime] = Field(default=None, description="When next attempt is allowed")
    
    class Config:
        orm_mode = True
    
    
class UsageStats(BaseModel):
    """Current usage statistics."""
    
    flash_stats: RateLimitMetadata = Field(description="Gemini 2.5 Flash usage stats")
    pro_stats: RateLimitMetadata = Field(description="Gemini 2.5 Pro usage stats")
    
    flash_circuit: CircuitBreakerStatus = Field(description="Flash circuit breaker status")
    pro_circuit: CircuitBreakerStatus = Field(description="Pro circuit breaker status")
    
    total_requests_today: int = Field(description="Total requests across all models today")
    total_requests_this_minute: int = Field(description="Total requests across all models this minute")
    
    uptime_percentage: float = Field(description="Service uptime percentage")
    last_updated: datetime = Field(default_factory=datetime.utcnow, description="When stats were last updated")

    class Config:
        orm_mode = True