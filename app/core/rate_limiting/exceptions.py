"""
Rate limiting exceptions for MB-Sparrow.
"""

from datetime import datetime
from typing import Dict, Any, Optional


class RateLimitException(Exception):
    """Base exception for rate limiting errors."""
    pass


class RateLimitExceededException(RateLimitException):
    """
    Raised when a rate limit is exceeded.
    
    Contains metadata about the current limits and usage.
    """
    
    def __init__(
        self, 
        message: str = "Rate limit exceeded. Please try again later.",
        retry_after: Optional[int] = None,
        limits: Optional[Dict[str, Any]] = None,
        model: Optional[str] = None
    ):
        super().__init__(message)
        self.message = message
        self.retry_after = retry_after
        self.limits = limits or {}
        self.model = model
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for API responses."""
        return {
            "error": "rate_limit_exceeded",
            "message": self.message,
            "retry_after": self.retry_after,
            "limits": self.limits,
            "model": self.model
        }


class GeminiQuotaExhaustedException(RateLimitExceededException):
    """
    Raised when Gemini API quota is exhausted.

    Provides a standardized message for quota exhaustion scenarios.
    """

    def __init__(self, model: str, retry_after: Optional[int] = None):
        message = f"Gemini quota exhausted for {model}; try again shortly"
        super().__init__(message=message, retry_after=retry_after, model=model)


class CircuitBreakerOpenException(RateLimitException):
    """
    Raised when circuit breaker is in OPEN state.
    
    Indicates the service is temporarily unavailable.
    """
    
    def __init__(
        self,
        message: str = "Service temporarily unavailable due to circuit breaker.",
        estimated_recovery: Optional[datetime] = None,
        failure_count: Optional[int] = None
    ):
        super().__init__(message)
        self.message = message
        self.estimated_recovery = estimated_recovery
        self.failure_count = failure_count
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for API responses."""
        return {
            "error": "circuit_breaker_open",
            "message": self.message,
            "estimated_recovery": self.estimated_recovery.isoformat() if self.estimated_recovery else None,
            "failure_count": self.failure_count
        }


class GeminiServiceUnavailableException(RateLimitException):
    """
    Raised when Gemini service is unavailable.
    
    This could be due to network issues, API downtime, or other service issues.
    """
    
    def __init__(
        self,
        message: str = "Gemini service is currently unavailable.",
        service_status: Optional[str] = None,
        retry_after: Optional[int] = None
    ):
        super().__init__(message)
        self.message = message
        self.service_status = service_status
        self.retry_after = retry_after
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for API responses."""
        return {
            "error": "service_unavailable",
            "message": self.message,
            "service_status": self.service_status,
            "retry_after": self.retry_after
        }