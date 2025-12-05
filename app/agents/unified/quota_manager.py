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
    """Tracks per-service usage using Redis counters.

    Note: This implementation requires Redis for cross-process safety. In-memory
    limiters are single-process only; ensure `settings.redis_url` is reachable.
    """

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
        # Prefer config-driven limits; fall back to provided overrides or conservative defaults.
        self.minute_limits = per_minute_limits or {
            "grounding": max(0, settings.grounding_minute_limit),
            "embeddings": max(0, getattr(settings, "embeddings_minute_limit", 1000)),
        }
        self.daily_limits = per_day_limits or {
            "grounding": max(0, settings.grounding_daily_limit),
            "embeddings": max(0, getattr(settings, "embeddings_daily_limit", 10000)),
        }

    def check_and_track(self, service: str, increment: int = 1) -> bool:
        """Increment counters and return True if the request is within quota."""
        if increment <= 0:
            self.logger.warning("quota_increment_non_positive", service=service, increment=increment)
            return True

        minute_limit, daily_limit = self._get_limits(service)

        if minute_limit <= 0 and daily_limit <= 0:
            return True

        now = datetime.utcnow()
        minute_key, daily_key = self._build_keys(service, now)

        try:
            minute_count = self._increment(minute_key, increment, ttl_seconds=120) if minute_limit > 0 else None
            daily_count = self._increment(daily_key, increment, ttl_seconds=86400 + 60) if daily_limit > 0 else None
        except redis.RedisError as exc:  # pragma: no cover - network failure
            self.logger.warning("quota_manager_redis_error", error=str(exc))
            return True  # Fail-open to avoid blocking traffic when Redis is down

        if minute_limit > 0 and (minute_count or 0) > minute_limit:
            self._decrement(minute_key, increment)
            self.logger.info("quota_exceeded_minute", service=service, limit=minute_limit)
            return False
        if daily_limit > 0 and (daily_count or 0) > daily_limit:
            self._decrement(daily_key, increment)
            if minute_limit > 0:
                self._decrement(minute_key, increment)
            self.logger.info("quota_exceeded_daily", service=service, limit=daily_limit)
            return False
        return True

    def check_quota(self, service: str) -> bool:
        """Check if a service is within quota without incrementing."""
        minute_limit, daily_limit = self._get_limits(service)

        if minute_limit <= 0 and daily_limit <= 0:
            return True

        now = datetime.utcnow()
        minute_key, daily_key = self._build_keys(service, now)

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
        _, daily_key = self._build_keys(service, now)

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

    def get_status(self, service: str) -> dict:
        """Return current usage/limits for observability."""
        minute_limit, daily_limit = self._get_limits(service)
        usage = self.get_usage(service)
        return {
            "service": service,
            "minute_limit": minute_limit,
            "daily_limit": daily_limit,
            "daily_usage": usage,
            "daily_usage_pct": self.get_usage_percentage(service),
        }

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

    def _build_keys(self, service: str, now: datetime) -> tuple[str, str]:
        """Construct minute and daily keys for the service."""
        minute_key = f"{self.key_prefix}:{service}:minute:{now:%Y%m%d%H%M}"
        daily_key = f"{self.key_prefix}:{service}:day:{now:%Y%m%d}"
        return minute_key, daily_key

    def _get_limits(self, service: str) -> tuple[int, int]:
        """Return (per-minute, per-day) limits for a service."""
        return self.minute_limits.get(service, 0), self.daily_limits.get(service, 0)
