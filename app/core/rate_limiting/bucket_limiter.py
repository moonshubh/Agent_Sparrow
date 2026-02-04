"""Bucket-based rate limiter backed by models.yaml quotas."""

from __future__ import annotations

import asyncio
import random
import time
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Optional, Iterator, Tuple

import redis.asyncio as redis

from app.core.config import (
    get_models_config,
    iter_rate_limit_buckets,
    resolve_bucket_config,
)
from app.core.logging_config import get_logger

from .circuit_breaker import CircuitBreaker
from .config import RateLimitConfig
from .exceptions import (
    CircuitBreakerOpenException,
    RateLimitExceededException,
    GeminiServiceUnavailableException,
)
from .redis_limiter import RedisRateLimiter
from .schemas import (
    CircuitState,
    CircuitBreakerStatus,
    RateLimitMetadata,
    RateLimitResult,
    UsageStats,
)


class BucketRateLimiter:
    """Provider-agnostic rate limiter for model usage buckets."""

    def __init__(self, config: Optional[RateLimitConfig] = None) -> None:
        self.config = config or RateLimitConfig.from_environment()
        self.logger = get_logger("bucket_rate_limiter")

        self.redis_client = redis.from_url(
            f"{self.config.redis_url}/{self.config.redis_db}",
            decode_responses=True,
        )
        self.redis_limiter = RedisRateLimiter(
            self.redis_client,
            self.config.redis_key_prefix,
        )
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}

    async def check_and_consume(
        self,
        bucket: str,
        *,
        token_count: Optional[int] = None,
    ) -> RateLimitResult:
        config = get_models_config()
        model_cfg = resolve_bucket_config(config, bucket)
        safety_margin = config.rate_limiting.safety_margin

        try:
            result = await self.redis_limiter.check_rate_limit(
                bucket,
                model_cfg.rate_limits.rpm,
                model_cfg.rate_limits.rpd,
                model=model_cfg.model_id,
                provider=model_cfg.provider or "google",
                safety_margin=safety_margin,
            )
        except Exception as exc:
            self.logger.error("rate_limit_check_failed", bucket=bucket, error=str(exc))
            raise GeminiServiceUnavailableException(
                f"Rate limiting service unavailable: {exc}"
            ) from exc

        if not result.allowed:
            return result

        tpm_limit = model_cfg.rate_limits.tpm
        if tpm_limit and token_count is not None:
            tpm_result = await self._check_tpm(
                bucket,
                model_cfg,
                token_count,
                safety_margin,
                rpm_metadata=result.metadata,
                token_identifier=result.token_identifier,
            )
            if not tpm_result.allowed:
                if result.token_identifier is not None:
                    await self.redis_limiter.release(bucket, result.token_identifier)
                return tpm_result

            result = tpm_result

        return result

    async def release_slot(self, bucket: str, token_identifier: Optional[str]) -> None:
        if token_identifier is None:
            return
        try:
            await self.redis_limiter.release(bucket, token_identifier)
        except Exception as exc:  # pragma: no cover
            self.logger.warning("release_slot_failed", bucket=bucket, error=str(exc))

    async def execute_with_protection(
        self,
        bucket: str,
        func: Callable,
        *args,
        token_count: Optional[int] = None,
        **kwargs,
    ) -> Any:
        rate_limit_result = await self._await_rate_limit_slot(
            bucket, token_count=token_count
        )
        circuit_breaker = self._get_circuit_breaker(bucket)

        try:
            return await circuit_breaker.call(func, *args, **kwargs)
        except CircuitBreakerOpenException:
            raise
        except Exception as exc:
            self.logger.error("bucket_call_failed", bucket=bucket, error=str(exc))
            raise
        finally:
            if rate_limit_result.token_identifier is None:
                return

    async def get_usage_stats(self) -> UsageStats:
        config = get_models_config()
        safety_margin = config.rate_limiting.safety_margin
        now = datetime.utcnow()

        redis_stats = await self.redis_limiter.get_all_usage_stats()
        buckets: Dict[str, RateLimitMetadata] = {}
        circuits: Dict[str, CircuitBreakerStatus] = {}

        total_requests_today = 0
        total_requests_this_minute = 0

        for bucket, model_cfg in self._iter_bucket_configs(config):
            rpm_used = int(redis_stats.get(bucket, {}).get("rpm", 0))
            rpd_used = int(redis_stats.get(bucket, {}).get("rpd", 0))
            tpm_limit = model_cfg.rate_limits.tpm
            tpm_used = await self._get_tpm_usage(bucket) if tpm_limit else 0

            effective_rpm = int(model_cfg.rate_limits.rpm * (1.0 - safety_margin))
            effective_rpd = int(model_cfg.rate_limits.rpd * (1.0 - safety_margin))
            effective_tpm = (
                int(tpm_limit * (1.0 - safety_margin)) if tpm_limit else None
            )

            metadata = RateLimitMetadata(
                bucket=bucket,
                model=model_cfg.model_id,
                provider=model_cfg.provider or "google",
                rpm_limit=effective_rpm,
                rpm_used=rpm_used,
                rpm_remaining=max(0, effective_rpm - rpm_used),
                rpd_limit=effective_rpd,
                rpd_used=rpd_used,
                rpd_remaining=max(0, effective_rpd - rpd_used),
                tpm_limit=effective_tpm,
                tpm_used=tpm_used,
                tpm_remaining=(
                    max(0, effective_tpm - tpm_used) if effective_tpm else None
                ),
                reset_time_rpm=now.replace(second=0, microsecond=0)
                + timedelta(minutes=1),
                reset_time_rpd=now.replace(hour=0, minute=0, second=0, microsecond=0)
                + timedelta(days=1),
                reset_time_tpm=(
                    now.replace(second=0, microsecond=0) + timedelta(minutes=1)
                    if effective_tpm is not None
                    else None
                ),
                safety_margin=safety_margin,
            )
            buckets[bucket] = metadata

            circuit = await self._get_circuit_breaker(bucket).get_status()
            circuits[bucket] = circuit

            total_requests_today += rpd_used
            total_requests_this_minute += rpm_used

        uptime_percentage = self._calculate_uptime(circuits)

        return UsageStats(
            buckets=buckets,
            circuits=circuits,
            total_requests_today=total_requests_today,
            total_requests_this_minute=total_requests_this_minute,
            uptime_percentage=uptime_percentage,
            last_updated=now,
        )

    async def reset_limits(self, bucket: Optional[str] = None) -> None:
        if bucket:
            await self.redis_limiter.reset_limits(bucket)
            if bucket in self._circuit_breakers:
                await self._circuit_breakers[bucket].reset()
            return

        config = get_models_config()
        for bucket_name, _ in self._iter_bucket_configs(config):
            await self.redis_limiter.reset_limits(bucket_name)
        for breaker in self._circuit_breakers.values():
            await breaker.reset()

    async def health_check(self) -> Dict[str, Any]:
        health: Dict[str, Any] = {
            "overall": "healthy",
            "redis": False,
            "circuit_breakers": {},
            "rate_limits": {},
        }

        try:
            health["redis"] = await self.redis_limiter.health_check()
            stats = await self.get_usage_stats()

            for bucket, circuit in stats.circuits.items():
                health["circuit_breakers"][bucket] = {
                    "state": circuit.state,
                    "healthy": circuit.state != CircuitState.OPEN,
                }
            for bucket, metadata in stats.buckets.items():
                rpm_util = metadata.rpm_used / max(1, metadata.rpm_limit)
                rpd_util = metadata.rpd_used / max(1, metadata.rpd_limit)
                health["rate_limits"][bucket] = {
                    "rpm_utilization": rpm_util,
                    "rpd_utilization": rpd_util,
                }

            if not health["redis"]:
                health["overall"] = "degraded"
            for cb_info in health["circuit_breakers"].values():
                if not cb_info["healthy"]:
                    health["overall"] = "degraded"
                    break

        except Exception as exc:
            health["overall"] = "unhealthy"
            health["error"] = str(exc)

        return health

    async def close(self) -> None:
        await self.redis_client.close()

    def get_circuit_breaker(self, bucket: str) -> CircuitBreaker:
        """Expose the circuit breaker for a bucket (for streaming wrappers)."""
        return self._get_circuit_breaker(bucket)

    async def _await_rate_limit_slot(
        self,
        bucket: str,
        *,
        token_count: Optional[int] = None,
    ) -> RateLimitResult:
        attempts = 0
        while True:
            result = await self.check_and_consume(bucket, token_count=token_count)
            if result.allowed:
                return result

            if (
                not self.config.enable_backpressure
                or result.blocked_by == "rpd"
                or attempts >= self.config.backpressure_retry_attempts
            ):
                raise RateLimitExceededException(
                    message=f"Rate limit exceeded for {bucket}",
                    retry_after=result.retry_after,
                    limits=result.metadata.dict(),
                    model=bucket,
                )

            wait_seconds: float = float(
                result.retry_after or self.config.backpressure_max_wait_seconds
            )
            wait_seconds = min(
                wait_seconds, float(self.config.backpressure_max_wait_seconds)
            )
            wait_seconds += random.uniform(0, self.config.backpressure_jitter_seconds)
            attempts += 1
            self.logger.warning(
                "Rate limit reached for %s (%s). Waiting %.2fs before retry %d/%d",
                bucket,
                result.blocked_by,
                wait_seconds,
                attempts,
                self.config.backpressure_retry_attempts,
            )
            await asyncio.sleep(wait_seconds)

    async def _check_tpm(
        self,
        bucket: str,
        model_cfg,
        token_count: int,
        safety_margin: float,
        *,
        rpm_metadata: Optional[RateLimitMetadata] = None,
        token_identifier: Optional[str] = None,
    ) -> RateLimitResult:
        tpm_limit = model_cfg.rate_limits.tpm or 0
        effective_tpm = int(tpm_limit * (1.0 - safety_margin))
        effective_tpm = max(1, effective_tpm)
        now = time.time()
        minute_key = datetime.utcnow().strftime("%Y%m%d%H%M")
        key = f"{self.config.redis_key_prefix}:{bucket}:tpm:{minute_key}"

        try:
            new_total = await self.redis_client.incrby(key, token_count)
            if new_total == token_count:
                await self.redis_client.expire(key, 120)
        except Exception as exc:
            self.logger.error("tpm_rate_limit_failed", bucket=bucket, error=str(exc))
            raise GeminiServiceUnavailableException(
                f"TPM rate limiting unavailable: {exc}"
            ) from exc

        allowed = new_total <= effective_tpm
        blocked_by = None
        retry_after = None
        if not allowed:
            await self.redis_client.decrby(key, token_count)
            blocked_by = "tpm"
            seconds_until_next_minute = max(1, int(60 - (now % 60)))
            retry_after = seconds_until_next_minute

        tpm_used = await self._get_tpm_usage(bucket)
        rpm_limit = (
            rpm_metadata.rpm_limit
            if rpm_metadata
            else int(model_cfg.rate_limits.rpm * (1.0 - safety_margin))
        )
        rpd_limit = (
            rpm_metadata.rpd_limit
            if rpm_metadata
            else int(model_cfg.rate_limits.rpd * (1.0 - safety_margin))
        )
        rpm_used = rpm_metadata.rpm_used if rpm_metadata else 0
        rpd_used = rpm_metadata.rpd_used if rpm_metadata else 0
        reset_time_rpm = (
            rpm_metadata.reset_time_rpm
            if rpm_metadata
            else datetime.utcnow().replace(second=0, microsecond=0)
            + timedelta(minutes=1)
        )
        reset_time_rpd = (
            rpm_metadata.reset_time_rpd
            if rpm_metadata
            else datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            + timedelta(days=1)
        )
        metadata = RateLimitMetadata(
            bucket=bucket,
            model=model_cfg.model_id,
            provider=model_cfg.provider or "google",
            rpm_limit=rpm_limit,
            rpm_used=rpm_used,
            rpm_remaining=max(0, rpm_limit - rpm_used),
            rpd_limit=rpd_limit,
            rpd_used=rpd_used,
            rpd_remaining=max(0, rpd_limit - rpd_used),
            tpm_limit=effective_tpm,
            tpm_used=tpm_used,
            tpm_remaining=max(0, effective_tpm - tpm_used),
            reset_time_rpm=reset_time_rpm,
            reset_time_rpd=reset_time_rpd,
            reset_time_tpm=datetime.utcnow().replace(second=0, microsecond=0)
            + timedelta(minutes=1),
            safety_margin=safety_margin,
        )

        return RateLimitResult(
            allowed=allowed,
            metadata=metadata,
            retry_after=retry_after,
            blocked_by=blocked_by,
            token_identifier=token_identifier if allowed else None,
        )

    async def _get_tpm_usage(self, bucket: str) -> int:
        minute_key = datetime.utcnow().strftime("%Y%m%d%H%M")
        key = f"{self.config.redis_key_prefix}:{bucket}:tpm:{minute_key}"
        try:
            value = await self.redis_client.get(key)
            return int(value) if value else 0
        except Exception:
            return 0

    def _get_circuit_breaker(self, bucket: str) -> CircuitBreaker:
        breaker = self._circuit_breakers.get(bucket)
        if breaker is None:
            breaker = CircuitBreaker(
                failure_threshold=self.config.circuit_breaker_failure_threshold,
                timeout_seconds=self.config.circuit_breaker_timeout_seconds,
                success_threshold=self.config.circuit_breaker_success_threshold,
                name=bucket.replace(".", "_").replace("/", "_"),
            )
            self._circuit_breakers[bucket] = breaker
        return breaker

    def _calculate_uptime(self, circuits: Dict[str, CircuitBreakerStatus]) -> float:
        if not circuits:
            return 100.0
        open_count = sum(
            1 for status in circuits.values() if status.state == CircuitState.OPEN
        )
        return max(0.0, 100.0 - (open_count / max(1, len(circuits))) * 100.0)

    def _iter_bucket_configs(self, config) -> Iterator[Tuple[str, Any]]:
        for bucket, model_cfg in iter_rate_limit_buckets(config):
            yield bucket, model_cfg
