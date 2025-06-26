"""
FeedMe API Endpoints

API endpoints for customer support transcript ingestion, processing, and management.
Provides functionality for uploading transcripts, managing conversations, and searching examples.
"""

import logging
import os
from typing import List, Optional, Dict, Any
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form, Query, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import asyncio
import io

from app.core.settings import settings
from app.feedme.schemas import (
    FeedMeConversation,
    FeedMeExample,
    ConversationCreate,
    ConversationUpdate,
    ExampleCreate,
    ExampleUpdate,
    TranscriptUploadRequest,
    ProcessingStatus,
    FeedMeSearchResult,
    ConversationListResponse,
    ExampleListResponse,
    ProcessingStatusResponse,
    SearchQuery,
    SearchResponse,
    ConversationStats,
    AnalyticsResponse,
    # Phase 3: Versioning schemas
    ConversationVersion,
    VersionListResponse,
    VersionDiff,
    ConversationEditRequest,
    ConversationRevertRequest,
    EditResponse,
    RevertResponse
)

# Import database utilities
from app.db.connection_manager import get_connection_manager
from app.db.embedding_utils import get_embedding_model
import psycopg2
import psycopg2.extras as psycopg2_extras
logger = logging.getLogger(__name__)
router = APIRouter()

# Database connection helper
def get_db_connection():
    """Get a database connection from the connection manager"""
    manager = get_connection_manager()
    return manager.get_connection(cursor_factory=psycopg2_extras.RealDictCursor)

# Database helper functions

async def get_conversation_by_id(conversation_id: int) -> Optional[FeedMeConversation]:
    """
    Retrieve a conversation record from the database by its unique ID.
    
    Parameters:
        conversation_id (int): The unique identifier of the conversation to retrieve.
    
    Returns:
        Optional[FeedMeConversation]: The conversation object if found, otherwise None.
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2_extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM feedme_conversations WHERE id = %s
                """, (conversation_id,))
                row = cur.fetchone()
                if row:
                    return FeedMeConversation(**dict(row))
                return None
    except Exception as e:
        logger.error(f"Error fetching conversation {conversation_id}: {e}")
        return None


async def create_conversation_in_db(conversation_data: ConversationCreate) -> FeedMeConversation:
    """
    Inserts a new conversation record into the database using the provided conversation data.
    
    Parameters:
    	conversation_data (ConversationCreate): The data required to create a new conversation, including title, original filename, transcript content, metadata, and uploader.
    
    Returns:
    	FeedMeConversation: The newly created conversation record.
    
    Raises:
    	HTTPException: If the database operation fails, an HTTP 500 error is raised with details.
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2_extras.RealDictCursor) as cur:
                cur.execute("""
                    INSERT INTO feedme_conversations 
                    (title, original_filename, raw_transcript, metadata, uploaded_by)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING *
                """, (
                    conversation_data.title,
                    conversation_data.original_filename,
                    conversation_data.raw_transcript,
                    psycopg2.extras.Json(conversation_data.metadata),
                    conversation_data.uploaded_by
                ))
                row = cur.fetchone()
                conn.commit()
                return FeedMeConversation(**dict(row))
    except Exception as e:
        logger.error(f"Error creating conversation: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create conversation: {str(e)}")


async def update_conversation_in_db(conversation_id: int, update_data: ConversationUpdate) -> Optional[FeedMeConversation]:
    """
    Updates specified fields of a conversation record in the database and returns the updated conversation.
    
    If no fields are provided for update, retrieves and returns the existing conversation. Updates the `updated_at` timestamp on modification.
    
    Parameters:
        conversation_id (int): The ID of the conversation to update.
        update_data (ConversationUpdate): Fields to update in the conversation.
    
    Returns:
        FeedMeConversation or None: The updated conversation object if found, otherwise None.
    
    Raises:
        HTTPException: If a database error occurs during the update.
    """
    try:
        # Build dynamic update query
        update_fields = []
        values = []
        
        if update_data.title is not None:
            update_fields.append("title = %s")
            values.append(update_data.title)
        
        if update_data.metadata is not None:
            update_fields.append("metadata = %s")
            values.append(psycopg2.extras.Json(update_data.metadata))
        
        if update_data.processing_status is not None:
            update_fields.append("processing_status = %s")
            values.append(update_data.processing_status.value)
        
        if update_data.error_message is not None:
            update_fields.append("error_message = %s")
            values.append(update_data.error_message)
        
        if update_data.total_examples is not None:
            update_fields.append("total_examples = %s")
            values.append(update_data.total_examples)
        
        if not update_fields:
            # No fields to update
            return await get_conversation_by_id(conversation_id)
        
        # Add updated_at timestamp
        update_fields.append("updated_at = NOW()")
        values.append(conversation_id)
        
        query = f"""
            UPDATE feedme_conversations 
            SET {', '.join(update_fields)}
            WHERE id = %s
            RETURNING *
        """
        
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2_extras.RealDictCursor) as cur:
                cur.execute(query, values)
                row = cur.fetchone()
                conn.commit()
                
                if row:
                    return FeedMeConversation(**dict(row))
                return None
                
    except Exception as e:
        logger.error(f"Error updating conversation {conversation_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update conversation: {str(e)}")


# API Endpoints

@router.post("/conversations/upload", response_model=FeedMeConversation, tags=["FeedMe"])
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
        # Create conversation in database
        conversation = await create_conversation_in_db(conversation_data)
        
        # Schedule background processing if auto_process is enabled
        async_processing_failed = False
        if auto_process and settings.feedme_async_processing:
            try:
                # Import Celery task and trigger async processing
                from app.feedme.tasks import process_transcript
                
                # Start async processing task
                task = process_transcript.delay(conversation.id, uploaded_by)
                
                # Update conversation with task ID and processing status
                await update_conversation_in_db(
                    conversation.id,
                    ConversationUpdate(
                        processing_status=ProcessingStatus.PROCESSING,
                        metadata={**conversation.metadata, "task_id": task.id}
                    )
                )
                logger.info(f"Started async processing for conversation {conversation.id}, task_id={task.id}")
                
            except ImportError as e:
                logger.warning(f"Celery not available for async processing: {e}. Falling back to manual processing.")
                async_processing_failed = True
            except Exception as e:
                logger.error(f"Failed to start async processing: {e}. Falling back to manual processing.")
                async_processing_failed = True
            
        if auto_process and (not settings.feedme_async_processing or async_processing_failed):
            # Async processing disabled or failed, set to pending for manual processing
            await update_conversation_in_db(
                conversation.id,
                ConversationUpdate(processing_status=ProcessingStatus.PENDING)
            )
            if async_processing_failed:
                logger.info(f"Set conversation {conversation.id} to pending (async processing failed, fallback to manual)")
            else:
                logger.info(f"Set conversation {conversation.id} to pending (async processing disabled)")
        
        logger.info(f"Successfully uploaded transcript: conversation_id={conversation.id}, title='{title}'")
        
        # Return appropriate response based on processing mode
        if auto_process and settings.feedme_async_processing and not async_processing_failed:
            # Return 202 Accepted for async processing
            return JSONResponse(
                status_code=202,
                content={
                    **conversation.model_dump(mode='json'),
                    "message": "Transcript uploaded successfully. Processing started in background.",
                    "processing_mode": "async"
                }
            )
        else:
            # Return 200 OK for synchronous or manual processing
            # Use model_dump with mode='json' to properly serialize datetime objects
            response_data = conversation.model_dump(mode='json')
            if async_processing_failed:
                response_data["message"] = "Transcript uploaded successfully. Async processing unavailable, set to manual processing."
                response_data["processing_mode"] = "manual_fallback"
            elif not auto_process:
                response_data["message"] = "Transcript uploaded successfully. Auto-processing disabled."
                response_data["processing_mode"] = "manual"
            else:
                response_data["message"] = "Transcript uploaded successfully. Async processing disabled, set to manual processing."
                response_data["processing_mode"] = "manual"
                
            return JSONResponse(status_code=200, content=response_data)
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except psycopg2.Error as e:
        logger.error(f"Database error during upload: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error uploading transcript: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to upload transcript: {str(e)}")


@router.get("/conversations", response_model=ConversationListResponse, tags=["FeedMe"])
async def list_conversations(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Number of items per page"),
    status: Optional[ProcessingStatus] = Query(None, description="Filter by processing status"),
    uploaded_by: Optional[str] = Query(None, description="Filter by uploader")
):
    """
    Retrieve a paginated list of conversations with optional filtering by processing status and uploader.
    
    Parameters:
        page (int): The page number to retrieve (1-based).
        page_size (int): The number of conversations per page.
        status (Optional[ProcessingStatus]): Filter conversations by their processing status.
        uploaded_by (Optional[str]): Filter conversations by the uploader's identifier.
    
    Returns:
        ConversationListResponse: A paginated response containing the list of conversations, total count, current page, page size, and a flag indicating if more pages are available.
    
    Raises:
        HTTPException: If the FeedMe service is disabled (503) or if a database error occurs (500).
    """
    
    if not settings.feedme_enabled:
        raise HTTPException(status_code=503, detail="FeedMe service is currently disabled")
    
    try:
        with get_db_connection() as conn:
            # Build query with filters
            conditions = []
            params = []
            
            if status:
                conditions.append("processing_status = %s")
                params.append(status.value)
            
            if uploaded_by:
                conditions.append("uploaded_by = %s")
                params.append(uploaded_by)
            
            where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
            
            # Count total items
            count_query = f"SELECT COUNT(*) as count FROM feedme_conversations{where_clause}"
            
            # Get paginated results
            offset = (page - 1) * page_size
            data_query = f"""
                SELECT * FROM feedme_conversations{where_clause}
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
            """
            
            with conn.cursor(cursor_factory=psycopg2_extras.RealDictCursor) as cur:
                # Get total count
                cur.execute(count_query, params)
                count_result = cur.fetchone()
                total_count = count_result['count'] if count_result else 0
                
                # Get paginated data
                cur.execute(data_query, params + [page_size, offset])
                rows = cur.fetchall()
                
                conversations = [FeedMeConversation(**dict(row)) for row in rows]
                
                return ConversationListResponse(
                    conversations=conversations,
                    total_count=total_count,
                    page=page,
                    page_size=page_size,
                    has_next=offset + len(conversations) < total_count
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


@router.delete("/conversations/{conversation_id}", tags=["FeedMe"])
async def delete_conversation(conversation_id: int):
    """
    Deletes a conversation and all associated examples from the database.
    
    Raises:
        HTTPException: If the FeedMe service is disabled (503), the conversation does not exist (404), or deletion fails (500).
    
    Returns:
        dict: A message confirming successful deletion.
    """
    
    if not settings.feedme_enabled:
        raise HTTPException(status_code=503, detail="FeedMe service is currently disabled")
    
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Check if conversation exists
                cur.execute("SELECT id FROM feedme_conversations WHERE id = %s", (conversation_id,))
                if not cur.fetchone():
                    raise HTTPException(status_code=404, detail="Conversation not found")
                
                # Delete conversation (cascade will delete examples)
                cur.execute("DELETE FROM feedme_conversations WHERE id = %s", (conversation_id,))
                conn.commit()
                
                logger.info(f"Deleted conversation {conversation_id}")
                return {"message": "Conversation deleted successfully"}
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting conversation {conversation_id}: {e}")
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
        with get_db_connection() as conn:
            # Build query with filters
            conditions = ["conversation_id = %s"]
            params = [conversation_id]
            
            if is_active is not None:
                conditions.append("is_active = %s")
                params.append(is_active)
            
            where_clause = " WHERE " + " AND ".join(conditions)
            
            # Count total items
            count_query = f"SELECT COUNT(*) as count FROM feedme_examples{where_clause}"
            
            # Get paginated results
            offset = (page - 1) * page_size
            data_query = f"""
                SELECT * FROM feedme_examples{where_clause}
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
            """
            
            with conn.cursor(cursor_factory=psycopg2_extras.RealDictCursor) as cur:
                # Get total count
                cur.execute(count_query, params)
                count_result = cur.fetchone()
                total_count = count_result['count'] if count_result else 0
                
                # Get paginated data
                cur.execute(data_query, params + [page_size, offset])
                rows = cur.fetchall()
                
                examples = [FeedMeExample(**dict(row)) for row in rows]
                
                return ExampleListResponse(
                    examples=examples,
                    total_count=total_count,
                    page=page,
                    page_size=page_size,
                    has_next=offset + len(examples) < total_count
                )
            
    except Exception as e:
        logger.error(f"Error listing examples for conversation {conversation_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to list examples")


@router.get("/conversations/{conversation_id}/status", response_model=ProcessingStatusResponse, tags=["FeedMe"])
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
    
    # Calculate progress percentage based on status
    progress_map = {
        ProcessingStatus.PENDING: 0.0,
        ProcessingStatus.PROCESSING: 50.0,
        ProcessingStatus.COMPLETED: 100.0,
        ProcessingStatus.FAILED: 0.0
    }
    
    return ProcessingStatusResponse(
        conversation_id=conversation.id,
        status=conversation.processing_status,
        progress_percentage=progress_map.get(conversation.processing_status, 0.0),
        error_message=conversation.error_message,
        examples_extracted=conversation.total_examples,
        estimated_completion=None  # Would be calculated by Celery task
    )


@router.post("/search", response_model=SearchResponse, tags=["FeedMe"])
async def search_examples(search_query: SearchQuery):
    """
    Performs a similarity search on FeedMe examples based on the provided query.
    
    Currently returns a placeholder response with no results. Raises HTTP 503 if the FeedMe service is disabled and HTTP 500 on internal errors.
    
    Parameters:
        search_query (SearchQuery): The search query containing the text to search for.
    
    Returns:
        SearchResponse: The search results, including the original query, an empty results list, total found count, and search time in milliseconds.
    """
    
    if not settings.feedme_enabled:
        raise HTTPException(status_code=503, detail="FeedMe service is currently disabled")
    
    start_time = datetime.now()
    
    try:
        # This would integrate with the updated embedding_utils.py in the next chunk
        # For now, return a placeholder response
        
        search_time_ms = (datetime.now() - start_time).total_seconds() * 1000
        
        return SearchResponse(
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
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2_extras.RealDictCursor) as cur:
                # Get conversation statistics
                cur.execute("""
                    SELECT 
                        COUNT(*) as total_conversations,
                        COUNT(*) FILTER (WHERE processing_status = 'completed') as processed_conversations,
                        COUNT(*) FILTER (WHERE processing_status = 'failed') as failed_conversations,
                        COUNT(*) FILTER (WHERE processing_status = 'pending') as pending_conversations,
                        AVG(total_examples) as average_examples_per_conversation
                    FROM feedme_conversations
                """)
                conv_stats = cur.fetchone()
                
                # Get example statistics
                cur.execute("""
                    SELECT 
                        COUNT(*) as total_examples,
                        COUNT(*) FILTER (WHERE is_active = true) as active_examples
                    FROM feedme_examples
                """)
                example_stats = cur.fetchone()
                
                # Get top tags
                cur.execute("""
                    SELECT tag, COUNT(*) as count
                    FROM feedme_examples, unnest(tags) as tag
                    WHERE is_active = true
                    GROUP BY tag
                    ORDER BY count DESC
                    LIMIT 10
                """)
                tag_rows = cur.fetchall()
                
                # Get issue type distribution
                cur.execute("""
                    SELECT 
                        issue_type,
                        COUNT(*) as count,
                        AVG(confidence_score) as average_confidence
                    FROM feedme_examples
                    WHERE is_active = true AND issue_type IS NOT NULL
                    GROUP BY issue_type
                    ORDER BY count DESC
                """)
                issue_type_rows = cur.fetchall()
                
                # Calculate percentages
                total_examples = example_stats['total_examples'] or 1
                
                # Build response
                conversation_stats = {
                    'total_conversations': conv_stats['total_conversations'] or 0,
                    'processed_conversations': conv_stats['processed_conversations'] or 0,
                    'failed_conversations': conv_stats['failed_conversations'] or 0,
                    'pending_conversations': conv_stats['pending_conversations'] or 0,
                    'average_examples_per_conversation': float(conv_stats['average_examples_per_conversation'] or 0),
                    'total_examples': total_examples,
                    'active_examples': example_stats['active_examples'] or 0
                }
                
                top_tags = [
                    {
                        'tag': row['tag'],
                        'count': row['count'],
                        'percentage': (row['count'] / total_examples) * 100
                    }
                    for row in tag_rows
                ]
                
                issue_type_distribution = [
                    {
                        'issue_type': row['issue_type'],
                        'count': row['count'],
                        'percentage': (row['count'] / total_examples) * 100,
                        'average_confidence': float(row['average_confidence'] or 0)
                    }
                    for row in issue_type_rows
                ]
                
                quality_metrics = {
                    'average_confidence_score': 0.0,  # Would be calculated from actual data
                    'average_usefulness_score': 0.0,  # Would be calculated from actual data
                    'processing_success_rate': 0.0    # Would be calculated from actual data
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
        # Get the conversation to verify it exists
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, title, raw_transcript, processing_status
                    FROM feedme_conversations
                    WHERE id = %s
                """, (conversation_id,))
                
                conversation = cur.fetchone()
                
                if not conversation:
                    raise HTTPException(status_code=404, detail=f"Conversation {conversation_id} not found")
                
                if conversation['processing_status'] == 'completed':
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
            
            # Reset status to pending before queueing
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE feedme_conversations
                        SET processing_status = %s, error_message = NULL, updated_at = %s
                        WHERE id = %s
                    """, (ProcessingStatus.PENDING.value, datetime.utcnow(), conversation_id))
                    conn.commit()
            
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
                
                # Update status to processing
                with get_db_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            UPDATE feedme_conversations
                            SET processing_status = %s, updated_at = %s
                            WHERE id = %s
                        """, (ProcessingStatus.PROCESSING.value, datetime.utcnow(), conversation_id))
                        conn.commit()
                
                parser = TranscriptParser()
                
                # Parse the transcript
                examples = parser.parse_transcript(conversation['raw_transcript'])
                
                if not examples:
                    # No examples found
                    with get_db_connection() as conn:
                        with conn.cursor() as cur:
                            cur.execute("""
                                UPDATE feedme_conversations
                                SET processing_status = %s, processed_at = %s, 
                                    total_examples = 0, updated_at = %s
                                WHERE id = %s
                            """, (ProcessingStatus.COMPLETED.value, datetime.utcnow(), 
                                  datetime.utcnow(), conversation_id))
                            conn.commit()
                    
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
                
                # Save examples to database
                with get_db_connection() as conn:
                    with conn.cursor() as cur:
                        # Delete existing examples (in case of reprocessing)
                        cur.execute("""
                            DELETE FROM feedme_examples WHERE conversation_id = %s
                        """, (conversation_id,))
                        
                        # Insert new examples
                        for example in examples_with_embeddings:
                            cur.execute("""
                                INSERT INTO feedme_examples (
                                    conversation_id, question_text, answer_text,
                                    context_before, context_after,
                                    question_embedding, answer_embedding, combined_embedding,
                                    tags, issue_type, resolution_type,
                                    confidence_score, usefulness_score, is_active
                                ) VALUES (
                                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                                )
                            """, (
                                conversation_id,
                                example['question_text'],
                                example['answer_text'],
                                example.get('context_before'),
                                example.get('context_after'),
                                example['question_embedding'],
                                example['answer_embedding'],
                                example['combined_embedding'],
                                example.get('tags', []),
                                example.get('issue_type'),
                                example.get('resolution_type'),
                                example.get('confidence_score', 0.8),
                                example.get('usefulness_score', 0.7),
                                True
                            ))
                        
                        # Update conversation status
                        cur.execute("""
                            UPDATE feedme_conversations
                            SET processing_status = %s, processed_at = %s,
                                total_examples = %s, updated_at = %s
                            WHERE id = %s
                        """, (ProcessingStatus.COMPLETED.value, datetime.utcnow(),
                              len(examples), datetime.utcnow(), conversation_id))
                        
                        conn.commit()
                
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
                
                # Update status to failed
                with get_db_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            UPDATE feedme_conversations
                            SET processing_status = %s, error_message = %s, updated_at = %s
                            WHERE id = %s
                        """, (ProcessingStatus.FAILED.value, str(e), datetime.utcnow(), conversation_id))
                        conn.commit()
                
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
            "timestamp": datetime.utcnow().isoformat(),
            "version": "2.0",
            "components": {}
        }
        
        # Check database health
        try:
            from app.db.connection_manager import health_check
            db_health = health_check()
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
                "timestamp": datetime.utcnow().isoformat(),
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