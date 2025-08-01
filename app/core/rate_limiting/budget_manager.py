"""
Budget Manager for free-tier rate limiting with per-model RPM/RPD/TPM tracking.

This module implements comprehensive budget management for multiple models with:
- Per-model RPM (requests per minute), RPD (requests per day), TPM (tokens per minute) tracking
- Rolling window tracking with midnight Pacific Time reset
- Model downgrade logic when limits exceeded
- Reserve pools for critical escalations
- Redis-backed persistence for distributed systems
"""

import logging
import asyncio
from typing import Dict, Optional, Tuple, Any
from datetime import datetime, timezone, timedelta
try:
    from zoneinfo import ZoneInfo
except ImportError:
    # Fallback for Python < 3.9
    from backports.zoneinfo import ZoneInfo
import redis.asyncio as redis
from dataclasses import dataclass, field
import json

from app.core.settings import settings
from app.core.rate_limiting.config import RateLimitConfig

logger = logging.getLogger(__name__)

@dataclass
class ModelLimits:
    """Configuration for model-specific rate limits."""
    rpm: int
    rpd: int
    tpm: int = 0  # 0 means no TPM limit
    reserve_pool: int = 0  # Reserved calls for escalations

@dataclass 
class ModelUsage:
    """Current usage stats for a model."""
    rpm_used: int = 0
    rpd_used: int = 0
    tpm_used: int = 0
    last_reset_time: datetime = field(default_factory=lambda: datetime.now(ZoneInfo('US/Pacific')))
    
    def to_dict(self) -> dict:
        """Convert to dictionary for Redis storage."""
        return {
            'rpm_used': self.rpm_used,
            'rpd_used': self.rpd_used,
            'tpm_used': self.tpm_used,
            # Ensure timezone info is preserved in ISO format
            'last_reset_time': self.last_reset_time.isoformat() if self.last_reset_time.tzinfo else self.last_reset_time.replace(tzinfo=ZoneInfo('US/Pacific')).isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'ModelUsage':
        """Create from dictionary loaded from Redis."""
        from dateutil import parser
        pacific_tz = ZoneInfo('US/Pacific')
        
        # Parse datetime preserving timezone info
        reset_time_str = data.get('last_reset_time')
        if reset_time_str:
            try:
                # Use dateutil.parser to correctly parse timezone info
                last_reset_time = parser.isoparse(reset_time_str)
                # Ensure it has timezone info
                if not last_reset_time.tzinfo:
                    last_reset_time = last_reset_time.replace(tzinfo=pacific_tz)
            except:
                last_reset_time = datetime.now(pacific_tz)
        else:
            last_reset_time = datetime.now(pacific_tz)
            
        return cls(
            rpm_used=data.get('rpm_used', 0),
            rpd_used=data.get('rpd_used', 0),
            tpm_used=data.get('tpm_used', 0),
            last_reset_time=last_reset_time
        )

class BudgetManager:
    """
    Manages rate limiting budgets across multiple models with free-tier safety.
    
    Features:
    - Per-model RPM/RPD/TPM tracking with configurable limits
    - Automatic model downgrade when limits exceeded
    - Reserve pools for critical escalations
    - Rolling window tracking with Pacific Time midnight reset
    - Redis persistence for distributed systems
    - Headroom calculation for UI display
    """
    
    # Model hierarchy for downgrades (highest to lowest capability)
    MODEL_HIERARCHY = [
        "gemini-2.5-pro",
        "gemini-2.5-flash",
        "kimi-k2",
        "gemini-2.5-flash-lite"
    ]
    
    # Configurable status thresholds for headroom calculation
    STATUS_THRESHOLD_OK = 0.5  # Above 50% headroom
    STATUS_THRESHOLD_LOW = 0.2  # Above 20% headroom
    
    def __init__(self, config: Optional[RateLimitConfig] = None):
        """Initialize BudgetManager with configuration."""
        self.config = config or RateLimitConfig.from_environment()
        self.redis_client: Optional[redis.Redis] = None
        self._usage_cache: Dict[str, ModelUsage] = {}
        self._lock = asyncio.Lock()
        
        # Model limits configuration (free tier with safety margin)
        self.model_limits = {
            "gemini-2.5-pro": ModelLimits(
                rpm=5,  # Free tier limit
                rpd=100,  # Daily limit
                tpm=0,  # No TPM limit for now
                reserve_pool=20  # Reserve 20 calls for escalations
            ),
            "gemini-2.5-flash": ModelLimits(
                rpm=10,
                rpd=500,
                tpm=0,
                reserve_pool=0  # No reserve needed
            ),
            "gemini-2.5-flash-lite": ModelLimits(
                rpm=15,
                rpd=1000,
                tpm=0,
                reserve_pool=0
            ),
            "kimi-k2": ModelLimits(
                rpm=10,  # Assumed limit
                rpd=100,  # Conservative daily cap
                tpm=0,
                reserve_pool=0
            )
        }
        
        # Pacific timezone for consistent reset timing
        self.pacific_tz = ZoneInfo('US/Pacific')
        
    async def initialize(self):
        """Initialize Redis connection."""
        try:
            self.redis_client = redis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                db=self.config.redis_db,
                decode_responses=True,
                socket_connect_timeout=self.config.redis_connection_timeout,
                socket_timeout=self.config.redis_operation_timeout
            )
            await self.redis_client.ping()
            logger.info("BudgetManager: Redis connection established")
        except Exception as e:
            logger.warning(f"BudgetManager: Redis unavailable, using in-memory tracking: {e}")
            self.redis_client = None
    
    async def _get_usage(self, model: str) -> ModelUsage:
        """Get current usage for a model, handling resets."""
        async with self._lock:
            # Check for midnight reset
            now = datetime.now(self.pacific_tz)
            
            # Try Redis first
            if self.redis_client:
                try:
                    key = f"{self.config.redis_key_prefix}:budget:{model}"
                    data = await self.redis_client.get(key)
                    if data:
                        usage = ModelUsage.from_dict(json.loads(data))
                        
                        # Check if we need to reset (past midnight Pacific)
                        # Properly handle timezone-aware datetime
                        if usage.last_reset_time.tzinfo:
                            last_reset = usage.last_reset_time
                        else:
                            # For zoneinfo, use replace for naive datetime
                            last_reset = usage.last_reset_time.replace(tzinfo=self.pacific_tz)
                        if now.date() > last_reset.date():
                            # Reset daily counters
                            usage.rpd_used = 0
                            usage.last_reset_time = now
                            await self._save_usage(model, usage)
                            logger.info(f"BudgetManager: Reset daily counters for {model}")
                        
                        # Reset minute counters if needed
                        if (now - last_reset).total_seconds() >= 60:
                            usage.rpm_used = 0
                            usage.tpm_used = 0
                            usage.last_reset_time = now
                            await self._save_usage(model, usage)
                            
                        return usage
                except Exception as e:
                    logger.error(f"BudgetManager: Redis error getting usage: {e}")
            
            # Fallback to in-memory cache
            if model not in self._usage_cache:
                self._usage_cache[model] = ModelUsage(last_reset_time=now)
            
            usage = self._usage_cache[model]
            
            # Check for resets
            if now.date() > usage.last_reset_time.date():
                usage.rpd_used = 0
                usage.last_reset_time = now
                
            if (now - usage.last_reset_time).total_seconds() >= 60:
                usage.rpm_used = 0
                usage.tpm_used = 0
                usage.last_reset_time = now
                
            return usage
    
    async def _save_usage(self, model: str, usage: ModelUsage):
        """Save usage to Redis."""
        if self.redis_client:
            try:
                key = f"{self.config.redis_key_prefix}:budget:{model}"
                await self.redis_client.set(
                    key, 
                    json.dumps(usage.to_dict()),
                    ex=86400  # 24 hour expiry
                )
            except Exception as e:
                logger.error(f"BudgetManager: Redis error saving usage: {e}")
    
    async def check_and_record(self, model: str, tokens_in: int = 0, tokens_out: int = 0) -> bool:
        """
        Atomically check if a request is allowed and record usage if so.
        This prevents race conditions between checking and recording.
        
        Args:
            model: Model identifier (e.g., "gemini-2.5-pro")
            tokens_in: Input tokens (for TPM tracking)
            tokens_out: Output tokens (for TPM tracking)
            
        Returns:
            bool: True if request was allowed and recorded, False otherwise
        """
        if model not in self.model_limits:
            logger.error(f"BudgetManager: Unknown model {model}, denying by default")
            return False
            
        async with self._lock:
            limits = self.model_limits[model]
            usage = await self._get_usage(model)
            
            # Check RPM limit
            if usage.rpm_used >= limits.rpm:
                logger.warning(f"BudgetManager: RPM limit exceeded for {model} ({usage.rpm_used}/{limits.rpm})")
                return False
                
            # Check RPD limit (considering reserve pool)
            effective_rpd = limits.rpd - limits.reserve_pool
            if usage.rpd_used >= effective_rpd:
                logger.warning(f"BudgetManager: RPD limit exceeded for {model} ({usage.rpd_used}/{effective_rpd})")
                return False
                
            # Check TPM limit if applicable
            if limits.tpm > 0:
                total_tokens = tokens_in + tokens_out
                if usage.tpm_used + total_tokens > limits.tpm:
                    logger.warning(f"BudgetManager: TPM limit exceeded for {model}")
                    return False
            
            # All checks passed, now record the usage atomically
            usage.rpm_used += 1
            usage.rpd_used += 1
            if limits.tpm > 0:
                usage.tpm_used += tokens_in + tokens_out
                
            # Save to Redis
            await self._save_usage(model, usage)
            
            # Update in-memory cache
            self._usage_cache[model] = usage
            
            logger.debug(f"BudgetManager: Recorded usage for {model} - RPM: {usage.rpm_used}, RPD: {usage.rpd_used}")
            return True
    
    async def allow(self, model: str, tokens_in: int = 0, tokens_out: int = 0) -> bool:
        """
        Check if a request is allowed within budget constraints.
        Note: This method only checks without recording. Use check_and_record() for atomic operations.
        
        Args:
            model: Model identifier (e.g., "gemini-2.5-pro")
            tokens_in: Input tokens (for TPM tracking)
            tokens_out: Output tokens (for TPM tracking)
            
        Returns:
            bool: True if request is allowed, False otherwise
        """
        if model not in self.model_limits:
            logger.error(f"BudgetManager: Unknown model {model}, denying by default")
            return False
            
        limits = self.model_limits[model]
        usage = await self._get_usage(model)
        
        # Check RPM limit
        if usage.rpm_used >= limits.rpm:
            logger.warning(f"BudgetManager: RPM limit exceeded for {model} ({usage.rpm_used}/{limits.rpm})")
            return False
            
        # Check RPD limit (considering reserve pool)
        effective_rpd = limits.rpd - limits.reserve_pool
        if usage.rpd_used >= effective_rpd:
            logger.warning(f"BudgetManager: RPD limit exceeded for {model} ({usage.rpd_used}/{effective_rpd})")
            return False
            
        # Check TPM limit if applicable
        if limits.tpm > 0:
            total_tokens = tokens_in + tokens_out
            if usage.tpm_used + total_tokens > limits.tpm:
                logger.warning(f"BudgetManager: TPM limit exceeded for {model}")
                return False
                
        return True
    
    async def record(self, model: str, tokens_in: int = 0, tokens_out: int = 0):
        """
        Record usage of a model.
        Note: This method only records without checking. Use check_and_record() for atomic operations.
        
        Args:
            model: Model identifier
            tokens_in: Input tokens used
            tokens_out: Output tokens used
        """
        if model not in self.model_limits:
            return
            
        usage = await self._get_usage(model)
        
        # Update counters
        usage.rpm_used += 1
        usage.rpd_used += 1
        if self.model_limits[model].tpm > 0:
            usage.tpm_used += tokens_in + tokens_out
            
        # Save to Redis
        await self._save_usage(model, usage)
        
        # Update in-memory cache
        self._usage_cache[model] = usage
        
        logger.debug(f"BudgetManager: Recorded usage for {model} - RPM: {usage.rpm_used}, RPD: {usage.rpd_used}")
    
    async def pick_allowed(self, requested: str) -> str:
        """
        Pick an allowed model, downgrading if necessary.
        
        Args:
            requested: The requested model
            
        Returns:
            str: The allowed model (may be downgraded)
        """
        # Normalize model name
        if requested not in self.MODEL_HIERARCHY:
            requested = "gemini-2.5-flash"  # Default
            
        # Check if requested model is allowed
        if await self.allow(requested):
            return requested
            
        # Try downgrade path
        if requested in self.MODEL_HIERARCHY:
            current_idx = self.MODEL_HIERARCHY.index(requested)
            for i in range(current_idx + 1, len(self.MODEL_HIERARCHY)):
                downgrade = self.MODEL_HIERARCHY[i]
                if await self.allow(downgrade):
                    logger.info(f"BudgetManager: Downgrading from {requested} to {downgrade}")
                    return downgrade
        
        # If all else fails, return the lowest tier
        return "gemini-2.5-flash-lite"
    
    async def headroom(self, model: str) -> Dict[str, Any]:
        """
        Get headroom information for a model.
        
        Returns:
            dict: Contains usage stats, limits, headroom percentage, and reset time
        """
        if model not in self.model_limits:
            return {
                "status": "unknown",
                "model": model
            }
            
        limits = self.model_limits[model]
        usage = await self._get_usage(model)
        
        # Calculate headroom percentages
        rpm_headroom = max(0, (limits.rpm - usage.rpm_used) / limits.rpm) if limits.rpm > 0 else 1.0
        effective_rpd = limits.rpd - limits.reserve_pool
        rpd_headroom = max(0, (effective_rpd - usage.rpd_used) / effective_rpd) if effective_rpd > 0 else 1.0
        
        # Overall headroom is minimum of all constraints
        overall_headroom = min(rpm_headroom, rpd_headroom)
        
        # Determine status using configurable thresholds
        if overall_headroom > self.STATUS_THRESHOLD_OK:
            status = "OK"
        elif overall_headroom > self.STATUS_THRESHOLD_LOW:
            status = "Low"
        else:
            status = "Exhausted"
            
        # Calculate reset time (midnight Pacific)
        now = datetime.now(self.pacific_tz)
        tomorrow = now.date() + timedelta(days=1)
        reset_time = datetime.combine(tomorrow, datetime.min.time()).replace(tzinfo=self.pacific_tz)
        hours_to_reset = (reset_time - now).total_seconds() / 3600
        
        return {
            "status": status,
            "model": model,
            "rpm_used": usage.rpm_used,
            "rpm_limit": limits.rpm,
            "rpd_used": usage.rpd_used,
            "rpd_limit": effective_rpd,
            "rpd_reserve": limits.reserve_pool,
            "headroom_percent": round(overall_headroom * 100),
            "reset_hours": round(hours_to_reset, 1),
            "reset_time": reset_time.isoformat()
        }
    
    async def get_all_headroom(self) -> Dict[str, Dict[str, Any]]:
        """Get headroom information for all models."""
        result = {}
        for model in self.model_limits:
            result[model] = await self.headroom(model)
        return result
    
    async def can_use_reserve(self, model: str, tokens_in: int = 0, tokens_out: int = 0) -> bool:
        """
        Check if reserve pool can be used and record usage if allowed.
        This is for critical escalations that need to bypass normal limits.
        
        Args:
            model: Model to use from reserve
            tokens_in: Input tokens (for TPM tracking)
            tokens_out: Output tokens (for TPM tracking)
            
        Returns:
            bool: True if reserve usage was allowed and recorded
        """
        if model not in self.model_limits:
            return False
            
        async with self._lock:
            limits = self.model_limits[model]
            if limits.reserve_pool == 0:
                return False
                
            usage = await self._get_usage(model)
            
            # Check RPM limit even for reserve usage
            if usage.rpm_used >= limits.rpm:
                logger.warning(f"BudgetManager: RPM limit exceeded for reserve pool {model}")
                return False
            
            # Check if we're within total limit (including reserve)
            if usage.rpd_used >= limits.rpd:
                logger.warning(f"BudgetManager: Total RPD limit exceeded for {model}, cannot use reserve")
                return False
                
            # Check TPM limit if applicable
            if limits.tpm > 0:
                total_tokens = tokens_in + tokens_out
                if usage.tpm_used + total_tokens > limits.tpm:
                    logger.warning(f"BudgetManager: TPM limit exceeded for reserve pool {model}")
                    return False
            
            # All checks passed, record the usage
            usage.rpm_used += 1
            usage.rpd_used += 1
            if limits.tpm > 0:
                usage.tpm_used += tokens_in + tokens_out
                
            # Save to Redis
            await self._save_usage(model, usage)
            
            # Update in-memory cache
            self._usage_cache[model] = usage
            
            logger.info(f"BudgetManager: Using reserve pool for {model} - RPD: {usage.rpd_used}/{limits.rpd}")
            return True
    
    async def close(self):
        """Close Redis connection."""
        if self.redis_client:
            await self.redis_client.close()