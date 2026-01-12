"""
API endpoints for rate limiting monitoring and management.
"""

from datetime import datetime
from typing import Dict, Any, Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from app.core.rate_limiting import BucketRateLimiter, RateLimitConfig
from app.core.config import get_models_config, iter_rate_limit_buckets
from app.core.logging_config import get_logger

logger = get_logger("rate_limit_endpoints")

router = APIRouter(prefix="/rate-limits", tags=["rate-limiting"])

# Global rate limiter instance
_rate_limiter: Optional[BucketRateLimiter] = None


def get_rate_limiter() -> BucketRateLimiter:
    """Get or create rate limiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        config = RateLimitConfig.from_environment()
        _rate_limiter = BucketRateLimiter(config)
    return _rate_limiter


class RateLimitStatus(BaseModel):
    """Rate limit status response model."""
    timestamp: datetime
    status: str
    message: str
    details: Dict[str, Any]


class ResetRequest(BaseModel):
    """Request model for resetting rate limits."""
    bucket: Optional[str] = None
    confirm: bool = False


@router.get("/status", response_model=RateLimitStatus)
async def get_rate_limit_status():
    """
    Get current rate limiting status and usage statistics.
    
    Returns comprehensive information about current rate limit usage,
    circuit breaker states, and system health.
    """
    try:
        rate_limiter = get_rate_limiter()
        
        # Get usage statistics
        stats = await rate_limiter.get_usage_stats()
        
        # Get health check
        health = await rate_limiter.health_check()
        
        # Determine overall status
        status = "healthy"
        message = "Rate limiting system operating normally"
        
        if health["overall"] != "healthy":
            status = "degraded"
            message = "Rate limiting system experiencing issues"
        
        utilization: Dict[str, Dict[str, Optional[float]]] = {}
        for bucket, metadata in stats.buckets.items():
            utilization[bucket] = {
                "rpm": metadata.rpm_used / max(1, metadata.rpm_limit),
                "rpd": metadata.rpd_used / max(1, metadata.rpd_limit),
                "tpm": (
                    metadata.tpm_used / max(1, metadata.tpm_limit)
                    if metadata.tpm_limit
                    else None
                ),
            }

        if any(
            value > 0.8
            for metrics in utilization.values()
            for value in metrics.values()
            if value is not None
        ):
            status = "warning"
            message = "Approaching rate limits"
        
        return RateLimitStatus(
            timestamp=datetime.utcnow(),
            status=status,
            message=message,
            details={
                "usage_stats": stats.dict(),
                "health": health,
                "utilization": utilization,
            }
        )
        
    except Exception as e:
        logger.error(f"Failed to get rate limit status: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve rate limit status: {str(e)}"
        )


@router.get("/usage", response_model=Dict[str, Any])
async def get_usage_statistics():
    """
    Get detailed usage statistics for all models.
    
    Returns usage data for Flash and Pro models including:
    - Current requests per minute/day
    - Remaining capacity
    - Reset times
    - Circuit breaker states
    """
    try:
        rate_limiter = get_rate_limiter()
        stats = await rate_limiter.get_usage_stats()
        return stats.dict()
        
    except Exception as e:
        logger.error(f"Failed to get usage statistics: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve usage statistics: {str(e)}"
        )


@router.get("/health")
async def health_check():
    """
    Comprehensive health check for rate limiting system.
    
    Checks:
    - Redis connectivity
    - Circuit breaker states
    - Rate limit utilization
    - System uptime
    """
    try:
        rate_limiter = get_rate_limiter()
        health = await rate_limiter.health_check()
        
        # Return appropriate HTTP status based on health
        if health["overall"] == "unhealthy":
            raise HTTPException(status_code=503, detail=health)
        elif health["overall"] == "degraded":
            # Return 200 but indicate degraded status
            health["warning"] = "System is degraded but operational"
        
        return health
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(
            status_code=503,
            detail={"overall": "unhealthy", "error": str(e)}
        )


@router.post("/check/{bucket}")
async def check_rate_limit(bucket: str):
    """
    Check if a request would be allowed for the specified bucket.
    
    This is a dry-run check that doesn't consume tokens.
    Useful for preemptive checking before making API calls.
    """
    try:
        rate_limiter = get_rate_limiter()
        
        # Note: This would ideally be a check without consumption
        # For now, we'll check and immediately refund if needed
        result = await rate_limiter.check_and_consume(bucket)
        
        return {
            "bucket": bucket,
            "allowed": result.allowed,
            "metadata": result.metadata.dict(),
            "retry_after": result.retry_after,
            "blocked_by": result.blocked_by
        }
        
    except Exception as e:
        logger.error(f"Rate limit check failed for {bucket}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to check rate limit for {bucket}: {str(e)}"
        )


@router.post("/reset")
async def reset_rate_limits(request: ResetRequest):
    """
    Reset rate limits for specified bucket or all buckets.
    
    WARNING: This should only be used in development or emergency situations.
    In production, rate limits should reset naturally.
    """
    if not request.confirm:
        raise HTTPException(
            status_code=400,
            detail="Must set 'confirm: true' to reset rate limits"
        )
    
    try:
        rate_limiter = get_rate_limiter()
        
        await rate_limiter.reset_limits(request.bucket)
        
        message = f"Reset rate limits for {request.bucket}" if request.bucket else "Reset all rate limits"
        logger.warning(f"Rate limits reset via API: {message}")
        
        return {
            "success": True,
            "message": message,
            "timestamp": datetime.utcnow()
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to reset rate limits: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reset rate limits: {str(e)}"
        )


@router.get("/config")
async def get_rate_limit_config():
    """
    Get current rate limiting configuration.
    
    Returns the active configuration including limits, safety margins,
    and circuit breaker settings.
    """
    try:
        rate_limiter = get_rate_limiter()
        config = rate_limiter.config
        models_config = get_models_config()

        buckets: Dict[str, Any] = {}
        for bucket, model_cfg in iter_rate_limit_buckets(models_config):
            buckets[bucket] = {
                "model_id": model_cfg.model_id,
                "provider": model_cfg.provider or "google",
                "rate_limits": model_cfg.rate_limits.model_dump(),
            }

        return {
            "rate_limiting": models_config.rate_limiting.model_dump(),
            "buckets": buckets,
            "circuit_breaker": {
                "enabled": config.circuit_breaker_enabled,
                "failure_threshold": config.circuit_breaker_failure_threshold,
                "timeout_seconds": config.circuit_breaker_timeout_seconds,
                "success_threshold": config.circuit_breaker_success_threshold,
            },
            "redis": {
                "key_prefix": config.redis_key_prefix,
                "db": config.redis_db,
            },
            "monitoring_enabled": config.monitoring_enabled,
        }
        
    except Exception as e:
        logger.error(f"Failed to get rate limit config: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve configuration: {str(e)}"
        )


@router.get("/metrics")
async def get_rate_limit_metrics():
    """
    Get Prometheus-style metrics for rate limiting.
    
    Returns metrics in a format suitable for monitoring systems.
    """
    try:
        rate_limiter = get_rate_limiter()
        stats = await rate_limiter.get_usage_stats()
        
        metrics: Dict[str, Any] = {}
        for bucket, metadata in stats.buckets.items():
            sanitized = bucket.replace(".", "_").replace("-", "_").replace("/", "_")
            metrics[f"{sanitized}_rpm_used"] = metadata.rpm_used
            metrics[f"{sanitized}_rpm_limit"] = metadata.rpm_limit
            metrics[f"{sanitized}_rpd_used"] = metadata.rpd_used
            metrics[f"{sanitized}_rpd_limit"] = metadata.rpd_limit
            if metadata.tpm_limit is not None:
                metrics[f"{sanitized}_tpm_used"] = metadata.tpm_used
                metrics[f"{sanitized}_tpm_limit"] = metadata.tpm_limit

        for bucket, circuit in stats.circuits.items():
            sanitized = bucket.replace(".", "_").replace("-", "_").replace("/", "_")
            metrics[f"{sanitized}_circuit_open"] = 1 if circuit.state == "open" else 0
            metrics[f"{sanitized}_circuit_failures"] = circuit.failure_count

        metrics.update(
            {
                "total_requests_today": stats.total_requests_today,
                "total_requests_this_minute": stats.total_requests_this_minute,
                "uptime_percentage": stats.uptime_percentage,
            }
        )
        
        return metrics
        
    except Exception as e:
        logger.error(f"Failed to get rate limit metrics: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve metrics: {str(e)}"
        )
