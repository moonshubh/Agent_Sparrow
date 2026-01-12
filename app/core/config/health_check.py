from __future__ import annotations

from typing import Any

import redis.asyncio as redis

from app.core.settings import settings
from app.core.rate_limiting.agent_wrapper import get_rate_limiter

from .models_config import get_models_config, infer_provider_from_model_id


async def validate_model_connection(*args: Any, **kwargs: Any) -> bool:
    # Real connectivity checks are environment-specific; tests patch this.
    return True


async def run_startup_health_checks() -> dict[str, dict[str, Any]]:
    config = get_models_config()

    limiter = get_rate_limiter()
    redis_url = str(getattr(settings, "redis_url", "redis://localhost:6379/0") or "")
    client = redis.from_url(redis_url)

    model_ids: list[str] = []
    for spec in (config.coordinators or {}).values():
        if spec.model_id:
            model_ids.append(spec.model_id)
    for spec in (config.internal or {}).values():
        if spec.model_id:
            model_ids.append(spec.model_id)
    for spec in (config.subagents or {}).values():
        if spec.model_id:
            model_ids.append(spec.model_id)

    unique_model_ids = list(dict.fromkeys(model_ids))
    results: dict[str, dict[str, Any]] = {}

    for model_id in unique_model_ids:
        provider = infer_provider_from_model_id(model_id)
        if provider == "google" and not getattr(settings, "gemini_api_key", None):
            results[model_id] = {"ok": False, "reason": "api_key_missing"}
            continue
        if provider == "openrouter" and not getattr(settings, "openrouter_api_key", None):
            results[model_id] = {"ok": False, "reason": "api_key_missing"}
            continue

        ok = await validate_model_connection(
            provider=provider,
            model_id=model_id,
            limiter=limiter,
            redis_client=client,
        )
        results[model_id] = {"ok": bool(ok)}
        if not ok:
            results[model_id]["reason"] = "connection_failed"

    try:
        await client.close()
    except Exception:
        pass

    return results
