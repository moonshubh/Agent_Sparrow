"""
FeedMe v2.0 Phase 2: Celery Tasks
Background processing tasks for transcript parsing and embedding generation

This module provides:
- Async transcript processing
- Embedding generation
- Conversation parsing
- Progress tracking and status updates
- Error handling and retry logic
"""

import traceback
import time
from typing import Dict, Any, List, Optional
from datetime import datetime
import logging

from celery import Task
from celery.exceptions import Retry

from app.feedme.celery_app import celery_app
from app.db.connection_manager import get_connection_manager, with_db_connection
from app.feedme.transcript_parser import TranscriptParser
from app.db.embedding_utils import get_embedding_model, generate_feedme_embeddings
from app.feedme.schemas import ProcessingStatus
from app.core.settings import settings

logger = logging.getLogger(__name__)


class CallbackTask(Task):
    """Base task class with common functionality"""
    
    def on_success(self, retval, task_id, args, kwargs):
        """Called on task success"""
        logger.info(f"Task {task_id} completed successfully")
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Called on task failure"""
        logger.error(f"Task {task_id} failed: {exc}")
        logger.debug(f"Error info: {einfo}")
    
    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """Called on task retry"""
        logger.warning(f"Task {task_id} retrying due to: {exc}")


@celery_app.task(bind=True, base=CallbackTask, name='app.feedme.tasks.process_transcript')
def process_transcript(self, conversation_id: int, user_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Main transcript processing task that orchestrates the entire pipeline
    
    Args:
        conversation_id: ID of the conversation to process
        user_id: Optional user ID for tracking
        
    Returns:
        Dict containing processing results and statistics
    """
    start_time = time.time()
    task_id = self.request.id
    
    logger.info(f"Starting transcript processing for conversation {conversation_id} (task: {task_id})")
    
    try:
        # Update status to processing
        update_conversation_status(conversation_id, ProcessingStatus.PROCESSING, task_id=task_id)
        
        # Get conversation data
        conversation_data = get_conversation_data(conversation_id)
        if not conversation_data:
            raise ValueError(f"Conversation {conversation_id} not found")
        
        # Step 1: Parse conversation and extract Q&A examples
        logger.info(f"Parsing conversation {conversation_id}")
        parsing_result = parse_conversation.delay(
            conversation_id,
            conversation_data['raw_transcript'],
            conversation_data.get('metadata', {})
        )
        
        # Wait for parsing to complete
        parsing_result.get(timeout=300)  # 5 minutes timeout
        parsing_data = parsing_result.result
        
        if not parsing_data['success']:
            raise Exception(f"Parsing failed: {parsing_data.get('error', 'Unknown error')}")
        
        # Step 2: Generate embeddings for extracted examples
        logger.info(f"Generating embeddings for conversation {conversation_id}")
        embedding_result = generate_embeddings.delay(conversation_id)
        
        # Wait for embeddings to complete
        embedding_result.get(timeout=600)  # 10 minutes timeout
        embedding_data = embedding_result.result
        
        if not embedding_data['success']:
            logger.warning(f"Embedding generation had issues: {embedding_data.get('error', 'Unknown error')}")
        
        # Calculate processing time
        processing_time_ms = int((time.time() - start_time) * 1000)
        
        # Update conversation with final status
        update_conversation_status(
            conversation_id, 
            ProcessingStatus.COMPLETED,
            processing_time_ms=processing_time_ms,
            total_examples=parsing_data.get('examples_created', 0)
        )
        
        result = {
            "success": True,
            "conversation_id": conversation_id,
            "task_id": task_id,
            "processing_time_ms": processing_time_ms,
            "examples_created": parsing_data.get('examples_created', 0),
            "embeddings_generated": embedding_data.get('embeddings_generated', 0),
            "completed_at": datetime.utcnow().isoformat()
        }
        
        logger.info(f"Completed transcript processing for conversation {conversation_id}: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Transcript processing failed for conversation {conversation_id}: {e}")
        logger.debug(traceback.format_exc())
        
        # Update status to failed
        update_conversation_status(
            conversation_id,
            ProcessingStatus.FAILED,
            error_message=str(e)
        )
        
        # Retry logic
        if self.request.retries < self.max_retries:
            logger.info(f"Retrying transcript processing (attempt {self.request.retries + 1})")
            raise self.retry(countdown=60, exc=e)
        
        return {
            "success": False,
            "conversation_id": conversation_id,
            "task_id": task_id,
            "error": str(e),
            "failed_at": datetime.utcnow().isoformat()
        }


@celery_app.task(bind=True, base=CallbackTask, name='app.feedme.tasks.parse_conversation')
def parse_conversation(self, conversation_id: int, raw_transcript: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse conversation transcript and extract Q&A examples
    
    Args:
        conversation_id: ID of the conversation
        raw_transcript: Raw transcript content
        metadata: Additional metadata for parsing
        
    Returns:
        Dict containing parsing results
    """
    task_id = self.request.id
    logger.info(f"Parsing conversation {conversation_id} (task: {task_id})")
    
    try:
        # Initialize parser
        parser = TranscriptParser()
        
        # Parse transcript and extract examples
        examples = parser.extract_qa_examples(
            transcript=raw_transcript,
            conversation_id=conversation_id,
            metadata=metadata
        )
        
        # Save examples to database
        examples_created = save_examples_to_db(conversation_id, examples)
        
        # Update parsed content
        update_parsed_content(conversation_id, parser.clean_transcript(raw_transcript))
        
        result = {
            "success": True,
            "conversation_id": conversation_id,
            "task_id": task_id,
            "examples_created": examples_created,
            "examples_data": [
                {
                    "question": example.get("question_text", ""),
                    "answer": example.get("answer_text", ""),
                    "confidence": example.get("confidence_score", 0.0)
                }
                for example in examples[:5]  # Return first 5 for preview
            ]
        }
        
        logger.info(f"Successfully parsed conversation {conversation_id}: {examples_created} examples created")
        return result
        
    except Exception as e:
        logger.error(f"Conversation parsing failed for {conversation_id}: {e}")
        logger.debug(traceback.format_exc())
        
        if self.request.retries < self.max_retries:
            raise self.retry(countdown=30, exc=e)
        
        return {
            "success": False,
            "conversation_id": conversation_id,
            "task_id": task_id,
            "error": str(e)
        }


@celery_app.task(bind=True, base=CallbackTask, name='app.feedme.tasks.generate_embeddings')
def generate_embeddings(self, conversation_id: int) -> Dict[str, Any]:
    """
    Generate embeddings for all examples in a conversation
    
    Args:
        conversation_id: ID of the conversation
        
    Returns:
        Dict containing embedding generation results
    """
    task_id = self.request.id
    logger.info(f"Generating embeddings for conversation {conversation_id} (task: {task_id})")
    
    try:
        # Generate embeddings using existing utility
        embeddings_generated = generate_feedme_embeddings(
            conversation_id=conversation_id,
            batch_size=settings.feedme_embedding_batch_size
        )
        
        result = {
            "success": True,
            "conversation_id": conversation_id,
            "task_id": task_id,
            "embeddings_generated": embeddings_generated
        }
        
        logger.info(f"Successfully generated embeddings for conversation {conversation_id}: {embeddings_generated} embeddings")
        return result
        
    except Exception as e:
        logger.error(f"Embedding generation failed for conversation {conversation_id}: {e}")
        logger.debug(traceback.format_exc())
        
        if self.request.retries < self.max_retries:
            raise self.retry(countdown=30, exc=e)
        
        return {
            "success": False,
            "conversation_id": conversation_id,
            "task_id": task_id,
            "error": str(e)
        }


@celery_app.task(bind=True, base=CallbackTask, name='app.feedme.tasks.health_check')
def health_check(self) -> Dict[str, Any]:
    """
    Health check task for monitoring
    
    Returns:
        Dict containing health status
    """
    try:
        from app.db.connection_manager import health_check as db_health_check
        
        # Check database connection
        db_health = db_health_check()
        
        # Check embedding model
        embedding_health = {"status": "healthy"}
        try:
            model = get_embedding_model()
            test_embedding = model.embed_query("test")
            if len(test_embedding) != 768:
                embedding_health = {"status": "unhealthy", "error": "Invalid embedding dimension"}
        except Exception as e:
            embedding_health = {"status": "unhealthy", "error": str(e)}
        
        return {
            "status": "healthy" if db_health["status"] == "healthy" and embedding_health["status"] == "healthy" else "unhealthy",
            "database": db_health,
            "embeddings": embedding_health,
            "timestamp": datetime.utcnow().isoformat(),
            "task_id": self.request.id
        }
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat(),
            "task_id": self.request.id
        }


# Helper functions

@with_db_connection()
def get_conversation_data(conn, conversation_id: int) -> Optional[Dict[str, Any]]:
    """Get conversation data from database"""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, title, raw_transcript, metadata FROM feedme_conversations WHERE id = %s",
            (conversation_id,)
        )
        result = cur.fetchone()
        return dict(result) if result else None


@with_db_connection()
def update_conversation_status(
    conn,
    conversation_id: int,
    status: ProcessingStatus,
    task_id: Optional[str] = None,
    error_message: Optional[str] = None,
    processing_time_ms: Optional[int] = None,
    total_examples: Optional[int] = None
):
    """Update conversation processing status"""
    with conn.cursor() as cur:
        update_fields = ["processing_status = %s", "updated_at = NOW()"]
        params = [status.value]
        
        if status == ProcessingStatus.PROCESSING:
            update_fields.append("processed_at = NULL")
        elif status == ProcessingStatus.COMPLETED:
            update_fields.append("processed_at = NOW()")
            if processing_time_ms is not None:
                update_fields.append("processing_time_ms = %s")
                params.append(processing_time_ms)
            if total_examples is not None:
                update_fields.append("total_examples = %s")
                params.append(total_examples)
        
        if error_message:
            update_fields.append("error_message = %s")
            params.append(error_message)
        
        # Add task_id to metadata if provided
        if task_id:
            update_fields.append("metadata = COALESCE(metadata, '{}') || %s")
            params.append(f'{{"task_id": "{task_id}"}}')
        
        params.append(conversation_id)
        
        query = f"UPDATE feedme_conversations SET {', '.join(update_fields)} WHERE id = %s"
        cur.execute(query, params)
        conn.commit()


@with_db_connection()
def save_examples_to_db(conn, conversation_id: int, examples: List[Dict[str, Any]]) -> int:
    """Save extracted examples to database"""
    if not examples:
        return 0
    
    with conn.cursor() as cur:
        insert_query = """
        INSERT INTO feedme_examples (
            conversation_id, question_text, answer_text, context_before, context_after,
            tags, issue_type, resolution_type, confidence_score, extraction_method,
            extraction_confidence, source_position
        ) VALUES %s
        """
        
        values = []
        for i, example in enumerate(examples):
            values.append((
                conversation_id,
                example.get('question_text', ''),
                example.get('answer_text', ''),
                example.get('context_before'),
                example.get('context_after'),
                example.get('tags', []),
                example.get('issue_type'),
                example.get('resolution_type'),
                example.get('confidence_score', 0.0),
                example.get('extraction_method', 'ai'),
                example.get('extraction_confidence', 0.0),
                i + 1  # source_position
            ))
        
        from psycopg2.extras import execute_values
        execute_values(cur, insert_query, values)
        conn.commit()
        
        return len(values)


@with_db_connection()
def update_parsed_content(conn, conversation_id: int, parsed_content: str):
    """Update parsed content for conversation"""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE feedme_conversations SET parsed_content = %s WHERE id = %s",
            (parsed_content, conversation_id)
        )
        conn.commit()


# Task monitoring utilities

def get_task_status(task_id: str) -> Dict[str, Any]:
    """Get status of a specific task"""
    try:
        result = celery_app.AsyncResult(task_id)
        return {
            "task_id": task_id,
            "status": result.status,
            "result": result.result if result.ready() else None,
            "info": result.info,
            "successful": result.successful(),
            "failed": result.failed(),
            "ready": result.ready()
        }
    except Exception as e:
        return {
            "task_id": task_id,
            "status": "ERROR",
            "error": str(e)
        }


def cancel_task(task_id: str) -> bool:
    """Cancel a running task"""
    try:
        celery_app.control.revoke(task_id, terminate=True)
        return True
    except Exception as e:
        logger.error(f"Failed to cancel task {task_id}: {e}")
        return False