"""
Memory UI Service for Agent Sparrow.

This service provides CRUD operations for the memories table, including
embedding generation via Google Gemini and integration with database functions
for feedback, merge, duplicate detection, and statistics.
"""

from __future__ import annotations

import asyncio
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from app.core.logging_config import get_logger
from app.core.rate_limiting.agent_wrapper import get_rate_limiter
from app.core.rate_limiting.exceptions import RateLimitExceededException
from app.core.settings import settings
from app.db.embedding_config import EXPECTED_DIM, MODEL_NAME
from app.db.supabase.client import get_supabase_client, SupabaseClient
from app.memory.title import ensure_memory_title
from app.security.pii_redactor import redact_pii, redact_pii_from_dict

logger = get_logger(__name__)


class MemoryUIService:
    """
    Service class for Memory UI operations.

    Handles CRUD operations for the memories table with Gemini embedding generation
    and integration with database functions for feedback, merging, and statistics.
    """

    # Avoid selecting the 3072-dim `embedding` column unless explicitly needed.
    MEMORY_SELECT_COLUMNS = (
        "id,content,metadata,source_type,confidence_score,retrieval_count,last_retrieved_at,"
        "feedback_positive,feedback_negative,resolution_success_count,resolution_failure_count,"
        "agent_id,tenant_id,created_at,updated_at"
    )

    def __init__(self) -> None:
        self._supabase: Optional[SupabaseClient] = None
        self._embedding_model = None
        self._lock = asyncio.Lock()

    def _get_supabase(self) -> SupabaseClient:
        """Get or initialize Supabase client."""
        if self._supabase is None:
            self._supabase = get_supabase_client()
        return self._supabase

    def _get_embedding_model(self):
        """
        Get or initialize the embedding model using LangChain's GoogleGenerativeAIEmbeddings.
        """
        if self._embedding_model is not None:
            return self._embedding_model

        if not settings.gemini_api_key:
            raise ValueError("GEMINI_API_KEY is required for embedding generation")

        try:
            from langchain_google_genai import embeddings as gen_embeddings

            self._embedding_model = gen_embeddings.GoogleGenerativeAIEmbeddings(
                model=MODEL_NAME,
                google_api_key=settings.gemini_api_key,
            )
            logger.info("Initialized Gemini embedding model: %s", MODEL_NAME)
            return self._embedding_model
        except Exception as exc:
            logger.error("Failed to initialize Gemini embedding model: %s", exc)
            raise

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Estimate tokens for embedding rate limiting (roughly 1 token per 4 chars)."""
        return max(1, len(text) // 4)

    async def generate_embedding(self, text: str) -> List[float]:
        """
        Generate a 3072-dimensional embedding vector using Google Gemini.

        Args:
            text: The text to embed.

        Returns:
            A list of floats representing the embedding vector.

        Raises:
            ValueError: If the text is empty or embedding generation fails.
        """
        text = (text or "").strip()
        if not text:
            raise ValueError("Cannot generate embedding for empty text")

        async with self._lock:
            model = self._get_embedding_model()

        try:
            token_count = self._estimate_tokens(text)
            limiter = get_rate_limiter()
            rate_result = await limiter.check_and_consume(
                "internal.embedding",
                token_count=token_count,
            )
            if not rate_result.allowed:
                raise RateLimitExceededException(
                    message="Embedding rate limit exceeded",
                    retry_after=rate_result.retry_after,
                    limits=rate_result.metadata.dict(),
                    model="internal.embedding",
                )

            loop = asyncio.get_running_loop()
            embedding = await loop.run_in_executor(None, model.embed_query, text)

            if len(embedding) != EXPECTED_DIM:
                raise ValueError(
                    f"Embedding dimension mismatch: got {len(embedding)}, expected {EXPECTED_DIM}"
                )

            logger.debug("Generated embedding with dimension %d", len(embedding))
            return embedding
        except Exception as exc:
            logger.error("Failed to generate embedding: %s", exc)
            raise

    async def add_memory(
        self,
        content: str,
        metadata: Dict[str, Any],
        source_type: str,
        agent_id: str,
        tenant_id: str,
    ) -> Dict[str, Any]:
        """
        Add a new memory with Gemini embedding generation.

        Args:
            content: The memory content text.
            metadata: Additional metadata for the memory.
            source_type: The source type of the memory (e.g., 'user_input', 'agent_response').
            agent_id: The agent identifier.
            tenant_id: The tenant identifier.

        Returns:
            The created memory record including the generated ID.

        Raises:
            ValueError: If content is empty or required fields are missing.
        """
        content = (content or "").strip()
        if not content:
            raise ValueError("Memory content cannot be empty")

        # Basic PII redaction to reduce risk of storing sensitive data.
        content = redact_pii(content)
        metadata = redact_pii_from_dict(metadata or {})
        metadata = ensure_memory_title(metadata, content=content)

        if not agent_id:
            raise ValueError("agent_id is required")
        if not tenant_id:
            raise ValueError("tenant_id is required")

        # Generate embedding
        embedding = await self.generate_embedding(content)

        payload: Dict[str, Any] = {
            "content": content,
            "metadata": metadata or {},
            "source_type": source_type or "manual",
            "agent_id": agent_id,
            "tenant_id": tenant_id,
            "embedding": embedding,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        supabase = self._get_supabase()
        try:
            response = await supabase._exec(
                lambda: supabase.client.table("memories").insert(payload).execute()
            )

            if response.data:
                memory = response.data[0]
                logger.info("Created memory with ID: %s", memory.get("id"))
                return memory

            raise RuntimeError("No data returned from memory creation")
        except Exception as exc:
            logger.error("Failed to create memory: %s", exc)
            raise

    async def update_memory(
        self,
        memory_id: UUID,
        content: str,
        metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Update an existing memory, regenerating embedding if content changed.

        Args:
            memory_id: The UUID of the memory to update.
            content: The new content (if changed, embedding is regenerated).
            metadata: The new metadata.

        Returns:
            The updated memory record.

        Raises:
            ValueError: If memory_id is invalid or content is empty.
        """
        content = (content or "").strip()
        if not content:
            raise ValueError("Memory content cannot be empty")

        # Keep updates safe as well (admin edits can still accidentally include PII).
        content = redact_pii(content)
        metadata = redact_pii_from_dict(metadata or {})
        metadata = ensure_memory_title(metadata, content=content)

        supabase = self._get_supabase()
        memory_id_str = str(memory_id)

        # Fetch existing memory to check if content changed
        try:
            existing_response = await supabase._exec(
                lambda: supabase.client.table("memories")
                .select("content")
                .eq("id", memory_id_str)
                .maybe_single()
                .execute()
            )
        except Exception as exc:
            logger.error("Failed to fetch existing memory %s: %s", memory_id_str, exc)
            raise

        if not existing_response.data:
            raise ValueError(f"Memory {memory_id_str} not found")

        existing_content = (existing_response.data.get("content") or "").strip()

        # Build update payload
        update_payload: Dict[str, Any] = {
            "content": content,
            "metadata": metadata or {},
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        # Regenerate embedding if content changed
        if content != existing_content:
            embedding = await self.generate_embedding(content)
            update_payload["embedding"] = embedding
            logger.info("Content changed for memory %s, regenerated embedding", memory_id_str)

        try:
            response = await supabase._exec(
                lambda: supabase.client.table("memories")
                .update(update_payload)
                .eq("id", memory_id_str)
                .execute()
            )

            if response.data:
                memory = response.data[0]
                logger.info("Updated memory: %s", memory_id_str)
                return memory

            raise RuntimeError(f"Memory {memory_id_str} not found for update")
        except Exception as exc:
            logger.error("Failed to update memory %s: %s", memory_id_str, exc)
            raise

    async def delete_memory(self, memory_id: UUID) -> Dict[str, Any]:
        """
        Delete a memory from the memories table.

        Args:
            memory_id: The UUID of the memory to delete.

        Returns:
            A dict with orphaned_entities_count and removed_relationships_count.
        """
        supabase = self._get_supabase()
        memory_id_str = str(memory_id)

        # First, check for related entities that might become orphaned
        # This is a simplified version; the actual cleanup logic may be in a DB function
        orphaned_count = 0
        relationships_count = 0

        try:
            # Delete the memory
            response = await supabase._exec(
                lambda: supabase.client.table("memories")
                .delete()
                .eq("id", memory_id_str)
                .execute()
            )

            if response.data:
                logger.info("Deleted memory: %s", memory_id_str)
            else:
                logger.warning("Memory %s not found for deletion", memory_id_str)

            return {
                "deleted_memory_id": memory_id_str,
                "orphaned_entities_count": orphaned_count,
                "removed_relationships_count": relationships_count,
            }
        except Exception as exc:
            logger.error("Failed to delete memory %s: %s", memory_id_str, exc)
            raise

    async def submit_feedback(
        self,
        memory_id: UUID,
        user_id: UUID,
        feedback_type: str,
        session_id: Optional[str] = None,
        ticket_id: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Submit feedback for a memory using the record_memory_feedback database function.

        Args:
            memory_id: The UUID of the memory receiving feedback.
            user_id: The UUID of the user submitting feedback.
            feedback_type: Type of feedback (e.g., 'positive', 'negative', 'correction').
            session_id: Optional session identifier.
            ticket_id: Optional ticket identifier.
            notes: Optional notes for the feedback.

        Returns:
            A dict containing the new confidence score.
        """
        supabase = self._get_supabase()

        params: Dict[str, Any] = {
            "p_memory_id": str(memory_id),
            "p_user_id": str(user_id),
            "p_feedback_type": feedback_type,
            "p_session_id": session_id,
            "p_ticket_id": ticket_id,
            "p_notes": notes,
        }

        try:
            response = await supabase._exec(
                lambda: supabase.rpc("record_memory_feedback", params).execute()
            )

            result = response.data if response.data else {}
            logger.info(
                "Recorded feedback for memory %s, new confidence: %s",
                memory_id,
                result.get("new_confidence"),
            )
            return result
        except Exception as exc:
            logger.error("Failed to record feedback for memory %s: %s", memory_id, exc)
            raise

    async def merge_memories(
        self,
        candidate_id: UUID,
        keep_memory_id: UUID,
        reviewer_id: UUID,
        merged_content: str,
    ) -> Dict[str, Any]:
        """
        Merge duplicate memories using the merge_duplicate_memories database function.

        Args:
            candidate_id: The UUID of the duplicate candidate to merge/remove.
            keep_memory_id: The UUID of the memory to keep.
            reviewer_id: The UUID of the reviewer performing the merge.
            merged_content: The merged content for the kept memory.

        Returns:
            The result of the merge operation.
        """
        merged_content = (merged_content or "").strip()
        if not merged_content:
            raise ValueError("Merged content cannot be empty")

        supabase = self._get_supabase()

        # Generate embedding for merged content
        embedding = await self.generate_embedding(merged_content)

        params: Dict[str, Any] = {
            "p_candidate_id": str(candidate_id),
            "p_keep_memory_id": str(keep_memory_id),
            "p_reviewer_id": str(reviewer_id),
            "p_merged_content": merged_content,
            "p_merged_embedding": embedding,
        }

        try:
            response = await supabase._exec(
                lambda: supabase.rpc("merge_duplicate_memories", params).execute()
            )

            result = response.data if response.data else {}
            logger.info(
                "Merged memory %s into %s",
                candidate_id,
                keep_memory_id,
            )
            return result
        except Exception as exc:
            logger.error(
                "Failed to merge memories %s into %s: %s",
                candidate_id,
                keep_memory_id,
                exc,
            )
            raise

    async def dismiss_duplicate(
        self,
        candidate_id: UUID,
        reviewer_id: UUID,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Dismiss a duplicate candidate using the dismiss_duplicate_candidate database function.

        Args:
            candidate_id: The UUID of the duplicate candidate to dismiss.
            reviewer_id: The UUID of the reviewer dismissing the candidate.
            notes: Optional notes explaining the dismissal.

        Returns:
            The result of the dismiss operation.
        """
        supabase = self._get_supabase()

        params: Dict[str, Any] = {
            "p_candidate_id": str(candidate_id),
            "p_reviewer_id": str(reviewer_id),
            "p_notes": notes,
        }

        try:
            response = await supabase._exec(
                lambda: supabase.rpc("dismiss_duplicate_candidate", params).execute()
            )

            result = response.data if response.data else {}
            logger.info("Dismissed duplicate candidate %s", candidate_id)
            return result
        except Exception as exc:
            logger.error("Failed to dismiss duplicate %s: %s", candidate_id, exc)
            raise

    async def get_stats(self) -> Dict[str, Any]:
        """
        Get memory statistics using the get_memory_stats database function.

        Returns:
            A dict containing memory statistics (total count, by source type,
            average confidence, etc.).
        """
        supabase = self._get_supabase()

        try:
            response = await supabase._exec(
                lambda: supabase.rpc("get_memory_stats").execute()
            )

            stats = response.data if response.data else {}
            logger.debug("Retrieved memory stats")
            return stats
        except Exception as exc:
            logger.error("Failed to get memory stats: %s", exc)
            raise

    async def detect_duplicates(self, memory_id: UUID) -> int:
        """
        Detect duplicates for a specific memory using the detect_duplicates_for_memory
        database function.

        Args:
            memory_id: The UUID of the memory to check for duplicates.

        Returns:
            The count of duplicate candidates found.
        """
        supabase = self._get_supabase()

        params: Dict[str, Any] = {
            "p_memory_id": str(memory_id),
        }

        try:
            response = await supabase._exec(
                lambda: supabase.rpc("detect_duplicates_for_memory", params).execute()
            )

            # The RPC function returns the count of duplicates found
            result = response.data
            if isinstance(result, int):
                count = result
            elif isinstance(result, dict):
                count = result.get("count", 0)
            elif isinstance(result, list) and result:
                count = result[0].get("count", 0) if isinstance(result[0], dict) else len(result)
            else:
                count = 0

            logger.info("Detected %d duplicates for memory %s", count, memory_id)
            return count
        except Exception as exc:
            logger.error("Failed to detect duplicates for memory %s: %s", memory_id, exc)
            raise

    async def get_memory_by_id(self, memory_id: UUID) -> Optional[Dict[str, Any]]:
        """
        Retrieve a single memory by its ID.

        Args:
            memory_id: The UUID of the memory to retrieve.

        Returns:
            The memory record if found, None otherwise.
        """
        supabase = self._get_supabase()
        memory_id_str = str(memory_id)

        try:
            response = await supabase._exec(
                lambda: supabase.client.table("memories")
                .select(self.MEMORY_SELECT_COLUMNS)
                .eq("id", memory_id_str)
                .maybe_single()
                .execute()
            )

            if response.data:
                logger.debug("Retrieved memory %s", memory_id_str)
                return response.data

            return None
        except Exception as exc:
            logger.error("Failed to get memory %s: %s", memory_id_str, exc)
            raise

    async def list_memories(
        self,
        agent_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        source_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        sort_order: str = "desc",
    ) -> List[Dict[str, Any]]:
        """
        List memories with optional filters and pagination.

        Args:
            agent_id: Filter by agent ID.
            tenant_id: Filter by tenant ID.
            source_type: Filter by source type.
            limit: Maximum number of results.
            offset: Number of results to skip.

        Returns:
            A list of memory records.
        """
        supabase = self._get_supabase()

        sort_order_norm = (sort_order or "desc").lower()
        if sort_order_norm not in ("asc", "desc"):
            sort_order_norm = "desc"

        try:
            query = supabase.client.table("memories").select(self.MEMORY_SELECT_COLUMNS)

            if agent_id:
                query = query.eq("agent_id", agent_id)
            if tenant_id:
                query = query.eq("tenant_id", tenant_id)
            if source_type:
                query = query.eq("source_type", source_type)

            query = query.order("created_at", desc=sort_order_norm == "desc").range(
                offset, offset + limit - 1
            )

            response = await supabase._exec(lambda: query.execute())

            memories = response.data if response.data else []
            logger.debug("Listed %d memories", len(memories))
            return memories
        except Exception as exc:
            logger.error("Failed to list memories: %s", exc)
            raise

    async def search_memories(
        self,
        query: str,
        agent_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        limit: int = 10,
        similarity_threshold: float = 0.5,
    ) -> List[Dict[str, Any]]:
        """
        Search memories using semantic similarity.

        Args:
            query: The search query text.
            agent_id: Optional filter by agent ID.
            tenant_id: Optional filter by tenant ID.
            limit: Maximum number of results.
            similarity_threshold: Minimum similarity score (0-1).

        Returns:
            A list of memory records with similarity scores.

        Raises:
            ValueError: If similarity_threshold is outside [0, 1] range.
        """
        if not 0.0 <= similarity_threshold <= 1.0:
            raise ValueError("similarity_threshold must be between 0 and 1")

        query = (query or "").strip()
        if not query:
            return []

        supabase = self._get_supabase()

        # Generate embedding for query
        embedding = await self.generate_embedding(query)

        params: Dict[str, Any] = {
            "query_embedding": embedding,
            "match_count": limit,
            "match_threshold": similarity_threshold,
        }

        if agent_id:
            params["filter_agent_id"] = agent_id
        if tenant_id:
            params["filter_tenant_id"] = tenant_id

        try:
            response = await supabase._exec(
                lambda: supabase.rpc("search_memories", params).execute()
            )

            results = response.data if response.data else []
            logger.debug("Found %d memories matching query", len(results))
            return results
        except Exception as exc:
            logger.error("Failed to search memories: %s", exc)
            raise


# Global singleton instance with thread-safe initialization
_memory_ui_service: Optional[MemoryUIService] = None
_memory_ui_service_lock = threading.Lock()


def get_memory_ui_service() -> MemoryUIService:
    """
    Get or create the global MemoryUIService instance.

    Uses double-checked locking for thread-safe initialization
    in concurrent ASGI environments.
    """
    global _memory_ui_service
    if _memory_ui_service is not None:
        return _memory_ui_service
    with _memory_ui_service_lock:
        if _memory_ui_service is None:
            _memory_ui_service = MemoryUIService()
    return _memory_ui_service


__all__ = [
    "MemoryUIService",
    "get_memory_ui_service",
]
