"""Redis-backed quota manager for agent services."""
from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional

import redis

from app.core.logging_config import get_logger
from app.core.settings import settings


class QuotaManagerError(RuntimeError):
    """Base error for quota manager operations."""


class QuotaExceededError(QuotaManagerError):
    """Raised when a service exceeds its configured quota."""

    def __init__(self, service: str) -> None:
        super().__init__(f"Quota exceeded for service '{service}'")
        self.service = service


class QuotaManager:
    """Tracks per-service usage using Redis counters."""

    def __init__(
        self,
        redis_client: Optional[redis.Redis] = None,
        key_prefix: str = "ag_unified_quota",
        per_minute_limits: Optional[Dict[str, int]] = None,
        per_day_limits: Optional[Dict[str, int]] = None,
    ) -> None:
        self.logger = get_logger("quota_manager")
        self.redis = redis_client or redis.Redis.from_url(settings.redis_url, decode_responses=True)
        self.redis_client = self.redis  # Expose as redis_client for compatibility
        self.key_prefix = key_prefix
        self.minute_limits = per_minute_limits or {
            "grounding": max(0, settings.grounding_minute_limit),
            "embeddings": 1000,  # Default embedding limit
        }
        self.daily_limits = per_day_limits or {
            "grounding": max(0, settings.grounding_daily_limit),
            "embeddings": 10000,  # Default daily embedding limit
        }

    def check_and_track(self, service: str, increment: int = 1) -> bool:
        """Increment counters and return True if the request is within quota."""

        minute_limit = self.minute_limits.get(service, 0)
        daily_limit = self.daily_limits.get(service, 0)

        if minute_limit <= 0 and daily_limit <= 0:
            return True

        now = datetime.utcnow()
        minute_key = f"{self.key_prefix}:{service}:minute:{now:%Y%m%d%H%M}"
        daily_key = f"{self.key_prefix}:{service}:day:{now:%Y%m%d}"

        try:
            minute_count = self._increment(minute_key, increment, ttl_seconds=120) if minute_limit > 0 else None
            daily_count = self._increment(daily_key, increment, ttl_seconds=86400 + 60) if daily_limit > 0 else None
        except redis.RedisError as exc:  # pragma: no cover - network failure
            self.logger.warning("quota_manager_redis_error", error=str(exc))
            return True  # Fail-open to avoid blocking traffic when Redis is down

        if minute_limit > 0 and (minute_count or 0) > minute_limit:
            self._decrement(minute_key, increment)
            return False
        if daily_limit > 0 and (daily_count or 0) > daily_limit:
            self._decrement(daily_key, increment)
            if minute_limit > 0:
                self._decrement(minute_key, increment)
            return False
        return True

    def check_quota(self, service: str) -> bool:
        """Check if a service is within quota without incrementing."""
        minute_limit = self.minute_limits.get(service, 0)
        daily_limit = self.daily_limits.get(service, 0)

        if minute_limit <= 0 and daily_limit <= 0:
            return True

        now = datetime.utcnow()
        minute_key = f"{self.key_prefix}:{service}:minute:{now:%Y%m%d%H%M}"
        daily_key = f"{self.key_prefix}:{service}:day:{now:%Y%m%d}"

        try:
            if minute_limit > 0:
                minute_count = self.redis.get(minute_key)
                if minute_count and int(minute_count) >= minute_limit:
                    return False

            if daily_limit > 0:
                daily_count = self.redis.get(daily_key)
                if daily_count and int(daily_count) >= daily_limit:
                    return False
        except redis.RedisError as exc:
            self.logger.warning("quota_check_redis_error", error=str(exc))
            return True  # Fail-open

        return True

    def get_usage(self, service: str) -> int:
        """Get current usage count for a service (daily)."""
        now = datetime.utcnow()
        daily_key = f"{self.key_prefix}:{service}:day:{now:%Y%m%d}"

        try:
            count = self.redis.get(daily_key)
            return int(count) if count else 0
        except (redis.RedisError, ValueError) as exc:
            self.logger.warning("quota_get_usage_error", error=str(exc))
            return 0

    def get_limit(self, service: str) -> int:
        """Get configured daily limit for a service."""
        return self.daily_limits.get(service, 0)

    def get_usage_percentage(self, service: str) -> float:
        """Get usage as a percentage of the daily limit."""
        limit = self.get_limit(service)
        if limit <= 0:
            return 0.0

        usage = self.get_usage(service)
        return min(100.0, (usage / limit) * 100)

    def _increment(self, key: str, increment: int, ttl_seconds: int) -> int:
        value = self.redis.incrby(key, increment)
        if value == increment:
            self.redis.expire(key, ttl_seconds)
        return value

    def _decrement(self, key: str, decrement: int) -> None:
        try:
            self.redis.decrby(key, decrement)
        except redis.RedisError:  # pragma: no cover - best effort
            pass
