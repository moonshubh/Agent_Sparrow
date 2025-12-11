"""Issue Resolution Store for tracking resolved support tickets.

This module provides a store for tracking issue resolutions with vector embeddings
for semantic similarity search. Used to find similar past resolutions when handling
new support tickets.

The store:
- Tracks resolved issues with category, problem/solution summaries
- Uses Gemini embeddings for semantic search on problem descriptions
- Supports efficient similarity queries via IVFFlat index
- Auto-cleans old resolutions (30-day TTL via pg_cron)

Usage:
    from app.agents.harness.store import IssueResolutionStore

    store = IssueResolutionStore()

    # Store a new resolution
    await store.store_resolution(
        ticket_id="12345",
        category="account_setup",
        problem_summary="User cannot log in after password reset",
        solution_summary="Cleared browser cache and regenerated session token",
        was_escalated=False,
        kb_articles_used=["KB001", "KB002"],
        macros_used=["macro_password_reset"],
    )

    # Find similar past resolutions
    similar = await store.find_similar_resolutions(
        query="Customer having login issues after changing password",
        limit=5,
        min_similarity=0.7,
    )
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from loguru import logger

if TYPE_CHECKING:
    from supabase import Client as SupabaseClient


# Table name for issue resolutions
RESOLUTIONS_TABLE = "issue_resolutions"

# Sentinel for import failure detection
_IMPORT_FAILED = object()


def _parse_datetime(value: str | None) -> Optional[datetime]:
    """Parse ISO datetime string, handling trailing Z."""
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@dataclass(frozen=True, slots=True)
class IssueResolution:
    """A resolved issue record.

    Attributes:
        id: Unique identifier (UUID).
        ticket_id: Original ticket/session ID.
        category: Issue category (e.g., "account_setup", "sync_auth").
        problem_summary: Summary of the problem encountered.
        solution_summary: Summary of how it was resolved.
        was_escalated: Whether this required escalation.
        kb_articles_used: List of KB article IDs used in resolution.
        macros_used: List of macro IDs used in resolution.
        similarity: Similarity score (only present in search results).
        created_at: When the resolution was stored.
    """

    id: str
    ticket_id: str
    category: str
    problem_summary: str
    solution_summary: str
    was_escalated: bool = False
    kb_articles_used: List[str] | None = None
    macros_used: List[str] | None = None
    similarity: float | None = None
    created_at: datetime | None = None


class IssueResolutionStore:
    """Store for tracking issue resolutions with vector similarity search.

    Uses Supabase with pgvector for storing and querying resolved issues.
    Embeddings are generated using the model registry's configured embedding model.

    Example:
        store = IssueResolutionStore()

        # Store resolution
        await store.store_resolution(
            ticket_id="12345",
            category="account_setup",
            problem_summary="User cannot login",
            solution_summary="Reset session tokens",
        )

        # Find similar
        results = await store.find_similar_resolutions(
            query="Login issues after password change",
            limit=5,
        )
    """

    def __init__(self, supabase_client: Optional["SupabaseClient"] = None) -> None:
        """Initialize the issue resolution store.

        Args:
            supabase_client: Optional Supabase client. If not provided,
                             will be lazy-loaded from app.db.supabase.
        """
        self._client = supabase_client
        self._embeddings_model = None

    @property
    def client(self) -> Optional["SupabaseClient"]:
        """Lazy-load the Supabase client.

        Returns None if import failed or client unavailable.
        """
        if self._client is _IMPORT_FAILED:
            return None

        if self._client is None:
            try:
                from app.db.supabase.client import get_supabase_client

                self._client = get_supabase_client()
            except ImportError:
                logger.warning(
                    "Supabase client not available for IssueResolutionStore"
                )
                self._client = _IMPORT_FAILED  # type: ignore
                return None
            except Exception as exc:
                logger.warning(
                    "Supabase client initialization failed",
                    error=str(exc),
                )
                self._client = _IMPORT_FAILED  # type: ignore
                return None

        return self._client

    def _get_embeddings_model(self):
        """Lazy-load the embeddings model using the registry.

        Uses the model registry to get the configured embedding model,
        ensuring consistency with the rest of the system.
        """
        if self._embeddings_model is _IMPORT_FAILED:
            return None

        if self._embeddings_model is None:
            try:
                from langchain_google_genai import GoogleGenerativeAIEmbeddings

                from app.core.config import get_registry

                registry = get_registry()
                self._embeddings_model = GoogleGenerativeAIEmbeddings(
                    model=registry.embedding.id
                )
            except ImportError as exc:
                logger.warning(
                    "Embeddings model not available",
                    error=str(exc),
                )
                self._embeddings_model = _IMPORT_FAILED  # type: ignore
                return None
            except Exception as exc:
                logger.warning(
                    "Embeddings model initialization failed",
                    error=str(exc),
                )
                self._embeddings_model = _IMPORT_FAILED  # type: ignore
                return None

        return self._embeddings_model

    async def get_embedding(self, text: str) -> List[float] | None:
        """Get embedding vector for text using registry-configured model.

        Args:
            text: Text to embed.

        Returns:
            List of floats representing the embedding, or None if embedding failed.
        """
        model = self._get_embeddings_model()
        if model is None:
            return None

        try:
            # Use async embed if available, else run sync in executor
            if hasattr(model, "aembed_query"):
                return await model.aembed_query(text)
            else:
                loop = asyncio.get_running_loop()
                return await loop.run_in_executor(None, model.embed_query, text)
        except Exception as exc:
            logger.warning(
                "embedding_generation_failed",
                text_length=len(text),
                error=str(exc),
            )
            return None

    async def store_resolution(
        self,
        ticket_id: str,
        category: str,
        problem_summary: str,
        solution_summary: str,
        was_escalated: bool = False,
        kb_articles_used: List[str] | None = None,
        macros_used: List[str] | None = None,
    ) -> Optional[str]:
        """Store a new issue resolution.

        Args:
            ticket_id: The original ticket/session ID.
            category: Issue category (e.g., "account_setup", "sync_auth").
            problem_summary: Summary of the problem (used for embedding).
            solution_summary: Summary of the resolution.
            was_escalated: Whether this required escalation.
            kb_articles_used: List of KB article IDs used.
            macros_used: List of macro IDs used.

        Returns:
            The resolution ID if successful, None otherwise.
        """
        if not self.client:
            logger.warning("store_resolution_failed: no client")
            return None

        # Generate embedding for the problem summary
        embedding = await self.get_embedding(problem_summary)

        data: Dict[str, Any] = {
            "ticket_id": ticket_id,
            "category": category,
            "problem_summary": problem_summary,
            "solution_summary": solution_summary,
            "was_escalated": was_escalated,
            "kb_articles_used": kb_articles_used or [],
            "macros_used": macros_used or [],
        }

        # Only include embedding if we got one
        if embedding is not None:
            data["embedding"] = embedding

        try:
            response = (
                self.client.table(RESOLUTIONS_TABLE)
                .insert(data)
                .execute()
            )

            if response.data and len(response.data) > 0:
                resolution_id = response.data[0].get("id")
                logger.info(
                    "resolution_stored",
                    resolution_id=resolution_id,
                    ticket_id=ticket_id,
                    category=category,
                    has_embedding=embedding is not None,
                )
                return resolution_id

        except Exception as exc:
            logger.warning(
                "store_resolution_error",
                ticket_id=ticket_id,
                category=category,
                error=str(exc),
            )

        return None

    async def find_similar_resolutions(
        self,
        query: str,
        category: Optional[str] = None,
        limit: int = 5,
        min_similarity: float = 0.6,
    ) -> List[IssueResolution]:
        """Find similar past resolutions using semantic search.

        Args:
            query: The problem description to search for.
            category: Optional category filter.
            limit: Maximum number of results.
            min_similarity: Minimum similarity threshold (0-1).

        Returns:
            List of similar IssueResolution objects, sorted by similarity.
        """
        if not self.client:
            return []

        # Generate embedding for the query
        embedding = await self.get_embedding(query)
        if embedding is None:
            logger.warning("find_similar_resolutions: embedding generation failed")
            return []

        try:
            # Use Supabase RPC for vector similarity search
            # The RPC function should be created by the migration
            params: Dict[str, Any] = {
                "query_embedding": embedding,
                "match_count": limit,
                "min_similarity": min_similarity,
            }

            if category:
                params["filter_category"] = category

            response = self.client.rpc(
                "search_similar_resolutions",
                params,
            ).execute()

            results: List[IssueResolution] = []
            for row in response.data or []:
                results.append(
                    IssueResolution(
                        id=row["id"],
                        ticket_id=row["ticket_id"],
                        category=row["category"],
                        problem_summary=row["problem_summary"],
                        solution_summary=row["solution_summary"],
                        was_escalated=row.get("was_escalated", False),
                        kb_articles_used=row.get("kb_articles_used"),
                        macros_used=row.get("macros_used"),
                        similarity=row.get("similarity"),
                        created_at=_parse_datetime(row.get("created_at")),
                    )
                )

            logger.info(
                "similar_resolutions_found",
                query_length=len(query),
                category=category,
                results_count=len(results),
            )

            return results

        except Exception as exc:
            logger.warning(
                "find_similar_resolutions_error",
                error=str(exc),
            )
            return []

    async def get_resolution_by_ticket(
        self, ticket_id: str
    ) -> Optional[IssueResolution]:
        """Get the resolution for a specific ticket.

        Args:
            ticket_id: The ticket ID to look up.

        Returns:
            IssueResolution if found, None otherwise.
        """
        if not self.client:
            return None

        try:
            response = (
                self.client.table(RESOLUTIONS_TABLE)
                .select("*")
                .eq("ticket_id", ticket_id)
                .limit(1)
                .execute()
            )

            if response.data and len(response.data) > 0:
                row = response.data[0]
                return IssueResolution(
                    id=row["id"],
                    ticket_id=row["ticket_id"],
                    category=row["category"],
                    problem_summary=row["problem_summary"],
                    solution_summary=row["solution_summary"],
                    was_escalated=row.get("was_escalated", False),
                    kb_articles_used=row.get("kb_articles_used"),
                    macros_used=row.get("macros_used"),
                    created_at=_parse_datetime(row.get("created_at")),
                )

        except Exception as exc:
            logger.warning(
                "get_resolution_by_ticket_error",
                ticket_id=ticket_id,
                error=str(exc),
            )

        return None

    async def get_resolutions_by_category(
        self,
        category: str,
        limit: int = 20,
        include_escalated: bool = True,
    ) -> List[IssueResolution]:
        """Get recent resolutions for a category.

        Args:
            category: The category to filter by.
            limit: Maximum number of results.
            include_escalated: Whether to include escalated issues.

        Returns:
            List of IssueResolution objects, sorted by recency.
        """
        if not self.client:
            return []

        try:
            query = (
                self.client.table(RESOLUTIONS_TABLE)
                .select("*")
                .eq("category", category)
            )

            if not include_escalated:
                query = query.eq("was_escalated", False)

            response = (
                query.order("created_at", desc=True)
                .limit(limit)
                .execute()
            )

            results: List[IssueResolution] = []
            for row in response.data or []:
                results.append(
                    IssueResolution(
                        id=row["id"],
                        ticket_id=row["ticket_id"],
                        category=row["category"],
                        problem_summary=row["problem_summary"],
                        solution_summary=row["solution_summary"],
                        was_escalated=row.get("was_escalated", False),
                        kb_articles_used=row.get("kb_articles_used"),
                        macros_used=row.get("macros_used"),
                        created_at=_parse_datetime(row.get("created_at")),
                    )
                )

            return results

        except Exception as exc:
            logger.warning(
                "get_resolutions_by_category_error",
                category=category,
                error=str(exc),
            )
            return []

    async def delete_resolution(self, resolution_id: str) -> bool:
        """Delete a resolution by ID.

        Args:
            resolution_id: The resolution ID to delete.

        Returns:
            True if deleted, False otherwise.
        """
        if not self.client:
            return False

        try:
            response = (
                self.client.table(RESOLUTIONS_TABLE)
                .delete()
                .eq("id", resolution_id)
                .execute()
            )

            deleted_count = getattr(response, "count", None)
            if deleted_count is None and response.data is not None:
                deleted_count = len(response.data)

            if deleted_count and deleted_count > 0:
                logger.info("resolution_deleted", resolution_id=resolution_id)
                return True

            logger.warning(
                "resolution_delete_not_found",
                resolution_id=resolution_id,
            )
            return False

        except Exception as exc:
            logger.warning(
                "delete_resolution_error",
                resolution_id=resolution_id,
                error=str(exc),
            )
            return False

    async def get_category_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for each category.

        Returns:
            Dict mapping category to stats (count, escalation_rate, etc.).
        """
        if not self.client:
            return {}

        try:
            # Get counts per category
            response = (
                self.client.table(RESOLUTIONS_TABLE)
                .select("category, was_escalated")
                .execute()
            )

            # Aggregate stats
            stats: Dict[str, Dict[str, Any]] = {}
            for row in response.data or []:
                category = row["category"]
                if category not in stats:
                    stats[category] = {"count": 0, "escalated": 0}
                stats[category]["count"] += 1
                if row.get("was_escalated"):
                    stats[category]["escalated"] += 1

            # Calculate rates
            for category, cat_stats in stats.items():
                count = cat_stats["count"]
                escalated = cat_stats["escalated"]
                cat_stats["escalation_rate"] = (
                    escalated / count if count > 0 else 0.0
                )

            return stats

        except Exception as exc:
            logger.warning(
                "get_category_stats_error",
                error=str(exc),
            )
            return {}
