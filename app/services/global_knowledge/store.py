"""Helpers for interacting with the LangGraph asynchronous Postgres store."""

from __future__ import annotations

import asyncio
import logging
from functools import lru_cache
from typing import List, Optional

try:  # Optional dependency: langgraph-postgres runtime
    from langgraph.store.postgres.aio import AsyncPostgresStore
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    AsyncPostgresStore = None  # type: ignore

from app.core.settings import settings
from app.db import embedding_utils
from app.db.embedding_config import EXPECTED_DIM, assert_dim

from .models import EnhancedPayload

logger = logging.getLogger(__name__)

_store_lock = asyncio.Lock()
_store_instance: Optional[AsyncPostgresStore] = None


@lru_cache(maxsize=1)
def _resolve_embeddings():
    """Return the embedding model used for LangGraph store indexing."""

    return embedding_utils.get_embedding_model()


async def get_async_store() -> Optional[AsyncPostgresStore]:
    """Return a cached AsyncPostgresStore instance when configuration is available."""

    global _store_instance

    if AsyncPostgresStore is None:
        logger.debug("LangGraph Postgres store dependency not available; skipping store initialisation")
        return None

    if _store_instance is not None:
        return _store_instance

    if not settings.has_global_store_configuration():
        logger.debug("Global store configuration not provided; skipping store initialization")
        return None

    async with _store_lock:
        if _store_instance is not None:
            return _store_instance

        db_uri = settings.global_store_db_uri
        if not db_uri:
            logger.debug("Global store DB URI missing; cannot initialise store")
            return None

        try:
            ctx = AsyncPostgresStore.from_conn_string(
                db_uri,
                index={
                    "dims": EXPECTED_DIM,
                    "distance_type": "cosine",
                    "embed": _resolve_embeddings(),
                },
            )
            store = await ctx.__aenter__()
            _store_instance = store
            logger.debug("AsyncPostgresStore initialised for global knowledge")
            return _store_instance
        except Exception as exc:
            logger.warning(
                "Failed to initialise AsyncPostgresStore (error=%s)",
                exc.__class__.__name__,
            )
            logger.debug("AsyncPostgresStore initialisation detail", exc_info=exc)
            return None


async def upsert_enhanced_entry(
    enhanced: EnhancedPayload,
    embedding: Optional[List[float]],
    *,
    store: Optional[AsyncPostgresStore] = None,
) -> bool:
    """Upsert enhanced payload into the LangGraph store, returning success status."""

    store_instance = store or await get_async_store()
    if store_instance is None:
        logger.debug("Async store unavailable; skipping upsert for %s", enhanced.kind)
        return False

    try:
        namespace, key, value = enhanced.to_store_item()

        if embedding is None:
            logger.debug("No embedding provided; skipping store write for key=%s", key)
            return False

        try:
            assert_dim(embedding, "global_knowledge_store")
        except ValueError as err:
            logger.warning("Skipping store write due to embedding dimension mismatch: %s", err)
            return False

        value["embedding"] = embedding

        await store_instance.aput(namespace, key, value, index=True)
        logger.debug(
            "Upserted enhanced entry into store namespace=%s key=%s dim=%s",
            namespace,
            key,
            len(embedding),
        )
        return True
    except Exception as exc:
        logger.warning(
            "Failed to upsert enhanced entry into store (error=%s)",
            exc.__class__.__name__,
        )
        logger.debug("AsyncPostgresStore upsert detail", exc_info=exc)
        return False
