"""Quota-aware model health helpers for the unified agent."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Dict, Optional

from loguru import logger

from app.core.rate_limiting.agent_wrapper import get_rate_limiter
from app.core.rate_limiting.schemas import CircuitState, RateLimitMetadata, UsageStats


FLASH_FAMILY = {"gemini-2.5-flash", "gemini-2.5-flash-lite"}
PRO_FAMILY = {"gemini-2.5-pro"}


@dataclass
class ModelHealth:
    model: str
    available: bool
    rpm_used: int
    rpm_limit: int
    rpd_used: int
    rpd_limit: int
    circuit_state: str
    reason: Optional[str] = None

    def as_dict(self) -> Dict[str, Optional[str]]:
        return {
            "model": self.model,
            "available": self.available,
            "rpm_used": self.rpm_used,
            "rpm_limit": self.rpm_limit,
            "rpd_used": self.rpd_used,
            "rpd_limit": self.rpd_limit,
            "circuit_state": self.circuit_state,
            "reason": self.reason,
        }


class ModelQuotaTracker:
    """Thin wrapper around the Gemini rate limiter for read-only health checks."""

    def __init__(self, cache_ttl_seconds: float = 5.0, warning_threshold: float = 0.9) -> None:
        self._limiter = get_rate_limiter()
        self._cache: Optional[UsageStats] = None
        self._cache_ts: float = 0.0
        self._cache_ttl = max(1.0, cache_ttl_seconds)
        self._warning_threshold = warning_threshold
        self._lock = asyncio.Lock()

    async def get_health(self, model: str) -> ModelHealth:
        stats = await self._get_usage_stats()
        base = self._normalize_model(model)

        if base in FLASH_FAMILY:
            metadata = stats.flash_stats
            circuit = stats.flash_circuit
        elif base in PRO_FAMILY:
            metadata = stats.pro_stats
            circuit = stats.pro_circuit
        else:
            logger.warning("ModelQuotaTracker invoked for unsupported model '%s'", model)
            return ModelHealth(
                model=model,
                available=False,
                rpm_used=0,
                rpm_limit=0,
                rpd_used=0,
                rpd_limit=0,
                circuit_state="unknown",
                reason="unsupported_model",
            )

        available, reason = self._evaluate_availability(metadata, circuit.state)
        return ModelHealth(
            model=model,
            available=available,
            rpm_used=metadata.rpm_used,
            rpm_limit=metadata.rpm_limit,
            rpd_used=metadata.rpd_used,
            rpd_limit=metadata.rpd_limit,
            circuit_state=circuit.state.value,
            reason=reason,
        )

    async def _get_usage_stats(self) -> UsageStats:
        now = time.monotonic()
        if self._cache and (now - self._cache_ts) < self._cache_ttl:
            return self._cache

        async with self._lock:
            now = time.monotonic()
            if self._cache and (now - self._cache_ts) < self._cache_ttl:
                return self._cache
            stats = await self._limiter.get_usage_stats()
            self._cache = stats
            self._cache_ts = now
            return stats

    def _normalize_model(self, model: str) -> str:
        normalized = (model or "").strip().lower()
        if normalized in FLASH_FAMILY:
            return "gemini-2.5-flash"
        if normalized in PRO_FAMILY:
            return "gemini-2.5-pro"
        return normalized

    def _evaluate_availability(self, metadata: RateLimitMetadata, circuit_state: CircuitState) -> tuple[bool, Optional[str]]:
        if circuit_state == CircuitState.OPEN:
            return False, "circuit_open"

        rpm_limit = metadata.rpm_limit or 1
        rpd_limit = metadata.rpd_limit or 1
        rpm_ratio = metadata.rpm_used / rpm_limit
        rpd_ratio = metadata.rpd_used / rpd_limit

        if rpm_ratio >= self._warning_threshold:
            return False, "rpm_exhausted"
        if rpd_ratio >= self._warning_threshold:
            return False, "rpd_exhausted"
        return True, None


quota_tracker = ModelQuotaTracker()

