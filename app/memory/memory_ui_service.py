"""
Memory UI Service for Agent Sparrow.

This service provides CRUD operations for the memories table, including
embedding generation via Google Gemini and integration with database functions
for feedback, merge, duplicate detection, and statistics.
"""

from __future__ import annotations

import asyncio
import os
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Sequence

from postgrest.base_request_builder import CountMethod
from uuid import UUID

from app.core.logging_config import get_logger
from app.core.rate_limiting.agent_wrapper import get_rate_limiter
from app.core.rate_limiting.exceptions import RateLimitExceededException
from app.core.settings import settings
from app.db.embedding_config import EXPECTED_DIM, MODEL_NAME
from app.db.supabase.client import get_supabase_client, SupabaseClient
from app.memory.edit_state import (
    CLEANUP_PROTECTED_MIN_CONFIDENCE,
    is_memory_edited,
    partition_cleanup_candidates,
)
from app.memory.title import ensure_memory_title
from app.security.pii_redactor import redact_pii, redact_pii_from_dict

logger = get_logger(__name__)

COUNT_EXACT: CountMethod = CountMethod.exact
ZERO_UUID = UUID("00000000-0000-0000-0000-000000000000")
EMBEDDING_SYNC_TIMEOUT_SECONDS = 12.0
EMBEDDING_DEFERRED_TIMEOUT_SECONDS = 45.0
DEFAULT_EDITED_FILTER_SCAN_CAP = 20000


def _load_edited_filter_scan_cap() -> int:
    raw = os.getenv("MEMORY_EDITED_FILTER_SCAN_CAP", str(DEFAULT_EDITED_FILTER_SCAN_CAP))
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_EDITED_FILTER_SCAN_CAP
    return value if value > 0 else DEFAULT_EDITED_FILTER_SCAN_CAP


EDITED_FILTER_SCAN_CAP = _load_edited_filter_scan_cap()
DELETE_MEMORIES_RPC = "delete_memories_with_relationship_cleanup"
LIST_MEMORIES_EDITED_RPC = "list_memories_with_edited_state"


class MemoryUIService:
    """
    Service class for Memory UI operations.

    Handles CRUD operations for the memories table with Gemini embedding generation
    and integration with database functions for feedback, merging, and statistics.
    """

    # Avoid selecting the 3072-dim `embedding` column unless explicitly needed.
    MEMORY_SELECT_COLUMNS = (
        "id,content,metadata,source_type,review_status,reviewed_by,reviewed_at,confidence_score,"
        "retrieval_count,last_retrieved_at,feedback_positive,feedback_negative,"
        "resolution_success_count,resolution_failure_count,agent_id,tenant_id,created_at,updated_at"
    )
    # Used for edited-state scans to avoid loading large content payloads.
    EDIT_STATE_SCAN_COLUMNS = "id,created_at,updated_at,reviewed_by,metadata"

    def __init__(self) -> None:
        self._supabase: Optional[SupabaseClient] = None
        self._embedding_model = None
        self._lock = asyncio.Lock()
        self._embedding_refresh_tasks: dict[str, asyncio.Task[None]] = {}

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

    def _schedule_embedding_refresh(
        self,
        memory_id: str,
        content: str,
        expected_updated_at: str | None,
    ) -> None:
        """Schedule a best-effort background embedding refresh for a memory."""
        active_task = self._embedding_refresh_tasks.get(memory_id)
        if active_task and not active_task.done():
            active_task.cancel()

        async def _runner() -> None:
            await self._refresh_embedding_for_memory(
                memory_id=memory_id,
                content=content,
                expected_updated_at=expected_updated_at,
            )

        try:
            task = asyncio.create_task(_runner())
        except RuntimeError as exc:
            logger.warning(
                "Failed to schedule deferred embedding refresh for memory %s: %s",
                memory_id,
                exc,
            )
            return

        self._embedding_refresh_tasks[memory_id] = task
        task.add_done_callback(
            lambda completed_task: self._clear_embedding_refresh_task(
                memory_id, completed_task
            )
        )

    def _clear_embedding_refresh_task(
        self, memory_id: str, completed_task: asyncio.Task[None]
    ) -> None:
        current_task = self._embedding_refresh_tasks.get(memory_id)
        if current_task is completed_task:
            self._embedding_refresh_tasks.pop(memory_id, None)

    async def _refresh_embedding_for_memory(
        self,
        memory_id: str,
        content: str,
        expected_updated_at: str | None,
    ) -> None:
        """Regenerate and persist embedding in the background (best effort)."""
        try:
            embedding = await asyncio.wait_for(
                self.generate_embedding(content),
                timeout=EMBEDDING_DEFERRED_TIMEOUT_SECONDS,
            )
            supabase = self._get_supabase()
            response = await supabase._exec(
                lambda: (
                    supabase.client.table("memories")
                    .update({"embedding": embedding})
                    .eq("id", memory_id)
                    .eq("updated_at", expected_updated_at)
                    .execute()
                    if expected_updated_at
                    else supabase.client.table("memories")
                    .update({"embedding": embedding})
                    .eq("id", memory_id)
                    .execute()
                )
            )
            if not response.data:
                logger.info(
                    "Skipped deferred embedding refresh for memory %s because a newer update exists",
                    memory_id,
                )
                return
            logger.info(
                "Deferred embedding refresh completed for memory %s", memory_id
            )
        except asyncio.CancelledError:
            logger.debug("Deferred embedding refresh cancelled for memory %s", memory_id)
            raise
        except Exception as exc:
            logger.warning(
                "Deferred embedding refresh failed for memory %s: %s",
                memory_id,
                exc,
            )

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
        reviewer_id: Optional[UUID] = None,
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

        if reviewer_id and reviewer_id != ZERO_UUID:
            reviewer_id_str = str(reviewer_id)
            reviewer_exists = False
            try:
                reviewer_lookup = await supabase._exec(
                    lambda: supabase.client.schema("auth")
                    .table("users")
                    .select("id")
                    .eq("id", reviewer_id_str)
                    .maybe_single()
                    .execute()
                )
                reviewer_exists = bool(reviewer_lookup and reviewer_lookup.data)
            except Exception as exc:  # noqa: BLE001 -- non-critical lookup should fail open
                logger.warning(
                    "Reviewer lookup failed for %s while updating memory %s; skipping reviewed_by update: %s",
                    reviewer_id_str,
                    memory_id_str,
                    exc,
                )

            if reviewer_exists:
                update_payload["reviewed_by"] = reviewer_id_str
                update_payload["reviewed_at"] = datetime.now(timezone.utc).isoformat()
            else:
                logger.warning(
                    "Skipping reviewed_by update for memory %s because reviewer %s does not exist in auth.users",
                    memory_id_str,
                    reviewer_id_str,
                )

        defer_embedding_refresh = False

        # Regenerate embedding if content changed
        if content != existing_content:
            try:
                embedding = await asyncio.wait_for(
                    self.generate_embedding(content),
                    timeout=EMBEDDING_SYNC_TIMEOUT_SECONDS,
                )
                update_payload["embedding"] = embedding
                logger.info(
                    "Content changed for memory %s, regenerated embedding",
                    memory_id_str,
                )
            except Exception as exc:
                # Fail open for edit durability; refresh embedding in background.
                defer_embedding_refresh = True
                logger.warning(
                    "Embedding regeneration deferred for memory %s after sync failure: %s",
                    memory_id_str,
                    exc,
                )

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
                if defer_embedding_refresh:
                    expected_updated_at = (
                        memory.get("updated_at")
                        if isinstance(memory.get("updated_at"), str)
                        else update_payload.get("updated_at")
                    )
                    self._schedule_embedding_refresh(
                        memory_id=memory_id_str,
                        content=content,
                        expected_updated_at=(
                            str(expected_updated_at)
                            if expected_updated_at is not None
                            else None
                        ),
                    )
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

        orphaned_count = 0
        relationships_count = 0

        try:
            deleted_memories = 0
            try:
                rpc_response = await supabase._exec(
                    lambda: supabase.rpc(
                        DELETE_MEMORIES_RPC, {"p_memory_ids": [memory_id_str]}
                    ).execute()
                )
                rpc_rows = rpc_response.data or []
                rpc_row = rpc_rows[0] if rpc_rows else {}
                deleted_memories = int(rpc_row.get("deleted_memories") or 0)
                relationships_count = int(rpc_row.get("deleted_relationships") or 0)
            except Exception as rpc_exc:
                message = str(rpc_exc).lower()
                rpc_missing = (
                    DELETE_MEMORIES_RPC in message
                    and (
                        "not found" in message
                        or "does not exist" in message
                        or "could not find the function" in message
                        or "schema cache" in message
                    )
                )
                if not rpc_missing:
                    raise
                logger.error(
                    "delete_memory_rpc_unavailable_blocked id=%s error=%s",
                    memory_id_str,
                    str(rpc_exc)[:200],
                )
                raise RuntimeError(
                    f"{DELETE_MEMORIES_RPC} is required for safe deletion. "
                    "Apply migration 041_add_guarded_memory_delete_rpc.sql "
                    "before deleting memories."
                )

            if deleted_memories > 0:
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

    async def partition_cleanup_delete_candidates(
        self,
        memory_rows: Sequence[dict[str, Any]],
        *,
        min_confidence: float = CLEANUP_PROTECTED_MIN_CONFIDENCE,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """
        Safety guard for bulk cleanup paths.

        Splits candidate rows into:
        - deletable rows
        - protected rows (edited + confidence >= threshold)
        """
        deletable, protected = partition_cleanup_candidates(
            memory_rows, min_confidence=min_confidence
        )
        if protected:
            logger.warning(
                "memory_cleanup_guard_excluded protected_count=%d threshold=%.2f",
                len(protected),
                float(min_confidence),
            )
        return deletable, protected

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
                count = (
                    result[0].get("count", 0)
                    if isinstance(result[0], dict)
                    else len(result)
                )
            else:
                count = 0

            logger.info("Detected %d duplicates for memory %s", count, memory_id)
            return count
        except Exception as exc:
            logger.error(
                "Failed to detect duplicates for memory %s: %s", memory_id, exc
            )
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

            if response and response.data:
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
        edited_state: Literal["all", "edited", "unedited"] = "all",
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
            edited_state: Optional edited-state filter ("all", "edited", "unedited").
            limit: Maximum number of results.
            offset: Number of results to skip.

        Returns:
            A list of memory records.
        """
        memories, _total = await self.list_memories_with_total(
            agent_id=agent_id,
            tenant_id=tenant_id,
            source_type=source_type,
            edited_state=edited_state,
            limit=limit,
            offset=offset,
            sort_order=sort_order,
        )
        return memories

    async def list_memories_with_total(
        self,
        agent_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        source_type: Optional[str] = None,
        edited_state: Literal["all", "edited", "unedited"] = "all",
        limit: int = 50,
        offset: int = 0,
        sort_order: str = "desc",
    ) -> tuple[List[Dict[str, Any]], int]:
        """
        List memories with optional filters and an exact total count.

        Returns:
            Tuple of (memory records, total count).
        """
        supabase = self._get_supabase()

        sort_order_norm = (sort_order or "desc").lower()
        if sort_order_norm not in ("asc", "desc"):
            sort_order_norm = "desc"
        edited_state_norm = (edited_state or "all").lower()
        if edited_state_norm not in {"all", "edited", "unedited"}:
            edited_state_norm = "all"

        def apply_filters(query):
            if agent_id:
                query = query.eq("agent_id", agent_id)
            if tenant_id:
                query = query.eq("tenant_id", tenant_id)
            if source_type:
                query = query.eq("source_type", source_type)
            return query

        def matches_edit_state(memory_row: dict[str, Any]) -> bool:
            if edited_state_norm == "all":
                return True
            edited = is_memory_edited(memory_row)
            return edited if edited_state_norm == "edited" else not edited

        async def list_with_python_fallback() -> tuple[list[dict[str, Any]], int]:
            count_query = apply_filters(
                supabase.client.table("memories").select("id", count=COUNT_EXACT, head=True)
            )
            count_response = await supabase._exec(lambda: count_query.execute())
            base_total = int(count_response.count or 0)
            if base_total > EDITED_FILTER_SCAN_CAP:
                raise ValueError(
                    "edited_state filter scan limit exceeded "
                    f"({base_total} rows > {EDITED_FILTER_SCAN_CAP} cap). "
                    "Narrow the query with source_type/agent_id/tenant_id filters "
                    "or increase MEMORY_EDITED_FILTER_SCAN_CAP."
                )

            batch_size = max(200, min(1000, int(limit) * 5))
            fetched = 0
            matched_total = 0
            page_ids: list[str] = []
            page_start = int(offset)
            page_end = page_start + int(limit)

            while fetched < base_total:
                page_query = (
                    apply_filters(
                        supabase.client.table("memories").select(self.EDIT_STATE_SCAN_COLUMNS)
                    )
                    .order("created_at", desc=sort_order_norm == "desc")
                    .range(fetched, fetched + batch_size - 1)
                )
                page_response = await supabase._exec(lambda: page_query.execute())
                batch = page_response.data if page_response.data else []
                if not batch:
                    break
                for row in batch:
                    if not matches_edit_state(row):
                        continue
                    memory_id = row.get("id")
                    if not isinstance(memory_id, str) or not memory_id:
                        continue
                    if page_start <= matched_total < page_end:
                        page_ids.append(memory_id)
                    matched_total += 1
                fetched += len(batch)
                if len(batch) < batch_size:
                    break

            total = matched_total
            paged_rows: list[dict[str, Any]] = []
            if page_ids:
                row_query = apply_filters(
                    supabase.client.table("memories").select(self.MEMORY_SELECT_COLUMNS)
                ).in_("id", page_ids)
                row_response = await supabase._exec(lambda: row_query.execute())
                rows = row_response.data if row_response.data else []
                row_map: dict[str, dict[str, Any]] = {}
                for row in rows:
                    row_id = row.get("id")
                    if isinstance(row_id, str):
                        row_map[row_id] = row
                paged_rows = [row_map[row_id] for row_id in page_ids if row_id in row_map]
            logger.warning(
                "list_memories_edited_state_using_python_fallback edited_state=%s total=%d",
                edited_state_norm,
                total,
            )
            return paged_rows, total

        try:
            if edited_state_norm != "all":
                try:
                    rpc_response = await supabase._exec(
                        lambda: supabase.rpc(
                            LIST_MEMORIES_EDITED_RPC,
                            {
                                "p_agent_id": agent_id,
                                "p_tenant_id": tenant_id,
                                "p_source_type": source_type,
                                "p_edited_state": edited_state_norm,
                                "p_limit": int(limit),
                                "p_offset": int(offset),
                                "p_sort_order": sort_order_norm,
                            },
                        ).execute()
                    )
                except Exception as rpc_exc:
                    message = str(rpc_exc).lower()
                    rpc_missing = LIST_MEMORIES_EDITED_RPC in message and (
                        "not found" in message
                        or "does not exist" in message
                        or "could not find the function" in message
                        or "schema cache" in message
                    )
                    if rpc_missing:
                        logger.warning(
                            "list_memories_edited_state_rpc_unavailable_fallback error=%s",
                            str(rpc_exc)[:200],
                        )
                        return await list_with_python_fallback()
                    raise

                rpc_rows = list(rpc_response.data or [])
                total = int(rpc_rows[0].get("total_count") or 0) if rpc_rows else 0
                if not rpc_rows and int(offset) > 0:
                    summary_response = await supabase._exec(
                        lambda: supabase.rpc(
                            LIST_MEMORIES_EDITED_RPC,
                            {
                                "p_agent_id": agent_id,
                                "p_tenant_id": tenant_id,
                                "p_source_type": source_type,
                                "p_edited_state": edited_state_norm,
                                "p_limit": 1,
                                "p_offset": 0,
                                "p_sort_order": sort_order_norm,
                            },
                        ).execute()
                    )
                    summary_rows = list(summary_response.data or [])
                    total = int(summary_rows[0].get("total_count") or 0) if summary_rows else 0
                paged_rows: list[dict[str, Any]] = []
                for row in rpc_rows:
                    if not isinstance(row, dict):
                        continue
                    normalized = dict(row)
                    normalized.pop("total_count", None)
                    paged_rows.append(normalized)
                logger.debug(
                    "Listed %d memories (total=%d, edited_state=%s)",
                    len(paged_rows),
                    total,
                    edited_state_norm,
                )
                return paged_rows, total

            data_query = (
                apply_filters(
                    supabase.client.table("memories").select(self.MEMORY_SELECT_COLUMNS)
                )
                .order("created_at", desc=sort_order_norm == "desc")
                .range(offset, offset + limit - 1)
            )

            count_query = apply_filters(
                supabase.client.table("memories").select(
                    "id", count=COUNT_EXACT, head=True
                )
            )

            data_response = await supabase._exec(lambda: data_query.execute())
            count_response = await supabase._exec(lambda: count_query.execute())

            memories = data_response.data if data_response.data else []
            total = int(count_response.count or 0)

            logger.debug(
                "Listed %d memories (total=%d, edited_state=%s)",
                len(memories),
                total,
                edited_state_norm,
            )
            return memories, total
        except Exception as exc:
            logger.error("Failed to list memories with total: %s", exc)
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
