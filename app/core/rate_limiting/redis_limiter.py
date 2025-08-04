"""
Redis-based distributed rate limiter using sliding window algorithm.

This provides distributed rate limiting across multiple server instances
using Redis as the shared storage for request counters.
"""

import asyncio
import json
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple

import redis.asyncio as redis
from app.core.logging_config import get_logger
from .schemas import RateLimitResult, RateLimitMetadata


class RedisRateLimiter:
    """
    Redis-backed distributed rate limiter using sliding window counters.
    
    Uses Redis sorted sets to track requests within time windows,
    providing accurate distributed rate limiting across multiple instances.
    """
    
    def __init__(
        self,
        redis_client: redis.Redis,
        key_prefix: str = "rate_limit"
    ):
        """
        Initialize Redis rate limiter.
        
        Args:
            redis_client: Async Redis client instance
            key_prefix: Prefix for Redis keys
        """
        self.redis = redis_client
        self.key_prefix = key_prefix
        self.logger = get_logger("redis_rate_limiter")
    
    async def check_rate_limit(
        self,
        identifier: str,
        rpm_limit: int,
        rpd_limit: int,
        model: str = "gemini",
        safety_margin: float = 0.0
    ) -> RateLimitResult:
        self.logger.info(f"Redis rate limit check for {model} (identifier: {identifier})")
        """
        Check if request is within rate limits.
        
        Args:
            identifier: Unique identifier (e.g., "flash", "pro")
            rpm_limit: Requests per minute limit
            rpd_limit: Requests per day limit
            model: Model name for metadata
            safety_margin: Safety margin to apply (0.0 to 1.0)
            
        Returns:
            RateLimitResult with decision and metadata
        """
        now = time.time()
        
        # Apply safety margin
        effective_rpm = int(rpm_limit * (1.0 - safety_margin))
        effective_rpd = int(rpd_limit * (1.0 - safety_margin))
        
        # Check both RPM and RPD limits
        rpm_result = await self._check_sliding_window(
            identifier, "rpm", effective_rpm, 60, now
        )
        
        rpd_result = await self._check_sliding_window(
            identifier, "rpd", effective_rpd, 86400, now  # 24 hours
        )
        
        # Determine if request is allowed
        allowed = rpm_result["allowed"] and rpd_result["allowed"]
        blocked_by = None
        retry_after = None
        
        if not rpm_result["allowed"]:
            blocked_by = "rpm"
            retry_after = 60 - (now % 60)  # Seconds until next minute
        elif not rpd_result["allowed"]:
            blocked_by = "rpd"
            # Calculate seconds until next day
            next_day = datetime.utcnow().replace(
                hour=0, minute=0, second=0, microsecond=0
            ) + timedelta(days=1)
            retry_after = int((next_day - datetime.utcnow()).total_seconds())
        
        # Build metadata
        metadata = RateLimitMetadata(
            rpm_limit=effective_rpm,
            rpm_used=rpm_result["used"],
            rpm_remaining=max(0, effective_rpm - rpm_result["used"]),
            rpd_limit=effective_rpd,
            rpd_used=rpd_result["used"],
            rpd_remaining=max(0, effective_rpd - rpd_result["used"]),
            reset_time_rpm=datetime.fromtimestamp(now + (60 - (now % 60))),
            reset_time_rpd=datetime.utcnow().replace(
                hour=0, minute=0, second=0, microsecond=0
            ) + timedelta(days=1),
            model=model,
            safety_margin=safety_margin
        )
        
        return RateLimitResult(
            allowed=allowed,
            metadata=metadata,
            retry_after=retry_after,
            blocked_by=blocked_by
        )
    
    async def _check_sliding_window(
        self,
        identifier: str,
        window_type: str,  # "rpm" or "rpd"
        limit: int,
        window_seconds: int,
        now: float
    ) -> Dict[str, Any]:
        """
        Check sliding window rate limit using Redis sorted sets.
        
        Args:
            identifier: Rate limit identifier
            window_type: Type of window ("rpm" or "rpd")
            limit: Maximum requests allowed in window
            window_seconds: Window size in seconds
            now: Current timestamp
            
        Returns:
            Dict with "allowed" boolean and "used" count
        """
        key = f"{self.key_prefix}:{identifier}:{window_type}"
        
        # Lua script for atomic rate limit check and increment
        lua_script = """
        local key = KEYS[1]
        local now = tonumber(ARGV[1])
        local cutoff = tonumber(ARGV[2])
        local limit = tonumber(ARGV[3])
        local window_seconds = tonumber(ARGV[4])
        
        -- Remove expired entries
        redis.call('ZREMRANGEBYSCORE', key, 0, cutoff)
        
        -- Count current requests
        local current_count = redis.call('ZCARD', key)
        
        if current_count < limit then
            -- Add current request
            redis.call('ZADD', key, now, tostring(now))
            -- Set expiration
            redis.call('EXPIRE', key, window_seconds + 60)
            return {1, current_count + 1}  -- allowed=true, used=count+1
        else
            return {0, current_count}  -- allowed=false, used=count
        end
        """
        
        try:
            cutoff = now - window_seconds
            result = await self.redis.eval(
                lua_script, 
                1, 
                key, 
                str(now), 
                str(cutoff), 
                str(limit), 
                str(window_seconds)
            )
            
            allowed = bool(result[0])
            used = int(result[1])
            
            return {
                "allowed": allowed,
                "used": used
            }
                
        except Exception as e:
            self.logger.error(f"Redis rate limit check failed: {e}")
            # Fail closed - deny request when Redis is unavailable to prevent free tier overages
            return {
                "allowed": False,
                "used": 0
            }
    
    async def get_current_usage(
        self,
        identifier: str,
        window_seconds: int
    ) -> int:
        """
        Get current usage count for a sliding window.
        
        Args:
            identifier: Rate limit identifier
            window_seconds: Window size in seconds
            
        Returns:
            Current request count in the window
        """
        key = f"{self.key_prefix}:{identifier}"
        now = time.time()
        cutoff = now - window_seconds
        
        try:
            # Clean up and count
            pipe = self.redis.pipeline()
            pipe.zremrangebyscore(key, 0, cutoff)
            pipe.zcard(key)
            results = await pipe.execute()
            return results[1]
            
        except Exception as e:
            self.logger.error(f"Failed to get usage count: {e}")
            return 0
    
    async def reset_limits(self, identifier: str) -> None:
        """
        Reset all rate limits for an identifier.
        
        Args:
            identifier: Rate limit identifier to reset
        """
        pattern = f"{self.key_prefix}:{identifier}:*"
        
        try:
            # Use SCAN to safely iterate over keys in production
            keys_to_delete = []
            cursor = 0
            
            while True:
                cursor, keys = await self.redis.scan(
                    cursor=cursor, 
                    match=pattern, 
                    count=100
                )
                keys_to_delete.extend(keys)
                
                if cursor == 0:
                    break
            
            # Delete collected keys if any found
            if keys_to_delete:
                await self.redis.delete(*keys_to_delete)
                self.logger.info(f"Reset rate limits for {identifier} ({len(keys_to_delete)} keys)")
                
        except Exception as e:
            self.logger.error(f"Failed to reset limits for {identifier}: {e}")
    
    async def get_all_usage_stats(self) -> Dict[str, Dict[str, int]]:
        """
        Get usage statistics for all identifiers.
        
        Returns:
            Dictionary with usage stats for each identifier
        """
        pattern = f"{self.key_prefix}:*"
        stats = {}
        
        try:
            # Use SCAN to safely iterate over keys in production
            cursor = 0
            
            while True:
                cursor, keys = await self.redis.scan(
                    cursor=cursor, 
                    match=pattern, 
                    count=100
                )
                
                for key_bytes in keys:
                    key = key_bytes.decode() if isinstance(key_bytes, bytes) else key_bytes
                    parts = key.split(":")
                    if len(parts) >= 3:
                        identifier = parts[1]
                        window_type = parts[2]
                        
                        count = await self.redis.zcard(key)
                        
                        if identifier not in stats:
                            stats[identifier] = {}
                        stats[identifier][window_type] = count
                
                if cursor == 0:
                    break
                    
        except Exception as e:
            self.logger.error(f"Failed to get usage stats: {e}")
            
        return stats
    
    async def health_check(self) -> bool:
        """
        Check if Redis connection is healthy.
        
        Returns:
            True if Redis is accessible, False otherwise
        """
        try:
            await self.redis.ping()
            return True
        except Exception as e:
            self.logger.error(f"Redis health check failed: {e}")
            return False