"""
FeedMe Conversations Endpoints

CRUD operations for conversations and examples management.
"""

import logging
from typing import Any, Dict, Optional


from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.core.settings import settings
from app.core.security import TokenPayload
from app.feedme.security import limiter
from app.feedme.schemas import (
    FeedMeConversation,
    ConversationUpdate,
    ProcessingStatus,
    ProcessingStage,
    ProcessingMethod,
    ConversationListResponse,
    DeleteConversationResponse,
    ConversationProcessingStatus,
)

from .helpers import (
    get_feedme_supabase_client,
    get_conversation_by_id,
    record_feedme_action_audit,
    update_conversation_in_db,
    supabase_client,
)
from .auth import require_feedme_admin

logger = logging.getLogger(__name__)

router = APIRouter(tags=["FeedMe"])


@router.get("/conversations", response_model=ConversationListResponse)
@limiter.limit("100/minute")
async def list_conversations(
    request: Request,
    page: int = Query(1, ge=1, le=10000, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Number of items per page"),
    status: Optional[ProcessingStatus] = Query(
        None, description="Filter by processing status"
    ),
    uploaded_by: Optional[str] = Query(None, description="Filter by uploader"),
    folder_id: Optional[int] = Query(None, description="Filter by folder ID"),
):
    """Retrieve a paginated list of conversations with optional filtering."""
    if not settings.feedme_enabled:
        raise HTTPException(
            status_code=503, detail="FeedMe service is currently disabled"
        )

    client = get_feedme_supabase_client()
    if client is None:
        raise HTTPException(
            status_code=503, detail="FeedMe service is temporarily unavailable."
        )

    try:
        status_value = status.value if status else None
        result = await client.get_conversations_with_pagination(
            page=page,
            page_size=page_size,
            status=status_value,
            uploaded_by=uploaded_by,
            folder_id=folder_id,
        )

        conversations = []
        for conv in result["conversations"]:
            if conv.get("processing_method") in (None, ""):
                conv["processing_method"] = ProcessingMethod.PDF_AI.value
            conversations.append(FeedMeConversation(**conv))

        return ConversationListResponse(
            conversations=conversations,
            total_count=result["total_count"],
            page=result["page"],
            page_size=result["page_size"],
            has_next=result["has_next"],
        )

    except Exception as e:
        logger.error(f"Error listing conversations: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to list conversations")


@router.get("/conversations/{conversation_id}", response_model=FeedMeConversation)
async def get_conversation(conversation_id: int):
    """Retrieve a conversation by its unique ID."""
    if not settings.feedme_enabled:
        raise HTTPException(
            status_code=503, detail="FeedMe service is currently disabled"
        )

    conversation = await get_conversation_by_id(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return conversation


@router.put("/conversations/{conversation_id}", response_model=FeedMeConversation)
async def update_conversation(
    conversation_id: int,
    update_data: ConversationUpdate,
    current_user: TokenPayload = Depends(require_feedme_admin),
):
    """Updates a conversation record with the specified fields."""
    if not settings.feedme_enabled:
        raise HTTPException(
            status_code=503, detail="FeedMe service is currently disabled"
        )

    existing = await get_conversation_by_id(conversation_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Conversation not found")

    before_state = existing.model_dump(mode="json")
    updated_conversation = await update_conversation_in_db(conversation_id, update_data)
    if not updated_conversation:
        raise HTTPException(status_code=500, detail="Failed to update conversation")
    await record_feedme_action_audit(
        action="update_conversation",
        actor_id=current_user.sub,
        conversation_id=conversation_id,
        before_state=before_state,
        after_state=updated_conversation.model_dump(mode="json"),
    )

    return updated_conversation


@router.delete(
    "/conversations/{conversation_id}", response_model=DeleteConversationResponse
)
async def delete_conversation(
    conversation_id: int,
    current_user: TokenPayload = Depends(require_feedme_admin),
):
    """Deletes a conversation and all associated examples."""
    if not settings.feedme_enabled:
        raise HTTPException(
            status_code=503, detail="FeedMe service is currently disabled"
        )

    try:
        conversation = await supabase_client.get_conversation_by_id(conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")

        deletion_success = await supabase_client.delete_conversation(conversation_id)
        if not deletion_success:
            raise HTTPException(status_code=500, detail="Failed to delete conversation")

        await record_feedme_action_audit(
            action="delete_conversation",
            actor_id=current_user.sub,
            conversation_id=conversation_id,
            before_state=conversation,
        )

        logger.info(f"Successfully deleted conversation {conversation_id}")

        return DeleteConversationResponse(
            conversation_id=conversation_id,
            title=conversation.get("title", "Unknown"),
            examples_deleted=0,
            message=f"Successfully deleted conversation '{conversation.get('title', 'Unknown')}'",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete conversation {conversation_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete conversation")


@router.get(
    "/conversations/{conversation_id}/status",
    response_model=ConversationProcessingStatus,
)
async def get_processing_status(conversation_id: int):
    """Retrieve the processing status and progress for a conversation."""
    if not settings.feedme_enabled:
        raise HTTPException(
            status_code=503, detail="FeedMe service is currently disabled"
        )

    conversation = await get_conversation_by_id(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    tracker: Dict[str, Any] = {}
    if conversation.metadata and isinstance(conversation.metadata, dict):
        tracker = conversation.metadata.get("processing_tracker", {}) or {}

    stage_raw = tracker.get("stage")
    try:
        stage = ProcessingStage(stage_raw) if stage_raw else None
    except ValueError:
        stage = None

    if stage is None:
        if conversation.processing_status == ProcessingStatus.COMPLETED:
            stage = ProcessingStage.COMPLETED
        elif conversation.processing_status == ProcessingStatus.FAILED:
            stage = ProcessingStage.FAILED
        elif conversation.processing_status == ProcessingStatus.PROCESSING:
            stage = ProcessingStage.AI_EXTRACTION
        else:
            stage = ProcessingStage.QUEUED

    progress = tracker.get("progress")
    if progress is None:
        progress = (
            100 if conversation.processing_status == ProcessingStatus.COMPLETED else 0
        )

    default_messages = {
        ProcessingStatus.PENDING: "Pending processing",
        ProcessingStatus.PROCESSING: "Processing transcript",
        ProcessingStatus.COMPLETED: "Processing completed",
        ProcessingStatus.FAILED: "Processing failed",
    }
    message = tracker.get("message") or default_messages.get(
        conversation.processing_status, "Processing updated"
    )
    error_message = conversation.error_message or tracker.get("error")

    return ConversationProcessingStatus(
        conversation_id=conversation.id,
        status=conversation.processing_status,
        stage=stage,
        progress_percentage=int(progress),
        message=message,
        error_message=error_message,
        processing_started_at=tracker.get("started_at"),
        processing_completed_at=tracker.get("completed_at"),
        processing_time_ms=tracker.get("processing_time_ms"),
        metadata={
            **tracker,
            "examples_extracted": tracker.get("examples_extracted", 0),
        },
    )
