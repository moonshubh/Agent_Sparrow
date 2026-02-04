"""
FeedMe Helpers

Shared helper functions and utilities for FeedMe endpoints.
"""

import logging
from typing import Optional
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
