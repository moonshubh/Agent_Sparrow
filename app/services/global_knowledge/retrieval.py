"""Utilities for retrieving global knowledge entries for agent injection."""

from __future__ import annotations

import asyncio
import logging
from time import perf_counter
from typing import Any, Dict, List, Optional, Tuple

from langgraph.store.base import SearchItem

from app.core.settings import settings
from app.db import embedding_utils
from app.db.embedding_config import assert_dim
from app.services.global_knowledge.store import get_async_store

ALLOWED_SOURCES = {"correction", "feedback"}


logger = logging.getLogger(__name__)
def _resolve_adapter():
    try:
        from app.agents.orchestration.orchestration.store_adapter import get_hybrid_store_adapter

        return get_hybrid_store_adapter()
    except Exception:  # pragma: no cover - optional dependency or circular import
        logger.debug("Hybrid store adapter unavailable; fallback disabled")
        return None



def _truncate(text: str, limit: int) -> str:
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _format_store_item(item: SearchItem, char_budget: int) -> Tuple[Dict[str, Any], str]:
    value = item.value or {}
    source = value.get("source") or (item.namespace[-1] if item.namespace else "global")
    summary = (value.get("summary") or "").strip()
    key_facts: List[str] = []
    try:
        key_facts = [str(f).strip() for f in (value.get("key_facts") or []) if f]
    except Exception:  # pragma: no cover - defensive
        key_facts = []
    normalized_pair = value.get("normalized_pair") if isinstance(value.get("normalized_pair"), dict) else None
    attachments = value.get("attachments") or []
    metadata = value.get("metadata") or {}
    tags = value.get("tags") or []

    content_parts: List[str] = []
    if summary:
        content_parts.append(summary)
    if key_facts:
        facts_joined = "; ".join(key_facts[:3])
        content_parts.append(f"Key facts: {facts_joined}")
    if normalized_pair:
        incorrect = normalized_pair.get("incorrect")
        corrected = normalized_pair.get("corrected")
        if incorrect and corrected:
            content_parts.append(f"Correction: '{incorrect}' → '{corrected}'")
    content = _truncate("\n".join(content_parts), char_budget)

    relevance = None
    try:
        relevance = float(item.score) if item.score is not None else None
    except Exception:  # pragma: no cover
        relevance = None

    payload = {
        "title": metadata.get("title") or summary or f"{source.title()} insight",
        "summary": summary,
        "content": content,
        "key_facts": key_facts,
        "normalized_pair": normalized_pair,
        "tags": tags,
        "attachments": attachments,
        "metadata": metadata,
        "source": source,
        "source_id": metadata.get("source_id"),
        "relevance_score": relevance,
        "created_at": getattr(item, "created_at", None),
        "updated_at": getattr(item, "updated_at", None),
    }

    memory_line_parts: List[str] = []
    if summary:
        memory_line_parts.append(summary)
    if normalized_pair:
        incorrect = normalized_pair.get("incorrect")
        corrected = normalized_pair.get("corrected")
        if incorrect and corrected:
            memory_line_parts.append(f"Fix: '{incorrect}' → '{corrected}'")
    if key_facts:
        memory_line_parts.append("Facts: " + "; ".join(key_facts[:2]))
    memory_line = " | ".join(memory_line_parts) or content

    return payload, memory_line


def _format_adapter_item(row: Dict[str, Any], char_budget: int) -> Tuple[Dict[str, Any], str]:
    source = row.get("source") or "legacy"
    content = (row.get("content") or "").strip()
    truncated = _truncate(content, char_budget)
    title = row.get("title") or f"Conversation {row.get('conversation_id', '')}".strip()
    similarity = None
    try:
        similarity = float(row.get("similarity") or row.get("similarity_score") or 0.0)
    except Exception:
        similarity = None

    payload = {
        "title": title or "Legacy knowledge entry",
        "summary": truncated,
        "content": truncated,
        "key_facts": [],
        "normalized_pair": None,
        "tags": [],
        "attachments": [],
        "metadata": {
            "conversation_id": row.get("conversation_id") or row.get("conversationId"),
            "chunk_id": row.get("chunk_id") or row.get("id"),
        },
        "source": source,
        "source_id": row.get("conversation_id") or row.get("conversationId"),
        "relevance_score": similarity,
        "created_at": None,
        "updated_at": None,
    }

    memory_line = truncated
    return payload, memory_line


async def retrieve_global_knowledge(query_text: str, *, top_k: Optional[int] = None) -> Dict[str, Any]:
    """Retrieve global knowledge entries using store-first strategy with adapter fallback."""

    query = (query_text or "").strip()
    if not query:
        return {
            "items": [],
            "memory_snippet": "",
            "source": "none",
            "fallback_used": False,
            "latency_ms": 0.0,
            "errors": ["empty_query"],
        }

    k = top_k or settings.global_knowledge_top_k
    k = max(1, min(settings.global_knowledge_top_k, k))
    char_budget = settings.global_knowledge_max_chars

    start = perf_counter()
    errors: List[str] = []
    items: List[Dict[str, Any]] = []
    memory_lines: List[str] = []
    source = "none"
    fallback_used = False

    # Attempt store retrieval when configured
    if settings.has_global_store_configuration() and settings.should_enable_global_knowledge():
        store = await get_async_store()
        if store is not None:
            try:
                store_hits = await store.asearch(("global_knowledge",), query=query, limit=k)
                for idx, hit in enumerate(store_hits):
                    payload, memory_line = _format_store_item(hit, char_budget)
                    if payload["source"] in ALLOWED_SOURCES:
                        items.append(payload)
                        memory_lines.append(memory_line)
                if items:
                    source = "store"
            except Exception as exc:  # pragma: no cover - network failures
                logger.warning("Global knowledge store search failed: %s", exc)
                errors.append(f"store_error:{exc.__class__.__name__}")
        else:
            errors.append("store_unavailable")
    else:
        logger.debug("Global store not configured or injection disabled; skipping store search")

    # Fallback to adapter when enabled and we need more results
    use_adapter_fallback = settings.enable_store_adapter or settings.get_retrieval_primary() == "rpc"

    if len(items) < k and use_adapter_fallback:
        fallback_used = True
        try:
            embed_model = embedding_utils.get_embedding_model()
            loop = asyncio.get_running_loop()
            query_vector = await loop.run_in_executor(None, embed_model.embed_query, query)
            assert_dim(query_vector, "global_knowledge_adapter_fallback")
            adapter = _resolve_adapter()
            if adapter is None:
                raise RuntimeError("adapter_unavailable")
            remaining = k - len(items)
            adapter_rows = await adapter.search(query_vector, match_count=max(remaining, k))
            for row in adapter_rows:
                payload, memory_line = _format_adapter_item(row, char_budget)
                items.append(payload)
                memory_lines.append(memory_line)
            if source == "none" and items:
                source = "adapter"
        except Exception as exc:  # pragma: no cover - network failures
            logger.warning("Global knowledge adapter fallback failed: %s", exc)
            errors.append(f"adapter_error:{exc.__class__.__name__}")

    latency_ms = (perf_counter() - start) * 1000

    ranked_items = items[:k]
    clipped_lines = memory_lines[:k]
    memory_snippet = _truncate("\n".join(f"{idx + 1}. {line}" for idx, line in enumerate(clipped_lines)), char_budget)

    logger.info(
        "global_knowledge_retrieval",
        extra={
            "query_len": len(query),
            "hits": len(ranked_items),
            "source": source,
            "fallback_used": fallback_used,
            "latency_ms": round(latency_ms, 2),
            "errors": errors,
        },
    )

    return {
        "items": ranked_items,
        "memory_snippet": memory_snippet,
        "source": source,
        "fallback_used": fallback_used,
        "latency_ms": latency_ms,
        "errors": errors,
        "top_k": k,
        "char_budget": char_budget,
    }
