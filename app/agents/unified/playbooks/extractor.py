"""Playbook Extractor for building category-specific playbooks.

This module extracts and assembles playbooks for issue categories by combining:
- Static playbook content (from /playbooks/source/ workspace files)
- Approved learned entries from resolved conversations
- Pending entries (shown with warnings for transparency)

Only APPROVED entries are included in active playbooks to prevent hallucinated
solutions from being surfaced to agents. Pending entries are shown separately
for transparency during human review.

Usage:
    from app.agents.unified.playbooks import PlaybookExtractor

    extractor = PlaybookExtractor()
    playbook = await extractor.build_playbook_with_learned(category="account_setup")

    # Access approved solutions
    for entry in playbook.approved_entries:
        print(f"Problem: {entry.problem_summary}")
        print(f"Solution: {entry.final_solution}")

    # Review pending entries
    for entry in playbook.pending_entries:
        print(f"[UNVERIFIED] {entry.problem_summary}")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from loguru import logger

if TYPE_CHECKING:
    from app.db.supabase.client import SupabaseClient


# Table name for playbook learned entries
LEARNED_ENTRIES_TABLE = "playbook_learned_entries"

# Sentinel for import failure detection
_IMPORT_FAILED = object()

# Trust status values
STATUS_PENDING_REVIEW = "pending_review"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"


def _escape_like(value: str) -> str:
    """Escape characters that are special in SQL LIKE patterns."""
    return value.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")


@dataclass(frozen=True, slots=True)
class PlaybookEntry:
    """A learned playbook entry from a resolved conversation.

    Attributes:
        id: Unique identifier (UUID).
        conversation_id: Original conversation/session ID.
        category: Issue category (e.g., "account_setup", "sync_auth").
        problem_summary: Summary of the problem encountered.
        resolution_steps: List of resolution step objects.
        diagnostic_questions: List of follow-up questions to ask.
        final_solution: The final solution that worked.
        why_it_worked: Explanation of why the solution worked.
        key_learnings: Key takeaways from this resolution.
        source_word_count: Word count of source conversation.
        source_message_count: Message count of source conversation.
        status: Trust status (pending_review, approved, rejected).
        reviewed_by: Who approved/rejected the entry.
        reviewed_at: When the entry was reviewed.
        quality_score: Quality score (0-1) for ranking.
        created_at: When the entry was created.
    """

    id: str
    conversation_id: str
    category: str
    problem_summary: str
    resolution_steps: List[Dict[str, Any]]
    final_solution: str
    diagnostic_questions: List[str] | None = None
    why_it_worked: str | None = None
    key_learnings: str | None = None
    source_word_count: int | None = None
    source_message_count: int | None = None
    status: str = STATUS_PENDING_REVIEW
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    quality_score: float | None = None
    created_at: datetime | None = None

    @property
    def is_approved(self) -> bool:
        """Check if entry is approved."""
        return self.status == STATUS_APPROVED

    @property
    def is_pending(self) -> bool:
        """Check if entry is pending review."""
        return self.status == STATUS_PENDING_REVIEW


@dataclass
class Playbook:
    """A category-specific playbook combining static and learned content.

    Attributes:
        category: The issue category this playbook covers.
        static_content: Curated playbook content from `/playbooks/source/`.
        approved_entries: List of approved learned entries.
        pending_entries: List of pending entries (shown with warning).
        kb_articles: List of relevant KB article IDs.
        macros: List of relevant macro IDs.
    """

    category: str
    static_content: str | None = None
    approved_entries: List[PlaybookEntry] = field(default_factory=list)
    pending_entries: List[PlaybookEntry] = field(default_factory=list)
    kb_articles: List[str] = field(default_factory=list)
    macros: List[str] = field(default_factory=list)

    @property
    def total_entries(self) -> int:
        """Total number of learned entries (approved + pending)."""
        return len(self.approved_entries) + len(self.pending_entries)

    @property
    def has_approved_content(self) -> bool:
        """Check if playbook has any approved content."""
        return bool(self.static_content) or len(self.approved_entries) > 0

    def to_prompt_context(self, include_pending: bool = False) -> str:
        """Generate prompt context string for the playbook.

        Args:
            include_pending: Whether to include pending entries (with warning).

        Returns:
            Formatted string for use in agent prompts.
        """
        parts = []

        # Static content
        if self.static_content:
            parts.append(f"## {self.category.replace('_', ' ').title()} Playbook\n")
            parts.append(self.static_content)
            parts.append("")

        # Approved learned entries
        if self.approved_entries:
            parts.append("### Verified Solutions from Past Tickets\n")
            for i, entry in enumerate(self.approved_entries, 1):
                parts.append(
                    f"**Solution {i}** (Quality: {entry.quality_score or 'N/A'})"
                )
                parts.append(f"- Problem: {entry.problem_summary}")
                parts.append(f"- Solution: {entry.final_solution}")
                if entry.why_it_worked:
                    parts.append(f"- Why: {entry.why_it_worked}")
                if entry.resolution_steps:
                    steps_str = " → ".join(
                        s.get("action", str(s)) for s in entry.resolution_steps[:5]
                    )
                    parts.append(f"- Steps: {steps_str}")
                parts.append("")

        # Pending entries (optional, with warning)
        if include_pending and self.pending_entries:
            parts.append("### Unverified Solutions (Pending Review)\n")
            parts.append("⚠️ These solutions have not been verified by a human.\n")
            for entry in self.pending_entries[:3]:  # Limit to 3
                parts.append(f"- [UNVERIFIED] {entry.problem_summary}")
                parts.append(f"  → {entry.final_solution}")
            parts.append("")

        # Related resources
        if self.kb_articles:
            parts.append(f"### Related KB Articles: {', '.join(self.kb_articles[:5])}")
        if self.macros:
            parts.append(f"### Related Macros: {', '.join(self.macros[:5])}")

        return "\n".join(parts)


class PlaybookExtractor:
    """Extracts and assembles playbooks for issue categories.

    Combines static playbook content with learned entries from the database.
    Only approved entries are included in active playbooks to prevent
    hallucinated solutions from being surfaced.

    Example:
        extractor = PlaybookExtractor()
        playbook = await extractor.build_playbook_with_learned("account_setup")

        # Use in agent prompt
        context = playbook.to_prompt_context()
    """

    def __init__(
        self,
        supabase_client: Optional["SupabaseClient"] = None,
        max_approved_entries: int = 20,
        max_pending_entries: int = 5,
    ) -> None:
        """Initialize the playbook extractor.

        Args:
            supabase_client: Optional Supabase client. If not provided,
                             will be lazy-loaded from app.db.supabase.
            max_approved_entries: Maximum approved entries to include.
            max_pending_entries: Maximum pending entries to include.
        """
        self._client = supabase_client
        self.max_approved_entries = max_approved_entries
        self.max_pending_entries = max_pending_entries

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
                logger.warning("Supabase client not available for PlaybookExtractor")
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

    def _row_to_entry(self, row: Dict[str, Any]) -> PlaybookEntry:
        """Convert a database row to a PlaybookEntry.

        Args:
            row: Database row dictionary.

        Returns:
            PlaybookEntry instance.
        """
        return PlaybookEntry(
            id=row["id"],
            conversation_id=row["conversation_id"],
            category=row["category"],
            problem_summary=row["problem_summary"],
            resolution_steps=row.get("resolution_steps") or [],
            final_solution=row["final_solution"],
            diagnostic_questions=row.get("diagnostic_questions"),
            why_it_worked=row.get("why_it_worked"),
            key_learnings=row.get("key_learnings"),
            source_word_count=row.get("source_word_count"),
            source_message_count=row.get("source_message_count"),
            status=row.get("status", STATUS_PENDING_REVIEW),
            reviewed_by=row.get("reviewed_by"),
            reviewed_at=(
                datetime.fromisoformat(row["reviewed_at"].replace("Z", "+00:00"))
                if row.get("reviewed_at")
                else None
            ),
            quality_score=row.get("quality_score"),
            created_at=(
                datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))
                if row.get("created_at")
                else None
            ),
        )

    async def get_approved_entries(
        self,
        category: str,
        limit: int | None = None,
    ) -> List[PlaybookEntry]:
        """Get approved learned entries for a category.

        Args:
            category: Issue category to filter by.
            limit: Maximum entries to return.

        Returns:
            List of approved PlaybookEntry objects, sorted by quality.
        """
        client = self.client
        if not client:
            return []

        limit = limit or self.max_approved_entries

        try:
            response = (
                client.client.table(LEARNED_ENTRIES_TABLE)
                .select("*")
                .eq("category", category)
                .eq("status", STATUS_APPROVED)
                .order("quality_score", desc=True)
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )

            entries: List[PlaybookEntry] = []
            for row in response.data or []:
                if not isinstance(row, dict):
                    continue
                entries.append(self._row_to_entry(row))
            return entries

        except Exception as exc:
            logger.warning(
                "get_approved_entries_error",
                category=category,
                error=str(exc),
            )
            return []

    async def get_pending_entries(
        self,
        category: str,
        limit: int | None = None,
    ) -> List[PlaybookEntry]:
        """Get pending (unverified) learned entries for a category.

        Args:
            category: Issue category to filter by.
            limit: Maximum entries to return.

        Returns:
            List of pending PlaybookEntry objects, sorted by recency.
        """
        client = self.client
        if not client:
            return []

        limit = limit or self.max_pending_entries

        try:
            response = (
                client.client.table(LEARNED_ENTRIES_TABLE)
                .select("*")
                .eq("category", category)
                .eq("status", STATUS_PENDING_REVIEW)
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )

            entries: List[PlaybookEntry] = []
            for row in response.data or []:
                if not isinstance(row, dict):
                    continue
                entries.append(self._row_to_entry(row))
            return entries

        except Exception as exc:
            logger.warning(
                "get_pending_entries_error",
                category=category,
                error=str(exc),
            )
            return []

    async def get_static_playbook_content(self, category: str) -> str | None:
        """Get static playbook content from workspace files.

        Args:
            category: Issue category to load playbook for.

        Returns:
            Playbook content string, or None if not found.
        """
        # Map category to playbook filename
        playbook_files = {
            "account_setup": "account_setup.md",
            "sync_auth": "sync_auth.md",
            "licensing": "licensing.md",
            "sending": "sending.md",
            "performance": "performance.md",
            "features": "features.md",
        }

        filename = playbook_files.get(category)
        if not filename:
            return None

        # Try to read curated "source" playbooks (compiled playbooks live at /playbooks/{category}.md)
        try:
            from app.agents.harness.store import SparrowWorkspaceStore

            # Use a temporary store for reading global playbooks
            store = SparrowWorkspaceStore(session_id="playbook-extractor")
            path = f"/playbooks/source/{filename}"
            content = await store.read_file(path)
            return content
        except Exception as exc:
            logger.debug(
                "static_playbook_not_found",
                category=category,
                filename=filename,
                error=str(exc),
            )
            return None

    async def get_related_kb_articles(self, category: str) -> List[str]:
        """Get KB article IDs related to a category.

        Args:
            category: Issue category to find articles for.

        Returns:
            List of KB article IDs.
        """
        client = self.client
        if not client:
            return []

        try:
            # Query mailbird_knowledge for articles tagged with this category
            response = (
                client.client.table("mailbird_knowledge")
                .select("id, url")
                .ilike("content", f"%{_escape_like(category.replace('_', ' '))}%")
                .limit(10)
                .execute()
            )

            out: List[str] = []
            for row in response.data or []:
                if not isinstance(row, dict):
                    continue
                if row.get("id") is not None:
                    out.append(str(row["id"]))
                elif row.get("url"):
                    out.append(str(row["url"]))
            return out

        except Exception:
            # Fallback: try markdown column if content is unavailable.
            try:
                response = (
                    client.client.table("mailbird_knowledge")
                    .select("id, url")
                    .ilike("markdown", f"%{_escape_like(category.replace('_', ' '))}%")
                    .limit(10)
                    .execute()
                )
                fallback_out: List[str] = []
                for row in response.data or []:
                    if not isinstance(row, dict):
                        continue
                    if row.get("id") is not None:
                        fallback_out.append(str(row["id"]))
                    elif row.get("url"):
                        fallback_out.append(str(row["url"]))
                return fallback_out
            except Exception as inner_exc:
                logger.debug(
                    "get_related_kb_articles_error",
                    category=category,
                    error=str(inner_exc)[:180],
                )
                return []

    async def build_playbook_with_learned(self, category: str) -> Playbook:
        """Build a complete playbook for a category.

        Combines:
        - Static playbook content from workspace files
        - APPROVED learned entries (verified by humans)
        - Pending entries (shown with warning for review)
        - Related KB articles and macros

        Args:
            category: Issue category to build playbook for.

        Returns:
            Playbook object with all combined content.
        """
        # Fetch all components in parallel
        import asyncio

        static_content_task = asyncio.create_task(
            self.get_static_playbook_content(category)
        )
        approved_task = asyncio.create_task(self.get_approved_entries(category))
        pending_task = asyncio.create_task(self.get_pending_entries(category))
        kb_task = asyncio.create_task(self.get_related_kb_articles(category))

        static_content = await static_content_task
        approved_entries = await approved_task
        pending_entries = await pending_task
        kb_articles = await kb_task

        playbook = Playbook(
            category=category,
            static_content=static_content,
            approved_entries=approved_entries,
            pending_entries=pending_entries,
            kb_articles=kb_articles,
        )

        logger.info(
            "playbook_built",
            category=category,
            has_static=bool(static_content),
            approved_count=len(approved_entries),
            pending_count=len(pending_entries),
            kb_article_count=len(kb_articles),
        )

        return playbook

    async def approve_entry(
        self,
        entry_id: str,
        reviewed_by: str,
        quality_score: float = 0.7,
    ) -> bool:
        """Approve a pending entry.

        Args:
            entry_id: The entry ID to approve.
            reviewed_by: Identifier of the reviewer.
            quality_score: Quality score to assign (0-1).

        Returns:
            True if approved successfully, False otherwise.
        """
        client = self.client
        if not client:
            return False

        try:
            client.client.table(LEARNED_ENTRIES_TABLE).update(
                {
                    "status": STATUS_APPROVED,
                    "reviewed_by": reviewed_by,
                    "reviewed_at": datetime.now(timezone.utc).isoformat(),
                    "quality_score": max(0.0, min(1.0, quality_score)),
                }
            ).eq("id", entry_id).execute()

            logger.info(
                "entry_approved",
                entry_id=entry_id,
                reviewed_by=reviewed_by,
                quality_score=quality_score,
            )
            return True

        except Exception as exc:
            logger.warning(
                "approve_entry_error",
                entry_id=entry_id,
                error=str(exc),
            )
            return False

    async def reject_entry(
        self,
        entry_id: str,
        reviewed_by: str,
    ) -> bool:
        """Reject a pending entry.

        Args:
            entry_id: The entry ID to reject.
            reviewed_by: Identifier of the reviewer.

        Returns:
            True if rejected successfully, False otherwise.
        """
        client = self.client
        if not client:
            return False

        try:
            client.client.table(LEARNED_ENTRIES_TABLE).update(
                {
                    "status": STATUS_REJECTED,
                    "reviewed_by": reviewed_by,
                    "reviewed_at": datetime.now(timezone.utc).isoformat(),
                }
            ).eq("id", entry_id).execute()

            logger.info(
                "entry_rejected",
                entry_id=entry_id,
                reviewed_by=reviewed_by,
            )
            return True

        except Exception as exc:
            logger.warning(
                "reject_entry_error",
                entry_id=entry_id,
                error=str(exc),
            )
            return False

    async def get_review_queue(
        self,
        category: str | None = None,
        limit: int = 20,
    ) -> List[PlaybookEntry]:
        """Get entries pending review.

        Args:
            category: Optional category filter.
            limit: Maximum entries to return.

        Returns:
            List of pending PlaybookEntry objects.
        """
        client = self.client
        if not client:
            return []

        try:
            query = (
                client.client.table(LEARNED_ENTRIES_TABLE)
                .select("*")
                .eq("status", STATUS_PENDING_REVIEW)
            )

            if category:
                query = query.eq("category", category)

            response = query.order("created_at", desc=True).limit(limit).execute()

            entries: List[PlaybookEntry] = []
            for row in response.data or []:
                if not isinstance(row, dict):
                    continue
                entries.append(self._row_to_entry(row))
            return entries

        except Exception as exc:
            logger.warning(
                "get_review_queue_error",
                category=category,
                error=str(exc),
            )
            return []
