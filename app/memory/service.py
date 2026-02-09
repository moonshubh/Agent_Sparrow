"""
Async memory service wrapper integrating mem0 with Supabase pgvector.

This module exposes a lightweight facade that allows the orchestration layer
to retrieve and persist long-term memories without importing mem0 details.
"""

from __future__ import annotations

import asyncio
import inspect
from typing import Any, Dict, List, Optional, Sequence
from time import perf_counter

from app.core.logging_config import get_logger
from app.core.settings import settings
from app.db.embedding_config import EXPECTED_DIM
from app.core.config import get_models_config
from app.memory.observability import memory_metrics
from app.security.pii_redactor import redact_pii

try:  # pragma: no cover - import guard for optional dependency during boot
    from mem0 import Memory as Mem0Memory  # type: ignore[import-not-found,import-untyped]

    _MEM0_AVAILABLE = True
except ImportError:  # pragma: no cover - handled gracefully when mem0 is missing
    Mem0Memory = None  # type: ignore
    _MEM0_AVAILABLE = False


logger = get_logger(__name__)

TENANT_ID = "mailbot"
DEFAULT_MEMORY_TYPE = "fact"
DEFAULT_SOURCE = "primary_agent"
LOG_AGENT_ID = "log_analyst"
LOG_MEMORY_TYPE = "log_pattern"
MEM0_MAX_INDEX_DIM = 2000


class _NoopTelemetryVectorStore:
    """Best-effort fallback store used when mem0 telemetry store initialization fails."""

    def __init__(self, embedding_model_dims: int) -> None:
        self.embedding_model_dims = max(1, int(embedding_model_dims))

    def get(self, vector_id: str) -> None:  # pragma: no cover - trivial fallback
        _ = vector_id
        return None

    def insert(
        self,
        vectors: Sequence[Sequence[float]],
        payloads: Optional[Sequence[Dict[str, Any]]] = None,
        ids: Optional[Sequence[str]] = None,
    ) -> None:  # pragma: no cover - trivial fallback
        _ = (vectors, payloads, ids)
        return None


class MemoryService:
    """Facade around mem0 Memory configured for Supabase pgvector."""

    def __init__(self) -> None:
        self._clients: Dict[str, Any] = {}
        self._lock = asyncio.Lock()
        self._warned_mem0_missing = False
        self._warned_mem0_runtime_unavailable = False
        self._warned_missing_connection = False
        self._warned_missing_api_key = False
        self._warned_dim_mismatch = False
        self._runtime_unavailable = False

    async def retrieve(
        self, agent_id: str, query: str, top_k: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve memories for a given agent scoped query.

        Args:
            agent_id: Identifier for the agent or persona.
            query: Natural language query to search for relevant memories.
            top_k: Optional override for the number of results (defaults to settings).

        Returns:
            List of memory dictionaries sorted by relevance (best first).
        """
        if not self._is_configured():
            return []

        query_text = (query or "").strip()
        if not query_text:
            return []

        limit = self._resolve_limit(top_k)

        start = perf_counter()
        try:
            client = await self._get_client(settings.memory_collection_primary)
            result = await self._call_mem0_method(
                client,
                "search",
                query_text,
                agent_id=agent_id,
                limit=limit,
                filters={"tenant_id": TENANT_ID},
            )
        except Exception as exc:  # pragma: no cover - network/runtime failures
            logger.exception("memory_retrieve_error", agent_id=agent_id, error=str(exc))
            duration_ms = (perf_counter() - start) * 1000.0
            memory_metrics.record_retrieval(
                "primary",
                hit=False,
                duration_ms=duration_ms,
                result_count=0,
                error=True,
            )
            return []

        raw_results = self._extract_results(result)
        formatted: List[Dict[str, Any]] = []
        for item in raw_results:
            formatted.append(
                {
                    "id": item.get("id"),
                    "memory": item.get("memory"),
                    "score": item.get("score"),
                    "metadata": item.get("metadata") or {},
                }
            )
        duration_ms = (perf_counter() - start) * 1000.0
        memory_metrics.record_retrieval(
            "primary",
            hit=bool(raw_results),
            duration_ms=duration_ms,
            result_count=len(raw_results),
            error=False,
        )
        return formatted

    async def list_primary_memories(
        self,
        *,
        agent_id: str,
        limit: int = 200,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        List mem0 primary-collection memories using metadata filters.

        This is useful for backfilling the Memory UI schema for admin review.
        """
        if not self._is_configured():
            return []

        safe_limit = max(1, min(2000, int(limit)))
        effective_filters = filters or {"tenant_id": TENANT_ID}
        return await self._get_by_filters(
            collection_name=settings.memory_collection_primary,
            filters=effective_filters,
            agent_id=agent_id,
            limit=safe_limit,
        )

    async def add_facts(
        self,
        agent_id: str,
        facts: Sequence[str],
        meta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Persist distilled facts for later retrieval.

        Args:
            agent_id: Identifier for the agent/persona originating the facts.
            facts: Iterable of fact strings to persist (empty/blank entries are ignored).
            meta: Optional metadata to merge into the stored payload.

        Returns:
            Result dictionary returned by mem0 (empty when disabled or on error).
        """
        if not self._is_configured():
            return {"results": []}

        # Strip once, redact, and filter empty results
        normalized_facts = []
        for fact in facts:
            if isinstance(fact, str):
                stripped = fact.strip()
                if stripped:
                    redacted = redact_pii(stripped)
                    if redacted:  # Also exclude if redaction produces empty string
                        normalized_facts.append(redacted)
        if not normalized_facts:
            return {"results": []}

        extra_meta = dict(meta or {})
        memory_type = str(
            extra_meta.pop("memory_type", DEFAULT_MEMORY_TYPE) or DEFAULT_MEMORY_TYPE
        )
        source = str(extra_meta.pop("source", DEFAULT_SOURCE) or DEFAULT_SOURCE)

        metadata = self._build_metadata(
            agent_id=agent_id, memory_type=memory_type, source=source, extra=extra_meta
        )
        messages = [
            {"role": "assistant", "content": fact, "name": agent_id}
            for fact in normalized_facts
        ]

        start = perf_counter()
        success = False
        error_flag = False
        try:
            client = await self._get_client(settings.memory_collection_primary)
            response = await self._call_mem0_method(
                client,
                "add",
                messages,
                agent_id=agent_id,
                metadata=metadata,
                infer=settings.memory_llm_inference,
            )
            normalized_response = self._normalize_response(response)
            success = bool(self._extract_results(normalized_response))
            return normalized_response
        except Exception as exc:  # pragma: no cover - network/runtime failures
            logger.exception(
                "memory_add_facts_error", agent_id=agent_id, error=str(exc)
            )
            error_flag = True
            return {"results": []}
        finally:
            duration_ms = (perf_counter() - start) * 1000.0
            memory_metrics.record_write(
                "primary",
                success=success,
                duration_ms=duration_ms,
                error=error_flag,
            )

    async def retrieve_log_patterns(
        self, signature: str, limit: int = 3
    ) -> List[Dict[str, Any]]:
        """Return stored log patterns matching a deterministic signature."""
        if not self._is_configured():
            return []
        normalized = (signature or "").strip()
        if not normalized:
            return []
        start = perf_counter()
        try:
            results = await self._get_by_filters(
                collection_name=settings.memory_collection_logs,
                filters={"tenant_id": TENANT_ID, "signature": normalized},
                agent_id=LOG_AGENT_ID,
                limit=limit,
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception(
                "memory_log_retrieve_error", signature=normalized, error=str(exc)
            )
            duration_ms = (perf_counter() - start) * 1000.0
            memory_metrics.record_retrieval(
                "log_signature",
                hit=False,
                duration_ms=duration_ms,
                result_count=0,
                error=True,
            )
            return []
        results = results or []
        duration_ms = (perf_counter() - start) * 1000.0
        hit = bool(results)
        memory_metrics.record_retrieval(
            "log_signature",
            hit=hit,
            duration_ms=duration_ms,
            result_count=len(results),
            error=False,
        )
        return results

    async def upsert_log_pattern(
        self,
        *,
        signature: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Upsert a log analysis pattern into the dedicated collection.

        Args:
            signature: Deterministic signature string derived from log content.
            content: Redacted summary/steps describing the pattern.
            metadata: Additional metadata (component, severity, frequency, trace_id, etc.).

        Returns:
            Dict describing the add operation; includes existing_id when an entry was replaced.
        """
        if not self._is_configured():
            return {"results": []}

        signature_value = (signature or "").strip()
        content_value = redact_pii((content or "").strip())
        if not signature_value or not content_value:
            return {"results": []}

        try:
            existing = await self.retrieve_log_patterns(signature_value, limit=1)
        except Exception as exc:  # pragma: no cover
            logger.exception(
                "memory_log_signature_lookup_failed",
                signature=signature_value,
                error=str(exc),
            )
            existing = []

        existing_id: Optional[str] = existing[0].get("id") if existing else None
        existing_memory = existing[0].get("memory") if existing else None

        if existing_id and existing_memory and existing_memory.strip() == content_value:
            # Nothing new to write; return metadata so callers can note the hit.
            memory_metrics.record_write(
                "log_pattern",
                success=True,
                duration_ms=0.0,
                error=False,
            )
            return {"results": [], "existing_id": existing_id, "unchanged": True}

        metadata_payload = self._build_metadata(
            agent_id=LOG_AGENT_ID,
            memory_type=LOG_MEMORY_TYPE,
            source="log_analysis",
            extra={**(metadata or {}), "signature": signature_value},
        )

        messages = [
            {"role": "assistant", "content": content_value, "name": LOG_AGENT_ID},
        ]

        start = perf_counter()
        success = False
        error_flag = False
        try:
            client = await self._get_client(settings.memory_collection_logs)
            if existing_id:
                try:
                    await self._call_mem0_method(client, "delete", existing_id)
                except Exception as exc:  # pragma: no cover - best effort delete
                    logger.warning(
                        "memory_log_delete_failed",
                        signature=signature_value,
                        memory_id=existing_id,
                        error=str(exc),
                    )
            result = await self._call_mem0_method(
                client,
                "add",
                messages,
                agent_id=LOG_AGENT_ID,
                metadata=metadata_payload,
                infer=settings.memory_llm_inference,
            )
            result = self._normalize_response(result)
            if existing_id:
                result["replaced_id"] = existing_id
            success = bool(result.get("results")) or bool(result.get("replaced_id"))
            return result
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception(
                "memory_log_upsert_error", signature=signature_value, error=str(exc)
            )
            error_flag = True
            return {"results": [], "error": str(exc)}
        finally:
            duration_ms = (perf_counter() - start) * 1000.0
            memory_metrics.record_write(
                "log_pattern",
                success=success,
                duration_ms=duration_ms,
                error=error_flag,
            )

    # ---------------------------------------------------------------------
    # Internal helpers
    # ---------------------------------------------------------------------

    def is_available(self) -> bool:
        """Return True when the mem0 backend is usable."""
        return self._is_configured()

    def _is_configured(self) -> bool:
        """Return True when the memory backend is ready for use."""
        if not settings.should_enable_agent_memory():
            return False

        if not _MEM0_AVAILABLE:
            self._warn_once(
                "_warned_mem0_missing",
                "mem0 package not installed; agent memory is disabled.",
            )
            return False
        if self._runtime_unavailable:
            self._warn_once(
                "_warned_mem0_runtime_unavailable",
                "mem0 runtime dependencies are unavailable; agent memory is disabled.",
            )
            return False

        connection = settings.get_memory_connection_string()
        if not connection:
            self._warn_once(
                "_warned_missing_connection",
                "ENABLE_AGENT_MEMORY=true but SUPABASE_DB_CONN is not configured.",
            )
            return False

        if not settings.gemini_api_key:
            self._warn_once(
                "_warned_missing_api_key",
                "ENABLE_AGENT_MEMORY=true but GEMINI_API_KEY is missing for embeddings.",
            )
            return False

        config = get_models_config()
        embedding_cfg = config.internal["embedding"]
        if (embedding_cfg.embedding_dims or EXPECTED_DIM) != EXPECTED_DIM:
            self._warn_once(
                "_warned_dim_mismatch",
                f"Configured memory embedding dims ({embedding_cfg.embedding_dims}) "
                f"do not match EXPECTED_DIM ({EXPECTED_DIM}).",
            )

        return True

    async def _get_client(self, collection_name: str) -> Any:
        """Return or lazily instantiate a mem0 client for a collection."""
        cached = self._clients.get(collection_name)
        if cached is not None:
            return cached

        async with self._lock:
            cached = self._clients.get(collection_name)
            if cached is not None:
                return cached

            try:
                client = self._build_client(collection_name)
            except Exception as exc:
                if self._is_mem0_runtime_dependency_error(exc):
                    self._runtime_unavailable = True
                    self._warn_once(
                        "_warned_mem0_runtime_unavailable",
                        "mem0 runtime dependencies are unavailable (vecs/pgvector).",
                    )
                raise
            self._clients[collection_name] = client
            return client

    def _build_client(self, collection_name: str) -> Any:
        if Mem0Memory is None:  # pragma: no cover - safeguarded by _is_configured
            raise RuntimeError(
                "mem0 Memory is unavailable in the current environment."
            )

        connection = settings.get_memory_connection_string()
        config = get_models_config()
        embedding_cfg = config.internal["embedding"]
        embedding_dims = embedding_cfg.embedding_dims or EXPECTED_DIM
        mem0_dims = min(int(embedding_dims), MEM0_MAX_INDEX_DIM)
        if mem0_dims != int(embedding_dims):
            logger.warning(
                "mem0_embedding_dims_clamped",
                requested_dims=int(embedding_dims),
                applied_dims=mem0_dims,
                max_supported_dims=MEM0_MAX_INDEX_DIM,
            )
        embedder_provider = embedding_cfg.provider or "google"
        mem0_provider = "gemini" if embedder_provider == "google" else embedder_provider

        coordinator_model = config.coordinators["google"].model_id
        mem0_config: Dict[str, Any] = {
            "vector_store": {
                "provider": settings.memory_backend,
                "config": {
                    "connection_string": connection,
                    "collection_name": collection_name,
                    "embedding_model_dims": mem0_dims,
                    "index_method": "ivfflat",
                },
            },
            "embedder": {
                "provider": mem0_provider,
                "config": {
                    "model": embedding_cfg.model_id,
                    "api_key": settings.gemini_api_key,
                    "embedding_dims": mem0_dims,
                    "output_dimensionality": mem0_dims,
                },
            },
            "llm": {
                "provider": "gemini",
                "config": {
                    "model": coordinator_model,
                    "api_key": settings.gemini_api_key,
                },
            },
        }
        try:
            return self._create_mem0_client(mem0_config)
        except Exception as exc:
            if not self._is_mem0_dimension_mismatch_error(exc):
                raise

            fallback_collection = f"{collection_name}_dim{mem0_dims}"
            if fallback_collection == collection_name:
                raise

            logger.warning(
                "mem0_collection_dimension_mismatch_fallback",
                collection=collection_name,
                fallback_collection=fallback_collection,
                dims=mem0_dims,
            )
            vector_cfg = mem0_config.get("vector_store", {}).get("config", {})
            if isinstance(vector_cfg, dict):
                vector_cfg["collection_name"] = fallback_collection
            return self._create_mem0_client(mem0_config)

    def _create_mem0_client(self, mem0_config: Dict[str, Any]) -> Any:
        """Build a mem0 client while tolerating telemetry vector-store init failures."""
        if Mem0Memory is None:  # pragma: no cover - safeguarded by _is_configured
            raise RuntimeError("mem0 Memory is unavailable in the current environment.")
        try:
            from mem0.utils.factory import (  # type: ignore[import-untyped]
                VectorStoreFactory as Mem0VectorStoreFactory,
            )
        except Exception:
            return Mem0Memory.from_config(mem0_config)

        original_create_descriptor = Mem0VectorStoreFactory.__dict__.get("create")
        if original_create_descriptor is None:
            return Mem0Memory.from_config(mem0_config)

        original_create = Mem0VectorStoreFactory.create

        def _patched_create(cls: Any, provider_name: str, config: Any) -> Any:
            _ = cls
            collection_name = self._get_mem0_config_value(config, "collection_name")
            if collection_name != "mem0migrations":
                return original_create(provider_name, config)
            try:
                return original_create(provider_name, config)
            except Exception as exc:
                dims = self._coerce_mem0_dims(
                    self._get_mem0_config_value(config, "embedding_model_dims", 1536)
                )
                logger.warning(
                    "mem0_telemetry_vector_store_disabled",
                    collection="mem0migrations",
                    dims=dims,
                    error=str(exc),
                    error_type=type(exc).__name__,
                )
                return _NoopTelemetryVectorStore(dims)

        Mem0VectorStoreFactory.create = classmethod(_patched_create)
        try:
            return Mem0Memory.from_config(mem0_config)
        finally:
            Mem0VectorStoreFactory.create = original_create_descriptor

    def _get_mem0_config_value(
        self,
        config: Any,
        key: str,
        default: Any = None,
    ) -> Any:
        if isinstance(config, dict):
            return config.get(key, default)
        return getattr(config, key, default)

    def _coerce_mem0_dims(self, value: Any) -> int:
        try:
            return max(1, int(value))
        except (TypeError, ValueError):
            return 1536

    async def _get_by_filters(
        self,
        *,
        collection_name: str,
        filters: Dict[str, Any],
        agent_id: str,
        limit: int,
    ) -> List[Dict[str, Any]]:
        """Fetch memories using metadata filters without embedding search."""
        client = await self._get_client(collection_name)
        result = await self._call_mem0_method(
            client,
            "get_all",
            agent_id=agent_id,
            filters=filters,
            limit=max(1, limit),
        )
        candidates = self._extract_results(result)

        formatted: List[Dict[str, Any]] = []
        for item in candidates:
            formatted.append(
                {
                    "id": item.get("id"),
                    "memory": item.get("memory"),
                    "metadata": item.get("metadata") or {},
                }
            )
        return formatted

    async def _call_mem0_method(
        self,
        client: Any,
        method_name: str,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Call mem0 methods with async-mode preference and sync fallback."""
        method = getattr(client, method_name, None)
        if method is None:
            raise AttributeError(f"mem0 client does not implement '{method_name}'")

        async_kwargs = dict(kwargs)
        async_kwargs.setdefault("async_mode", True)

        try:
            return await self._invoke_callable(method, *args, **async_kwargs)
        except TypeError as exc:
            if not self._is_async_mode_signature_error(exc):
                raise
        return await self._invoke_callable(method, *args, **kwargs)

    async def _invoke_callable(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        """Invoke callable while tolerating sync and async return styles."""
        if inspect.iscoroutinefunction(fn):
            return await fn(*args, **kwargs)

        value = await asyncio.to_thread(fn, *args, **kwargs)
        if inspect.isawaitable(value):
            return await value
        return value

    def _extract_results(self, payload: Any) -> List[Dict[str, Any]]:
        """Unwrap mem0 responses that may be dict-with-results or direct lists."""
        candidates: Any
        if isinstance(payload, dict):
            candidates = payload.get("results", payload)
        else:
            candidates = payload

        if not isinstance(candidates, list):
            return []

        return [item for item in candidates if isinstance(item, dict)]

    def _normalize_response(self, payload: Any) -> Dict[str, Any]:
        """Return a consistent dict shape with a `results` list."""
        if isinstance(payload, dict):
            response = dict(payload)
            response["results"] = self._extract_results(payload)
            return response
        return {"results": self._extract_results(payload)}

    def _is_async_mode_signature_error(self, exc: TypeError) -> bool:
        text = str(exc).lower()
        return (
            "async_mode" in text
            and ("unexpected keyword" in text or "got an unexpected" in text)
        )

    def _is_mem0_runtime_dependency_error(self, exc: Exception) -> bool:
        text = str(exc).lower()
        if "vecs" in text or "pgvector" in text:
            return True
        if isinstance(exc, ModuleNotFoundError):
            module_name = str(getattr(exc, "name", "") or "").lower()
            return module_name in {"vecs", "pgvector"}
        return False

    def _is_mem0_dimension_mismatch_error(self, exc: Exception) -> bool:
        text = str(exc).lower()
        if "mismatcheddimension" in text:
            return True
        if "dimension" in text and "do not match" in text:
            return True
        return False

    def _build_metadata(
        self,
        *,
        agent_id: str,
        memory_type: str,
        source: str,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Assemble base metadata for memory writes."""
        metadata: Dict[str, Any] = {
            "tenant_id": TENANT_ID,
            "agent_id": agent_id,
            "memory_type": memory_type,
            "source": source,
        }

        for key, value in (extra or {}).items():
            if value is None:
                continue
            metadata[key] = value
        return metadata

    def _resolve_limit(self, override: Optional[int]) -> int:
        """Clamp retrieval limits to a safe range."""
        desired = (
            override
            if isinstance(override, int) and override > 0
            else settings.memory_top_k
        )
        return max(1, min(settings.memory_top_k, desired))

    def _warn_once(self, attr: str, message: str) -> None:
        """Log a warning exactly once per attribute flag."""
        if getattr(self, attr, False):
            return
        logger.warning(message)
        setattr(self, attr, True)


# Global singleton used by orchestration nodes
memory_service = MemoryService()
