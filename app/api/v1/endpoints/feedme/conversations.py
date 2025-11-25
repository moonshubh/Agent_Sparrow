"""
FeedMe Conversations Endpoints

CRUD operations for conversations and examples management.
"""

import logging
from typing import Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Query, Request

from app.core.settings import settings
from app.db.supabase.client import get_supabase_client
from app.feedme.security import limiter
from app.feedme.schemas import (
    FeedMeConversation,
    FeedMeExample,
    ConversationUpdate,
    ExampleUpdate,
    ProcessingStatus,
    ProcessingStage,
    ProcessingMethod,
    ConversationListResponse,
    ExampleListResponse,
    DeleteConversationResponse,
    ConversationProcessingStatus,
)

from .helpers import (
    get_feedme_supabase_client,
    get_conversation_by_id,
    update_conversation_in_db,
    supabase_client,
    UNASSIGNED_FOLDER_ID,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["FeedMe"])


@router.get("/conversations", response_model=ConversationListResponse)
@limiter.limit("100/minute")
async def list_conversations(
    request: Request,
    page: int = Query(1, ge=1, le=10000, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Number of items per page"),
    status: Optional[ProcessingStatus] = Query(None, description="Filter by processing status"),
    uploaded_by: Optional[str] = Query(None, description="Filter by uploader"),
    folder_id: Optional[int] = Query(UNASSIGNED_FOLDER_ID, description="Filter by folder ID"),
    include_all: bool = Query(False, description="Include all conversations regardless of folder")
):
    """Retrieve a paginated list of conversations with optional filtering."""
    if not settings.feedme_enabled:
        raise HTTPException(status_code=503, detail="FeedMe service is currently disabled")

    client = get_feedme_supabase_client()
    if client is None:
        raise HTTPException(
            status_code=503,
            detail="FeedMe service is temporarily unavailable."
        )

    try:
        status_value = status.value if status else None
        effective_folder_id = None if include_all else folder_id

        result = await client.get_conversations_with_pagination(
            page=page,
            page_size=page_size,
            status=status_value,
            uploaded_by=uploaded_by,
            folder_id=effective_folder_id
        )

        conversations = []
        for conv in result["conversations"]:
            if conv.get('processing_method') in (None, ''):
                conv['processing_method'] = ProcessingMethod.PDF_AI.value
            conversations.append(FeedMeConversation(**conv))

        return ConversationListResponse(
            conversations=conversations,
            total_count=result["total_count"],
            page=result["page"],
            page_size=result["page_size"],
            has_next=result["has_next"]
        )

    except Exception as e:
        logger.error(f"Error listing conversations: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to list conversations")


@router.get("/conversations/{conversation_id}", response_model=FeedMeConversation)
async def get_conversation(conversation_id: int):
    """Retrieve a conversation by its unique ID."""
    if not settings.feedme_enabled:
        raise HTTPException(status_code=503, detail="FeedMe service is currently disabled")

    conversation = await get_conversation_by_id(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return conversation


@router.put("/conversations/{conversation_id}", response_model=FeedMeConversation)
async def update_conversation(conversation_id: int, update_data: ConversationUpdate):
    """Updates a conversation record with the specified fields."""
    if not settings.feedme_enabled:
        raise HTTPException(status_code=503, detail="FeedMe service is currently disabled")

    existing = await get_conversation_by_id(conversation_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Conversation not found")

    updated_conversation = await update_conversation_in_db(conversation_id, update_data)
    if not updated_conversation:
        raise HTTPException(status_code=500, detail="Failed to update conversation")

    return updated_conversation


@router.delete("/conversations/{conversation_id}", response_model=DeleteConversationResponse)
async def delete_conversation(conversation_id: int):
    """Deletes a conversation and all associated examples."""
    if not settings.feedme_enabled:
        raise HTTPException(status_code=503, detail="FeedMe service is currently disabled")

    try:
        conversation = await supabase_client.get_conversation_by_id(conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")

        deletion_success = await supabase_client.delete_conversation(conversation_id)
        if not deletion_success:
            raise HTTPException(status_code=500, detail="Failed to delete conversation")

        logger.info(f"Successfully deleted conversation {conversation_id}")

        return DeleteConversationResponse(
            conversation_id=conversation_id,
            title=conversation.get('title', 'Unknown'),
            examples_deleted=0,
            message=f"Successfully deleted conversation '{conversation.get('title', 'Unknown')}'"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete conversation {conversation_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete conversation")


@router.get("/conversations/{conversation_id}/examples", response_model=ExampleListResponse)
async def list_conversation_examples(
    conversation_id: int,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Number of items per page"),
    is_active: Optional[bool] = Query(None, description="Filter by active status")
):
    """Retrieve a paginated list of examples for a conversation."""
    if not settings.feedme_enabled:
        raise HTTPException(status_code=503, detail="FeedMe service is currently disabled")

    conversation = await get_conversation_by_id(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    try:
        client = get_supabase_client()

        query = client.client.table('feedme_examples').select("""
            id, uuid, conversation_id, question_text, answer_text,
            context_before, context_after, tags, issue_type, resolution_type,
            confidence_score, usefulness_score, is_active, version,
            review_status, reviewed_by, reviewed_at, reviewer_notes, generated_by_model,
            created_at, updated_at
        """)
        query = query.eq('conversation_id', conversation_id)

        if is_active is not None:
            query = query.eq('is_active', is_active)

        count_response = client.client.table('feedme_examples') \
            .select('id', count='exact') \
            .eq('conversation_id', conversation_id)

        if is_active is not None:
            count_response = count_response.eq('is_active', is_active)

        count_result = await client._exec(lambda: count_response.execute())
        total_count = count_result.count if count_result.count else 0

        offset = (page - 1) * page_size
        query = query.order('created_at', desc=True).range(offset, offset + page_size - 1)

        response = await client._exec(lambda: query.execute())

        examples = []
        for row in response.data:
            try:
                example_data = dict(row)
                if 'reviewer_notes' not in example_data:
                    example_data['reviewer_notes'] = None
                if 'generated_by_model' not in example_data:
                    example_data['generated_by_model'] = None
                examples.append(FeedMeExample(**example_data))
            except Exception as e:
                logger.error(f"Failed to parse example {row.get('id', 'unknown')}: {e}")
                continue

        total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 1

        return ExampleListResponse(
            examples=examples,
            total_examples=total_count,
            page=page,
            page_size=page_size,
            total_pages=total_pages
        )

    except Exception as e:
        logger.error(f"Error listing examples for conversation {conversation_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to list examples")


@router.put("/examples/{example_id}", response_model=FeedMeExample)
async def update_example(example_id: int, updates: ExampleUpdate):
    """Update an existing Q&A example."""
    if not settings.feedme_enabled:
        raise HTTPException(status_code=503, detail="FeedMe service is currently disabled")

    try:
        client = get_supabase_client()

        existing_example = await client.get_example_by_id(example_id)
        if not existing_example:
            raise HTTPException(status_code=404, detail="Example not found")

        update_data = updates.dict(exclude_unset=True)
        if not update_data:
            return FeedMeExample(**existing_example)

        updated_example = await client.update_example(
            example_id=example_id,
            update_data=update_data
        )

        if not updated_example:
            raise HTTPException(status_code=500, detail="Failed to update example")

        return FeedMeExample(**updated_example)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating example {example_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update example")


@router.get("/conversations/{conversation_id}/formatted-content")
async def get_formatted_qa_content(conversation_id: int):
    """Get formatted Q&A content for editing in the conversation modal."""
    if not settings.feedme_enabled:
        raise HTTPException(status_code=503, detail="FeedMe service is currently disabled")

    conversation = await get_conversation_by_id(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    try:
        examples = await supabase_client.get_examples_by_conversation(conversation_id)
        active_examples = [ex for ex in examples if ex.get('is_active', True)]

        if not active_examples:
            return {
                "formatted_content": conversation.raw_transcript or "",
                "total_examples": 0,
                "content_type": "raw_transcript",
                "message": "No Q&A examples extracted yet. Showing raw transcript."
            }

        formatted_lines = ["# Extracted Q&A Examples", "", f"**Total Examples:** {len(active_examples)}", ""]

        for i, example in enumerate(active_examples, 1):
            formatted_lines.append(f"## Example {i}")

            metadata_parts = []
            if example.get('issue_type'):
                metadata_parts.append(f"Issue: {example['issue_type']}")
            if example.get('resolution_type'):
                metadata_parts.append(f"Resolution: {example['resolution_type']}")
            if example.get('confidence_score'):
                metadata_parts.append(f"Confidence: {example['confidence_score']:.2f}")
            if example.get('tags'):
                metadata_parts.append(f"Tags: {', '.join(example['tags'])}")

            if metadata_parts:
                formatted_lines.append(f"*{' | '.join(metadata_parts)}*")
                formatted_lines.append("")

            if example.get('context_before'):
                formatted_lines.extend(["**Context Before:**", example['context_before'], ""])

            formatted_lines.extend(["**Question:**", example.get('question_text', ''), ""])
            formatted_lines.extend(["**Answer:**", example.get('answer_text', ''), ""])

            if example.get('context_after'):
                formatted_lines.extend(["**Context After:**", example['context_after'], ""])

            if i < len(active_examples):
                formatted_lines.extend(["---", ""])

        return {
            "formatted_content": "\n".join(formatted_lines),
            "total_examples": len(active_examples),
            "content_type": "qa_examples",
            "raw_transcript": conversation.raw_transcript or "",
            "message": f"Showing {len(active_examples)} extracted Q&A examples"
        }

    except Exception as e:
        logger.error(f"Error getting formatted content: {e}", exc_info=True)
        return {
            "formatted_content": conversation.raw_transcript or "",
            "total_examples": 0,
            "content_type": "raw_transcript",
            "message": "Error loading Q&A examples. Showing raw transcript."
        }


@router.get("/conversations/{conversation_id}/status", response_model=ConversationProcessingStatus)
async def get_processing_status(conversation_id: int):
    """Retrieve the processing status and progress for a conversation."""
    if not settings.feedme_enabled:
        raise HTTPException(status_code=503, detail="FeedMe service is currently disabled")

    conversation = await get_conversation_by_id(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    tracker = {}
    if conversation.metadata and isinstance(conversation.metadata, dict):
        tracker = conversation.metadata.get('processing_tracker', {}) or {}

    stage_raw = tracker.get('stage')
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

    progress = tracker.get('progress')
    if progress is None:
        progress = 100 if conversation.processing_status == ProcessingStatus.COMPLETED else 0

    default_messages = {
        ProcessingStatus.PENDING: "Pending processing",
        ProcessingStatus.PROCESSING: "Processing transcript",
        ProcessingStatus.COMPLETED: "Processing completed",
        ProcessingStatus.FAILED: "Processing failed"
    }
    message = tracker.get('message') or default_messages.get(conversation.processing_status, "Processing updated")
    error_message = conversation.error_message or tracker.get('error')

    return ConversationProcessingStatus(
        conversation_id=conversation.id,
        status=conversation.processing_status,
        stage=stage,
        progress_percentage=int(progress),
        message=message,
        error_message=error_message,
        started_at=tracker.get('started_at'),
        completed_at=tracker.get('completed_at'),
        examples_extracted=tracker.get('examples_extracted', 0)
    )
