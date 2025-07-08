"""
FeedMe API Endpoints

API endpoints for customer support transcript ingestion, processing, and management.
Provides functionality for uploading transcripts, managing conversations, and searching examples.
"""

import logging
import os
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form, Query, Body, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import asyncio
import io
# import psycopg2.extras as psycopg2_extras  # Removed - using Supabase exclusively

from app.core.settings import settings
from app.feedme.schemas import (
    FeedMeConversation,
    FeedMeExample,
    ConversationCreate,
    ConversationUpdate,
    ConversationUploadResponse,
    ExampleCreate,
    ExampleUpdate,
    TranscriptUploadRequest,
    ProcessingStatus,
    ApprovalStatus,
    ReviewStatus,

    ConversationListResponse,
    ExampleListResponse,

    SearchQuery,
    FeedMeSearchResponse,
    ConversationStats,
    AnalyticsResponse,
    # Phase 3: Versioning schemas
    ConversationVersion,
    VersionListResponse,
    VersionDiff,
    ConversationEditRequest,
    ConversationRevertRequest,
    EditResponse,
    RevertResponse,
    # Approval workflow schemas
    ApprovalRequest,
    RejectionRequest,
    ApprovalResponse,
    DeleteConversationResponse,
    ApprovalWorkflowStats,
    BulkApprovalRequest,
    BulkApprovalResponse,
    ExampleReviewRequest,
    ExampleReviewResponse
)

# Folder management schemas
class FeedMeFolder(BaseModel):
    id: int
    name: str
    color: str
    description: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    conversation_count: Optional[int] = 0

    class Config:
        from_attributes = True

class FolderCreate(BaseModel):
    name: str
    color: str = "#0095ff"
    description: Optional[str] = None
    created_by: Optional[str] = None

class FolderUpdate(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None
    description: Optional[str] = None

class AssignFolderRequest(BaseModel):
    folder_id: Optional[int] = None  # None to remove from folder
    conversation_ids: List[int]

class FolderListResponse(BaseModel):
    folders: List[FeedMeFolder]
    total_count: int

# Supabase integration schemas
class SupabaseApprovalRequest(BaseModel):
    approved_by: str
    example_ids: Optional[List[int]] = None  # None means all examples
    reviewer_notes: Optional[str] = None

# Import database utilities
from app.db.embedding_utils import get_embedding_model
from app.db.supabase_client import get_supabase_client
# from .feedme_db_helper import get_db_connection  # Removed - using Supabase exclusively

# Temporary function to catch remaining get_db_connection calls
def get_db_connection():
    """
    Legacy function - no longer supported.
    Use Supabase client for all database operations.
    """
    raise NotImplementedError("Local DB connections no longer supported. Use Supabase client instead.")

logger = logging.getLogger(__name__)
router = APIRouter()

# Global Supabase client instance
supabase_client = get_supabase_client()


async def update_conversation_status(conversation_id: int, status: ProcessingStatus, error_message: Optional[str] = None):
    """Updates the processing status and error message of a conversation in Supabase."""
    try:
        client = get_supabase_client()
        await client.update_conversation(
            conversation_id=conversation_id,
            update_data={
                'processing_status': status.value,
                'error_message': error_message
            }
        )
    except Exception as e:
        logger.error(f"Failed to update status for conversation {conversation_id}: {e}")

# Supabase client helper
def get_supabase_connection():
    """Get Supabase client instance"""
    return get_supabase_client()

# Database helper functions

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
            return FeedMeConversation(**result)
        return None
    except Exception as e:
        logger.error(f"Error fetching conversation {conversation_id}: {e}")
        return None


async def create_conversation_in_db(conversation_data: ConversationCreate) -> FeedMeConversation:
    """
    Inserts a new conversation record into Supabase using the provided conversation data.
    
    Parameters:
    	conversation_data (ConversationCreate): The data required to create a new conversation, including title, original filename, transcript content, metadata, and uploader.
    
    Returns:
    	FeedMeConversation: The newly created conversation record.
    
    Raises:
    	HTTPException: If the database operation fails, an HTTP 500 error is raised with details.
    """
    try:
        client = get_supabase_client()
        result = await client.insert_conversation(
            title=conversation_data.title,
            original_filename=conversation_data.original_filename,
            raw_transcript=conversation_data.raw_transcript,
            metadata=conversation_data.metadata,
            uploaded_by=conversation_data.uploaded_by
        )
        return FeedMeConversation(**result)
    except Exception as e:
        logger.error(f"Error creating conversation: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create conversation: {str(e)}")


async def update_conversation_in_db(conversation_id: int, update_data: ConversationUpdate) -> Optional[FeedMeConversation]:
    """
    Updates specified fields of a conversation record in Supabase and returns the updated conversation.
    
    If no fields are provided for update, retrieves and returns the existing conversation.
    
    Parameters:
        conversation_id (int): The ID of the conversation to update.
        update_data (ConversationUpdate): Fields to update in the conversation.
    
    Returns:
        FeedMeConversation or None: The updated conversation object if found, otherwise None.
    
    Raises:
        HTTPException: If a database error occurs during the update.
    """
    try:
        supabase_client = get_supabase_client()
        
        # Build update data
        update_dict = update_data.dict(exclude_unset=True)
        
        if not update_dict:
            # No fields to update
            return await get_conversation_by_id(conversation_id)
        
        # Convert processing_status enum to string if present
        if 'processing_status' in update_dict:
            update_dict['processing_status'] = update_dict['processing_status'].value
        
        # Update in Supabase
        updated_conversation = await supabase_client.update_conversation(
            conversation_id=conversation_id,
            update_data=update_dict
        )
        
        if updated_conversation:
            return FeedMeConversation(**updated_conversation)
        return None
                
    except Exception as e:
        logger.error(f"Error updating conversation {conversation_id}: {e}")
        return None
        raise HTTPException(status_code=500, detail=f"Failed to update conversation: {str(e)}")


# API Endpoints

@router.post("/conversations/upload", response_model=ConversationUploadResponse, status_code=202, tags=["FeedMe"])
async def upload_transcript(
    background_tasks: BackgroundTasks,
    title: str = Form(..., description="Conversation title"),
    uploaded_by: Optional[str] = Form(None, description="User uploading the transcript"),
    auto_process: bool = Form(True, description="Whether to automatically process the transcript"),
    transcript_file: Optional[UploadFile] = File(None, description="Transcript file to upload"),
    transcript_content: Optional[str] = Form(None, description="Transcript content as text")
):
    """
    Uploads a customer support transcript for ingestion, accepting either a file upload or direct text input.
    
    Validates input exclusivity, file size, UTF-8 encoding, and minimum content length. Creates a new conversation record with the provided transcript and metadata. If `auto_process` is enabled, schedules the conversation for background processing by updating its status to pending.
    
    Returns:
        FeedMeConversation: The created conversation record.
    
    Raises:
        HTTPException: If the service is disabled, input is invalid, file is too large, encoding fails, or database operations fail.
    """
    
    if not settings.feedme_enabled:
        raise HTTPException(status_code=503, detail="FeedMe service is currently disabled")
    
    # Validate input
    if not transcript_file and not transcript_content:
        raise HTTPException(status_code=400, detail="Either transcript_file or transcript_content must be provided")
    
    if transcript_file and transcript_content:
        raise HTTPException(status_code=400, detail="Provide either transcript_file or transcript_content, not both")
    
    # Extract transcript content
    final_content = ""
    original_filename = None
    
    if transcript_file:
        # Validate file
        if transcript_file.size and transcript_file.size > settings.feedme_max_file_size_mb * 1024 * 1024:
            raise HTTPException(
                status_code=413,
                detail=f"File size exceeds maximum allowed size of {settings.feedme_max_file_size_mb}MB"
            )
        
        # Validate file type and content type
        allowed_content_types = ["text/plain", "text/html", "application/html", "text/csv", "application/octet-stream"]
        allowed_extensions = [".txt", ".log", ".html", ".htm", ".csv"]
        
        # Check content type if provided
        if transcript_file.content_type and transcript_file.content_type not in allowed_content_types:
            logger.warning(
                f"Unexpected content type {transcript_file.content_type} for file {transcript_file.filename}"
            )
            raise HTTPException(status_code=400, detail="Invalid file content type")
        
        # Check file extension and HTML support
        if transcript_file.filename:
            file_extension = os.path.splitext(transcript_file.filename.lower())[1]
            
            # Check if HTML file and HTML support is enabled
            is_html_file = transcript_file.filename.lower().endswith(('.html', '.htm')) or \
                          (transcript_file.content_type and transcript_file.content_type in ["text/html", "application/html"])
            
            if is_html_file and not settings.feedme_html_enabled:
                raise HTTPException(
                    status_code=400, 
                    detail="HTML file uploads are not enabled. Please contact your administrator to enable FEEDME_HTML_ENABLED."
                )
            
            if file_extension and file_extension not in allowed_extensions:
                logger.warning(
                    f"Unexpected file extension {file_extension} for file {transcript_file.filename}"
                )
                raise HTTPException(status_code=400, detail="Invalid file extension")
        
        # Read file content
        try:
            content_bytes = await transcript_file.read()
            final_content = content_bytes.decode('utf-8')
            original_filename = transcript_file.filename
        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail="File must be valid UTF-8 text")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error reading file: {str(e)}")
    else:
        final_content = transcript_content
    
    # Validate content length
    if len(final_content.strip()) < 10:
        raise HTTPException(status_code=400, detail="Transcript content must be at least 10 characters long")
    
    # Create conversation
    conversation_data = ConversationCreate(
        title=title,
        original_filename=original_filename,
        raw_transcript=final_content,
        uploaded_by=uploaded_by,
        metadata={"auto_process": auto_process}
    )
    
    try:
        # Create conversation in database with 'pending' status
        conversation = await create_conversation_in_db(conversation_data)
        
        # Add background task for processing
        if auto_process:
            background_tasks.add_task(process_uploaded_transcript, conversation.id, conversation.uploaded_by)
        
        return ConversationUploadResponse(
            message="Conversation upload accepted for processing.",
            conversation_id=conversation.id,
            processing_status=conversation.processing_status
        )

    except HTTPException as e:
        logger.error(f"HTTP error during conversation creation: {e.detail}")
        raise
    except Exception as e:
        logger.error(f"Failed to create conversation: {e}")
        raise HTTPException(status_code=500, detail="Failed to create conversation")

async def process_uploaded_transcript(conversation_id: int, processed_by: str):
    """Background task to process a newly uploaded transcript."""
    try:
        from app.feedme.tasks import process_transcript
        logger.info(f"Starting background processing for conversation {conversation_id} - scheduling Celery task")
        await update_conversation_status(conversation_id, ProcessingStatus.PENDING)
        
        # Schedule the actual processing as a Celery task
        task = process_transcript.delay(conversation_id, processed_by)
        logger.info(f"Scheduled Celery task {task.id} for conversation {conversation_id}")
        
    except Exception as e:
        logger.error(f"Background processing scheduling failed for conversation {conversation_id}: {e}")
        await update_conversation_status(conversation_id, ProcessingStatus.FAILED)


@router.get("/conversations", response_model=ConversationListResponse, tags=["FeedMe"])
async def list_conversations(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Number of items per page"),
    status: Optional[ProcessingStatus] = Query(None, description="Filter by processing status"),
    uploaded_by: Optional[str] = Query(None, description="Filter by uploader"),
    folder_id: Optional[int] = Query(None, description="Filter by folder ID (null for unassigned)")
):
    """
    Retrieve a paginated list of conversations with optional filtering by processing status, uploader, and folder.
    
    Parameters:
        page (int): The page number to retrieve (1-based).
        page_size (int): The number of conversations per page.
        status (Optional[ProcessingStatus]): Filter conversations by their processing status.
        uploaded_by (Optional[str]): Filter conversations by the uploader's identifier.
        folder_id (Optional[int]): Filter conversations by folder ID. Use null for unassigned conversations.
    
    Returns:
        ConversationListResponse: A paginated response containing the list of conversations, total count, current page, page size, and a flag indicating if more pages are available.
    
    Raises:
        HTTPException: If the FeedMe service is disabled (503) or if a database error occurs (500).
    """
    
    if not settings.feedme_enabled:
        raise HTTPException(status_code=503, detail="FeedMe service is currently disabled")
    
    try:
        # Use Supabase client for pagination and filtering
        status_value = status.value if status else None
        
        result = await supabase_client.get_conversations_with_pagination(
            page=page,
            page_size=page_size,
            status=status_value,
            uploaded_by=uploaded_by,
            folder_id=folder_id
        )
        
        # Convert to FeedMeConversation objects
        conversations = [FeedMeConversation(**conv) for conv in result["conversations"]]
        
        return ConversationListResponse(
            conversations=conversations,
            total_count=result["total_count"],
            page=result["page"],
            page_size=result["page_size"],
            has_next=result["has_next"]
        )
                
    except Exception as e:
        logger.error(f"Error listing conversations: {e}")
        logger.error(f"Error type: {type(e).__name__}")
        logger.error(f"Error details: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Failed to list conversations: {str(e)}")


@router.get("/conversations/{conversation_id}", response_model=FeedMeConversation, tags=["FeedMe"])
async def get_conversation(conversation_id: int):
    """
    Retrieve a conversation by its unique ID.
    
    Raises:
        HTTPException: If the FeedMe service is disabled (503) or the conversation is not found (404).
    
    Returns:
        FeedMeConversation: The conversation record matching the provided ID.
    """
    
    if not settings.feedme_enabled:
        raise HTTPException(status_code=503, detail="FeedMe service is currently disabled")
    
    conversation = await get_conversation_by_id(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    return conversation


@router.put("/conversations/{conversation_id}", response_model=FeedMeConversation, tags=["FeedMe"])
async def update_conversation(conversation_id: int, update_data: ConversationUpdate):
    """
    Updates a conversation record with the specified fields.
    
    Raises:
        HTTPException: If the FeedMe service is disabled (503), the conversation is not found (404), or the update fails (500).
    
    Returns:
        FeedMeConversation: The updated conversation object.
    """
    
    if not settings.feedme_enabled:
        raise HTTPException(status_code=503, detail="FeedMe service is currently disabled")
    
    # Check if conversation exists
    existing = await get_conversation_by_id(conversation_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    # Update conversation
    updated_conversation = await update_conversation_in_db(conversation_id, update_data)
    if not updated_conversation:
        raise HTTPException(status_code=500, detail="Failed to update conversation")
    
    return updated_conversation


@router.delete("/conversations/{conversation_id}", response_model=DeleteConversationResponse, tags=["FeedMe"])
async def delete_conversation(conversation_id: int):
    """
    Deletes a conversation and all associated examples from the database.
    
    Raises:
        HTTPException: If the FeedMe service is disabled (503), the conversation does not exist (404), or deletion fails (500).
    
    Returns:
        DeleteConversationResponse: Details of the deleted conversation and examples.
    """
    
    if not settings.feedme_enabled:
        raise HTTPException(status_code=503, detail="FeedMe service is currently disabled")
    
    try:
        # Get conversation details before deletion
        conversation = await supabase_client.get_conversation_by_id(conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        # Count examples before deletion
        examples_response = supabase_client.client.table('feedme_examples')\
            .select('id', count='exact')\
            .eq('conversation_id', conversation_id)\
            .execute()
        
        examples_count = examples_response.count or 0
        
        # Delete using Supabase client
        deletion_success = await supabase_client.delete_conversation(conversation_id)
        
        if not deletion_success:
            raise HTTPException(status_code=500, detail="Failed to delete conversation")
        
        logger.info(f"Successfully deleted conversation {conversation_id} and {examples_count} examples using Supabase")
        
        return DeleteConversationResponse(
            conversation_id=conversation_id,
            title=conversation.get('title', 'Unknown'),
            examples_deleted=examples_count,
            message=f"Successfully deleted conversation '{conversation.get('title', 'Unknown')}' and {examples_count} associated examples"
        )
                
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete conversation {conversation_id} using Supabase: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete conversation")


@router.get("/conversations/{conversation_id}/examples", response_model=ExampleListResponse, tags=["FeedMe"])
async def list_conversation_examples(
    conversation_id: int,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Number of items per page"),
    is_active: Optional[bool] = Query(None, description="Filter by active status")
):
    """
    Retrieve a paginated list of examples associated with a specific conversation.
    
    Parameters:
        conversation_id (int): The ID of the conversation to retrieve examples for.
        page (int): The page number for pagination (default is 1).
        page_size (int): The number of examples per page (default is 20, maximum is 100).
        is_active (Optional[bool]): If provided, filters examples by their active status.
    
    Returns:
        ExampleListResponse: A paginated response containing the list of examples, total count, current page, page size, and whether more pages are available.
    
    Raises:
        HTTPException: Returns 404 if the conversation does not exist, 503 if the FeedMe service is disabled, or 500 on database errors.
    """
    
    if not settings.feedme_enabled:
        raise HTTPException(status_code=503, detail="FeedMe service is currently disabled")
    
    # Check if conversation exists
    conversation = await get_conversation_by_id(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    try:
        # Use Supabase client instead of local database
        client = get_supabase_client()
        
        # Build query with filters - select all fields needed for FeedMeExample
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
        
        # Get total count first
        count_response = client.client.table('feedme_examples')\
            .select('id', count='exact')\
            .eq('conversation_id', conversation_id)
        
        if is_active is not None:
            count_response = count_response.eq('is_active', is_active)
        
        count_result = count_response.execute()
        total_count = count_result.count if count_result.count else 0
        
        # Get paginated data
        offset = (page - 1) * page_size
        query = query.order('created_at', desc=True)\
                     .range(offset, offset + page_size - 1)
        
        response = query.execute()
        
        # Convert to FeedMeExample objects
        examples = []
        for row in response.data:
            try:
                # Add missing fields with defaults if needed
                example_data = dict(row)
                
                # Ensure optional fields have proper defaults
                if 'reviewer_notes' not in example_data:
                    example_data['reviewer_notes'] = None
                if 'generated_by_model' not in example_data:
                    example_data['generated_by_model'] = None
                
                examples.append(FeedMeExample(**example_data))
            except Exception as e:
                logger.error(f"Failed to parse example {row.get('id', 'unknown')}: {e}")
                logger.error(f"Row data: {row}")
                continue
        
        # Calculate total pages
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


@router.put("/examples/{example_id}", response_model=FeedMeExample, tags=["FeedMe"])
async def update_example(
    example_id: int,
    updates: ExampleUpdate
):
    """
    Update an existing Q&A example using Supabase.
    
    Parameters:
        example_id (int): The ID of the example to update.
        updates (ExampleUpdate): The fields to update.
    
    Returns:
        FeedMeExample: The updated example.
    
    Raises:
        HTTPException: Returns 404 if the example does not exist, 503 if the FeedMe service is disabled, or 500 on database errors.
    """
    
    if not settings.feedme_enabled:
        raise HTTPException(status_code=503, detail="FeedMe service is currently disabled")
    
    try:
        supabase_client = get_supabase_client()
        
        # Check if example exists
        existing_example = await supabase_client.get_example_by_id(example_id)
        if not existing_example:
            raise HTTPException(status_code=404, detail="Example not found")
        
        # Build update data
        update_data = updates.dict(exclude_unset=True)
        
        if not update_data:
            # No updates to apply, return existing example
            return FeedMeExample(**existing_example)
        
        # Update the example in Supabase
        updated_example = await supabase_client.update_example(
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


@router.get("/conversations/{conversation_id}/formatted-content", tags=["FeedMe"])
async def get_formatted_qa_content(conversation_id: int):
    """
    Get formatted Q&A content for editing in the conversation modal.
    
    Returns the extracted Q&A pairs formatted as readable text that can be
    displayed and edited in the conversation edit modal.
    
    Returns:
        dict: Contains 'formatted_content' with Q&A pairs as formatted text,
              'total_examples' count, and 'raw_transcript' as fallback.
    """
    
    if not settings.feedme_enabled:
        raise HTTPException(status_code=503, detail="FeedMe service is currently disabled")
    
    # Check if conversation exists
    conversation = await get_conversation_by_id(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    try:
        # Get all active examples for this conversation using Supabase
        examples = await supabase_client.get_examples_by_conversation(conversation_id)
        
        # Filter active examples (Supabase returns all, so we filter here)
        active_examples = [ex for ex in examples if ex.get('is_active', True)]
                
        if not active_examples:
            # No examples extracted yet, return raw transcript
            return {
                "formatted_content": conversation.raw_transcript or "",
                "total_examples": 0,
                "content_type": "raw_transcript",
                "message": "No Q&A examples extracted yet. Showing raw transcript."
            }
        
        # Format Q&A examples into readable text
        formatted_lines = []
        formatted_lines.append("# Extracted Q&A Examples")
        formatted_lines.append("")
        formatted_lines.append(f"**Total Examples:** {len(active_examples)}")
        formatted_lines.append("")
        
        for i, example in enumerate(active_examples, 1):
            formatted_lines.append(f"## Example {i}")
            
            # Add metadata if available
            metadata_parts = []
            if example['issue_type']:
                metadata_parts.append(f"Issue: {example['issue_type']}")
            if example['resolution_type']:
                metadata_parts.append(f"Resolution: {example['resolution_type']}")
            if example['confidence_score']:
                metadata_parts.append(f"Confidence: {example['confidence_score']:.2f}")
            if example['tags']:
                metadata_parts.append(f"Tags: {', '.join(example['tags'])}")
            
            if metadata_parts:
                formatted_lines.append(f"*{' | '.join(metadata_parts)}*")
                formatted_lines.append("")
            
            # Add context before if available
            if example['context_before']:
                formatted_lines.append("**Context Before:**")
                formatted_lines.append(example['context_before'])
                formatted_lines.append("")
            
            # Add Q&A pair
            formatted_lines.append("**Question:**")
            formatted_lines.append(example['question_text'])
            formatted_lines.append("")
            
            formatted_lines.append("**Answer:**")
            formatted_lines.append(example['answer_text'])
            formatted_lines.append("")
            
            # Add context after if available
            if example['context_after']:
                formatted_lines.append("**Context After:**")
                formatted_lines.append(example['context_after'])
                formatted_lines.append("")
            
            # Add separator between examples
            if i < len(active_examples):
                formatted_lines.append("---")
                formatted_lines.append("")
        
        formatted_content = "\n".join(formatted_lines)
        
        return {
            "formatted_content": formatted_content,
            "total_examples": len(active_examples),
            "content_type": "qa_examples", 
            "raw_transcript": conversation.raw_transcript or "",
            "message": f"Showing {len(active_examples)} extracted Q&A examples"
        }
                
    except Exception as e:
        logger.error(f"Error getting formatted content for conversation {conversation_id}: {e}")
        # Fallback to raw transcript on error
        return {
            "formatted_content": conversation.raw_transcript or "",
            "total_examples": 0,
            "content_type": "raw_transcript",
            "message": f"Error loading Q&A examples: {str(e)}. Showing raw transcript."
        }


@router.get("/conversations/{conversation_id}/status", response_model=FeedMeConversation, tags=["FeedMe"])
async def get_processing_status(conversation_id: int):
    """
    Retrieve the processing status and progress information for a specific conversation.
    
    Raises:
        HTTPException: If the FeedMe service is disabled (503) or the conversation is not found (404).
    
    Returns:
        ProcessingStatusResponse: An object containing the conversation's processing status, progress percentage, error message, number of examples extracted, and estimated completion time (if available).
    """
    
    if not settings.feedme_enabled:
        raise HTTPException(status_code=503, detail="FeedMe service is currently disabled")
    
    conversation = await get_conversation_by_id(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    return conversation


@router.post("/search", response_model=FeedMeSearchResponse, tags=["FeedMe"])
async def search_examples(search_query: SearchQuery):
    """
    Performs a similarity search on FeedMe examples based on the provided query.
    
    Currently returns a placeholder response with no results. Raises HTTP 503 if the FeedMe service is disabled and HTTP 500 on internal errors.
    
    Parameters:
        search_query (SearchQuery): The search query containing the text to search for.
    
    Returns:
        FeedMeSearchResponse: The search results, including the original query, an empty results list, total found count, and search time in milliseconds.
    """
    
    if not settings.feedme_enabled:
        raise HTTPException(status_code=503, detail="FeedMe service is currently disabled")
    
    start_time = datetime.now()
    
    try:
        # This would integrate with the updated embedding_utils.py in the next chunk
        # For now, return a placeholder response
        
        search_time_ms = (datetime.now() - start_time).total_seconds() * 1000
        
        return FeedMeSearchResponse(
            query=search_query.query,
            results=[],  # Will be populated when embedding search is implemented
            total_found=0,
            search_time_ms=search_time_ms
        )
        
    except Exception as e:
        logger.error(f"Error searching FeedMe examples: {e}")
        raise HTTPException(status_code=500, detail="Failed to search examples")


@router.get("/analytics", response_model=AnalyticsResponse, tags=["FeedMe"])
async def get_analytics():
    """
    Retrieve aggregated analytics and statistics for FeedMe conversations and examples.
    
    Returns:
        AnalyticsResponse: An object containing conversation statistics, top tags, issue type distribution, quality metrics, and the last updated timestamp.
    
    Raises:
        HTTPException: If the FeedMe service is disabled (503) or analytics generation fails (500).
    """
    
    if not settings.feedme_enabled:
        raise HTTPException(status_code=503, detail="FeedMe service is currently disabled")
    
    try:
        # Get comprehensive analytics using Supabase
        analytics_data = await supabase_client.get_conversation_analytics()
        
        # Build conversation stats from analytics data
        status_breakdown = analytics_data.get('status_breakdown', {})
        
        # Create ConversationStats object with required fields
        conversation_stats = ConversationStats(
            total_conversations=analytics_data.get('total_conversations', 0),
            total_examples=analytics_data.get('total_examples', 0),
            pending_processing=status_breakdown.get('pending', 0),
            processing_failed=status_breakdown.get('failed', 0),
            pending_approval=status_breakdown.get('pending', 0),  # Can be same as pending processing
            approved=status_breakdown.get('completed', 0),  # Assuming completed means approved
            rejected=0  # TODO: Add rejected status tracking
        )
        
        # Placeholder for additional analytics (tags, issue types) as dictionaries
        top_tags = {}  # TODO: Implement tag analytics
        issue_type_distribution = {}  # TODO: Implement issue type analytics
        
        quality_metrics = {
            'average_confidence_score': 0.0,  # TODO: Calculate from examples
            'average_usefulness_score': 0.0,  # TODO: Calculate from examples
            'processing_success_rate': float(
                conversation_stats.approved / max(conversation_stats.total_conversations, 1) * 100
            )
        }
        
        return AnalyticsResponse(
            conversation_stats=conversation_stats,
            top_tags=top_tags,
            issue_type_distribution=issue_type_distribution,
            quality_metrics=quality_metrics,
            last_updated=datetime.now()
        )
            
    except Exception as e:
        logger.error(f"Error generating analytics: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate analytics")


@router.post("/conversations/{conversation_id}/reprocess", tags=["FeedMe"])
async def reprocess_conversation(conversation_id: int, background_tasks: BackgroundTasks):
    """
    Schedules reprocessing of a conversation to extract examples.
    
    Raises:
    	HTTPException: If the FeedMe service is disabled (503), the conversation is not found (404), or scheduling fails (500).
    
    Returns:
    	Dict[str, str]: Confirmation message indicating that reprocessing has been scheduled.
    """
    
    if not settings.feedme_enabled:
        raise HTTPException(status_code=503, detail="FeedMe service is currently disabled")
    
    conversation = await get_conversation_by_id(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    try:
        # Update status to processing
        await update_conversation_in_db(
            conversation_id,
            ConversationUpdate(
                processing_status=ProcessingStatus.PROCESSING,
                error_message=None
            )
        )
        
        # Schedule background reprocessing
        # This would integrate with Celery task in the next implementation chunk
        logger.info(f"Scheduled reprocessing for conversation {conversation_id}")
        
        return {"message": "Conversation reprocessing scheduled"}
        
    except Exception as e:
        logger.error(f"Error scheduling reprocessing for conversation {conversation_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to schedule reprocessing")


@router.post("/conversations/{conversation_id}/process", tags=["FeedMe"])
async def manually_process_conversation(conversation_id: int):
    """
    Manually trigger processing for a conversation
    
    This endpoint allows manual triggering of Q&A extraction for conversations
    that are stuck in pending status or failed processing. It will attempt to use
    Celery if available, otherwise fall back to direct processing.
    
    Args:
        conversation_id: ID of the conversation to process
        
    Returns:
        Success message with processing status
        
    Raises:
        HTTPException: If conversation not found or processing fails
    """
    try:
        # Get the conversation to verify it exists using Supabase
        conversation = await supabase_client.get_conversation(conversation_id)
        
        if not conversation:
            raise HTTPException(status_code=404, detail=f"Conversation {conversation_id} not found")
        
        if conversation.get('processing_status') == 'completed':
            return JSONResponse(
                status_code=200,
                content={
                    "message": "Conversation already processed",
                    "conversation_id": conversation_id,
                    "status": "completed"
                }
            )
        
        # Try to use Celery first
        task_id = None
        try:
            from app.feedme.tasks import process_transcript
            
            # Reset status to pending before queueing using Supabase
            await supabase_client.update_conversation_status(
                conversation_id, 
                ProcessingStatus.PENDING.value,
                error_message=None
            )
            
            # Queue the task
            result = process_transcript.delay(conversation_id, "manual_trigger")
            task_id = result.id
            
            logger.info(f"Queued processing task {task_id} for conversation {conversation_id}")
            
            return JSONResponse(
                status_code=202,
                content={
                    "message": "Processing queued successfully",
                    "conversation_id": conversation_id,
                    "task_id": task_id,
                    "status": "queued"
                }
            )
            
        except Exception as celery_error:
            logger.warning(f"Celery not available: {celery_error}. Falling back to direct processing.")
            
            # Fall back to direct processing
            try:
                from app.feedme.transcript_parser import TranscriptParser
                from app.db.embedding_utils import generate_feedme_embeddings
                
                # Update status to processing using Supabase
                await supabase_client.update_conversation_status(
                    conversation_id, 
                    ProcessingStatus.PROCESSING.value
                )
                
                parser = TranscriptParser()
                
                # Parse the transcript
                examples = parser.parse_transcript(conversation['raw_transcript'])
                
                if not examples:
                    # No examples found - update status using Supabase
                    await supabase_client.update_conversation(
                        conversation_id,
                        {
                            "processing_status": ProcessingStatus.COMPLETED.value,
                            "processed_at": datetime.now(timezone.utc).isoformat(),
                            "total_examples": 0
                        }
                    )
                    
                    return JSONResponse(
                        status_code=200,
                        content={
                            "message": "Processing completed, no examples found",
                            "conversation_id": conversation_id,
                            "examples_extracted": 0,
                            "status": "completed"
                        }
                    )
                
                # Generate embeddings
                embedding_model = get_embedding_model()
                examples_with_embeddings = generate_feedme_embeddings(examples, embedding_model)
                
                # Save examples to database using Supabase
                # First delete existing examples (in case of reprocessing)
                # TODO: Implement delete_examples_by_conversation in Supabase client if needed
                
                # Prepare examples for Supabase insertion
                supabase_examples = []
                for example in examples_with_embeddings:
                    supabase_examples.append({
                        'conversation_id': conversation_id,
                        'question_text': example['question_text'],
                        'answer_text': example['answer_text'],
                        'context_before': example.get('context_before'),
                        'context_after': example.get('context_after'),
                        'question_embedding': example['question_embedding'],
                        'answer_embedding': example['answer_embedding'],
                        'combined_embedding': example['combined_embedding'],
                        'tags': example.get('tags', []),
                        'issue_type': example.get('issue_type'),
                        'resolution_type': example.get('resolution_type'),
                        'confidence_score': example.get('confidence_score', 0.8),
                        'usefulness_score': example.get('usefulness_score', 0.7),
                        'is_active': True
                    })
                
                # Insert examples using Supabase
                await supabase_client.insert_examples(supabase_examples)
                
                # Update conversation status
                await supabase_client.update_conversation(
                    conversation_id,
                    {
                        "processing_status": ProcessingStatus.COMPLETED.value,
                        "processed_at": datetime.now(timezone.utc).isoformat(),
                        "total_examples": len(examples)
                    }
                )
                
                logger.info(f"Successfully processed conversation {conversation_id} with {len(examples)} examples")
                
                return JSONResponse(
                    status_code=200,
                    content={
                        "message": "Processing completed successfully (direct mode)",
                        "conversation_id": conversation_id,
                        "examples_extracted": len(examples),
                        "status": "completed"
                    }
                )
                
            except Exception as e:
                logger.error(f"Error processing conversation {conversation_id}: {e}")
                
                # Update status to failed using Supabase
                await supabase_client.update_conversation_status(
                    conversation_id,
                    ProcessingStatus.FAILED.value,
                    error_message=str(e)
                )
                
                raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error processing conversation {conversation_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to process conversation")


@router.get("/health", tags=["FeedMe"])
async def feedme_health_check():
    """
    Comprehensive health check for FeedMe v2.0 system
    
    Checks:
    - Database connectivity and schema
    - Celery worker availability
    - Redis connectivity
    - Processing pipeline status
    """
    try:
        health_status = {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": "2.0",
            "components": {}
        }
        
        # Check Supabase health
        try:
            client = get_supabase_client()
            db_health = await client.health_check() if hasattr(client, 'health_check') else {"status": "healthy"}
            health_status["components"]["database"] = db_health
        except Exception as e:
            health_status["components"]["database"] = {
                "status": "unhealthy",
                "error": str(e)
            }
            health_status["status"] = "degraded"
        
        # Check Celery health if async processing is enabled
        if settings.feedme_async_processing:
            try:
                from app.feedme.celery_app import check_celery_health
                celery_health = check_celery_health()
                health_status["components"]["celery"] = celery_health
                
                if celery_health["status"] != "healthy":
                    health_status["status"] = "degraded"
                    
            except Exception as e:
                health_status["components"]["celery"] = {
                    "status": "unhealthy",
                    "error": str(e)
                }
                health_status["status"] = "degraded"
        else:
            health_status["components"]["celery"] = {
                "status": "disabled",
                "message": "Async processing is disabled"
            }
        
        # Check configuration
        health_status["components"]["configuration"] = {
            "async_processing_enabled": settings.feedme_async_processing,
            "max_file_size_mb": settings.feedme_max_file_size_mb,
            "similarity_threshold": settings.feedme_similarity_threshold,
            "version_control_enabled": settings.feedme_version_control
        }
        
        # Overall status determination
        component_statuses = [comp.get("status", "unknown") for comp in health_status["components"].values()]
        if any(status == "unhealthy" for status in component_statuses):
            health_status["status"] = "unhealthy"
        elif any(status in ["degraded", "disabled"] for status in component_statuses):
            health_status["status"] = "degraded"
        
        return health_status
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": str(e)
            }
        )


# Phase 3: Versioning and Edit API Endpoints

@router.put("/conversations/{conversation_id}/edit", response_model=EditResponse, tags=["FeedMe"])
async def edit_conversation(
    conversation_id: int,
    edit_request: ConversationEditRequest
):
    """
    Edit a conversation and create a new version
    
    Features:
    - Creates new version with edited content
    - Optionally triggers reprocessing
    - Maintains version history
    - Returns updated conversation and version info
    """
    try:
        from app.feedme.versioning_service import get_versioning_service
        
        versioning_service = get_versioning_service()
        result = await versioning_service.edit_conversation(conversation_id, edit_request)
        
        logger.info(f"Successfully edited conversation {conversation_id}, new version: {result.new_version}")
        return result
        
    except ValueError as e:
        logger.warning(f"Validation error editing conversation {conversation_id}: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error editing conversation {conversation_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to edit conversation")


@router.get("/conversations/{conversation_id}/versions", response_model=VersionListResponse, tags=["FeedMe"])
async def get_conversation_versions(conversation_id: int):
    """
    Get all versions of a conversation
    
    Returns:
    - List of all versions ordered by version number (newest first)
    - Total version count
    - Currently active version number
    """
    try:
        from app.feedme.versioning_service import get_versioning_service
        
        versioning_service = get_versioning_service()
        result = versioning_service.get_conversation_versions(conversation_id)
        
        logger.info(f"Retrieved {result.total_count} versions for conversation {conversation_id}")
        return result
        
    except ValueError as e:
        logger.warning(f"Conversation {conversation_id} not found: {e}")
        raise HTTPException(status_code=404, detail="Conversation not found")
    except Exception as e:
        logger.error(f"Error getting versions for conversation {conversation_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get conversation versions")


@router.get("/conversations/{conversation_id}/versions/{version_1}/diff/{version_2}", 
           response_model=VersionDiff, tags=["FeedMe"])
async def get_version_diff(conversation_id: int, version_1: int, version_2: int):
    """
    Generate diff between two versions of a conversation
    
    Features:
    - Shows added, removed, and modified lines
    - Provides diff statistics
    - Handles line-by-line comparison
    - Returns structured diff data for UI display
    """
    try:
        from app.feedme.versioning_service import get_versioning_service
        
        versioning_service = get_versioning_service()
        
        # Get both versions
        v1 = versioning_service.get_version_by_number(conversation_id, version_1)
        v2 = versioning_service.get_version_by_number(conversation_id, version_2)
        
        if not v1:
            raise HTTPException(status_code=404, detail=f"Version {version_1} not found")
        if not v2:
            raise HTTPException(status_code=404, detail=f"Version {version_2} not found")
        
        # Generate diff
        diff = versioning_service.generate_diff(v1, v2)
        
        logger.info(f"Generated diff between versions {version_1} and {version_2} for conversation {conversation_id}")
        return diff
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating diff for conversation {conversation_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate version diff")


@router.post("/conversations/{conversation_id}/revert/{target_version}", 
            response_model=RevertResponse, tags=["FeedMe"])
async def revert_conversation(
    conversation_id: int,
    target_version: int,
    revert_request: ConversationRevertRequest
):
    """
    Revert a conversation to a previous version
    
    Process:
    - Creates new version with content from target version
    - Maintains audit trail of revert operation
    - Optionally triggers reprocessing
    - Returns new version info
    """
    try:
        from app.feedme.versioning_service import get_versioning_service
        
        # Validate target version matches path parameter
        if revert_request.target_version != target_version:
            raise HTTPException(
                status_code=400, 
                detail="Target version in path must match request body"
            )
        
        versioning_service = get_versioning_service()
        result = await versioning_service.revert_conversation(conversation_id, revert_request)
        
        logger.info(f"Successfully reverted conversation {conversation_id} to version {target_version}, new version: {result.new_version}")
        return result
        
    except ValueError as e:
        logger.warning(f"Validation error reverting conversation {conversation_id}: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error reverting conversation {conversation_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to revert conversation")


@router.get("/conversations/{conversation_id}/versions/{version_number}", 
           response_model=ConversationVersion, tags=["FeedMe"])
async def get_specific_version(conversation_id: int, version_number: int):
    """
    Get a specific version of a conversation
    
    Returns:
    - Complete version data including content and metadata
    - Version creation and modification timestamps
    - User information for tracking changes
    """
    try:
        from app.feedme.versioning_service import get_versioning_service
        
        versioning_service = get_versioning_service()
        version = versioning_service.get_version_by_number(conversation_id, version_number)
        
        if not version:
            raise HTTPException(
                status_code=404, 
                detail=f"Version {version_number} not found for conversation {conversation_id}"
            )
        
        logger.info(f"Retrieved version {version_number} for conversation {conversation_id}")
        return version
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting version {version_number} for conversation {conversation_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get conversation version")


# Approval Workflow API Endpoints

@router.post("/conversations/{conversation_id}/approve", response_model=ApprovalResponse, tags=["FeedMe"])
async def approve_conversation(conversation_id: int, approval_request: ApprovalRequest):
    """
    Approve a conversation for publication
    
    Transitions the conversation from 'processed' to 'approved' status and marks
    all associated examples as approved for retrieval.
    
    Args:
        conversation_id: ID of the conversation to approve
        approval_request: Approval details including reviewer information
        
    Returns:
        ApprovalResponse: Updated conversation and approval details
        
    Raises:
        HTTPException: If conversation not found, not in processed state, or approval fails
    """
    
    if not settings.feedme_enabled:
        raise HTTPException(status_code=503, detail="FeedMe service is currently disabled")
    
    try:
        # Check conversation exists using Supabase
        conversation = await supabase_client.get_conversation_by_id(conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        # Check approval status
        current_status = conversation.get('approval_status', 'pending')
        if current_status not in ['processed', 'pending', 'completed']:
            raise HTTPException(
                status_code=400, 
                detail=f"Conversation is in '{current_status}' status and cannot be approved"
            )
        
        # Update conversation to approved status using Supabase
        approval_time = datetime.now(timezone.utc).isoformat()
        update_data = {
            'approval_status': 'approved',
            'approved_by': approval_request.approved_by,
            'approved_at': approval_time,
            'reviewer_notes': approval_request.approval_notes,  # ✅ FIXED: Use correct field name
            'updated_at': approval_time
        }
        
        updated_conversation = await supabase_client.update_conversation(conversation_id, update_data)
        if not updated_conversation:
            raise HTTPException(status_code=500, detail="Failed to update conversation approval status")
        
        # Approve all examples for this conversation using Supabase
        approval_result = await supabase_client.approve_conversation_examples(
            conversation_id=conversation_id,
            approved_by=approval_request.approved_by
        )
        
        logger.info(f"Conversation {conversation_id} approved by {approval_request.approved_by} using Supabase. Approved {approval_result.get('approved_count', 0)} examples.")
        
        return ApprovalResponse(
            conversation=FeedMeConversation(**updated_conversation),
            action="approved",
            timestamp=datetime.fromisoformat(approval_time.replace('Z', '+00:00'))
        )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error approving conversation {conversation_id} using Supabase: {e}")
        raise HTTPException(status_code=500, detail="Failed to approve conversation")


@router.post("/conversations/{conversation_id}/reject", response_model=ApprovalResponse, tags=["FeedMe"])
async def reject_conversation(conversation_id: int, rejection_request: RejectionRequest):
    """
    Reject a conversation
    
    Transitions the conversation from 'processed' to 'rejected' status and marks
    all associated examples as rejected (inactive for retrieval).
    
    Args:
        conversation_id: ID of the conversation to reject
        rejection_request: Rejection details including reviewer information and notes
        
    Returns:
        ApprovalResponse: Updated conversation and rejection details
        
    Raises:
        HTTPException: If conversation not found, not in processed state, or rejection fails
    """
    
    if not settings.feedme_enabled:
        raise HTTPException(status_code=503, detail="FeedMe service is currently disabled")
    
    try:
        # Check conversation exists using Supabase
        conversation = await supabase_client.get_conversation_by_id(conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        # Check approval status
        current_status = conversation.get('approval_status', 'pending')
        if current_status not in ['processed', 'pending', 'completed']:
            raise HTTPException(
                status_code=400, 
                detail=f"Conversation is in '{current_status}' status and cannot be rejected"
            )
        
        # Update conversation to rejected status using Supabase
        rejection_time = datetime.now(timezone.utc).isoformat()
        update_data = {
            'approval_status': 'rejected',
            'approved_by': rejection_request.rejected_by,  # Note: using approved_by field for rejected_by
            'rejected_at': rejection_time,
            'reviewer_notes': rejection_request.rejection_notes,  # ✅ FIXED: Use correct field name
            'updated_at': rejection_time
        }
        
        updated_conversation = await supabase_client.update_conversation(conversation_id, update_data)
        if not updated_conversation:
            raise HTTPException(status_code=500, detail="Failed to update conversation rejection status")
        
        # Mark all examples as rejected (inactive for retrieval) using Supabase
        examples_update_response = supabase_client.client.table('feedme_examples')\
            .update({
                'review_status': 'rejected',
                'reviewed_by': rejection_request.rejected_by,
                'reviewed_at': rejection_time,
                'is_active': False
            })\
            .eq('conversation_id', conversation_id)\
            .execute()
        
        rejected_count = len(examples_update_response.data) if examples_update_response.data else 0
        
        logger.info(f"Conversation {conversation_id} rejected by {rejection_request.rejected_by} using Supabase. Rejected {rejected_count} examples.")
        
        return ApprovalResponse(
            conversation=FeedMeConversation(**updated_conversation),
            action="rejected",
            timestamp=datetime.fromisoformat(rejection_time.replace('Z', '+00:00'))
        )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error rejecting conversation {conversation_id} using Supabase: {e}")
        raise HTTPException(status_code=500, detail="Failed to reject conversation")


@router.get("/approval/stats", response_model=ApprovalWorkflowStats, tags=["FeedMe"])
async def get_approval_workflow_stats():
    """
    Get approval workflow statistics
    
    Returns comprehensive statistics about the approval workflow including
    conversation counts by status, quality metrics, and processing times.
    
    Returns:
        ApprovalWorkflowStats: Complete workflow statistics
        
    Raises:
        HTTPException: If FeedMe service is disabled or stats retrieval fails
    """
    
    if not settings.feedme_enabled:
        raise HTTPException(status_code=503, detail="FeedMe service is currently disabled")
    
    try:
        # Get approval workflow statistics using Supabase
        stats_data = await supabase_client.get_approval_workflow_stats()
        
        # Extract conversation approval data
        conversation_approval = stats_data.get('conversation_approval', {})
        status_breakdown = conversation_approval.get('status_breakdown', {})
        
        # Map Supabase data to ApprovalWorkflowStats schema
        # Note: Some fields may not have direct mappings in current Supabase structure
        return ApprovalWorkflowStats(
            total_conversations=sum(status_breakdown.values()),
            pending_approval=status_breakdown.get('pending', 0),
            awaiting_review=status_breakdown.get('awaiting_review', 0),
            approved=status_breakdown.get('approved', 0),
            rejected=status_breakdown.get('rejected', 0),
            published=status_breakdown.get('published', 0),
            currently_processing=status_breakdown.get('processing', 0),
            processing_failed=status_breakdown.get('failed', 0),
            avg_quality_score=None,  # TODO: Calculate from examples if needed
            avg_processing_time_ms=None  # TODO: Calculate from processing times if needed
        )
            
    except Exception as e:
        logger.error(f"Error getting approval workflow stats using Supabase: {e}")
        raise HTTPException(status_code=500, detail="Failed to get approval workflow statistics")


@router.post("/conversations/bulk-approve", response_model=BulkApprovalResponse, tags=["FeedMe"])
async def bulk_approve_conversations(bulk_request: BulkApprovalRequest):
    """
    Bulk approve or reject multiple conversations
    
    Processes multiple conversations in a single operation, useful for
    batch approval workflows.
    
    Args:
        bulk_request: Bulk operation details including conversation IDs and action
        
    Returns:
        BulkApprovalResponse: Results of the bulk operation
        
    Raises:
        HTTPException: If FeedMe service is disabled or bulk operation fails
    """
    
    if not settings.feedme_enabled:
        raise HTTPException(status_code=503, detail="FeedMe service is currently disabled")
    
    successful = []
    failed = []
    
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2_extras.RealDictCursor) as cur:
                for conversation_id in bulk_request.conversation_ids:
                    try:
                        # Check conversation exists and is in processed state
                        cur.execute("""
                            SELECT id, approval_status FROM feedme_conversations 
                            WHERE id = %s
                        """, (conversation_id,))
                        
                        conversation = cur.fetchone()
                        if not conversation:
                            failed.append({
                                "conversation_id": conversation_id,
                                "error": "Conversation not found"
                            })
                            continue
                        
                        if conversation['approval_status'] not in ['processed', 'pending']:
                            failed.append({
                                "conversation_id": conversation_id,
                                "error": f"Conversation is in '{conversation['approval_status']}' status"
                            })
                            continue
                        
                        # Update conversation based on action
                        action_time = datetime.now(timezone.utc)
                        
                        if bulk_request.action == 'approve':
                            cur.execute("""
                                UPDATE feedme_conversations 
                                SET approval_status = %s, 
                                    approved_by = %s, 
                                    approved_at = %s,
                                    reviewer_notes = %s,
                                    updated_at = %s
                                WHERE id = %s
                            """, (
                                ApprovalStatus.APPROVED.value,
                                bulk_request.approved_by,
                                action_time,
                                bulk_request.reviewer_notes,
                                action_time,
                                conversation_id
                            ))
                            
                            # Mark examples as approved
                            cur.execute("""
                                UPDATE feedme_examples 
                                SET review_status = %s, 
                                    reviewed_by = %s,
                                    reviewed_at = %s,
                                    is_active = true
                                WHERE conversation_id = %s
                            """, (
                                ReviewStatus.APPROVED.value,
                                bulk_request.approved_by,
                                action_time,
                                conversation_id
                            ))
                            
                        else:  # reject
                            cur.execute("""
                                UPDATE feedme_conversations 
                                SET approval_status = %s, 
                                    approved_by = %s,
                                    rejected_at = %s,
                                    reviewer_notes = %s,
                                    updated_at = %s
                                WHERE id = %s
                            """, (
                                ApprovalStatus.REJECTED.value,
                                bulk_request.approved_by,
                                action_time,
                                bulk_request.reviewer_notes,
                                action_time,
                                conversation_id
                            ))
                            
                            # Mark examples as rejected
                            cur.execute("""
                                UPDATE feedme_examples 
                                SET review_status = %s, 
                                    reviewed_by = %s,
                                    reviewed_at = %s,
                                    is_active = false
                                WHERE conversation_id = %s
                            """, (
                                ReviewStatus.REJECTED.value,
                                bulk_request.approved_by,
                                action_time,
                                conversation_id
                            ))
                        
                        successful.append(conversation_id)
                        
                    except Exception as e:
                        failed.append({
                            "conversation_id": conversation_id,
                            "error": str(e)
                        })
                        continue
                
                # Commit all successful operations
                conn.commit()
                
                logger.info(f"Bulk {bulk_request.action} completed: {len(successful)} successful, {len(failed)} failed")
                
                return BulkApprovalResponse(
                    successful=successful,
                    failed=failed,
                    total_requested=len(bulk_request.conversation_ids),
                    total_successful=len(successful),
                    action_taken=bulk_request.action
                )
            
    except Exception as e:
        logger.error(f"Error in bulk approval operation: {e}")
        raise HTTPException(status_code=500, detail="Failed to complete bulk approval operation")


@router.post("/examples/{example_id}/review", response_model=ExampleReviewResponse, tags=["FeedMe"])
async def review_example(example_id: int, review_request: ExampleReviewRequest):
    """
    Review an individual example
    
    Allows reviewers to approve, reject, or edit individual examples
    within an approved conversation.
    
    Args:
        example_id: ID of the example to review
        review_request: Review details including status and optional edits
        
    Returns:
        ExampleReviewResponse: Updated example and review details
        
    Raises:
        HTTPException: If example not found or review fails
    """
    
    if not settings.feedme_enabled:
        raise HTTPException(status_code=503, detail="FeedMe service is currently disabled")
    
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2_extras.RealDictCursor) as cur:
                # Check example exists
                cur.execute("""
                    SELECT * FROM feedme_examples 
                    WHERE id = %s
                """, (example_id,))
                
                example = cur.fetchone()
                if not example:
                    raise HTTPException(status_code=404, detail="Example not found")
                
                # Prepare update fields
                update_fields = [
                    "review_status = %s",
                    "reviewed_by = %s", 
                    "reviewed_at = %s",
                    "updated_at = %s"
                ]
                params = [
                    review_request.review_status.value,
                    review_request.reviewed_by,
                    datetime.now(timezone.utc),
                    datetime.now(timezone.utc)
                ]
                
                # Add optional edits
                if review_request.question_text is not None:
                    update_fields.append("question_text = %s")
                    params.append(review_request.question_text)
                
                if review_request.answer_text is not None:
                    update_fields.append("answer_text = %s")
                    params.append(review_request.answer_text)
                
                if review_request.tags is not None:
                    update_fields.append("tags = %s")
                    params.append(review_request.tags)
                
                # Set active status based on review decision
                if review_request.review_status == ReviewStatus.APPROVED:
                    update_fields.append("is_active = true")
                elif review_request.review_status == ReviewStatus.REJECTED:
                    update_fields.append("is_active = false")
                
                # Add example ID for WHERE clause
                params.append(example_id)
                
                # Update example
                query = f"""
                    UPDATE feedme_examples 
                    SET {', '.join(update_fields)}
                    WHERE id = %s
                    RETURNING *
                """
                
                cur.execute(query, params)
                updated_example = cur.fetchone()
                conn.commit()
                
                logger.info(f"Example {example_id} reviewed by {review_request.reviewed_by}: {review_request.review_status.value}")
                
                return ExampleReviewResponse(
                    example=FeedMeExample(**dict(updated_example)),
                    action=review_request.review_status.value,
                    timestamp=datetime.now(timezone.utc)
                )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reviewing example {example_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to review example")


@router.get("/conversations/{conversation_id}/preview-examples", response_model=List[Dict[str, Any]], tags=["FeedMe"])
async def preview_extracted_examples(conversation_id: int):
    """
    Preview extracted Q&A examples before approval.
    
    This endpoint returns examples from the temporary table that haven't been approved yet.
    Human agents can review these examples before deciding which ones to approve.
    
    Args:
        conversation_id: ID of the conversation
        
    Returns:
        List of temporary examples with confidence scores and metadata
        
    Raises:
        HTTPException: If the FeedMe service is disabled (503), conversation not found (404),
                      or a database error occurs (500).
    """
    if not settings.feedme_enabled:
        raise HTTPException(status_code=503, detail="FeedMe service is currently disabled")
    
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2_extras.RealDictCursor) as cur:
                # Check if conversation exists
                cur.execute("SELECT id, processing_status FROM feedme_conversations WHERE id = %s", (conversation_id,))
                conversation = cur.fetchone()
                
                if not conversation:
                    raise HTTPException(status_code=404, detail="Conversation not found")
                
                # Get temporary examples
                cur.execute("""
                    SELECT 
                        id,
                        question_text,
                        answer_text,
                        context_before,
                        context_after,
                        confidence_score,
                        quality_score,
                        tags,
                        issue_type,
                        resolution_type,
                        extraction_method,
                        metadata,
                        created_at
                    FROM feedme_examples_temp
                    WHERE conversation_id = %s
                    ORDER BY confidence_score DESC
                """, (conversation_id,))
                
                examples = []
                for row in cur.fetchall():
                    examples.append({
                        'id': row['id'],
                        'question_text': row['question_text'],
                        'answer_text': row['answer_text'],
                        'context_before': row['context_before'],
                        'context_after': row['context_after'],
                        'confidence_score': row['confidence_score'],
                        'quality_score': row['quality_score'],
                        'tags': row['tags'] or [],
                        'issue_type': row['issue_type'],
                        'resolution_type': row['resolution_type'],
                        'extraction_method': row['extraction_method'],
                        'metadata': row['metadata'] or {},
                        'created_at': row['created_at'].isoformat() if row['created_at'] else None
                    })
                
                return examples
                
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error previewing examples for conversation {conversation_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/conversations/{conversation_id}/approve-examples", tags=["FeedMe"])
async def approve_conversation_examples(
    conversation_id: int,
    approval_data: Dict[str, Any] = Body(..., description="Approval data with selected example IDs")
):
    """
    Approve selected Q&A examples and move them to the main examples table.
    
    This endpoint allows human agents to approve specific examples or all examples
    from the temporary table. Approved examples are moved to the main table and
    become available for retrieval in agent responses.
    
    Args:
        conversation_id: ID of the conversation
        approval_data: Dict containing:
            - approved_by: ID/name of the approver
            - selected_example_ids: Optional list of specific example IDs to approve
                                  (if not provided, all examples will be approved)
            
    Returns:
        Dict with approval results
        
    Raises:
        HTTPException: If the FeedMe service is disabled (503), conversation not found (404),
                      or approval fails (500).
    """
    if not settings.feedme_enabled:
        raise HTTPException(status_code=503, detail="FeedMe service is currently disabled")
    
    approved_by = approval_data.get('approved_by')
    if not approved_by:
        raise HTTPException(status_code=400, detail="approved_by is required")
    
    selected_example_ids = approval_data.get('selected_example_ids')
    
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Check if conversation exists and has temp examples
                cur.execute(
                    "SELECT COUNT(*) as count FROM feedme_examples_temp WHERE conversation_id = %s",
                    (conversation_id,)
                )
                temp_count = cur.fetchone()[0]
                
                if temp_count == 0:
                    raise HTTPException(status_code=404, detail="No examples found for approval")
                
                # Call the approval function
                if selected_example_ids:
                    cur.execute(
                        "SELECT approve_conversation_examples(%s, %s, %s)",
                        (conversation_id, approved_by, selected_example_ids)
                    )
                else:
                    cur.execute(
                        "SELECT approve_conversation_examples(%s, %s)",
                        (conversation_id, approved_by)
                    )
                
                approved_count = cur.fetchone()[0]
                conn.commit()
                
                return {
                    "success": True,
                    "conversation_id": conversation_id,
                    "approved_examples": approved_count,
                    "approved_by": approved_by,
                    "approved_at": datetime.now(timezone.utc).isoformat(),
                    "approval_type": "selective" if selected_example_ids else "all"
                }
                
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error approving examples for conversation {conversation_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/conversations/{conversation_id}/reject-examples", tags=["FeedMe"])
async def reject_conversation_examples(
    conversation_id: int,
    rejection_data: Dict[str, Any] = Body(..., description="Rejection data")
):
    """
    Reject extracted Q&A examples and remove them from the temporary table.
    
    This endpoint allows human agents to reject examples that are not suitable
    for the knowledge base. Rejected examples are deleted from the temporary table.
    
    Args:
        conversation_id: ID of the conversation
        rejection_data: Dict containing:
            - rejected_by: ID/name of the reviewer
            - rejection_reason: Optional reason for rejection
            
    Returns:
        Dict with rejection results
        
    Raises:
        HTTPException: If the FeedMe service is disabled (503), conversation not found (404),
                      or rejection fails (500).
    """
    if not settings.feedme_enabled:
        raise HTTPException(status_code=503, detail="FeedMe service is currently disabled")
    
    rejected_by = rejection_data.get('rejected_by')
    if not rejected_by:
        raise HTTPException(status_code=400, detail="rejected_by is required")
    
    rejection_reason = rejection_data.get('rejection_reason')
    
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Check if conversation exists and has temp examples
                cur.execute(
                    "SELECT COUNT(*) as count FROM feedme_examples_temp WHERE conversation_id = %s",
                    (conversation_id,)
                )
                temp_count = cur.fetchone()[0]
                
                if temp_count == 0:
                    raise HTTPException(status_code=404, detail="No examples found for rejection")
                
                # Call the rejection function
                cur.execute(
                    "SELECT reject_conversation_examples(%s, %s, %s)",
                    (conversation_id, rejected_by, rejection_reason)
                )
                
                rejected_count = cur.fetchone()[0]
                conn.commit()
                
                return {
                    "success": True,
                    "conversation_id": conversation_id,
                    "rejected_examples": rejected_count,
                    "rejected_by": rejected_by,
                    "rejection_reason": rejection_reason,
                    "rejected_at": datetime.now(timezone.utc).isoformat()
                }
                
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error rejecting examples for conversation {conversation_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/conversations/{conversation_id}/summary", tags=["FeedMe"])
async def get_conversation_summary(conversation_id: int):
    """
    Get comprehensive summary of conversation processing status.
    
    This endpoint provides a complete overview of the conversation including
    processing status, approval status, and counts of temporary vs approved examples.
    
    Args:
        conversation_id: ID of the conversation
        
    Returns:
        Dict with comprehensive conversation summary
        
    Raises:
        HTTPException: If the FeedMe service is disabled (503), conversation not found (404),
                      or a database error occurs (500).
    """
    if not settings.feedme_enabled:
        raise HTTPException(status_code=503, detail="FeedMe service is currently disabled")
    
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2_extras.RealDictCursor) as cur:
                # Get comprehensive summary
                cur.execute("SELECT * FROM get_conversation_summary(%s)", (conversation_id,))
                result = cur.fetchone()
                
                if not result:
                    raise HTTPException(status_code=404, detail="Conversation not found")
                
                summary = dict(result)
                
                # Convert datetime objects to ISO strings
                for key in ['uploaded_at', 'processed_at', 'approved_at']:
                    if summary.get(key):
                        summary[key] = summary[key].isoformat()
                
                return summary
                
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting summary for conversation {conversation_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Folder Management API Endpoints

@router.get("/folders", response_model=FolderListResponse, tags=["FeedMe"])
async def list_folders():
    """
    Get all folders with conversation counts
    
    Returns:
        FolderListResponse: List of all folders with metadata and conversation counts
    """
    
    if not settings.feedme_enabled:
        logger.warning("FeedMe service is disabled")
        raise HTTPException(status_code=503, detail="FeedMe service is currently disabled")
    
    logger.info("Fetching folders list using Supabase...")
    
    try:
        # Get folders with stats using Supabase client
        folder_data = await supabase_client.get_folders_with_stats()
        
        # Convert to FeedMeFolder objects
        folders = []
        for folder_dict in folder_data:
            # Handle None folder case (No Folder)
            if folder_dict['id'] is None:
                continue  # Skip "No Folder" entry for now
            
            folders.append(FeedMeFolder(**folder_dict))
        
        logger.info(f"Found {len(folders)} folders using Supabase.")

        # Create default folder if none exist
        if not folders:
            logger.info("No folders found. Creating a default 'General' folder.")
            try:
                new_folder = await supabase_client.insert_folder(
                    name="General",
                    color="#0095ff", 
                    description="Default folder for conversations",
                    created_by="system"
                )
                new_folder['conversation_count'] = 0
                folders.append(FeedMeFolder(**new_folder))
                logger.info("Default 'General' folder created successfully.")
            except Exception as e:
                logger.error(f"Failed to create default folder: {e}")

        return FolderListResponse(
            folders=folders,
            total_count=len(folders)
        )
            
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.error(f"Unexpected error listing folders: {type(e).__name__}: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=500, 
            detail="An unexpected internal server error occurred. Please try again later."
        )


@router.post("/folders", response_model=FeedMeFolder, tags=["FeedMe"])
async def create_folder(folder_data: FolderCreate):
    """
    Create a new folder for organizing conversations
    
    Args:
        folder_data: Folder creation data including name, color, description
        
    Returns:
        FeedMeFolder: The created folder with metadata
    """
    
    if not settings.feedme_enabled:
        raise HTTPException(status_code=503, detail="FeedMe service is currently disabled")
    
    try:
        # Check if folder name already exists using Supabase
        existing_folders = supabase_client.client.table('feedme_folders')\
            .select('id')\
            .eq('name', folder_data.name)\
            .execute()
        
        if existing_folders.data and len(existing_folders.data) > 0:
            raise HTTPException(status_code=409, detail="Folder name already exists")
        
        # Create folder using Supabase client
        try:
            folder_result = await supabase_client.insert_folder(
                name=folder_data.name,
                color=folder_data.color,
                description=folder_data.description,
                created_by=folder_data.created_by
            )
        except Exception as create_error:
            logger.error(f"Supabase insert_folder failed: {create_error}")
            raise HTTPException(status_code=500, detail=f"Database error: {str(create_error)}")
        
        # Add conversation_count for consistency with schema
        folder_result['conversation_count'] = 0  # New folder has no conversations
        
        logger.info(f"Created folder using Supabase: {folder_data.name}")
        return FeedMeFolder(**folder_result)
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating folder using Supabase: {e}")
        raise HTTPException(status_code=500, detail="Failed to create folder")


@router.put("/folders/{folder_id}", response_model=FeedMeFolder, tags=["FeedMe"])
async def update_folder(folder_id: int, folder_data: FolderUpdate):
    """
    Update an existing folder's name, color, or description
    
    Args:
        folder_id: ID of the folder to update
        folder_data: Updated folder data
        
    Returns:
        FeedMeFolder: The updated folder with metadata
    """
    
    if not settings.feedme_enabled:
        raise HTTPException(status_code=503, detail="FeedMe service is currently disabled")
    
    try:
        # Check folder exists using Supabase
        existing_folder_response = supabase_client.client.table('feedme_folders')\
            .select('*')\
            .eq('id', folder_id)\
            .execute()
        
        if not existing_folder_response.data or len(existing_folder_response.data) == 0:
            raise HTTPException(status_code=404, detail="Folder not found")
        
        existing_folder = existing_folder_response.data[0]
        
        # Check for name conflicts if name is being updated
        if folder_data.name and folder_data.name != existing_folder['name']:
            name_conflict_response = supabase_client.client.table('feedme_folders')\
                .select('id')\
                .eq('name', folder_data.name)\
                .neq('id', folder_id)\
                .execute()
            
            if name_conflict_response.data and len(name_conflict_response.data) > 0:
                raise HTTPException(status_code=409, detail="Folder name already exists")
        
        # Build update data dynamically
        update_data = {}
        
        if folder_data.name is not None:
            update_data['name'] = folder_data.name
        
        if folder_data.color is not None:
            update_data['color'] = folder_data.color
        
        if folder_data.description is not None:
            update_data['description'] = folder_data.description
        
        if not update_data:
            # No fields to update, get conversation count and return existing folder
            count_response = supabase_client.client.table('feedme_conversations')\
                .select('id', count='exact')\
                .eq('folder_id', folder_id)\
                .execute()
            
            existing_folder['conversation_count'] = count_response.count or 0
            return FeedMeFolder(**existing_folder)
        
        # Update folder using Supabase client
        updated_folder = await supabase_client.update_folder(folder_id, update_data)
        if not updated_folder:
            raise HTTPException(status_code=500, detail="Failed to update folder")
        
        # Get conversation count
        count_response = supabase_client.client.table('feedme_conversations')\
            .select('id', count='exact')\
            .eq('folder_id', folder_id)\
            .execute()
        
        updated_folder['conversation_count'] = count_response.count or 0
        
        logger.info(f"Updated folder {folder_id} using Supabase")
        return FeedMeFolder(**updated_folder)
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating folder {folder_id} using Supabase: {e}")
        raise HTTPException(status_code=500, detail="Failed to update folder")


@router.delete("/folders/{folder_id}", tags=["FeedMe"])
async def delete_folder(folder_id: int, move_conversations_to: Optional[int] = Query(None, description="Folder ID to move conversations to, or null to remove from folders")):
    """
    Delete a folder and optionally move its conversations to another folder
    
    Args:
        folder_id: ID of the folder to delete
        move_conversations_to: Optional folder ID to move conversations to
        
    Returns:
        dict: Deletion summary with conversation move details
    """
    
    if not settings.feedme_enabled:
        raise HTTPException(status_code=503, detail="FeedMe service is currently disabled")
    
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2_extras.RealDictCursor) as cur:
                # Check folder exists
                cur.execute("SELECT * FROM feedme_folders WHERE id = %s", (folder_id,))
                folder = cur.fetchone()
                if not folder:
                    raise HTTPException(status_code=404, detail="Folder not found")
                
                # Count conversations in this folder
                cur.execute("""
                    SELECT COUNT(*) as count 
                    FROM feedme_conversations 
                    WHERE folder_id = %s AND is_active = true
                """, (folder_id,))
                count_result = cur.fetchone()
                conversation_count = count_result['count'] if count_result else 0
                
                # Validate target folder if specified
                if move_conversations_to is not None:
                    cur.execute("SELECT id FROM feedme_folders WHERE id = %s", (move_conversations_to,))
                    if not cur.fetchone():
                        raise HTTPException(status_code=404, detail="Target folder not found")
                
                # Move conversations if needed
                if conversation_count > 0:
                    cur.execute("""
                        UPDATE feedme_conversations 
                        SET folder_id = %s, updated_at = NOW()
                        WHERE folder_id = %s
                    """, (move_conversations_to, folder_id))
                
                # Delete the folder
                cur.execute("DELETE FROM feedme_folders WHERE id = %s", (folder_id,))
                conn.commit()
                
                logger.info(f"Deleted folder {folder_id}, moved {conversation_count} conversations")
                
                return {
                    "folder_id": folder_id,
                    "folder_name": folder['name'],
                    "conversations_moved": conversation_count,
                    "moved_to_folder_id": move_conversations_to,
                    "message": f"Folder '{folder['name']}' deleted successfully"
                }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting folder {folder_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete folder")


@router.post("/folders/assign", tags=["FeedMe"])
async def assign_conversations_to_folder(assign_request: AssignFolderRequest):
    """
    Assign multiple conversations to a folder or remove them from folders
    
    Args:
        assign_request: Assignment details including folder_id and conversation_ids
        
    Returns:
        dict: Assignment summary with success/failure details
    """
    
    if not settings.feedme_enabled:
        raise HTTPException(status_code=503, detail="FeedMe service is currently disabled")
    
    try:
        supabase_client = get_supabase_client()
        
        # Validate folder exists if folder_id is provided
        folder_name = None
        if assign_request.folder_id is not None:
            folder_response = supabase_client.client.table('feedme_folders')\
                .select('name')\
                .eq('id', assign_request.folder_id)\
                .execute()
            
            if not folder_response.data:
                raise HTTPException(status_code=404, detail="Folder not found")
            folder_name = folder_response.data[0]['name']
        
        # Validate conversations exist and are active
        if assign_request.conversation_ids:
            conversations_response = supabase_client.client.table('feedme_conversations')\
                .select('id')\
                .in_('id', assign_request.conversation_ids)\
                .eq('is_active', True)\
                .execute()
            
            existing_ids = [row['id'] for row in conversations_response.data]
            missing_ids = set(assign_request.conversation_ids) - set(existing_ids)
            
            if missing_ids:
                raise HTTPException(status_code=404, detail=f"Conversations not found: {list(missing_ids)}")
            
            # Update folder assignments using Supabase
            await supabase_client.bulk_assign_conversations_to_folder(
                conversation_ids=assign_request.conversation_ids,
                folder_id=assign_request.folder_id
            )
            
            updated_count = len(existing_ids)
            action = f"assigned to folder '{folder_name}'" if folder_name else "removed from folders"
            logger.info(f"Successfully {action} {updated_count} conversations")
            
            return {
                "folder_id": assign_request.folder_id,
                "folder_name": folder_name,
                "conversation_ids": assign_request.conversation_ids,
                "updated_count": updated_count,
                "action": action,
                "message": f"Successfully {action} {updated_count} conversations"
            }
        else:
            return {
                "folder_id": assign_request.folder_id,
                "folder_name": folder_name,
                "conversation_ids": [],
                "updated_count": 0,
                "action": "no conversations provided",
                "message": "No conversations were provided for assignment"
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error assigning conversations to folder: {e}")
        raise HTTPException(status_code=500, detail="Failed to assign conversations to folder")


@router.get("/folders/{folder_id}/conversations", response_model=ConversationListResponse, tags=["FeedMe"])
async def list_folder_conversations(
    folder_id: int,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Number of items per page")
):
    """
    Get all conversations in a specific folder
    
    Args:
        folder_id: ID of the folder
        page: Page number for pagination
        page_size: Number of conversations per page
        
    Returns:
        ConversationListResponse: Paginated list of conversations in the folder
    """
    
    if not settings.feedme_enabled:
        raise HTTPException(status_code=503, detail="FeedMe service is currently disabled")
    
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2_extras.RealDictCursor) as cur:
                # Validate folder exists
                cur.execute("SELECT name FROM feedme_folders WHERE id = %s", (folder_id,))
                folder = cur.fetchone()
                if not folder:
                    raise HTTPException(status_code=404, detail="Folder not found")
                
                # Count total conversations in folder
                cur.execute("""
                    SELECT COUNT(*) as count 
                    FROM feedme_conversations 
                    WHERE folder_id = %s AND is_active = true
                """, (folder_id,))
                count_result = cur.fetchone()
                total_count = count_result['count'] if count_result else 0
                
                # Get paginated conversations
                offset = (page - 1) * page_size
                cur.execute("""
                    SELECT * FROM feedme_conversations 
                    WHERE folder_id = %s AND is_active = true
                    ORDER BY updated_at DESC
                    LIMIT %s OFFSET %s
                """, (folder_id, page_size, offset))
                
                conversation_rows = cur.fetchall()
                conversations = []
                
                for row in conversation_rows:
                    # Convert to the expected response format
                    conversation_dict = dict(row)
                    # Map database fields to response model fields
                    response_conversation = {
                        'id': conversation_dict['id'],
                        'title': conversation_dict['title'],
                        'processing_status': conversation_dict.get('processing_status', 'pending'),
                        'total_examples': conversation_dict.get('total_examples', 0),
                        'created_at': conversation_dict['created_at'].isoformat(),
                        'metadata': conversation_dict.get('metadata', {})
                    }
                    conversations.append(response_conversation)
                
                return ConversationListResponse(
                    conversations=conversations,
                    total_count=total_count,
                    page=page,
                    page_size=page_size,
                    has_next=offset + len(conversations) < total_count
                )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing conversations for folder {folder_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to list folder conversations")


# =====================================================
# SUPABASE INTEGRATION ENDPOINTS
# =====================================================

@router.post("/conversations/{conversation_id}/examples/approve", response_model=Dict[str, Any], tags=["FeedMe"])
async def approve_conversation_examples_supabase(
    conversation_id: int,
    approval_request: SupabaseApprovalRequest
):
    """
    Approve conversation examples in Supabase
    
    This endpoint approves selected examples from a conversation directly in Supabase.
    
    Args:
        conversation_id: ID of the conversation containing examples
        approval_request: Approval details including approved_by and optional example_ids
        
    Returns:
        Dict containing approval summary
    """
    
    if not settings.feedme_enabled:
        raise HTTPException(status_code=503, detail="FeedMe service is currently disabled")
    
    try:
        supabase_client = get_supabase_client()
        
        # Get conversation from Supabase
        conversation = await supabase_client.get_conversation_by_id(conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        # Get examples to approve
        example_ids = approval_request.example_ids
        
        if example_ids:
            # Approve specific examples
            approved_examples = await supabase_client.approve_examples(
                example_ids=example_ids,
                approved_by=approval_request.approved_by
            )
            
            # Update conversation status
            await supabase_client.update_conversation(
                conversation_id=conversation_id,
                updates={'approval_status': 'approved'}
            )
            
            approval_result = {
                "conversation_id": conversation_id,
                "approved_count": len(approved_examples),
                "approved_by": approval_request.approved_by,
                "timestamp": datetime.utcnow().isoformat()
            }
        else:
            # Approve all examples from conversation (this method includes conversation status update)
            approval_result = await supabase_client.approve_conversation_examples(
                conversation_id=conversation_id,
                approved_by=approval_request.approved_by
            )
        
        if approval_result.get("approved_count", 0) == 0:
            raise HTTPException(
                status_code=404, 
                detail="No active examples found for approval"
            )
        
        logger.info(f"Successfully approved {approval_result['approved_count']} examples in conversation {conversation_id}")
        
        return approval_result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error approving conversation examples: {e}")
        raise HTTPException(status_code=500, detail="Failed to approve examples")


@router.put("/folders/{folder_id}/assign", response_model=Dict[str, Any], tags=["FeedMe"])
async def assign_conversations_to_folder_supabase(
    folder_id: int,
    assign_request: AssignFolderRequest,
    background_tasks: BackgroundTasks
):
    """
    Assign conversations to a folder with Supabase sync
    
    This endpoint assigns multiple conversations to a folder and syncs the
    changes to Supabase for consistent folder organization.
    
    Args:
        folder_id: Target folder ID
        assign_request: Request containing conversation IDs to assign
        background_tasks: Background task handler for Supabase sync
        
    Returns:
        Dict containing assignment summary
    """
    
    if not settings.feedme_enabled:
        raise HTTPException(status_code=503, detail="FeedMe service is currently disabled")
    
    try:
        supabase_client = get_supabase_client()
        
        # Validate folder exists in Supabase
        folder_response = supabase_client.client.table('feedme_folders')\
            .select('*')\
            .eq('id', folder_id)\
            .execute()
        
        if not folder_response.data:
            raise HTTPException(status_code=404, detail="Folder not found")
        
        folder = folder_response.data[0]
        
        # Update conversations in Supabase
        await supabase_client.bulk_assign_conversations_to_folder(
            conversation_ids=assign_request.conversation_ids,
            folder_id=folder_id
        )
        
        # Get updated conversations to return count
        conversation_response = supabase_client.client.table('feedme_conversations')\
            .select('id')\
            .in_('id', assign_request.conversation_ids)\
            .eq('folder_id', folder_id)\
            .execute()
        
        updated_count = len(conversation_response.data)
        updated_ids = [row['id'] for row in conversation_response.data]
        
        logger.info(f"Successfully assigned {updated_count} conversations to folder '{folder['name']}'")
        
        return {
            "folder_id": folder_id,
            "folder_name": folder['name'],
            "assigned_count": updated_count,
            "conversation_ids": updated_ids,
            "message": f"Successfully assigned {updated_count} conversations to folder '{folder['name']}'"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error assigning conversations to folder: {e}")
        raise HTTPException(status_code=500, detail="Failed to assign conversations")


# Supabase-enabled Folder Management Endpoints

@router.post("/folders/create", response_model=Dict[str, Any], tags=["FeedMe"])
async def create_folder_supabase(
    folder_data: FolderCreate
):
    """
    Create a new folder using Supabase
    
    Args:
        folder_data: Folder creation data
        
    Returns:
        Dict with folder info
    """
    
    if not settings.feedme_enabled:
        raise HTTPException(status_code=503, detail="FeedMe service is currently disabled")
    
    try:
        supabase_client = get_supabase_client()
        
        # Check if folder name already exists
        existing_folder_response = supabase_client.client.table('feedme_folders')\
            .select('id')\
            .eq('name', folder_data.name)\
            .execute()
        
        if existing_folder_response.data:
            raise HTTPException(status_code=409, detail="Folder name already exists")
        
        # Create folder in Supabase
        created_folder = await supabase_client.insert_folder(
            name=folder_data.name,
            color=folder_data.color,
            description=folder_data.description,
            created_by=folder_data.created_by
        )
        
        # Add conversation_count field for compatibility
        created_folder['conversation_count'] = 0
        
        logger.info(f"Successfully created folder: {folder_data.name} (ID: {created_folder['id']})")
        
        return {
            "folder": FeedMeFolder(**created_folder),
            "message": f"Successfully created folder '{folder_data.name}'"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating folder: {e}")
        raise HTTPException(status_code=500, detail="Failed to create folder")


@router.put("/folders/{folder_id}/update", response_model=Dict[str, Any], tags=["FeedMe"])
async def update_folder_supabase(
    folder_id: int,
    folder_data: FolderUpdate,
    background_tasks: BackgroundTasks
):
    """
    Update folder with Supabase synchronization
    
    Updates folder in local database and syncs to Supabase in background.
    
    Args:
        folder_id: ID of folder to update
        folder_data: Update data
        
    Returns:
        Dict with updated folder info and sync status
    """
    
    if not settings.feedme_enabled:
        raise HTTPException(status_code=503, detail="FeedMe service is currently disabled")
    
    try:
        updated_folder = None
        
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2_extras.RealDictCursor) as cur:
                # Check if folder exists
                cur.execute("SELECT * FROM feedme_folders WHERE id = %s", (folder_id,))
                folder_row = cur.fetchone()
                if not folder_row:
                    raise HTTPException(status_code=404, detail="Folder not found")
                
                # Check if new name conflicts with existing folder
                if folder_data.name:
                    cur.execute("SELECT id FROM feedme_folders WHERE name = %s AND id != %s", 
                              (folder_data.name, folder_id))
                    if cur.fetchone():
                        raise HTTPException(status_code=409, detail="Folder name already exists")
                
                # Build update query
                update_fields = []
                update_values = []
                
                if folder_data.name is not None:
                    update_fields.append("name = %s")
                    update_values.append(folder_data.name)
                
                if folder_data.color is not None:
                    update_fields.append("color = %s")
                    update_values.append(folder_data.color)
                
                if folder_data.description is not None:
                    update_fields.append("description = %s")
                    update_values.append(folder_data.description)
                
                update_fields.append("updated_at = NOW()")
                
                # Update folder
                update_values.append(folder_id)
                cur.execute(f"""
                    UPDATE feedme_folders 
                    SET {', '.join(update_fields)}
                    WHERE id = %s
                    RETURNING *
                """, update_values)
                
                updated_row = cur.fetchone()
                conn.commit()
                
                # Get conversation count
                cur.execute("SELECT COUNT(*) as count FROM feedme_conversations WHERE folder_id = %s", (folder_id,))
                count_row = cur.fetchone()
                
                updated_folder = dict(updated_row)
                updated_folder['conversation_count'] = count_row['count'] if count_row else 0
                
                logger.info(f"Updated folder locally: {folder_id}")
        
        # Schedule Supabase sync in background
        async def sync_folder_update_to_supabase():
            try:
                supabase_client = get_supabase_client()
                
                # Update folder in Supabase
                await supabase_client.update_folder(
                    folder_id=folder_id,
                    name=folder_data.name,
                    color=folder_data.color,
                    description=folder_data.description
                )
                
                logger.info(f"Successfully synced folder update {folder_id} to Supabase")
                
            except Exception as e:
                logger.error(f"Failed to sync folder update to Supabase: {e}")
                # Don't fail the entire operation if Supabase sync fails
        
        background_tasks.add_task(sync_folder_update_to_supabase)
        
        return {
            "folder": FeedMeFolder(**updated_folder),
            "supabase_sync": "pending",
            "message": f"Successfully updated folder. Supabase sync in progress."
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating folder: {e}")
        raise HTTPException(status_code=500, detail="Failed to update folder")


@router.delete("/folders/{folder_id}/remove", response_model=Dict[str, Any], tags=["FeedMe"])
async def delete_folder_supabase(
    folder_id: int,
    move_conversations_to: Optional[int] = Query(None, description="Folder ID to move conversations to")
):
    """
    Delete folder using Supabase
    
    Deletes folder and optionally moves conversations to another folder.
    
    Args:
        folder_id: ID of folder to delete
        move_conversations_to: Optional folder ID to move conversations to
        
    Returns:
        Dict with deletion status
    """
    
    if not settings.feedme_enabled:
        raise HTTPException(status_code=503, detail="FeedMe service is currently disabled")
    
    try:
        supabase_client = get_supabase_client()
        
        # Check if folder exists and get its info
        folder_response = supabase_client.client.table('feedme_folders')\
            .select('*')\
            .eq('id', folder_id)\
            .execute()
        
        if not folder_response.data:
            raise HTTPException(status_code=404, detail="Folder not found")
        
        folder = folder_response.data[0]
        deleted_folder_name = folder['name']
        
        # Get conversations in this folder
        conversations_response = supabase_client.client.table('feedme_conversations')\
            .select('id')\
            .eq('folder_id', folder_id)\
            .execute()
        
        conversation_ids = [conv['id'] for conv in conversations_response.data]
        conversation_count = len(conversation_ids)
        
        # Handle conversation reassignment if there are conversations
        if conversation_count > 0:
            if move_conversations_to is not None:
                # Verify target folder exists
                folder_exists = await supabase_client.validate_folder_exists(move_conversations_to)
                if not folder_exists:
                    raise HTTPException(status_code=404, detail="Target folder not found")
            
            # Move conversations (to target folder or remove folder assignment)
            await supabase_client.move_conversations_to_folder(
                conversation_ids=conversation_ids,
                target_folder_id=move_conversations_to
            )
        
        # Delete the folder
        await supabase_client.delete_folder(folder_id=folder_id)
        
        logger.info(f"Successfully deleted folder {folder_id} ({deleted_folder_name}) with {conversation_count} conversations")
        
        return {
            "folder_id": folder_id,
            "folder_name": deleted_folder_name,
            "conversations_affected": conversation_count,
            "conversations_moved_to": move_conversations_to,
            "message": f"Successfully deleted folder '{deleted_folder_name}'"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting folder: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete folder")


@router.delete("/examples/{example_id}", response_model=Dict[str, Any], tags=["FeedMe"])
async def delete_example(example_id: int):
    """
    Delete a specific Q&A example from Supabase.
    
    This endpoint allows for granular deletion of individual Q&A examples
    while preserving the conversation and other examples.
    
    Args:
        example_id: ID of the example to delete
        
    Returns:
        Dict with deletion confirmation and example details
        
    Raises:
        HTTPException: If service disabled (503), example not found (404), or deletion fails (500)
    """
    
    if not settings.feedme_enabled:
        raise HTTPException(status_code=503, detail="FeedMe service is currently disabled")
    
    try:
        supabase_client = get_supabase_client()
        
        # Check if example exists and get details
        example = await supabase_client.get_example_with_conversation(example_id)
        if not example:
            raise HTTPException(status_code=404, detail="Example not found")
        
        # Delete the example from Supabase
        success = await supabase_client.delete_example(example_id)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete example")
        
        # Update the conversation's total_examples count
        await supabase_client.update_conversation_example_count(example['conversation_id'])
        
        logger.info(f"Successfully deleted example {example_id} from conversation {example['conversation_id']}")
        
        return {
            "example_id": example_id,
            "conversation_id": example['conversation_id'],
            "conversation_title": example.get('conversation_title', 'Unknown'),
            "question_preview": example['question_text'][:100] + "..." if len(example['question_text']) > 100 else example['question_text'],
            "message": f"Successfully deleted Q&A example from conversation '{example.get('conversation_title', 'Unknown')}'"
        }
                
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete example {example_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete example")

