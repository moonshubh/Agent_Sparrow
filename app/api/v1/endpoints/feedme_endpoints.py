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
    AnalyticsResponse
)

# Import database utilities
from app.db.embedding_utils import get_db_connection, get_embedding_model
import psycopg2
import psycopg2.extras as psycopg2_extras
logger = logging.getLogger(__name__)
router = APIRouter()

# Database helper functions

async def get_conversation_by_id(conversation_id: int) -> Optional[FeedMeConversation]:
    """
    Retrieve a conversation record from the database by its unique ID.
    
    Parameters:
        conversation_id (int): The unique identifier of the conversation to retrieve.
    
    Returns:
        Optional[FeedMeConversation]: The conversation object if found, otherwise None.
    """
    conn = None
    try:
        conn = get_db_connection()
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
    finally:
        if conn:
            conn.close()


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
    conn = None
    try:
        conn = get_db_connection()
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
        if conn:
            conn.rollback()
        logger.error(f"Error creating conversation: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create conversation: {str(e)}")
    finally:
        if conn:
            conn.close()


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
    conn = None
    try:
        conn = get_db_connection()
        
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
        
        with conn.cursor(cursor_factory=psycopg2_extras.RealDictCursor) as cur:
            cur.execute(query, values)
            row = cur.fetchone()
            conn.commit()
            
            if row:
                return FeedMeConversation(**dict(row))
            return None
            
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Error updating conversation {conversation_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update conversation: {str(e)}")
    finally:
        if conn:
            conn.close()


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
        if auto_process:
            # Note: This would integrate with Celery task in the next implementation chunk
            # For now, we'll update the status to indicate processing will happen
            await update_conversation_in_db(
                conversation.id,
                ConversationUpdate(processing_status=ProcessingStatus.PENDING)
            )
            logger.info(f"Scheduled processing for conversation {conversation.id}")
        
        logger.info(f"Successfully uploaded transcript: conversation_id={conversation.id}, title='{title}'")
        return conversation
        
    except Exception as e:
        logger.error(f"Error uploading transcript: {e}")
        raise HTTPException(status_code=500, detail="Failed to upload transcript")


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
    
    conn = None
    try:
        conn = get_db_connection()
        
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
        count_query = f"SELECT COUNT(*) FROM feedme_conversations{where_clause}"
        
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
            total_count = cur.fetchone()[0]
            
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
        raise HTTPException(status_code=500, detail="Failed to list conversations")
    finally:
        if conn:
            conn.close()


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
    
    conn = None
    try:
        conn = get_db_connection()
        
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
        if conn:
            conn.rollback()
        logger.error(f"Error deleting conversation {conversation_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete conversation")
    finally:
        if conn:
            conn.close()


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
    
    conn = None
    try:
        conn = get_db_connection()
        
        # Build query with filters
        conditions = ["conversation_id = %s"]
        params = [conversation_id]
        
        if is_active is not None:
            conditions.append("is_active = %s")
            params.append(is_active)
        
        where_clause = " WHERE " + " AND ".join(conditions)
        
        # Count total items
        count_query = f"SELECT COUNT(*) FROM feedme_examples{where_clause}"
        
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
            total_count = cur.fetchone()[0]
            
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
    finally:
        if conn:
            conn.close()


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
    
    conn = None
    try:
        conn = get_db_connection()
        
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
    finally:
        if conn:
            conn.close()


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