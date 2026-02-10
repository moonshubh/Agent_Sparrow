"""
FeedMe conversation versioning service backed by persisted version history.
"""

from __future__ import annotations

import difflib
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

from app.db.supabase.client import get_supabase_client
from app.feedme.schemas import (
    ConversationVersion,
    VersionListResponse,
    VersionDiff,
    ConversationEditRequest,
    ConversationRevertRequest,
    EditResponse,
    RevertResponse,
    ProcessingStatus,
)

logger = logging.getLogger(__name__)


class VersioningService:
    """Service for managing FeedMe conversation versions."""

    def __init__(self) -> None:
        self._supabase_client = None

    @property
    def supabase_client(self):
        if self._supabase_client is None:
            self._supabase_client = get_supabase_client()
        return self._supabase_client

    @staticmethod
    def _parse_timestamp(value: Any) -> datetime:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return datetime.now(timezone.utc)
        return datetime.now(timezone.utc)

    @staticmethod
    def _extract_version_number(conversation: Dict[str, Any]) -> int:
        value = conversation.get("version")
        if isinstance(value, int) and value > 0:
            return value
        if isinstance(value, str):
            try:
                parsed = int(value)
            except ValueError:
                return 1
            return parsed if parsed > 0 else 1
        return 1

    async def _get_conversation_or_raise(self, conversation_id: int) -> Dict[str, Any]:
        conversation = await self.supabase_client.get_conversation(conversation_id)
        if not conversation:
            raise ValueError(f"Conversation {conversation_id} not found")
        return conversation

    async def _list_version_rows(self, conversation_id: int) -> list[Dict[str, Any]]:
        response = await self.supabase_client._exec(
            lambda: self.supabase_client.client.table("feedme_conversation_versions")
            .select("*")
            .eq("conversation_id", conversation_id)
            .order("version_number", desc=True)
            .execute()
        )
        return response.data or []

    async def _get_version_row(
        self, conversation_id: int, version_number: int
    ) -> Optional[Dict[str, Any]]:
        response = await self.supabase_client._exec(
            lambda: self.supabase_client.client.table("feedme_conversation_versions")
            .select("*")
            .eq("conversation_id", conversation_id)
            .eq("version_number", version_number)
            .limit(1)
            .execute()
        )
        if response.data:
            return response.data[0]
        return None

    def _row_to_version(self, row: Dict[str, Any]) -> ConversationVersion:
        return ConversationVersion(
            id=int(row["id"]),
            conversation_id=int(row["conversation_id"]),
            version_number=int(row["version_number"]),
            transcript_content=str(row.get("transcript_content") or ""),
            created_at=self._parse_timestamp(row.get("created_at")),
            created_by=row.get("created_by"),
            change_description=row.get("change_description"),
            is_active=True,
        )

    async def _insert_version(
        self,
        *,
        conversation_id: int,
        transcript_content: str,
        created_by: Optional[str],
        metadata: Optional[Dict[str, Any]] = None,
        change_description: Optional[str] = None,
        is_revert: bool = False,
        source_version_number: Optional[int] = None,
        force_version_number: Optional[int] = None,
    ) -> ConversationVersion:
        if force_version_number is not None:
            next_version = force_version_number
        else:
            latest = await self.supabase_client._exec(
                lambda: self.supabase_client.client.table("feedme_conversation_versions")
                .select("version_number")
                .eq("conversation_id", conversation_id)
                .order("version_number", desc=True)
                .limit(1)
                .execute()
            )
            if latest.data:
                next_version = int(latest.data[0].get("version_number", 0)) + 1
            else:
                next_version = 1

        payload = {
            "conversation_id": conversation_id,
            "version_number": next_version,
            "transcript_content": transcript_content,
            "metadata": metadata or {},
            "change_description": change_description,
            "created_by": created_by,
            "is_revert": is_revert,
            "source_version_number": source_version_number,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        response = await self.supabase_client._exec(
            lambda: self.supabase_client.client.table("feedme_conversation_versions")
            .insert(payload)
            .execute()
        )
        if not response.data:
            raise ValueError("Failed to persist conversation version")
        return self._row_to_version(response.data[0])

    async def _ensure_history_seeded(
        self,
        conversation_id: int,
        conversation: Dict[str, Any],
    ) -> list[Dict[str, Any]]:
        rows = await self._list_version_rows(conversation_id)
        if rows:
            return rows

        transcript = str(
            conversation.get("extracted_text")
            or conversation.get("raw_transcript")
            or ""
        )
        version_number = self._extract_version_number(conversation)
        await self._insert_version(
            conversation_id=conversation_id,
            transcript_content=transcript,
            created_by=conversation.get("uploaded_by"),
            metadata=(
                conversation.get("metadata")
                if isinstance(conversation.get("metadata"), dict)
                else {}
            ),
            change_description="Initial persisted version snapshot",
            force_version_number=version_number,
        )
        return await self._list_version_rows(conversation_id)

    async def get_conversation_versions(
        self, conversation_id: int
    ) -> VersionListResponse:
        conversation = await self._get_conversation_or_raise(conversation_id)
        rows = await self._ensure_history_seeded(conversation_id, conversation)
        versions = [self._row_to_version(row) for row in rows]
        active_version = versions[0].version_number if versions else 1
        return VersionListResponse(
            versions=versions,
            total_count=len(versions),
            active_version=active_version,
        )

    async def get_version_by_number(
        self,
        conversation_id: int,
        version_number: int,
    ) -> ConversationVersion | None:
        await self._get_conversation_or_raise(conversation_id)
        row = await self._get_version_row(conversation_id, version_number)
        if not row:
            return None
        return self._row_to_version(row)

    async def generate_diff(
        self,
        version_1: ConversationVersion,
        version_2: ConversationVersion,
    ) -> VersionDiff:
        old_lines = (version_1.transcript_content or "").splitlines()
        new_lines = (version_2.transcript_content or "").splitlines()

        diff = list(difflib.ndiff(old_lines, new_lines))
        additions = sum(1 for line in diff if line.startswith("+ "))
        deletions = sum(1 for line in diff if line.startswith("- "))

        diff_html = difflib.HtmlDiff().make_table(
            old_lines,
            new_lines,
            fromdesc=f"Version {version_1.version_number}",
            todesc=f"Version {version_2.version_number}",
            context=True,
            numlines=3,
        )

        return VersionDiff(
            diff_html=diff_html,
            additions=additions,
            deletions=deletions,
            version_1_id=version_1.id,
            version_2_id=version_2.id,
        )

    async def edit_conversation(
        self, conversation_id: int, edit_request: ConversationEditRequest
    ) -> EditResponse:
        conversation = await self._get_conversation_or_raise(conversation_id)
        await self._ensure_history_seeded(conversation_id, conversation)

        existing_metadata = conversation.get("metadata")
        metadata: Dict[str, Any] = (
            dict(existing_metadata) if isinstance(existing_metadata, dict) else {}
        )
        metadata.update(
            {
                "edit_reason": edit_request.edit_reason,
                "edited_by": edit_request.user_id,
                "edited_at": datetime.now(timezone.utc).isoformat(),
            }
        )

        new_version = await self._insert_version(
            conversation_id=conversation_id,
            transcript_content=edit_request.transcript_content,
            created_by=edit_request.user_id,
            metadata=metadata,
            change_description=edit_request.edit_reason,
            is_revert=False,
        )

        await self.supabase_client.update_conversation(
            conversation_id=conversation_id,
            updates={
                "extracted_text": edit_request.transcript_content,
                "metadata": metadata,
                "version": new_version.version_number,
                "is_latest_version": True,
                "processing_status": ProcessingStatus.PENDING.value,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )

        try:
            from app.feedme.tasks import process_transcript

            process_transcript.delay(conversation_id, edit_request.user_id)
        except Exception as exc:  # pragma: no cover - best effort
            logger.warning(
                "versioning_reprocess_not_triggered conversation_id=%s error=%s",
                conversation_id,
                exc,
            )

        return EditResponse(
            conversation_id=conversation_id,
            new_version=new_version.version_number,
            new_version_uuid=uuid4(),
            message="Conversation updated and queued for reprocessing",
        )

    async def revert_conversation(
        self, conversation_id: int, revert_request: ConversationRevertRequest
    ) -> RevertResponse:
        conversation = await self._get_conversation_or_raise(conversation_id)
        await self._ensure_history_seeded(conversation_id, conversation)

        target = await self.get_version_by_number(
            conversation_id, revert_request.target_version
        )
        if target is None:
            raise ValueError(
                f"Version {revert_request.target_version} not found for conversation {conversation_id}"
            )

        metadata = (
            dict(conversation.get("metadata"))
            if isinstance(conversation.get("metadata"), dict)
            else {}
        )
        metadata.update(
            {
                "reverted_by": revert_request.user_id,
                "reverted_at": datetime.now(timezone.utc).isoformat(),
                "revert_reason": revert_request.revert_reason,
                "reverted_to_version": revert_request.target_version,
            }
        )

        new_version = await self._insert_version(
            conversation_id=conversation_id,
            transcript_content=target.transcript_content,
            created_by=revert_request.user_id,
            metadata=metadata,
            change_description=f"Revert to version {revert_request.target_version}: {revert_request.revert_reason}",
            is_revert=True,
            source_version_number=revert_request.target_version,
        )

        await self.supabase_client.update_conversation(
            conversation_id=conversation_id,
            updates={
                "extracted_text": target.transcript_content,
                "metadata": metadata,
                "version": new_version.version_number,
                "is_latest_version": True,
                "processing_status": ProcessingStatus.PENDING.value,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )

        try:
            from app.feedme.tasks import process_transcript

            process_transcript.delay(conversation_id, revert_request.user_id)
        except Exception as exc:  # pragma: no cover - best effort
            logger.warning(
                "versioning_reprocess_not_triggered_after_revert conversation_id=%s error=%s",
                conversation_id,
                exc,
            )

        return RevertResponse(
            conversation_id=conversation_id,
            reverted_to_version=revert_request.target_version,
            new_version=new_version.version_number,
            new_version_uuid=uuid4(),
            message=(
                f"Conversation reverted to version {revert_request.target_version} "
                "and queued for reprocessing"
            ),
        )


def get_versioning_service() -> "VersioningService":
    """Factory for the versioning service."""
    return VersioningService()
