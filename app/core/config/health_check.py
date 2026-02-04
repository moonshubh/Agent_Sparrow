from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional, Tuple

import httpx
import redis.asyncio as redis
from redis.exceptions import RedisError

from app.core.settings import settings
from app.core.config.config_loader import (
    ModelsConfig,
    get_models_config,
    get_models_config_hash,
    resolve_subagent_config,
)
from app.core.rate_limiting.agent_wrapper import get_rate_limiter
from app.core.rate_limiting.exceptions import (
    CircuitBreakerOpenException,
    GeminiServiceUnavailableException,
    RateLimitExceededException,
)

logger = logging.getLogger(__name__)

HEALTH_CHECK_PROMPT = "health check"
DEFAULT_TIMEOUT_SECONDS = 12.0
LOCK_TTL_SECONDS = 300
RESULT_TTL_SECONDS = 900


@dataclass
class HealthCheckTarget:
    model_id: str
    provider: str
    bucket: str
    is_embedding: bool
    categories: list[str]


@dataclass
class HealthCheckOutcome:
    target: HealthCheckTarget
    ok: bool
    reason: Optional[str] = None


def _normalize_google_model_id(model_id: str) -> str:
    normalized = (model_id or "").strip()
    if normalized.startswith("models/"):
        return normalized[len("models/") :]
    return normalized


def _is_minimax_model(model_id: str) -> bool:
    """Check whether a model_id targets Minimax (e.g., minimax/MiniMax-M2.1)."""
    return "minimax" in (model_id or "").lower()


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _iter_health_targets(config: ModelsConfig) -> Iterable[Tuple[str, str, str]]:
    for key, model in config.coordinators.items():
        yield "coordinators", key, model.model_id
    for key, model in config.internal.items():
        yield "internal", key, model.model_id
    for key in config.subagents.keys():
        resolved = resolve_subagent_config(config, key)
        yield "subagents", key, resolved.model_id
    if config.zendesk is not None:
        for key, model in config.zendesk.coordinators.items():
            yield "zendesk.coordinators", key, model.model_id
        for key in config.zendesk.subagents.keys():
            resolved = resolve_subagent_config(config, key, zendesk=True)
            yield "zendesk.subagents", key, resolved.model_id


def _collect_targets(
    config: ModelsConfig,
) -> Dict[Tuple[str, str, bool], HealthCheckTarget]:
    targets: Dict[Tuple[str, str, bool], HealthCheckTarget] = {}

    for section, key, model_id in _iter_health_targets(config):
        if section == "internal":
            model_cfg = config.internal[key]
        elif section == "coordinators":
            model_cfg = config.coordinators[key]
        elif section == "subagents":
            model_cfg = resolve_subagent_config(config, key)
        elif section == "zendesk.coordinators" and config.zendesk is not None:
            model_cfg = config.zendesk.coordinators[key]
        elif section == "zendesk.subagents" and config.zendesk is not None:
            model_cfg = resolve_subagent_config(config, key, zendesk=True)
        else:
            continue

        provider = model_cfg.provider or "google"
        is_embedding = bool(model_cfg.embedding_dims) or model_cfg.model_id.startswith(
            "models/"
        )
        bucket = f"{section}.{key}"
        key_tuple = (provider, model_cfg.model_id, is_embedding)

        if key_tuple in targets:
            targets[key_tuple].categories.append(bucket)
            continue

        targets[key_tuple] = HealthCheckTarget(
            model_id=model_cfg.model_id,
            provider=provider,
            bucket=bucket,
            is_embedding=is_embedding,
            categories=[bucket],
        )

    return targets


def _provider_status() -> Dict[str, bool]:
    openrouter_ready = bool(getattr(settings, "openrouter_api_key", None)) or bool(
        getattr(settings, "minimax_api_key", None)
    )
    return {
        "google": bool(settings.gemini_api_key),
        "xai": bool(settings.xai_api_key),
        "openrouter": openrouter_ready,
    }


def _openrouter_ready_for_model(model_id: str) -> bool:
    if getattr(settings, "openrouter_api_key", None):
        return True
    return _is_minimax_model(model_id) and bool(
        getattr(settings, "minimax_api_key", None)
    )


async def _check_google_model(
    model_id: str, *, is_embedding: bool, timeout: float
) -> bool:
    api_key = settings.gemini_api_key
    if not api_key:
        return False

    model_name = _normalize_google_model_id(model_id)
    payload: Dict[str, Any]
    if is_embedding:
        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:embedContent"
        payload = {"content": {"parts": [{"text": HEALTH_CHECK_PROMPT}]}}
    else:
        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
        payload = {
            "contents": [{"role": "user", "parts": [{"text": HEALTH_CHECK_PROMPT}]}],
            "generationConfig": {"maxOutputTokens": 1},
        }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                endpoint, params={"key": api_key}, json=payload
            )
        if response.status_code >= 200 and response.status_code < 300:
            return True
        logger.warning(
            "google_model_health_failed",
            extra={"model": model_id, "status": response.status_code},
        )
        return False
    except httpx.HTTPError as exc:
        logger.warning(
            "google_model_health_error", extra={"model": model_id, "error": str(exc)}
        )
        return False


async def _check_openrouter_model(model_id: str, *, timeout: float) -> bool:
    api_key = getattr(settings, "openrouter_api_key", None)
    base_url = (
        getattr(settings, "openrouter_base_url", None) or "https://openrouter.ai/api/v1"
    )
    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": getattr(settings, "openrouter_referer", None)
        or "https://agentsparrow.local",
        "X-Title": getattr(settings, "openrouter_app_name", None) or "Agent Sparrow",
    }

    # Minimax models route through the same OpenRouter path but use Minimax's API
    # directly when MINIMAX_API_KEY or MINIMAX_CODING_PLAN_API_KEY is configured.
    # Prefer the Coding Plan key as it works for both chat completions and MCP tools.
    minimax_key = getattr(settings, "minimax_coding_plan_api_key", None) or getattr(
        settings, "minimax_api_key", None
    )
    if _is_minimax_model(model_id) and minimax_key:
        api_key = minimax_key
        base_url = (
            getattr(settings, "minimax_base_url", None) or "https://api.minimax.io/v1"
        )
        headers = {"Authorization": f"Bearer {api_key}"}
        model_id = model_id.split("/")[-1] if "/" in model_id else model_id

    if not api_key:
        return False

    endpoint = f"{base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": model_id,
        "messages": [{"role": "user", "content": HEALTH_CHECK_PROMPT}],
        "max_tokens": 4,
        "temperature": 0.0,
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(endpoint, headers=headers, json=payload)
        if response.status_code >= 200 and response.status_code < 300:
            return True
        logger.warning(
            "openrouter_model_health_failed",
            extra={"model": model_id, "status": response.status_code},
        )
        return False
    except httpx.HTTPError as exc:
        logger.warning(
            "openrouter_model_health_error",
            extra={"model": model_id, "error": str(exc)},
        )
        return False


async def _check_xai_model(model_id: str, *, timeout: float) -> bool:
    api_key = settings.xai_api_key
    if not api_key:
        return False

    endpoint = "https://api.x.ai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"}
    payload = {
        "model": model_id,
        "messages": [{"role": "user", "content": HEALTH_CHECK_PROMPT}],
        "max_tokens": 4,
        "temperature": 0.0,
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(endpoint, headers=headers, json=payload)
        if response.status_code >= 200 and response.status_code < 300:
            return True
        logger.warning(
            "xai_model_health_failed",
            extra={"model": model_id, "status": response.status_code},
        )
        return False
    except httpx.HTTPError as exc:
        logger.warning(
            "xai_model_health_error", extra={"model": model_id, "error": str(exc)}
        )
        return False


async def validate_model_connection(
    model_id: str,
    provider: str,
    *,
    is_embedding: bool = False,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> bool:
    """Test that a model is reachable and returns a valid response."""
    provider_key = (provider or "google").strip().lower()

    if provider_key == "google":
        return await _check_google_model(
            model_id, is_embedding=is_embedding, timeout=timeout
        )
    if provider_key == "openrouter":
        return await _check_openrouter_model(model_id, timeout=timeout)
    if provider_key == "xai":
        return await _check_xai_model(model_id, timeout=timeout)
    return False


async def _acquire_lock(
    redis_client: redis.Redis,
    lock_key: str,
    ttl: int,
) -> Optional[bool]:
    try:
        return bool(await redis_client.set(lock_key, "1", nx=True, ex=ttl))
    except RedisError as exc:
        logger.warning("health_check_lock_failed", extra={"error": str(exc)})
        return None


async def _load_cached_results(
    redis_client: redis.Redis, results_key: str
) -> Optional[Dict[str, Dict[str, Any]]]:
    try:
        cached = await redis_client.get(results_key)
    except RedisError:
        return None
    if not cached:
        return None
    try:
        payload = json.loads(cached)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        return None
    return None


async def _store_cached_results(
    redis_client: redis.Redis,
    results_key: str,
    results: Dict[str, Dict[str, Any]],
) -> None:
    try:
        await redis_client.setex(results_key, RESULT_TTL_SECONDS, json.dumps(results))
    except RedisError:
        return None


def _build_results(
    outcomes: Iterable[HealthCheckOutcome],
) -> Dict[str, Dict[str, Any]]:
    results: Dict[str, Dict[str, Any]] = {}
    for outcome in outcomes:
        model_id = outcome.target.model_id
        results[model_id] = {
            "ok": outcome.ok,
            "provider": outcome.target.provider,
            "reason": outcome.reason,
            "categories": outcome.target.categories,
        }
    return results


def _log_summary(results: Dict[str, Dict[str, Any]]) -> None:
    total = len(results)
    passed = sum(1 for payload in results.values() if payload.get("ok"))
    failed = total - passed
    logger.info(
        "model_health_check_summary",
        extra={"total": total, "passed": passed, "failed": failed},
    )


async def run_startup_health_checks(
    *,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    concurrency: int = 4,
) -> Dict[str, Dict[str, Any]]:
    """Run health checks for all configured models on startup."""
    config = get_models_config()
    targets = list(_collect_targets(config).values())
    provider_ready = _provider_status()

    if not provider_ready.get("openrouter"):
        logger.warning(
            "openrouter_api_key_missing",
            extra={"action": "subagents_will_fallback_to_coordinator"},
        )

    lock_key = None
    results_key = None
    redis_client: Optional[redis.Redis] = None
    lock_status: Optional[bool] = False
    config_hash = get_models_config_hash()

    try:
        redis_client = redis.from_url(settings.redis_url, decode_responses=True)
        lock_key = f"model_health_lock:{config_hash}"
        results_key = f"model_health_results:{config_hash}"
        lock_status = await _acquire_lock(redis_client, lock_key, LOCK_TTL_SECONDS)

        if lock_status is False:
            cached = await _load_cached_results(redis_client, results_key)
            if cached is not None:
                logger.info("model_health_check_using_cached_results")
                _log_summary(cached)
                return cached
            logger.info(
                "model_health_check_skipped", extra={"reason": "lock_unavailable"}
            )
            return {}

        if lock_status is None:
            logger.info(
                "model_health_check_running_without_lock",
                extra={"reason": "redis_unavailable"},
            )
            redis_client = None

        limiter = get_rate_limiter()
        semaphore = asyncio.Semaphore(max(1, concurrency))
        outcomes: list[HealthCheckOutcome] = []

        async def _run_target(target: HealthCheckTarget) -> None:
            async with semaphore:
                if target.provider == "openrouter":
                    if not _openrouter_ready_for_model(target.model_id):
                        outcomes.append(
                            HealthCheckOutcome(
                                target=target, ok=False, reason="api_key_missing"
                            )
                        )
                        return
                elif not provider_ready.get(target.provider, False):
                    outcomes.append(
                        HealthCheckOutcome(
                            target=target, ok=False, reason="api_key_missing"
                        )
                    )
                    return

                token_count = (
                    _estimate_tokens(HEALTH_CHECK_PROMPT)
                    if target.is_embedding
                    else None
                )
                try:
                    if limiter is not None:
                        await limiter.check_and_consume(
                            target.bucket, token_count=token_count
                        )
                except RateLimitExceededException:
                    outcomes.append(
                        HealthCheckOutcome(
                            target=target, ok=False, reason="rate_limited"
                        )
                    )
                    return
                except CircuitBreakerOpenException:
                    outcomes.append(
                        HealthCheckOutcome(
                            target=target, ok=False, reason="circuit_open"
                        )
                    )
                    return
                except GeminiServiceUnavailableException:
                    logger.warning(
                        "health_check_rate_limiter_unavailable",
                        extra={"bucket": target.bucket, "model": target.model_id},
                    )

                ok = await validate_model_connection(
                    target.model_id,
                    target.provider,
                    is_embedding=target.is_embedding,
                    timeout=timeout,
                )
                outcomes.append(
                    HealthCheckOutcome(
                        target=target,
                        ok=ok,
                        reason=None if ok else "request_failed",
                    )
                )

        await asyncio.gather(*[_run_target(target) for target in targets])

        results = _build_results(outcomes)
        _log_summary(results)
        if redis_client and results_key:
            await _store_cached_results(redis_client, results_key, results)
        return results

    finally:
        if redis_client:
            try:
                if lock_status and lock_key:
                    await redis_client.delete(lock_key)
            except RedisError:
                pass
            await redis_client.close()
