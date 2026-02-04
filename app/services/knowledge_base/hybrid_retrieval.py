"""Hybrid Mailbird KB retrieval (vector + full-text + filters)."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from loguru import logger
from postgrest.exceptions import APIError

from app.core.settings import settings
from app.db.supabase.client import SupabaseClient, get_supabase_client
from app.db.embedding import utils as embedding_utils
from app.security.pii_redactor import redact_pii_from_dict


class HybridRetrieval:
    """Combines vector similarity and lightweight text search for KB articles."""

    def __init__(
        self,
        supabase: Optional[SupabaseClient] = None,
        snippet_chars: Optional[int] = None,
    ) -> None:
        self.supabase = supabase or get_supabase_client()
        try:
            self.embedder = embedding_utils.get_embedding_model()
        except Exception as exc:  # pragma: no cover - init guard
            logger.error("Failed to initialize Gemini embedder: %s", exc)
            raise
        default_chars = getattr(settings, "primary_agent_max_kb_chars", 600)
        raw_chars = snippet_chars if snippet_chars is not None else default_chars
        self.snippet_chars = max(160, int(raw_chars or 600))

    async def search_knowledge_base(
        self,
        query: str,
        top_k: int = 5,
        min_score: float = 0.25,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        query_text = (query or "").strip()
        if not query_text:
            return []

        k = max(1, min(int(top_k or 5), 10))
        embedding = await self._embed_query(query_text)
        vector_rows = await self._vector_search(embedding, k, min_score)
        text_rows = await self._text_search(query_text, k, filters)
        fused = self._reciprocal_rank_fusion(vector_rows, text_rows, k)
        return [redact_pii_from_dict(row) for row in fused]

    async def _embed_query(self, query: str) -> List[float]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.embedder.embed_query, query)

    async def _vector_search(
        self, embedding: List[float], top_k: int, min_score: float
    ) -> List[Dict[str, Any]]:
        if getattr(self.supabase, "mock_mode", False):
            logger.warning("Supabase mock mode active; skipping vector KB search")
            return []
        try:
            rows = await self.supabase.search_kb_articles(
                query_embedding=embedding,
                limit=top_k,
                similarity_threshold=min_score,
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Vector KB search failed: %s", exc)
            return []

        normalized: List[Dict[str, Any]] = []
        for row in rows or []:
            normalized.append(self._format_article(row, source="vector"))
        return normalized

    async def _text_search(
        self,
        query_text: str,
        top_k: int,
        filters: Optional[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        if getattr(self.supabase, "mock_mode", False):
            return []

        rows = await self._full_text_rpc(query_text, top_k)
        if not rows:
            if getattr(settings, "enable_kb_legacy_fallback", False):
                rows = await self._legacy_text_search(query_text, top_k)
            if not rows:
                return []

        normalized: List[Dict[str, Any]] = []
        for row in rows:
            if not self._passes_filters(row, filters):
                continue
            normalized.append(self._format_article(row, source="full_text"))
        return normalized

    async def _full_text_rpc(self, query_text: str, top_k: int) -> List[Dict[str, Any]]:
        params = {
            "query_text": query_text,
            "match_count": max(1, min(top_k * 2, 20)),
        }

        def _call_rpc():
            return self.supabase.client.rpc(
                "search_mailbird_knowledge_full_text", params
            ).execute()

        try:
            response = await asyncio.to_thread(_call_rpc)
            return response.data or []
        except APIError as exc:
            # Graceful downgrade when RPC is missing or misconfigured
            logger.warning(
                "Full-text RPC search failed with APIError",
                error=str(exc),
                code=getattr(exc, "code", None),
                hint=getattr(exc, "hint", None),
            )
            return []
        except Exception as exc:
            logger.warning("Full-text RPC search failed: %s", exc)
            return []

    async def _legacy_text_search(
        self, query_text: str, top_k: int
    ) -> List[Dict[str, Any]]:
        safe_query = " ".join((query_text or "").split())
        if not safe_query:
            return []
        # Trim to avoid huge patterns
        safe_query = safe_query[:200]
        tokens = safe_query.split()
        if not tokens:
            return []
        # Use multiple sanitized tokens for better relevance while keeping patterns safe
        safe_tokens: List[str] = []
        for token in tokens[:3]:
            sanitized = token.replace("%", "").replace("_", "")
            if len(sanitized) >= 2:
                safe_tokens.append(sanitized)

        if not safe_tokens:
            return []

        pattern_body = "%".join(safe_tokens)
        if len(pattern_body) > 200:
            pattern_body = pattern_body[:200]
        pattern = f"%{pattern_body}%"

        def _run_query():
            builder = self.supabase.client.table("mailbird_knowledge").select(
                "id,title,url,markdown,content,metadata,tags"
            )
            try:
                query_builder = builder.or_(
                    f"content.ilike.{pattern},markdown.ilike.{pattern}"
                )
            except ImportError:
                logger.warning(
                    "postgrest.or_ unavailable; falling back to content-only search"
                )
                query_builder = builder.ilike("content", pattern)
            except APIError as exc:
                logger.warning(
                    "Combined content/markdown search failed, falling back to content: %s",
                    exc,
                )
                query_builder = builder.ilike("content", pattern)

            return query_builder.limit(top_k).execute()

        try:
            response = await asyncio.to_thread(_run_query)
            return response.data or []
        except Exception as exc:  # pragma: no cover - best effort fallback
            logger.warning("Fallback full-text KB search failed: %s", exc)
            return []

    def _passes_filters(
        self, row: Dict[str, Any], filters: Optional[Dict[str, Any]]
    ) -> bool:
        if not filters:
            return True
        metadata = row.get("metadata") or {}
        tags_filter = filters.get("tags")
        if tags_filter:
            row_tags = row.get("tags") or metadata.get("tags") or []
            try:
                if not set(tags_filter).issubset(set(row_tags)):
                    return False
            except Exception:
                return False
        target_version = filters.get("product_version")
        if target_version:
            version_val = metadata.get("product_version") or metadata.get("version")
            if (
                not version_val
                or str(target_version).lower() not in str(version_val).lower()
            ):
                return False
        return True

    def _format_article(self, row: Dict[str, Any], source: str) -> Dict[str, Any]:
        snippet_source = row.get("markdown") or row.get("content") or ""
        snippet = (snippet_source or "").strip()
        if snippet:
            snippet = snippet[: self.snippet_chars]
        score = 0.0
        for key in ("relevance_score", "similarity", "score"):
            raw = row.get(key)
            if raw is not None:
                try:
                    score = float(raw)
                    break
                except Exception:
                    continue
        return {
            "id": row.get("id"),
            "title": row.get("title") or row.get("url") or "Knowledge Base Article",
            "url": row.get("url"),
            "snippet": snippet,
            "score": score,
            "source": source,
            "metadata": row.get("metadata") or {},
        }

    def _reciprocal_rank_fusion(
        self,
        vector_rows: List[Dict[str, Any]],
        text_rows: List[Dict[str, Any]],
        top_k: int,
    ) -> List[Dict[str, Any]]:
        blended: Dict[Any, Dict[str, Any]] = {}
        scores: Dict[Any, float] = {}
        constant = 60

        def _update(rows: List[Dict[str, Any]], offset: int) -> None:
            for rank, row in enumerate(rows):
                key = (
                    row.get("id") or row.get("url") or (row.get("title"), rank + offset)
                )
                fused_score = 1.0 / (constant + rank + 1)
                scores[key] = scores.get(key, 0.0) + fused_score
                if key not in blended:
                    blended[key] = row
                elif row.get("score", 0) > blended[key].get("score", 0):
                    blended[key]["score"] = row.get("score", 0)

        _update(vector_rows, 0)
        _update(text_rows, len(vector_rows))

        ranked_keys = sorted(scores, key=lambda k: scores.get(k, 0.0), reverse=True)
        return [blended[key] for key in ranked_keys[:top_k]]
