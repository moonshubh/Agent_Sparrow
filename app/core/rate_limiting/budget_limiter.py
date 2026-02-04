from __future__ import annotations

import datetime as _dt
from typing import Optional

import redis.asyncio as redis

from app.core.logging_config import get_logger
from app.core.settings import settings

logger = get_logger(__name__)

_budget_client = redis.from_url(
    settings.redis_url,
    encoding="utf-8",
    decode_responses=True,
)


def _budget_key(scope: str, user_id: str, window: Optional[_dt.datetime] = None) -> str:
    """Construct a per-user budget key scoped by calendar day."""
    window = window or _dt.datetime.utcnow()
    return f"budget:{scope}:{window.strftime('%Y%m%d')}:{user_id}"


async def enforce_budget(
    scope: str,
    user_id: str,
    *,
    limit: int,
    window_seconds: int = 24 * 3600,
) -> bool:
    """
    Increment and validate a per-user budget counter using Redis.

    Args:
        scope: Logical budget scope (e.g., 'primary', 'router').
        user_id: Identifier for the user.
        limit: Maximum allowed increments within the window.
        window_seconds: TTL for the counter (defaults to one day).

    Returns:
        True if the increment succeeded (budget remaining), False if the limit was exceeded.
        On Redis errors, falls back to permissive mode.
    """
    if limit <= 0:
        return True

    key = _budget_key(scope, user_id)
    try:
        current = await _budget_client.incr(key)
        if current == 1:
            await _budget_client.expire(key, window_seconds)
        if current > limit:
            # Roll back increment to avoid permanent drift
            await _budget_client.decr(key)
            logger.info(
                "budget_limit_exceeded",
                scope=scope,
                user_id=user_id,
                limit=limit,
            )
            return False
        return True
    except Exception as exc:  # pragma: no cover - fallback behaviour
        logger.debug(
            "budget_enforce_failed", scope=scope, user_id=user_id, error=str(exc)
        )
        return True
