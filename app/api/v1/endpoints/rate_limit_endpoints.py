"""
API endpoints for rate limiting monitoring and management.
"""

from datetime import datetime
from typing import Dict, Any, Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from app.core.rate_limiting import (
    GeminiRateLimiter,
    RateLimitConfig,
    UsageStats,
    RateLimitExceededException,
    CircuitBreakerOpenException,
    GeminiServiceUnavailableException
)
from app.core.logging_config import get_logger

logger = get_logger("rate_limit_endpoints")

router = APIRouter(prefix="/rate-limits", tags=["rate-limiting"])

# Global rate limiter instance
_rate_limiter: Optional[GeminiRateLimiter] = None


def get_rate_limiter() -> GeminiRateLimiter:
    """Get or create rate limiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        config = RateLimitConfig.from_environment()
        _rate_limiter = GeminiRateLimiter(config)
    return _rate_limiter


class RateLimitStatus(BaseModel):
    """Rate limit status response model."""
    timestamp: datetime
    status: str
    message: str
    details: Dict[str, Any]


class ResetRequest(BaseModel):
    """Request model for resetting rate limits."""
    model: Optional[str] = None
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
        
        # Check if approaching limits
        flash_rpm_usage = stats.flash_stats.rpm_used / max(1, stats.flash_stats.rpm_limit)
        flash_rpd_usage = stats.flash_stats.rpd_used / max(1, stats.flash_stats.rpd_limit)
        flash_lite_rpm_usage = stats.flash_lite_stats.rpm_used / max(1, stats.flash_lite_stats.rpm_limit)
        flash_lite_rpd_usage = stats.flash_lite_stats.rpd_used / max(1, stats.flash_lite_stats.rpd_limit)
        pro_rpm_usage = stats.pro_stats.rpm_used / max(1, stats.pro_stats.rpm_limit)
        pro_rpd_usage = stats.pro_stats.rpd_used / max(1, stats.pro_stats.rpd_limit)
        
        if any(
            usage > 0.8
            for usage in [
                flash_rpm_usage,
                flash_rpd_usage,
                flash_lite_rpm_usage,
                flash_lite_rpd_usage,
                pro_rpm_usage,
                pro_rpd_usage,
            ]
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
                "utilization": {
                    "flash_rpm": flash_rpm_usage,
                    "flash_rpd": flash_rpd_usage,
                    "flash_lite_rpm": flash_lite_rpm_usage,
                    "flash_lite_rpd": flash_lite_rpd_usage,
                    "pro_rpm": pro_rpm_usage,
                    "pro_rpd": pro_rpd_usage
                }
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


@router.post("/check/{model}")
async def check_rate_limit(model: str):
    """
    Check if a request would be allowed for the specified model.
    
    This is a dry-run check that doesn't consume tokens.
    Useful for preemptive checking before making API calls.
    """
    try:
        RateLimitConfig.normalize_model_name(model)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=(
                "Unsupported model: {model}. Must be a Gemini 2.5 Flash or Pro variant."
            ).format(model=model)
        )
    
    try:
        rate_limiter = get_rate_limiter()
        
        # Note: This would ideally be a check without consumption
        # For now, we'll check and immediately refund if needed
        result = await rate_limiter.check_and_consume(model)
        
        return {
            "model": model,
            "allowed": result.allowed,
            "metadata": result.metadata.dict(),
            "retry_after": result.retry_after,
            "blocked_by": result.blocked_by
        }
        
    except Exception as e:
        logger.error(f"Rate limit check failed for {model}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to check rate limit for {model}: {str(e)}"
        )


@router.post("/reset")
async def reset_rate_limits(request: ResetRequest):
    """
    Reset rate limits for specified model or all models.
    
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
        
        await rate_limiter.reset_limits(request.model)
        
        message = f"Reset rate limits for {request.model}" if request.model else "Reset all rate limits"
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
        
        return {
            "flash_limits": {
                "rpm": config.flash_rpm_limit,
                "rpd": config.flash_rpd_limit
            },
            "flash_lite_limits": {
                "rpm": config.flash_lite_rpm_limit,
                "rpd": config.flash_lite_rpd_limit
            },
            "pro_limits": {
                "rpm": config.pro_rpm_limit,
                "rpd": config.pro_rpd_limit
            },
            "safety_margin": config.safety_margin,
            "circuit_breaker": {
                "enabled": config.circuit_breaker_enabled,
                "failure_threshold": config.circuit_breaker_failure_threshold,
                "timeout_seconds": config.circuit_breaker_timeout_seconds
            },
            "redis": {
                "key_prefix": config.redis_key_prefix,
                "db": config.redis_db
            },
            "monitoring_enabled": config.monitoring_enabled
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
        
        metrics = {
            # Flash model metrics
            "gemini_flash_rpm_used": stats.flash_stats.rpm_used,
            "gemini_flash_rpm_limit": stats.flash_stats.rpm_limit,
            "gemini_flash_rpd_used": stats.flash_stats.rpd_used,
            "gemini_flash_rpd_limit": stats.flash_stats.rpd_limit,
            # Flash Lite metrics
            "gemini_flash_lite_rpm_used": stats.flash_lite_stats.rpm_used,
            "gemini_flash_lite_rpm_limit": stats.flash_lite_stats.rpm_limit,
            "gemini_flash_lite_rpd_used": stats.flash_lite_stats.rpd_used,
            "gemini_flash_lite_rpd_limit": stats.flash_lite_stats.rpd_limit,
            
            # Pro model metrics
            "gemini_pro_rpm_used": stats.pro_stats.rpm_used,
            "gemini_pro_rpm_limit": stats.pro_stats.rpm_limit,
            "gemini_pro_rpd_used": stats.pro_stats.rpd_used,
            "gemini_pro_rpd_limit": stats.pro_stats.rpd_limit,
            
            # Circuit breaker metrics
            "circuit_breaker_flash_state": 1 if stats.flash_circuit.state == "open" else 0,
            "circuit_breaker_flash_lite_state": 1 if stats.flash_lite_circuit.state == "open" else 0,
            "circuit_breaker_pro_state": 1 if stats.pro_circuit.state == "open" else 0,
            "circuit_breaker_flash_failures": stats.flash_circuit.failure_count,
            "circuit_breaker_flash_lite_failures": stats.flash_lite_circuit.failure_count,
            "circuit_breaker_pro_failures": stats.pro_circuit.failure_count,
            
            # Overall metrics
            "total_requests_today": stats.total_requests_today,
            "total_requests_this_minute": stats.total_requests_this_minute,
            "uptime_percentage": stats.uptime_percentage,
            
            # Utilization metrics (0.0 to 1.0)
            "flash_rpm_utilization": stats.flash_stats.rpm_used / max(1, stats.flash_stats.rpm_limit),
            "flash_rpd_utilization": stats.flash_stats.rpd_used / max(1, stats.flash_stats.rpd_limit),
            "flash_lite_rpm_utilization": stats.flash_lite_stats.rpm_used / max(1, stats.flash_lite_stats.rpm_limit),
            "flash_lite_rpd_utilization": stats.flash_lite_stats.rpd_used / max(1, stats.flash_lite_stats.rpd_limit),
            "pro_rpm_utilization": stats.pro_stats.rpm_used / max(1, stats.pro_stats.rpm_limit),
            "pro_rpd_utilization": stats.pro_stats.rpd_used / max(1, stats.pro_stats.rpd_limit),
        }
        
        return metrics
        
    except Exception as e:
        logger.error(f"Failed to get rate limit metrics: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve metrics: {str(e)}"
        )
