"""Simple Redis caching layer for agent responses."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Optional

from app.core.settings import settings

import redis
from redis.exceptions import ConnectionError as RedisConnectionError

REDIS_URL = settings.redis_url
CACHE_TTL_SEC = settings.cache_ttl_sec

_redis_client: redis.Redis | None = None

def _get_client() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    return _redis_client


def _hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


class RedisCache:
    """Key-value cache for identical user queries."""

    def __init__(self, ttl: int = CACHE_TTL_SEC) -> None:
        self.client = _get_client()
        self.ttl = ttl

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------

    def get(self, query: str) -> Optional[Any]:
        key = _hash_key(query)
        try:
            value = self.client.get(key)
        except RedisConnectionError:
            # Redis unavailable; treat as cache miss
            return None
        if value is None:
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None

    def set(self, query: str, response: Any, ttl: Optional[int] = None) -> None:
        key = _hash_key(query)
        try:
            self.client.setex(key, ttl or self.ttl, json.dumps(response))
        except RedisConnectionError:
            # Redis unavailable; skip caching
            pass
