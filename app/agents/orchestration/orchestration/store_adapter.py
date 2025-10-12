"""Hybrid store adapter bridging LangGraph store interface with Supabase RPCs."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.db.supabase_client import SupabaseClient


ALLOWED_SOURCES = {"correction", "feedback"}
_adapter_singleton: Optional["HybridStoreAdapter"] = None


class HybridStoreAdapter:
    """Adapter that delegates store searches to Supabase while enforcing policies."""

    def __init__(self, supabase_client: Optional[SupabaseClient] = None) -> None:
        self._supabase_client = supabase_client or SupabaseClient()

    async def search(
        self,
        query_embedding: List[float],
        match_count: int = 10,
        *,
        folder_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Search text chunks via Supabase and surface approved sources only."""

        rows = await self._supabase_client.search_text_chunks(
            query_embedding,
            match_count=match_count,
            folder_id=folder_id,
        )

        filtered: List[Dict[str, Any]] = []
        for row in rows or []:
            metadata = row.get("metadata") or {}
            source = None
            if isinstance(metadata, dict):
                source = metadata.get("source")

            if source not in ALLOWED_SOURCES:
                continue

            filtered.append(
                {
                    "conversation_id": row.get("conversation_id")
                    or row.get("conversationId"),
                    "chunk_id": row.get("id") or row.get("chunk_id"),
                    "content": row.get("content"),
                    "similarity": row.get("similarity")
                    or row.get("similarity_score"),
                    "source": source,
                }
            )

        return filtered

    def is_ready(self) -> bool:
        """Return True when Supabase connectivity is available for searches."""

        client = getattr(self, "_supabase_client", None)
        if client is None:
            return False
        return not getattr(client, "mock_mode", False)


def get_hybrid_store_adapter(
    supabase_client: Optional[SupabaseClient] = None,
) -> HybridStoreAdapter:
    """Return a singleton adapter instance, allowing optional dependency override."""

    global _adapter_singleton

    if supabase_client is not None:
        return HybridStoreAdapter(supabase_client=supabase_client)

    if _adapter_singleton is None:
        _adapter_singleton = HybridStoreAdapter()

    return _adapter_singleton
