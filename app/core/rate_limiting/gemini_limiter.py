"""
Gemini-specific rate limiter that coordinates Redis rate limiting
and circuit breaker protection for Google Gemini API calls.
"""

import asyncio
import random
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Callable

import redis.asyncio as redis
from app.core.logging_config import get_logger
from app.core.settings import settings
from app.core.config import get_registry, ModelTier, Provider

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

        # Initialize circuit breakers keyed by normalized base names
        # This allows all variants in a family to share a circuit breaker
        # Base names: gemini-3-flash, gemini-3-pro, gemini-2.5-pro, gemini-2.5-flash, gemini-2.5-flash-lite
        base_names = (
            "gemini-3-flash",       # Gemini 3.0 Flash (newest - Dec 2025)
            "gemini-3-pro",
            "gemini-2.5-pro",
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite",
        )

        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        for base_name in base_names:
            # Generate a short name for the circuit breaker
            short_name = base_name.replace("gemini-", "").replace(".", "_")

            self.circuit_breakers[base_name] = CircuitBreaker(
                failure_threshold=self.config.circuit_breaker_failure_threshold,
                timeout_seconds=self.config.circuit_breaker_timeout_seconds,
                success_threshold=self.config.circuit_breaker_success_threshold,
                name=short_name
            )

        self.logger.info(
            "GeminiRateLimiter initialized with %d circuit breakers (by base model family)",
            len(self.circuit_breakers)
        )
    
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
        try:
            base_model = self.config.normalize_model_name(model)
        except ValueError as exc:
            raise ValueError(f"Unsupported model: {model}") from exc

        # Get effective limits for the model family
        rpm_limit, rpd_limit = self.config.get_effective_limits(base_model)
        safety_margin = self.config.get_safety_margin(base_model)

        try:
            # Check rate limits
            result = await self.redis_limiter.check_rate_limit(
                identifier=base_model,
                rpm_limit=rpm_limit,
                rpd_limit=rpd_limit,
                model=model,
                safety_margin=safety_margin,
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

    async def release_slot(self, model: str, token_identifier: Optional[str]) -> None:
        """Undo a provisional rate-limit reservation when a request fails early."""
        if not token_identifier:
            return
        try:
            base_model = self.config.normalize_model_name(model)
        except ValueError:
            return
        try:
            await self.redis_limiter.release(base_model, token_identifier)
        except Exception as exc:  # pragma: no cover - defensive cleanup logging
            self.logger.warning("release_slot_failed", model=model, error=str(exc))
    
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
        # Acquire a slot respecting backpressure when enabled
        rate_limit_result = await self._await_rate_limit_slot(model)
        base_model = self.config.normalize_model_name(model)
        
        # Get circuit breaker for the model
        circuit_breaker = self.circuit_breakers[base_model]
        
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
            gemini_3_flash_circuit = await self.circuit_breakers["gemini-3-flash"].get_status()
            gemini_3_pro_circuit = await self.circuit_breakers["gemini-3-pro"].get_status()
            flash_circuit = await self.circuit_breakers["gemini-2.5-flash"].get_status()
            flash_lite_circuit = await self.circuit_breakers["gemini-2.5-flash-lite"].get_status()
            pro_circuit = await self.circuit_breakers["gemini-2.5-pro"].get_status()

            # Build metadata for each model
            gemini_3_flash_rpm_limit, gemini_3_flash_rpd_limit = self.config.get_effective_limits("gemini-3-flash")
            gemini_3_pro_rpm_limit, gemini_3_pro_rpd_limit = self.config.get_effective_limits("gemini-3-pro")
            flash_rpm_limit, flash_rpd_limit = self.config.get_effective_limits("gemini-2.5-flash")
            flash_lite_rpm_limit, flash_lite_rpd_limit = self.config.get_effective_limits("gemini-2.5-flash-lite")
            pro_rpm_limit, pro_rpd_limit = self.config.get_effective_limits("gemini-2.5-pro")

            gemini_3_flash_stats = redis_stats.get("gemini-3-flash", {})
            gemini_3_pro_stats = redis_stats.get("gemini-3-pro", {})
            flash_stats = redis_stats.get("gemini-2.5-flash", {})
            flash_lite_stats = redis_stats.get("gemini-2.5-flash-lite", {})
            pro_stats = redis_stats.get("gemini-2.5-pro", {})
            
            now = datetime.utcnow()
            
            # Create comprehensive usage stats
            def _build_metadata(model_name: str, rpm_limit: int, rpd_limit: int, stats_bucket: Dict[str, int]) -> RateLimitMetadata:
                safety_margin = self.config.get_safety_margin(model_name)
                effective_rpm_limit = int(rpm_limit * (1.0 - safety_margin))
                effective_rpd_limit = int(rpd_limit * (1.0 - safety_margin))

                return RateLimitMetadata(
                    rpm_limit=effective_rpm_limit,
                    rpm_used=stats_bucket.get("rpm", 0),
                    rpm_remaining=max(0, effective_rpm_limit - stats_bucket.get("rpm", 0)),
                    rpd_limit=effective_rpd_limit,
                    rpd_used=stats_bucket.get("rpd", 0),
                    rpd_remaining=max(0, effective_rpd_limit - stats_bucket.get("rpd", 0)),
                    reset_time_rpm=now.replace(second=0, microsecond=0) + timedelta(minutes=1),
                    reset_time_rpd=now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1),
                    model=model_name,
                    safety_margin=safety_margin
                )

            gemini_3_flash_metadata = _build_metadata("gemini-3-flash", gemini_3_flash_rpm_limit, gemini_3_flash_rpd_limit, gemini_3_flash_stats)
            gemini_3_pro_metadata = _build_metadata("gemini-3-pro", gemini_3_pro_rpm_limit, gemini_3_pro_rpd_limit, gemini_3_pro_stats)
            flash_metadata = _build_metadata("gemini-2.5-flash", flash_rpm_limit, flash_rpd_limit, flash_stats)
            flash_lite_metadata = _build_metadata("gemini-2.5-flash-lite", flash_lite_rpm_limit, flash_lite_rpd_limit, flash_lite_stats)
            pro_metadata = _build_metadata("gemini-2.5-pro", pro_rpm_limit, pro_rpd_limit, pro_stats)

            # Calculate uptime percentage based on circuit breaker states (5 models now)
            uptime_percentage = 100.0
            if gemini_3_flash_circuit.state == CircuitState.OPEN:
                uptime_percentage -= 20.0
            if gemini_3_pro_circuit.state == CircuitState.OPEN:
                uptime_percentage -= 20.0
            if flash_circuit.state == CircuitState.OPEN:
                uptime_percentage -= 20.0
            if flash_lite_circuit.state == CircuitState.OPEN:
                uptime_percentage -= 20.0
            if pro_circuit.state == CircuitState.OPEN:
                uptime_percentage -= 20.0
            uptime_percentage = max(0.0, min(100.0, uptime_percentage))

            total_requests_today = (
                gemini_3_flash_metadata.rpd_used
                + gemini_3_pro_metadata.rpd_used
                + flash_metadata.rpd_used
                + flash_lite_metadata.rpd_used
                + pro_metadata.rpd_used
            )
            total_requests_this_minute = (
                gemini_3_flash_metadata.rpm_used
                + gemini_3_pro_metadata.rpm_used
                + flash_metadata.rpm_used
                + flash_lite_metadata.rpm_used
                + pro_metadata.rpm_used
            )

            return UsageStats(
                gemini_3_flash_stats=gemini_3_flash_metadata,
                gemini_3_flash_circuit=gemini_3_flash_circuit,
                gemini_3_pro_stats=gemini_3_pro_metadata,
                gemini_3_pro_circuit=gemini_3_pro_circuit,
                flash_stats=flash_metadata,
                flash_lite_stats=flash_lite_metadata,
                pro_stats=pro_metadata,
                flash_circuit=flash_circuit,
                flash_lite_circuit=flash_lite_circuit,
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

            identifier = self.config.normalize_model_name(model)
            await self.redis_limiter.reset_limits(identifier)
            await self.circuit_breakers[model].reset()
            self.logger.info(f"Reset limits for {model}")
        else:
            # Reset all models from registry
            for identifier in self.circuit_breakers.keys():
                await self.redis_limiter.reset_limits(identifier)

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
                "gemini-3-flash": {
                    "rpm_utilization": stats.gemini_3_flash_stats.rpm_used / max(1, stats.gemini_3_flash_stats.rpm_limit),
                    "rpd_utilization": stats.gemini_3_flash_stats.rpd_used / max(1, stats.gemini_3_flash_stats.rpd_limit)
                },
                "gemini-3-pro": {
                    "rpm_utilization": stats.gemini_3_pro_stats.rpm_used / max(1, stats.gemini_3_pro_stats.rpm_limit),
                    "rpd_utilization": stats.gemini_3_pro_stats.rpd_used / max(1, stats.gemini_3_pro_stats.rpd_limit)
                },
                "gemini-2.5-flash": {
                    "rpm_utilization": stats.flash_stats.rpm_used / max(1, stats.flash_stats.rpm_limit),
                    "rpd_utilization": stats.flash_stats.rpd_used / max(1, stats.flash_stats.rpd_limit)
                },
                "gemini-2.5-flash-lite": {
                    "rpm_utilization": stats.flash_lite_stats.rpm_used / max(1, stats.flash_lite_stats.rpm_limit),
                    "rpd_utilization": stats.flash_lite_stats.rpd_used / max(1, stats.flash_lite_stats.rpd_limit)
                },
                "gemini-2.5-pro": {
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

    async def _await_rate_limit_slot(self, model: str) -> RateLimitResult:
        """Wait for an available slot before surfacing rate limit errors."""
        attempts = 0
        while True:
            result = await self.check_and_consume(model)
            if result.allowed:
                return result

            if (
                not self.config.enable_backpressure
                or result.blocked_by == "rpd"
                or attempts >= self.config.backpressure_retry_attempts
            ):
                raise RateLimitExceededException(
                    message=f"Rate limit exceeded for {model}",
                    retry_after=result.retry_after,
                    limits=result.metadata.dict(),
                    model=model
                )

            wait_seconds = result.retry_after or self.config.backpressure_max_wait_seconds
            wait_seconds = min(wait_seconds, self.config.backpressure_max_wait_seconds)
            wait_seconds += random.uniform(0, self.config.backpressure_jitter_seconds)
            attempts += 1
            self.logger.warning(
                "Rate limit reached for %s (%s). Waiting %.2fs before retry %d/%d",
                model,
                result.blocked_by,
                wait_seconds,
                attempts,
                self.config.backpressure_retry_attempts
            )
            await asyncio.sleep(wait_seconds)
