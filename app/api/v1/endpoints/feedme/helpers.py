"""
FeedMe Helpers

Shared helper functions and utilities for FeedMe endpoints.
"""

import logging
from typing import Any, Optional
from datetime import datetime, timezone

from fastapi import HTTPException

from app.db.supabase.client import get_supabase_client
from app.feedme.schemas import (
    FeedMeConversation,
    ConversationCreate,
    ConversationUpdate,
    ProcessingStatus,
    ProcessingStage,
    ProcessingMethod,
)
from app.feedme.websocket.schemas import ProcessingUpdate
from app.api.v1.websocket.feedme_websocket import notify_processing_update

logger = logging.getLogger(__name__)

# Constants
UNASSIGNED_FOLDER_ID = 0

# Global Supabase client instance (lazy-loaded to prevent startup hang)
_supabase_client = None


def get_feedme_supabase_client():
    """Get Supabase client with error handling."""
    global _supabase_client
    if _supabase_client is None:
        try:
            _supabase_client = get_supabase_client()
        except Exception as e:
            logger.error(f"Failed to initialize Supabase client: {e}")
            return None
    return _supabase_client


class _SupabaseClientProxy:
    """Proxy class for backwards compatibility with attribute access."""

    def __getattr__(self, name):
        client = get_feedme_supabase_client()
        if not client:
            raise RuntimeError(
                "Supabase client not initialized. Please configure environment variables."
            )
        return getattr(client, name)


# Use the proxy for backwards compatibility
supabase_client = _SupabaseClientProxy()


def get_supabase_connection():
    """Get Supabase client instance."""
    return get_supabase_client()


async def update_conversation_status(
    conversation_id: int,
    status: ProcessingStatus,
    error_message: Optional[str] = None,
    stage: Optional[ProcessingStage] = None,
    progress: Optional[int] = None,
    message: Optional[str] = None,
):
    """Updates the processing status, persists progress, and emits websocket notifications."""
    client = get_feedme_supabase_client()

    stage = stage or (
        ProcessingStage.COMPLETED
        if status == ProcessingStatus.COMPLETED
        else (
            ProcessingStage.FAILED
            if status == ProcessingStatus.FAILED
            else (
                ProcessingStage.AI_EXTRACTION
                if status == ProcessingStatus.PROCESSING
                else ProcessingStage.QUEUED
            )
        )
    )

    if progress is None:
        if status == ProcessingStatus.COMPLETED:
            progress = 100
        elif status == ProcessingStatus.PENDING:
            progress = 0
        else:
            progress = 25

    default_messages = {
        ProcessingStatus.PENDING: "Pending processing",
        ProcessingStatus.PROCESSING: "Processing transcript",
        ProcessingStatus.COMPLETED: "Processing completed",
        ProcessingStatus.FAILED: "Processing failed",
    }
    message = message or default_messages.get(status, "Processing update")

    if client is not None:
        try:
            await client.record_processing_update(
                conversation_id=conversation_id,
                status=status.value,
                stage=stage.value,
                progress=progress,
                message=message,
                error_message=error_message,
                metadata_overrides=None,
                processed_at=(
                    datetime.now(timezone.utc)
                    if status == ProcessingStatus.COMPLETED
                    else None
                ),
            )
        except Exception as e:
            logger.error(
                f"Failed to record processing update for conversation {conversation_id}: {e}"
            )

    try:
        await notify_processing_update(
            ProcessingUpdate(
                conversation_id=conversation_id,
                status=status,
                stage=stage,
                progress=progress,
                message=message,
                quality_score=None,
                error_details=error_message,
            )
        )
    except Exception as e:
        logger.error(
            f"Failed to broadcast processing update for conversation {conversation_id}: {e}"
        )


async def get_conversation_by_id(conversation_id: int) -> Optional[FeedMeConversation]:
    """
    Retrieve a conversation record from Supabase by its unique ID.

    Parameters:
        conversation_id (int): The unique identifier of the conversation to retrieve.

    Returns:
        Optional[FeedMeConversation]: The conversation object if found, otherwise None.
    """
    try:
        client = get_supabase_client()
        result = await client.get_conversation(conversation_id)
        if result:
            # Backward compatibility: ensure processing_method is not null
            if result.get("processing_method") in (None, ""):
                result["processing_method"] = ProcessingMethod.PDF_AI.value
            return FeedMeConversation(**result)
        return None
    except Exception as e:
        logger.error(f"Error fetching conversation {conversation_id}: {e}")
        return None


async def create_conversation_in_db(
    conversation_data: ConversationCreate,
    *,
    upload_sha256: Optional[str] = None,
    os_category: Optional[str] = None,
) -> FeedMeConversation:
    """
    Inserts a new conversation record into Supabase.

    Parameters:
        conversation_data (ConversationCreate): The data required to create a new conversation.

    Returns:
        FeedMeConversation: The newly created conversation record.

    Raises:
        HTTPException: If the database operation fails.
    """
    try:
        client = get_supabase_client()
        result = await client.insert_conversation(
            title=conversation_data.title,
            original_filename=conversation_data.original_filename,
            raw_transcript=conversation_data.raw_transcript,
            metadata=conversation_data.metadata,
            uploaded_by=conversation_data.uploaded_by,
            mime_type=conversation_data.mime_type,
            pages=conversation_data.pages,
            pdf_metadata=conversation_data.pdf_metadata,
            processing_method=(
                conversation_data.processing_method.value
                if isinstance(conversation_data.processing_method, ProcessingMethod)
                else conversation_data.processing_method
            ),
            upload_sha256=upload_sha256,
            os_category=(
                os_category
                or (
                    conversation_data.os_category.value
                    if hasattr(conversation_data.os_category, "value")
                    else conversation_data.os_category
                )
            ),
        )
        return FeedMeConversation(**result)
    except Exception as e:
        logger.error(f"Error creating conversation: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to create conversation: {str(e)}"
        )


async def update_conversation_in_db(
    conversation_id: int, update_data: ConversationUpdate
) -> Optional[FeedMeConversation]:
    """
    Updates specified fields of a conversation record in Supabase.

    Parameters:
        conversation_id (int): The ID of the conversation to update.
        update_data (ConversationUpdate): Fields to update in the conversation.

    Returns:
        FeedMeConversation or None: The updated conversation object if found.

    Raises:
        HTTPException: If a database error occurs during the update.
    """
    try:
        supabase = get_supabase_client()

        # Build update data
        update_dict = update_data.dict(exclude_unset=True)

        if not update_dict:
            return await get_conversation_by_id(conversation_id)

        # Convert processing_status enum to string if present
        if "processing_status" in update_dict:
            update_dict["processing_status"] = update_dict["processing_status"].value

        updated_conversation = await supabase.update_conversation(
            conversation_id=conversation_id, updates=update_dict
        )

        if updated_conversation:
            return FeedMeConversation(**updated_conversation)
        return None

    except Exception as e:
        logger.error(f"Error updating conversation {conversation_id}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to update conversation: {str(e)}"
        )


async def get_feedme_settings(tenant_id: str = "default") -> dict[str, Any]:
    """Load FeedMe settings row, creating a deterministic default when missing."""
    client = get_feedme_supabase_client()
    if client is None:
        raise HTTPException(
            status_code=503, detail="FeedMe service is temporarily unavailable."
        )

    response = await client._exec(
        lambda: client.client.table("feedme_settings")
        .select("*")
        .eq("tenant_id", tenant_id)
        .limit(1)
        .execute()
    )
    if response.data:
        return response.data[0]

    inserted = await client._exec(
        lambda: client.client.table("feedme_settings")
        .insert({"tenant_id": tenant_id})
        .execute()
    )
    if inserted.data:
        return inserted.data[0]

    raise HTTPException(status_code=500, detail="Failed to initialize FeedMe settings")


async def update_feedme_settings(
    updates: dict[str, Any],
    *,
    tenant_id: str = "default",
    updated_by: Optional[str] = None,
) -> dict[str, Any]:
    """Update FeedMe settings and return the persisted row."""
    client = get_feedme_supabase_client()
    if client is None:
        raise HTTPException(
            status_code=503, detail="FeedMe service is temporarily unavailable."
        )

    existing = await get_feedme_settings(tenant_id=tenant_id)
    payload = {
        **updates,
        "updated_by": updated_by,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    response = await client._exec(
        lambda: client.client.table("feedme_settings")
        .update(payload)
        .eq("id", existing["id"])
        .execute()
    )
    if response.data:
        return response.data[0]
    raise HTTPException(status_code=500, detail="Failed to update FeedMe settings")


async def record_feedme_action_audit(
    *,
    action: str,
    actor_id: Optional[str],
    conversation_id: Optional[int] = None,
    folder_id: Optional[int] = None,
    before_state: Optional[dict[str, Any]] = None,
    after_state: Optional[dict[str, Any]] = None,
    reason: Optional[str] = None,
) -> None:
    """
    Best-effort write to FeedMe action audit table.

    This helper intentionally swallows failures to avoid blocking core workflows.
    """
    client = get_feedme_supabase_client()
    if client is None:
        return

    payload = {
        "action": action,
        "actor_id": actor_id,
        "conversation_id": conversation_id,
        "folder_id": folder_id,
        "reason": reason,
        "before_state": before_state,
        "after_state": after_state,
    }
    payload = {k: v for k, v in payload.items() if v is not None}
    try:
        await client._exec(
            lambda: client.client.table("feedme_action_audit")
            .insert(payload)
            .execute()
        )
    except Exception as e:  # pragma: no cover - non-blocking audit path
        logger.warning("Failed to persist FeedMe action audit: %s", e)
