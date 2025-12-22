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
import json
import math
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from loguru import logger

if TYPE_CHECKING:
    from supabase import Client as SupabaseClient


# Table name for issue resolutions
RESOLUTIONS_TABLE = "issue_resolutions"

# Heuristics to keep the store "pattern-focused" (high signal, low redundancy)
MIN_PROBLEM_SUMMARY_CHARS = 40
MIN_SOLUTION_SUMMARY_CHARS = 60
MAX_PROBLEM_SUMMARY_CHARS = 800
MAX_SOLUTION_SUMMARY_CHARS = 1200
DEFAULT_MAX_PER_CATEGORY = 500
DUPLICATE_MIN_SIMILARITY = 0.92
DUPLICATE_MIN_SOLUTION_JACCARD = 0.55
RERANK_CANDIDATE_MULTIPLIER = 5

# Sentinel for import failure detection
_IMPORT_FAILED = object()


def _parse_datetime(value: str | None) -> Optional[datetime]:
    """Parse ISO datetime string, handling trailing Z."""
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _normalize_one_line(text: str) -> str:
    """Normalize whitespace for stable comparisons."""
    return " ".join(str(text or "").split()).strip()


def _tokenize(text: str) -> set[str]:
    import re

    return set(re.findall(r"[a-z0-9]+", str(text or "").lower()))


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = a & b
    union = a | b
    return len(inter) / max(1, len(union))


def _build_embedding_text(problem_summary: str, solution_summary: str) -> str:
    """Build the text that gets embedded for storage/search.

    We intentionally emphasize the human-readable problem/solution summaries
    over raw metadata to keep the vector space high-signal.
    """
    p = _normalize_one_line(problem_summary)
    s = _normalize_one_line(solution_summary)
    return f"Problem: {p}\nSolution: {s}".strip()


def _lexical_similarity(query: str, problem_summary: str, solution_summary: str) -> float:
    """Cheap similarity proxy when vector RPC is unavailable."""
    q = _tokenize(query)
    if not q:
        return 0.0
    prob = _tokenize(problem_summary)
    sol = _tokenize(solution_summary)
    # Weight problem slightly higher than solution
    return (0.6 * _jaccard(q, prob)) + (0.4 * _jaccard(q, sol))


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """Cosine similarity for equal-length vectors (numpy-free)."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += float(x) * float(y)
        na += float(x) * float(x)
        nb += float(y) * float(y)
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


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
                from app.core.settings import settings

                registry = get_registry()
                api_key = getattr(settings, "gemini_api_key", None)
                if not api_key:
                    raise ValueError("GEMINI_API_KEY is not configured")
                self._embeddings_model = GoogleGenerativeAIEmbeddings(
                    model=registry.embedding.id,
                    google_api_key=api_key,
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
        *,
        dedupe: bool = True,
        prune: bool = True,
        max_per_category: int = DEFAULT_MAX_PER_CATEGORY,
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
        client = self.client
        if not client:
            logger.warning("store_resolution_failed: no client")
            return None

        problem_summary = str(problem_summary or "").strip()
        solution_summary = str(solution_summary or "").strip()

        # Quality gate: keep only high-utility patterns.
        if len(problem_summary) < MIN_PROBLEM_SUMMARY_CHARS or len(solution_summary) < MIN_SOLUTION_SUMMARY_CHARS:
            logger.info(
                "resolution_skipped_low_utility",
                ticket_id=ticket_id,
                category=category,
                problem_chars=len(problem_summary),
                solution_chars=len(solution_summary),
            )
            return None

        # Keep fields bounded to avoid unbounded prompt bloat in retrieved snippets.
        if len(problem_summary) > MAX_PROBLEM_SUMMARY_CHARS:
            problem_summary = problem_summary[:MAX_PROBLEM_SUMMARY_CHARS].rstrip() + "…"
        if len(solution_summary) > MAX_SOLUTION_SUMMARY_CHARS:
            solution_summary = solution_summary[:MAX_SOLUTION_SUMMARY_CHARS].rstrip() + "…"

        # Generate embedding for a combined "scenario" representation.
        embedding_text = _build_embedding_text(problem_summary, solution_summary)
        embedding = await self.get_embedding(embedding_text)
        if embedding is None:
            logger.warning(
                "store_resolution_failed_no_embedding",
                ticket_id=ticket_id,
                category=category,
            )
            return None

        # Optional dedupe: avoid storing near-identical patterns.
        if dedupe:
            try:
                existing = await asyncio.to_thread(
                    self._search_similar_by_embedding,
                    embedding=embedding,
                    category=category,
                    limit=3,
                    min_similarity=DUPLICATE_MIN_SIMILARITY,
                )
                solution_tokens = _tokenize(solution_summary)
                for hit in existing:
                    hit_solution_tokens = _tokenize(hit.solution_summary)
                    if _jaccard(solution_tokens, hit_solution_tokens) >= DUPLICATE_MIN_SOLUTION_JACCARD:
                        logger.info(
                            "resolution_deduped",
                            ticket_id=ticket_id,
                            category=category,
                            existing_id=hit.id,
                            similarity=hit.similarity,
                        )
                        return hit.id
            except Exception as exc:
                logger.debug("resolution_dedupe_failed", error=str(exc))

        data: Dict[str, Any] = {
            "ticket_id": ticket_id,
            "category": category,
            "problem_summary": problem_summary,
            "solution_summary": solution_summary,
            "was_escalated": was_escalated,
            "kb_articles_used": kb_articles_used or [],
            "macros_used": macros_used or [],
            "embedding": embedding,
        }

        try:
            response = await asyncio.to_thread(
                lambda: client.table(RESOLUTIONS_TABLE).insert(data).execute()
            )

            if response.data and len(response.data) > 0:
                resolution_id = response.data[0].get("id")
                logger.info(
                    "resolution_stored",
                    resolution_id=resolution_id,
                    ticket_id=ticket_id,
                    category=category,
                    has_embedding=True,
                )
                if prune:
                    try:
                        pruned = await asyncio.to_thread(
                            self.prune_category,
                            category=category,
                            max_per_category=max(1, int(max_per_category)),
                        )
                        if pruned:
                            logger.info(
                                "resolution_pruned",
                                category=category,
                                deleted=pruned,
                            )
                    except Exception as exc:
                        logger.debug("resolution_prune_failed", error=str(exc))
                return resolution_id

        except Exception as exc:
            logger.warning(
                "store_resolution_error",
                ticket_id=ticket_id,
                category=category,
                error=str(exc),
            )

        return None

    def _search_similar_by_embedding(
        self,
        *,
        embedding: List[float],
        category: Optional[str],
        limit: int,
        min_similarity: float,
    ) -> List[IssueResolution]:
        """Search similar resolutions using a precomputed embedding."""
        if not self.client:
            return []

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
        return results

    def _search_similar_by_text(
        self,
        *,
        query: str,
        category: Optional[str],
        limit: int,
        min_similarity: float,
        sample_limit: int = 250,
    ) -> List[IssueResolution]:
        """Fallback similarity search using lexical overlap (no RPC required)."""
        if not self.client:
            return []

        query_text = str(query or "").strip()
        if not query_text:
            return []

        sample_limit = max(20, min(1000, int(sample_limit)))
        try:
            q = (
                self.client.table(RESOLUTIONS_TABLE)
                .select(
                    "id,ticket_id,category,problem_summary,solution_summary,was_escalated,kb_articles_used,macros_used,created_at"
                )
                .order("created_at", desc=True)
                .limit(sample_limit)
            )
            if category:
                q = q.eq("category", category)
            resp = q.execute()
            rows = list(resp.data or [])
        except Exception as exc:
            logger.warning("text_fallback_query_failed", error=str(exc))
            return []

        scored: List[IssueResolution] = []
        # Lexical similarity tends to be lower than embeddings; relax threshold slightly.
        threshold = max(0.05, float(min_similarity) * 0.35)
        for row in rows:
            ps = str(row.get("problem_summary") or "")
            ss = str(row.get("solution_summary") or "")
            score = _lexical_similarity(query_text, ps, ss)
            if score < threshold:
                continue
            scored.append(
                IssueResolution(
                    id=row["id"],
                    ticket_id=row["ticket_id"],
                    category=row["category"],
                    problem_summary=ps,
                    solution_summary=ss,
                    was_escalated=row.get("was_escalated", False),
                    kb_articles_used=row.get("kb_articles_used"),
                    macros_used=row.get("macros_used"),
                    similarity=score,
                    created_at=_parse_datetime(row.get("created_at")),
                )
            )

        scored.sort(key=lambda r: float(r.similarity or 0.0), reverse=True)
        return scored[: max(0, int(limit))]

    def _search_similar_by_embedding_local(
        self,
        *,
        query_embedding: List[float],
        category: Optional[str],
        limit: int,
        min_similarity: float,
        sample_limit: int = 250,
    ) -> List[IssueResolution]:
        """Fallback similarity search using stored embeddings (no RPC required).

        This is more accurate than lexical fallback, but is bounded by `sample_limit`
        to keep payload size and CPU reasonable.
        """
        if not self.client:
            return []
        if not query_embedding:
            return []

        sample_limit = max(20, min(1000, int(sample_limit)))
        try:
            q = (
                self.client.table(RESOLUTIONS_TABLE)
                .select(
                    "id,ticket_id,category,problem_summary,solution_summary,was_escalated,kb_articles_used,macros_used,embedding,created_at"
                )
                .order("created_at", desc=True)
                .limit(sample_limit)
            )
            if category:
                q = q.eq("category", category)
            resp = q.execute()
            rows = list(resp.data or [])
        except Exception as exc:
            logger.warning("embedding_local_fallback_query_failed", error=str(exc))
            return []

        scored: List[IssueResolution] = []
        for row in rows:
            emb = row.get("embedding")
            if not emb:
                continue
            if isinstance(emb, str):
                # Some PostgREST setups serialize vectors as strings; try JSON parse.
                try:
                    emb = json.loads(emb)
                except Exception:
                    continue
            if not isinstance(emb, list):
                continue
            sim = _cosine_similarity(query_embedding, emb)
            if sim < float(min_similarity):
                continue
            scored.append(
                IssueResolution(
                    id=row["id"],
                    ticket_id=row["ticket_id"],
                    category=row["category"],
                    problem_summary=str(row.get("problem_summary") or ""),
                    solution_summary=str(row.get("solution_summary") or ""),
                    was_escalated=row.get("was_escalated", False),
                    kb_articles_used=row.get("kb_articles_used"),
                    macros_used=row.get("macros_used"),
                    similarity=sim,
                    created_at=_parse_datetime(row.get("created_at")),
                )
            )

        scored.sort(key=lambda r: float(r.similarity or 0.0), reverse=True)
        return scored[: max(0, int(limit))]

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

        query = str(query or "").strip()
        if not query:
            return []

        # Generate embedding for the query (searches against stored scenario embeddings)
        embedding = await self.get_embedding(query)
        if embedding is None:
            logger.warning("find_similar_resolutions: embedding generation failed")
            return []

        try:
            candidate_limit = max(
                int(limit) * RERANK_CANDIDATE_MULTIPLIER,
                int(limit),
            )
            candidate_limit = max(1, min(50, candidate_limit))
            try:
                candidates = await asyncio.to_thread(
                    self._search_similar_by_embedding,
                    embedding=embedding,
                    category=category,
                    limit=candidate_limit,
                    min_similarity=min_similarity,
                )
            except Exception as exc:
                # Fallback: lexical search when RPC is missing/broken.
                logger.warning(
                    "similar_resolutions_vector_rpc_failed_falling_back",
                    error=str(exc)[:180],
                )
                candidates = await asyncio.to_thread(
                    self._search_similar_by_embedding_local,
                    query_embedding=embedding,
                    category=category,
                    limit=candidate_limit,
                    min_similarity=min_similarity,
                )
                if not candidates:
                    candidates = await asyncio.to_thread(
                        self._search_similar_by_text,
                        query=query,
                        category=category,
                        limit=candidate_limit,
                        min_similarity=min_similarity,
                    )

            # Second-pass rerank: favor overlap between query and summaries.
            q_tokens = _tokenize(query)

            def _rank_key(item: IssueResolution) -> float:
                base = float(item.similarity or 0.0)
                text = f"{item.problem_summary}\n{item.solution_summary}"
                jac = _jaccard(q_tokens, _tokenize(text))
                # Weighted blend (still anchored on vector similarity)
                return (0.78 * base) + (0.22 * jac)

            candidates.sort(key=_rank_key, reverse=True)
            results = candidates[: max(0, int(limit))]

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
            # Final fallback: lexical-only search (best-effort)
            return await asyncio.to_thread(
                self._search_similar_by_text,
                query=query,
                category=category,
                limit=limit,
                min_similarity=min_similarity,
            )

    def prune_category(
        self,
        *,
        category: str,
        max_per_category: int = DEFAULT_MAX_PER_CATEGORY,
    ) -> int:
        """Prune oldest entries to keep per-category memory bounded.

        Returns number of deleted rows (best-effort).
        """
        client = self.client
        if not client:
            return 0

        max_per_category = max(1, int(max_per_category))
        try:
            # Preferred: single atomic prune via DB-side RPC (if available).
            # Falls back to batched deletes when the function is not deployed.
            try:
                rpc_resp = client.rpc(
                    "prune_issue_resolutions",
                    {"p_category": category, "p_keep": max_per_category},
                ).execute()
                rpc_data = getattr(rpc_resp, "data", None)
                if rpc_data in (None, [], {}):
                    return 0
                if isinstance(rpc_data, int):
                    return rpc_data
                if isinstance(rpc_data, float):
                    return int(rpc_data)
                if isinstance(rpc_data, str) and rpc_data.isdigit():
                    return int(rpc_data)
                if isinstance(rpc_data, dict):
                    for key in ("deleted", "deleted_count", "count", "pruned", "prune_issue_resolutions"):
                        value = rpc_data.get(key)
                        if isinstance(value, int):
                            return value
                        if isinstance(value, str) and value.isdigit():
                            return int(value)
                if isinstance(rpc_data, list) and rpc_data and isinstance(rpc_data[0], dict):
                    row0 = rpc_data[0]
                    for key in ("deleted", "deleted_count", "count", "pruned", "prune_issue_resolutions"):
                        value = row0.get(key)
                        if isinstance(value, int):
                            return value
                        if isinstance(value, str) and value.isdigit():
                            return int(value)
            except Exception as exc:
                logger.debug("prune_category_rpc_failed_falling_back", category=category, error=str(exc)[:180])

            # Fallback: prune based on a cutoff timestamp (minimizes round trips).
            cutoff_resp = (
                client.table(RESOLUTIONS_TABLE)
                .select("created_at")
                .eq("category", category)
                .order("created_at", desc=True)
                .offset(max_per_category)
                .limit(1)
                .execute()
            )
            cutoff_rows = list(getattr(cutoff_resp, "data", None) or [])
            if not cutoff_rows:
                return 0

            cutoff_created_at = cutoff_rows[0].get("created_at")
            if not cutoff_created_at:
                return 0

            deleted = 0
            while True:
                resp = (
                    client.table(RESOLUTIONS_TABLE)
                    .select("id")
                    .eq("category", category)
                    .lte("created_at", cutoff_created_at)
                    .limit(500)
                    .execute()
                )
                rows = list(getattr(resp, "data", None) or [])
                if not rows:
                    break

                delete_ids = [r.get("id") for r in rows if isinstance(r, dict) and r.get("id")]
                if not delete_ids:
                    break

                (
                    client.table(RESOLUTIONS_TABLE)
                    .delete()
                    .in_("id", delete_ids)
                    .execute()
                )
                deleted += len(delete_ids)
                if len(delete_ids) < 500:
                    break
            return deleted
        except Exception as exc:
            logger.debug("prune_category_error", category=category, error=str(exc))
        return 0

    async def get_resolution_by_ticket(
        self, ticket_id: str
    ) -> Optional[IssueResolution]:
        """Get the resolution for a specific ticket.

        Args:
            ticket_id: The ticket ID to look up.

        Returns:
            IssueResolution if found, None otherwise.
        """
        client = self.client
        if not client:
            return None

        try:
            response = await asyncio.to_thread(
                lambda: (
                    client.table(RESOLUTIONS_TABLE)
                    .select("*")
                    .eq("ticket_id", ticket_id)
                    .limit(1)
                    .execute()
                )
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
        client = self.client
        if not client:
            return []

        try:
            def _fetch():
                query = (
                    client.table(RESOLUTIONS_TABLE)
                    .select("*")
                    .eq("category", category)
                )
                if not include_escalated:
                    query = query.eq("was_escalated", False)
                return (
                    query.order("created_at", desc=True)
                    .limit(limit)
                    .execute()
                )

            response = await asyncio.to_thread(_fetch)

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
        client = self.client
        if not client:
            return False

        try:
            response = await asyncio.to_thread(
                lambda: (
                    client.table(RESOLUTIONS_TABLE)
                    .delete()
                    .eq("id", resolution_id)
                    .execute()
                )
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
        client = self.client
        if not client:
            return {}

        try:
            # Get counts per category
            response = await asyncio.to_thread(
                lambda: (
                    client.table(RESOLUTIONS_TABLE)
                    .select("category, was_escalated")
                    .execute()
                )
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
