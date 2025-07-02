"""
Gemini-specific rate limiter that coordinates Redis rate limiting
and circuit breaker protection for Google Gemini API calls.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Callable

import redis.asyncio as redis
from app.core.logging_config import get_logger
from app.core.settings import settings

from .redis_limiter import RedisRateLimiter
from .circuit_breaker import CircuitBreaker
from .config import RateLimitConfig
from .schemas import RateLimitResult, UsageStats, CircuitState, RateLimitMetadata
from .exceptions import (
    RateLimitExceededException,
    CircuitBreakerOpenException,
    GeminiServiceUnavailableException
)


class GeminiRateLimiter:
    """
    Comprehensive rate limiter for Gemini API calls.
    
    Combines Redis-based distributed rate limiting with circuit breaker
    protection to ensure zero free tier overage while maintaining service quality.
    """
    
    def __init__(self, config: Optional[RateLimitConfig] = None):
        """
        Initialize Gemini rate limiter.
        
        Args:
            config: Rate limiting configuration (uses environment defaults if None)
        """
        self.config = config or RateLimitConfig.from_environment()
        self.logger = get_logger("gemini_rate_limiter")
        
        # Initialize Redis client
        self.redis_client = redis.from_url(
            f"{self.config.redis_url}/{self.config.redis_db}",
            decode_responses=True
        )
        
        # Initialize Redis rate limiter
        self.redis_limiter = RedisRateLimiter(
            self.redis_client,
            self.config.redis_key_prefix
        )
        
        # Initialize circuit breakers for each model
        self.circuit_breakers = {
            "gemini-2.5-flash": CircuitBreaker(
                failure_threshold=self.config.circuit_breaker_failure_threshold,
                timeout_seconds=self.config.circuit_breaker_timeout_seconds,
                success_threshold=self.config.circuit_breaker_success_threshold,
                name="flash"
            ),
            "gemini-2.5-pro": CircuitBreaker(
                failure_threshold=self.config.circuit_breaker_failure_threshold,
                timeout_seconds=self.config.circuit_breaker_timeout_seconds,
                success_threshold=self.config.circuit_breaker_success_threshold,
                name="pro"
            )
        }
        
        self.logger.info("GeminiRateLimiter initialized with safety margins")
    
    async def check_and_consume(self, model: str) -> RateLimitResult:
        """
        Check rate limits and consume a token if allowed.
        
        Args:
            model: Gemini model name ("gemini-2.5-flash" or "gemini-2.5-pro")
            
        Returns:
            RateLimitResult indicating if request is allowed
            
        Raises:
            ValueError: If model is not supported
        """
        if model not in ["gemini-2.5-flash", "gemini-2.5-pro"]:
            raise ValueError(f"Unsupported model: {model}")
        
        # Get effective limits for the model
        rpm_limit, rpd_limit = self.config.get_effective_limits(model)
        
        # Determine identifier for Redis keys
        identifier = "flash" if "flash" in model else "pro"
        
        try:
            # Check rate limits
            result = await self.redis_limiter.check_rate_limit(
                identifier=identifier,
                rpm_limit=rpm_limit,
                rpd_limit=rpd_limit,
                model=model,
                safety_margin=self.config.safety_margin
            )
            
            self.logger.debug(
                f"Rate limit check for {model}: allowed={result.allowed}, "
                f"rpm_used={result.metadata.rpm_used}/{result.metadata.rpm_limit}, "
                f"rpd_used={result.metadata.rpd_used}/{result.metadata.rpd_limit}"
            )
            
            return result
            
        except Exception as e:
            self.logger.error(f"Rate limit check failed for {model}: {e}")
            # Fail safe - block request
            raise GeminiServiceUnavailableException(
                f"Rate limiting service unavailable: {e}"
            )
    
    async def execute_with_protection(
        self,
        model: str,
        func: Callable,
        *args,
        **kwargs
    ) -> Any:
        """
        Execute a function with full rate limiting and circuit breaker protection.
        
        Args:
            model: Gemini model name
            func: Function to execute (Gemini API call)
            *args: Function arguments
            **kwargs: Function keyword arguments
            
        Returns:
            Function result
            
        Raises:
            RateLimitExceededException: If rate limit is exceeded
            CircuitBreakerOpenException: If circuit breaker is open
            GeminiServiceUnavailableException: If service is unavailable
        """
        # First check rate limits
        rate_limit_result = await self.check_and_consume(model)
        
        if not rate_limit_result.allowed:
            raise RateLimitExceededException(
                message=f"Rate limit exceeded for {model}",
                retry_after=rate_limit_result.retry_after,
                limits=rate_limit_result.metadata.dict(),
                model=model
            )
        
        # Get circuit breaker for the model
        circuit_breaker = self.circuit_breakers[model]
        
        # Execute with circuit breaker protection
        try:
            result = await circuit_breaker.call(func, *args, **kwargs)
            
            self.logger.debug(f"Successfully executed {model} request")
            return result
            
        except CircuitBreakerOpenException:
            # Circuit breaker is open, don't retry
            raise
        except Exception as e:
            # Log the error and re-raise
            self.logger.error(f"Gemini API call failed for {model}: {e}")
            raise
    
    async def get_usage_stats(self) -> UsageStats:
        """
        Get comprehensive usage statistics.
        
        Returns:
            UsageStats with current usage information
        """
        try:
            # Get rate limit stats
            redis_stats = await self.redis_limiter.get_all_usage_stats()
            
            # Get circuit breaker statuses
            flash_circuit = await self.circuit_breakers["gemini-2.5-flash"].get_status()
            pro_circuit = await self.circuit_breakers["gemini-2.5-pro"].get_status()
            
            # Build metadata for each model
            flash_rpm_limit, flash_rpd_limit = self.config.get_effective_limits("gemini-2.5-flash")
            pro_rpm_limit, pro_rpd_limit = self.config.get_effective_limits("gemini-2.5-pro")
            
            flash_stats = redis_stats.get("flash", {})
            pro_stats = redis_stats.get("pro", {})
            
            now = datetime.utcnow()
            
            # Create comprehensive usage stats
            
            flash_metadata = RateLimitMetadata(
                rpm_limit=flash_rpm_limit,
                rpm_used=flash_stats.get("rpm", 0),
                rpm_remaining=max(0, flash_rpm_limit - flash_stats.get("rpm", 0)),
                rpd_limit=flash_rpd_limit,
                rpd_used=flash_stats.get("rpd", 0),
                rpd_remaining=max(0, flash_rpd_limit - flash_stats.get("rpd", 0)),
                reset_time_rpm=now.replace(second=0, microsecond=0) + timedelta(minutes=1),
                reset_time_rpd=now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1),
                model="gemini-2.5-flash",
                safety_margin=self.config.safety_margin
            )
            
            pro_metadata = RateLimitMetadata(
                rpm_limit=pro_rpm_limit,
                rpm_used=pro_stats.get("rpm", 0),
                rpm_remaining=max(0, pro_rpm_limit - pro_stats.get("rpm", 0)),
                rpd_limit=pro_rpd_limit,
                rpd_used=pro_stats.get("rpd", 0),
                rpd_remaining=max(0, pro_rpd_limit - pro_stats.get("rpd", 0)),
                reset_time_rpm=now.replace(second=0, microsecond=0) + timedelta(minutes=1),
                reset_time_rpd=now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1),
                model="gemini-2.5-pro",
                safety_margin=self.config.safety_margin
            )
            
            # Calculate uptime percentage based on circuit breaker states
            uptime_percentage = 100.0
            if flash_circuit.state == CircuitState.OPEN:
                uptime_percentage -= 50.0  # 50% down if Flash is down
            if pro_circuit.state == CircuitState.OPEN:
                uptime_percentage -= 50.0  # 50% down if Pro is down
            
            total_requests_today = flash_metadata.rpd_used + pro_metadata.rpd_used
            total_requests_this_minute = flash_metadata.rpm_used + pro_metadata.rpm_used
            
            return UsageStats(
                flash_stats=flash_metadata,
                pro_stats=pro_metadata,
                flash_circuit=flash_circuit,
                pro_circuit=pro_circuit,
                total_requests_today=total_requests_today,
                total_requests_this_minute=total_requests_this_minute,
                uptime_percentage=uptime_percentage,
                last_updated=now
            )
            
        except Exception as e:
            self.logger.error(f"Failed to get usage stats: {e}")
            raise GeminiServiceUnavailableException(
                f"Unable to retrieve usage statistics: {e}"
            )
    
    async def reset_limits(self, model: Optional[str] = None) -> None:
        """
        Reset rate limits and circuit breakers.
        
        Args:
            model: Specific model to reset, or None for all models
        """
        if model:
            if model not in self.circuit_breakers:
                raise ValueError(f"Unknown model: {model}")
            
            identifier = "flash" if "flash" in model else "pro"
            await self.redis_limiter.reset_limits(identifier)
            await self.circuit_breakers[model].reset()
            self.logger.info(f"Reset limits for {model}")
        else:
            # Reset all
            await self.redis_limiter.reset_limits("flash")
            await self.redis_limiter.reset_limits("pro")
            
            for cb in self.circuit_breakers.values():
                await cb.reset()
            
            self.logger.info("Reset all rate limits and circuit breakers")
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Comprehensive health check.
        
        Returns:
            Dictionary with health status information
        """
        health = {
            "overall": "healthy",
            "redis": False,
            "circuit_breakers": {},
            "rate_limits": {}
        }
        
        try:
            # Check Redis health
            health["redis"] = await self.redis_limiter.health_check()
            
            # Check circuit breaker states
            for model, cb in self.circuit_breakers.items():
                status = await cb.get_status()
                health["circuit_breakers"][model] = {
                    "state": status.state,
                    "healthy": status.state != CircuitState.OPEN
                }
            
            # Get current usage
            stats = await self.get_usage_stats()
            health["rate_limits"] = {
                "flash": {
                    "rpm_utilization": stats.flash_stats.rpm_used / max(1, stats.flash_stats.rpm_limit),
                    "rpd_utilization": stats.flash_stats.rpd_used / max(1, stats.flash_stats.rpd_limit)
                },
                "pro": {
                    "rpm_utilization": stats.pro_stats.rpm_used / max(1, stats.pro_stats.rpm_limit),
                    "rpd_utilization": stats.pro_stats.rpd_used / max(1, stats.pro_stats.rpd_limit)
                }
            }
            
            # Determine overall health
            if not health["redis"]:
                health["overall"] = "degraded"
            
            for cb_info in health["circuit_breakers"].values():
                if not cb_info["healthy"]:
                    health["overall"] = "degraded"
                    break
            
        except Exception as e:
            health["overall"] = "unhealthy"
            health["error"] = str(e)
            self.logger.error(f"Health check failed: {e}")
        
        return health
    
    async def close(self) -> None:
        """Close Redis connection and cleanup resources."""
        await self.redis_client.close()
        self.logger.info("GeminiRateLimiter closed")