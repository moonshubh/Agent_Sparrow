"""Unit tests for RedisCache and QdrantMemory wrappers.
Only RedisCache behaviour is fully tested with a dummy redis client to avoid
external dependencies. QdrantMemory's core methods are smoke-tested via mocks.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

from app.cache.redis_cache import RedisCache, _hash_key, _get_client


class DummyRedis:
    """Very small in-memory stand-in for redis.Redis."""

    def __init__(self):
        self._store: dict[str, str] = {}

    # Redis `get`
    def get(self, key: str):
        return self._store.get(key)

    # Redis `setex`
    def setex(self, key: str, ttl: int, value: str):
        self._store[key] = value


# ---------------------------------------------------------------------------
# Fixture to monkeypatch the Redis client creation
# ---------------------------------------------------------------------------

def test_redis_cache_set_get(monkeypatch):
    dummy = DummyRedis()
    # Patch the factory to return our dummy client
    monkeypatch.setattr("app.cache.redis_cache._get_client", lambda: dummy)

    cache = RedisCache(ttl=10)

    query = "Hello world?"
    resp = {"answer": "Hi"}

    # Should miss initially
    assert cache.get(query) is None

    # Set and then retrieve
    cache.set(query, resp)
    cached = cache.get(query)
    assert cached == resp

    # Ensure key hashing deterministic
    assert _hash_key(query) in dummy._store


# ---------------------------------------------------------------------------
# Smoke test QdrantMemory with monkeypatched embed & client
# ---------------------------------------------------------------------------

from app.services.qdrant_memory import QdrantMemory


class DummyQdrantClient(SimpleNamespace):
    def __init__(self):
        super().__init__(collections=[])
        self.upsert_calls = []

    def get_collections(self):
        return SimpleNamespace(collections=self.collections)

    def create_collection(self, collection_name, vectors_config):
        self.collections.append(SimpleNamespace(name=collection_name))

    def upsert(self, collection, points):
        self.upsert_calls.append((collection, points))

    def search(self, collection_name, query_vector, limit, search_params):
        # Return a dummy payload list
        return [SimpleNamespace(payload={"text": "dummy context"})]


def test_qdrant_memory_add_retrieve(monkeypatch):
    dummy_client = DummyQdrantClient()
    # Patch QdrantClient inside module namespace
    monkeypatch.setattr("app.services.qdrant_memory.QdrantClient", lambda url, api_key: dummy_client)
    # Patch embedder to deterministic vector
    monkeypatch.setattr("app.services.qdrant_memory.GoogleGenerativeAIEmbeddings", lambda model, google_api_key: SimpleNamespace(embed_query=lambda x: [0.1, 0.2]))

    mem = QdrantMemory()

    mem.add_interaction("session1", "Hi?", "Hello!")
    assert dummy_client.upsert_calls, "Upsert should be called"

    out = mem.retrieve_context("session1", [0.1, 0.2])
    assert out == ["dummy context"]
