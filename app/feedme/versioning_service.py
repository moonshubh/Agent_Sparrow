"""
FeedMe v3.0 Versioning Service - Supabase Only
Handles conversation versioning, diffs, and edit operations

This module provides:
- Version creation on conversation updates
- Version history management
- Diff generation between versions
- Revert functionality
- Integration with async reprocessing
"""

import difflib
import logging
from datetime import datetime, timezone
from typing import Any, Dict
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
    """Service for managing conversation versions in Supabase"""

    def __init__(self) -> None:
        self._supabase_client = None

    @property
    def supabase_client(self):
        """Lazy load Supabase client"""
        if self._supabase_client is None:
            self._supabase_client = get_supabase_client()
        return self._supabase_client

    async def create_new_version(
        self,
        conversation_id: int,
        updated_data: Dict[str, Any],
        updated_by: str,
    ) -> ConversationVersion:
        """
        Create a new version of a conversation

        Note: Version control should be implemented at the Supabase level
        using RLS policies and audit tables
        """
        conversation = await self.supabase_client.get_conversation(conversation_id)
        if not conversation:
            raise ValueError(f"Conversation {conversation_id} not found")

        current_version = self._extract_version_number(conversation)
        new_version = current_version + 1

        updates = dict(updated_data)
        updates["version"] = new_version
        updates["is_latest_version"] = True

        await self.supabase_client.update_conversation(
            conversation_id=conversation_id,
            updates=updates,
        )

        transcript_content = str(updated_data.get("raw_transcript") or "")

        return ConversationVersion(
            id=new_version,
            conversation_id=conversation_id,
            version_number=new_version,
            transcript_content=transcript_content,
            created_at=datetime.now(timezone.utc),
            created_by=updated_by,
            is_active=True,
        )

    async def get_conversation_versions(
        self, conversation_id: int
    ) -> VersionListResponse:
        """
        Get version history for a conversation

        Note: Requires Supabase audit table implementation
        """
        conversation = await self.supabase_client.get_conversation(conversation_id)
        if not conversation:
            raise ValueError(f"Conversation {conversation_id} not found")

        version = self._build_version_from_conversation(conversation_id, conversation)

        return VersionListResponse(
            versions=[version],
            total_count=1,
            active_version=version.version_number,
        )

    async def get_version_by_number(
        self,
        conversation_id: int,
        version_number: int,
    ) -> ConversationVersion | None:
        conversation = await self.supabase_client.get_conversation(conversation_id)
        if not conversation:
            return None

        current_version = self._extract_version_number(conversation)
        if version_number != current_version:
            return None

        return self._build_version_from_conversation(conversation_id, conversation)

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
        """
        Edit conversation transcript and trigger reprocessing
        """
        try:
            conversation = await self.supabase_client.get_conversation(conversation_id)
            if not conversation:
                raise ValueError(f"Conversation {conversation_id} not found")

            current_version = self._extract_version_number(conversation)
            new_version = current_version + 1

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

            # Update conversation in Supabase
            update_data = {
                "raw_transcript": edit_request.transcript_content,
                "processing_status": ProcessingStatus.PENDING.value,
                "version": new_version,
                "is_latest_version": True,
                "metadata": metadata,
            }

            await self.supabase_client.update_conversation(
                conversation_id=conversation_id,
                updates=update_data,
            )

            # Trigger async reprocessing via Celery if configured
            try:
                from app.feedme.tasks import process_transcript

                process_transcript.delay(conversation_id, edit_request.user_id)
            except Exception as exc:  # pragma: no cover - best effort
                logger.warning(
                    f"versioning_reprocess_not_triggered conversation_id={conversation_id} error={exc}"
                )

            return EditResponse(
                conversation_id=conversation_id,
                new_version=new_version,
                new_version_uuid=uuid4(),
                message="Conversation updated and queued for reprocessing",
            )

        except Exception as e:
            logger.error(f"Error editing conversation {conversation_id}: {e}")
            raise

    async def revert_conversation(
        self, conversation_id: int, revert_request: ConversationRevertRequest
    ) -> RevertResponse:
        """
        Revert conversation to a previous version

        Note: Requires Supabase audit table implementation
        """
        conversation = await self.supabase_client.get_conversation(conversation_id)
        if not conversation:
            raise ValueError(f"Conversation {conversation_id} not found")

        current_version = self._extract_version_number(conversation)
        if revert_request.target_version != current_version:
            raise ValueError(
                "Version history is not available; only the current version can be returned."
            )

        return RevertResponse(
            conversation_id=conversation_id,
            reverted_to_version=revert_request.target_version,
            new_version=current_version,
            new_version_uuid=uuid4(),
            message="Conversation already at requested version.",
        )

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

    def _build_version_from_conversation(
        self,
        conversation_id: int,
        conversation: Dict[str, Any],
    ) -> ConversationVersion:
        created_at = self._parse_timestamp(
            conversation.get("updated_at") or conversation.get("created_at")
        )
        transcript_content = str(conversation.get("raw_transcript") or "")
        version_number = self._extract_version_number(conversation)

        return ConversationVersion(
            id=version_number,
            conversation_id=conversation_id,
            version_number=version_number,
            transcript_content=transcript_content,
            created_at=created_at,
            created_by=conversation.get("uploaded_by"),
            change_description=None,
            is_active=bool(conversation.get("is_latest_version", True)),
        )


def get_versioning_service() -> "VersioningService":
    """Factory for the versioning service."""
    return VersioningService()
