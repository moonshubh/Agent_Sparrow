"""Helpers for interacting with the LangGraph asynchronous Postgres store."""

from __future__ import annotations

import asyncio
import logging
import os
from functools import lru_cache
from typing import Any, List, Optional

try:  # pragma: no cover - optional import for retry logic
    from psycopg import OperationalError as PsycopgOperationalError
except Exception:  # pragma: no cover - fallback when psycopg is unavailable
    PsycopgOperationalError = Exception  # type: ignore

try:  # Optional dependency: langgraph-postgres runtime
    from langgraph.store.postgres.aio import AsyncPostgresStore
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    AsyncPostgresStore = None  # type: ignore

from app.core.settings import settings
from app.db.embedding import utils as embedding_utils
from app.db.embedding_config import EXPECTED_DIM, assert_dim

from .models import EnhancedPayload

logger = logging.getLogger(__name__)

_store_lock = asyncio.Lock()
_store_instance: Optional[AsyncPostgresStore] = None
_store_context: Optional[Any] = None
_store_setup_complete = False


@lru_cache(maxsize=1)
def _resolve_embeddings():
    """Return the embedding model used for LangGraph store indexing."""

    return embedding_utils.get_embedding_model()


def _should_enable_store_index() -> bool:
    if os.getenv("DISABLE_GLOBAL_STORE_INDEX", "").lower() in {"1", "true", "yes"}:
        return False
    if os.getenv("ENABLE_GLOBAL_STORE_INDEX", "").lower() in {"1", "true", "yes"}:
        return True
    return not settings.skip_auth


async def _close_store_instance() -> None:
    """Close and reset the cached store instance."""

    global _store_instance, _store_context, _store_setup_complete

    if _store_instance is None:
        return

    context = _store_context
    _store_context = None
    if context is not None:
        try:
            await context.__aexit__(None, None, None)
        except Exception as exc:  # pragma: no cover - defensive cleanup
            logger.debug("Error closing store context", exc_info=exc)

    conn = getattr(_store_instance, "conn", None)
    try:
        close = getattr(conn, "close", None)
        if close is not None:
            result = close()
            if asyncio.iscoroutine(result):
                await result
    except Exception as exc:  # pragma: no cover - defensive cleanup
        logger.debug("Error closing async store connection", exc_info=exc)

    _store_instance = None
    _store_setup_complete = False


async def get_async_store(force_refresh: bool = False) -> Optional[AsyncPostgresStore]:
    """Return a cached AsyncPostgresStore instance when configuration is available."""

    global _store_instance, _store_context, _store_setup_complete

    if force_refresh:
        await _close_store_instance()

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

        index_config = None
        if _should_enable_store_index():
            index_config = {
                "dims": EXPECTED_DIM,
                "distance_type": "cosine",
                "embed": _resolve_embeddings(),
            }

        try:
            ctx = AsyncPostgresStore.from_conn_string(
                db_uri,
                index=index_config,
            )
            store = await ctx.__aenter__()

            # Supabase currently rejects pipeline usage; fall back to transactional mode.
            setattr(store, "supports_pipeline", False)

            if not _store_setup_complete:
                try:
                    await store.setup()
                    _store_setup_complete = True
                    logger.info("AsyncPostgresStore setup completed")
                except Exception as setup_exc:
                    await ctx.__aexit__(
                        setup_exc.__class__, setup_exc, setup_exc.__traceback__
                    )
                    logger.warning(
                        "AsyncPostgresStore setup failed (error=%s message=%s)",
                        setup_exc.__class__.__name__,
                        str(setup_exc),
                    )
                    logger.debug("AsyncPostgresStore setup detail", exc_info=setup_exc)
                    return None

            _store_instance = store
            _store_context = ctx
            if index_config is None:
                logger.info("AsyncPostgresStore initialised without vector index (fallback mode)")
            else:
                logger.debug("AsyncPostgresStore initialised for global knowledge")
            return _store_instance
        except Exception as exc:
            logger.warning(
                "Failed to initialise AsyncPostgresStore (error=%s message=%s)",
                exc.__class__.__name__,
                str(exc),
            )
            logger.debug("AsyncPostgresStore initialisation detail", exc_info=exc)
            return None


def _should_retry_store_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return (
        isinstance(exc, PsycopgOperationalError)
        or "connection is closed" in message
        or "not in pipeline mode" in message
    )


async def upsert_enhanced_entry(
    enhanced: EnhancedPayload,
    embedding: Optional[List[float]],
    *,
    store: Optional[AsyncPostgresStore] = None,
) -> bool:
    """Upsert enhanced payload into the LangGraph store, returning success status."""

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

    last_error: Optional[Exception] = None
    current_store = store

    def resolve_index_config(store_instance: AsyncPostgresStore | Any) -> bool | list[str]:  # type: ignore[type-arg]
        index_cfg = getattr(store_instance, "index_config", None)
        if index_cfg:
            return ["embedding"]
        return False

    for attempt in range(2):
        store_instance = current_store
        if store_instance is None:
            store_instance = await get_async_store(force_refresh=attempt == 1)
        if store_instance is None:
            logger.debug("Async store unavailable; skipping upsert for %s", enhanced.kind)
            return False

        try:
            await store_instance.aput(namespace, key, value, index=resolve_index_config(store_instance))
            logger.debug(
                "Upserted enhanced entry into store namespace=%s key=%s dim=%s",
                namespace,
                key,
                len(embedding),
            )
            return True
        except Exception as exc:
            last_error = exc
            if attempt == 0 and _should_retry_store_error(exc):
                logger.warning(
                    "AsyncPostgresStore write failed (%s); attempting connection refresh",
                    exc,
                )
                await _close_store_instance()
                current_store = None
                continue

            logger.warning(
                "Failed to upsert enhanced entry into store (error=%s message=%s)",
                exc.__class__.__name__,
                str(exc),
                exc_info=exc,
            )
            return False

    if last_error is not None:
        logger.warning(
            "Failed to upsert enhanced entry into store after retry (error=%s message=%s)",
            last_error.__class__.__name__,
            str(last_error),
            exc_info=last_error,
        )
    return False
