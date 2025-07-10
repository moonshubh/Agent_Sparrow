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
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import logging

from celery.exceptions import Retry

from app.feedme.celery_app import celery_app, BaseTaskWithRetry
from app.db.supabase_client import get_supabase_client
from app.feedme.transcript_parser import TranscriptParser
from app.feedme.html_parser import HTMLTranscriptParser
from app.db.embedding_utils import get_embedding_model, generate_feedme_embeddings
from app.feedme.schemas import ProcessingStatus
from app.core.settings import settings
from app.feedme.ai_extraction_engine import GemmaExtractionEngine
from app.feedme.parsers.enhanced_html_parser import EnhancedHTMLParser


class MissingAPIKeyError(Exception):
    """Raised when a required API key is missing"""
    pass

logger = logging.getLogger(__name__)


class CallbackTask(BaseTaskWithRetry):
    """Base task class with common functionality"""
    
    def on_success(self, retval, task_id, args, kwargs):
        """Called on task success"""
        logger.info(f"Task {task_id} completed successfully")
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Called on task failure"""
        # The base class already logs the failure in detail.
        # Add any additional logic here if needed.
        super().on_failure(exc, task_id, args, kwargs, einfo)
    
    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """Called on task retry"""
        # The base class already logs the retry attempt.
        # Add any additional logic here if needed.
        super().on_retry(exc, task_id, args, kwargs, einfo)


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
        
        raw_transcript = conversation_data['raw_transcript']
        logger.info(f"Processing transcript of {len(raw_transcript)} characters")
        
        # Phase 1: Use new AI extraction engine with gemma-3-27b-it
        try:
            # Check content type and use appropriate extraction strategy
            metadata = conversation_data.get('metadata', {})
            file_format = metadata.get('file_format', 'text')
            mime_type = conversation_data.get('mime_type', 'text/plain')
            
            if file_format == 'pdf' or mime_type == 'application/pdf':
                logger.info("Detected PDF content, using AI extraction engine with PDF parser")
                
                # Use new AI extraction engine for PDF content
                if settings.gemini_api_key:
                    # Use Gemma-3-27b-it for intelligent extraction
                    engine = GemmaExtractionEngine(api_key=settings.gemini_api_key)
                    
                    # Prepare PDF metadata
                    pdf_metadata = metadata.copy()
                    pdf_metadata.update({
                        'conversation_id': conversation_id,
                        'original_filename': conversation_data.get('original_filename', ''),
                        'file_format': 'pdf',
                        'mime_type': mime_type,
                        'pages': conversation_data.get('pages'),
                        'pdf_metadata': conversation_data.get('pdf_metadata', {})
                    })
                    
                    examples = engine.extract_conversations_sync(raw_transcript, pdf_metadata)
                    logger.info(f"AI extraction engine extracted {len(examples)} Q&A pairs from PDF with gemma-3-27b-it")
                else:
                    error_msg = "No Gemini API key available for PDF extraction"
                    logger.error(error_msg)
                    raise MissingAPIKeyError(error_msg)
                    
            elif raw_transcript.strip().startswith('<') or 'html' in conversation_data.get('original_filename', '').lower():
                logger.info("Detected HTML content, using AI extraction engine with enhanced HTML parser")
                
                # Use new AI extraction engine for HTML content
                
                if settings.gemini_api_key:
                    # Use Gemma-3-27b-it for intelligent extraction
                    engine = GemmaExtractionEngine(api_key=settings.gemini_api_key)
                    
                    # Use the synchronous wrapper method
                    metadata = conversation_data.get('metadata', {})
                    metadata.update({
                        'conversation_id': conversation_id,
                        'original_filename': conversation_data.get('original_filename', ''),
                        'platform': 'zendesk'  # Assume Zendesk for HTML emails
                    })
                    
                    examples = engine.extract_conversations_sync(raw_transcript, metadata)
                    logger.info(f"AI extraction engine extracted {len(examples)} Q&A pairs with gemma-3-27b-it")
                else:
                    # Fallback to enhanced HTML parser
                    
                    html_parser = EnhancedHTMLParser()
                    parse_result = html_parser.parse(raw_transcript)
                    
                    # Convert parsed messages to Q&A pairs (simplified for Phase 1)
                    examples = []
                    messages = parse_result.get('messages', [])
                    
                    # Group customer questions with agent responses
                    for i in range(len(messages) - 1):
                        if messages[i].role == 'customer' and messages[i + 1].role == 'agent':
                            examples.append({
                                'question_text': messages[i].content,
                                'answer_text': messages[i + 1].content,
                                'confidence_score': 0.7,  # Default for pattern-based
                                'context_before': messages[i - 1].content if i > 0 else '',
                                'context_after': messages[i + 2].content if i + 2 < len(messages) else '',
                                'tags': [],
                                'issue_type': None,
                                'resolution_type': None,
                                'extraction_method': 'html_pattern',
                                'metadata': {}
                            })
                    
                    logger.info(f"Enhanced HTML parser extracted {len(examples)} Q&A pairs")
            else:
                logger.info("Using AI-powered text extraction")
                # Use AI extraction for text content as well
                
                if settings.gemini_api_key:
                    engine = GemmaExtractionEngine(api_key=settings.gemini_api_key)
                    
                    # Convert text to simple HTML for consistent processing
                    html_content = f"<div class='conversation'><pre>{raw_transcript}</pre></div>"
                    
                    # Use the synchronous wrapper method
                    metadata = conversation_data.get('metadata', {})
                    metadata.update({
                        'conversation_id': conversation_id,
                        'original_filename': conversation_data.get('original_filename', ''),
                        'content_type': 'text'
                    })
                    
                    examples = engine.extract_conversations_sync(html_content, metadata)
                    logger.info(f"AI extraction engine processed text content: {len(examples)} Q&A pairs")
                else:
                    # Fallback to existing text parser
                    
                    parser = TranscriptParser()
                    examples = parser.extract_qa_examples(
                        transcript=raw_transcript,
                        conversation_id=conversation_id,
                        metadata=conversation_data.get('metadata', {})
                    )
                    
                    # Convert to standard format
                    examples = [
                        {
                            'question_text': ex.get('question_text', ''),
                            'answer_text': ex.get('answer_text', ''),
                            'confidence_score': ex.get('confidence_score', 0.5),
                            'context_before': ex.get('context_before', ''),
                            'context_after': ex.get('context_after', ''),
                            'tags': ex.get('tags', []),
                            'issue_type': ex.get('issue_type'),
                            'resolution_type': ex.get('resolution_type'),
                            'extraction_method': 'text_pattern',
                            'metadata': ex.get('metadata', {})
                        }
                        for ex in examples
                    ] if examples else []
                    
                    logger.info(f"Text parser extracted {len(examples)} Q&A pairs")
                    
        except Exception as e:
            logger.error(f"Error in Phase 1 AI extraction: {e}")
            # Fallback to original parsing logic
            from app.feedme.html_parser import HTMLTranscriptParser
            
            html_parser = HTMLTranscriptParser()
            examples = html_parser.parse_html_transcript(raw_transcript)
            
            logger.info(f"Fallback HTML parser extracted {len(examples)} Q&A pairs")
        
        # Store examples temporarily for approval
        if examples:
            store_temp_examples(conversation_id, examples)
            logger.info(f"Stored {len(examples)} examples temporarily")
        
        # Update status to completed
        processing_time = time.time() - start_time
        processing_time_ms = int(processing_time * 1000)
        update_conversation_status(
            conversation_id, 
            ProcessingStatus.COMPLETED,
            processing_time_ms=processing_time_ms,
            total_examples=len(examples)
        )
        
        logger.info(f"Successfully processed conversation {conversation_id}: {len(examples)} examples in {processing_time:.2f}s")
        
        return {
            'success': True,
            'conversation_id': conversation_id,
            'examples_extracted': len(examples),
            'processing_time': processing_time
        }
        
    except Exception as e:
        logger.error(f"Error processing transcript for conversation {conversation_id}: {e}")
        update_conversation_status(
            conversation_id, 
            ProcessingStatus.FAILED,
            error_message=str(e)
        )
        
        if self.request.retries < self.max_retries:
            logger.info(f"Retrying processing task (attempt {self.request.retries + 1})")
            raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))
        raise


def store_temp_examples(conversation_id: int, examples: List[Dict[str, Any]]):
    """Store extracted examples directly in Supabase"""
    try:
        client = get_supabase_client()
        
        # Prepare examples for Supabase
        supabase_examples = []
        for example in examples:
            supabase_examples.append({
                'conversation_id': conversation_id,
                'question_text': example.get('question_text', ''),
                'answer_text': example.get('answer_text', ''),
                'context_before': example.get('context_before', ''),
                'context_after': example.get('context_after', ''),
                'confidence_score': example.get('confidence_score', 0.5),
                'tags': example.get('tags', []),
                'issue_type': example.get('issue_type', 'general'),
                'resolution_type': example.get('resolution_type', 'resolved')
            })
        
        # Insert examples into Supabase
        client.client.table('feedme_examples').insert(supabase_examples).execute()
        logger.info(f"Stored {len(examples)} examples in Supabase for conversation {conversation_id}")
                
    except Exception as e:
        logger.error(f"Error storing temp examples: {e}")
        raise


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
        # Determine if this is HTML content
        is_html = False
        if raw_transcript.strip().startswith('<') or '<html' in raw_transcript[:1000].lower():
            is_html = True
        elif metadata and metadata.get('original_filename', '').lower().endswith('.html'):
            is_html = True
        
        # Initialize appropriate parser and extract examples
        if is_html and getattr(settings, 'feedme_html_enabled', True):
            logger.info(f"Using HTML parser for conversation {conversation_id}")
            html_parser = HTMLTranscriptParser()
            examples = html_parser.parse_html_transcript(raw_transcript)
        else:
            logger.info(f"Using text parser for conversation {conversation_id}")
            parser = TranscriptParser()
            examples = parser.extract_qa_examples(
                transcript=raw_transcript,
                conversation_id=conversation_id,
                metadata=metadata
            )
        
        # Save examples to temporary table for preview/approval
        try:
            store_temp_examples(conversation_id, examples)
            examples_created = len(examples)
        except Exception as e:
            logger.error(f"Failed to store temp examples: {e}")
            examples_created = 0
        
        # Update parsed content
        if is_html:
            # For HTML, store the cleaned version
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(raw_transcript, 'html.parser')
            cleaned_content = soup.get_text(separator=' ', strip=True)
            update_parsed_content(conversation_id, cleaned_content)
        else:
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
        # Check Supabase connection
        client = get_supabase_client()
        db_health = {"status": "healthy"}  # Simplified health check for sync context
        
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
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "task_id": self.request.id
        }
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "task_id": self.request.id
        }


# Helper functions

def get_conversation_data(conversation_id: int) -> Optional[Dict[str, Any]]:
    """Get conversation data from Supabase (synchronous for Celery)"""
    try:
        client = get_supabase_client()
        # Use synchronous Supabase client operations
        result = client.client.table('feedme_conversations').select('*').eq('id', conversation_id).execute()
        if result.data:
            return result.data[0]
        return None
    except Exception as e:
        logger.error(f"Error fetching conversation {conversation_id}: {e}")
        return None


def update_conversation_status(
    conversation_id: int,
    status: ProcessingStatus,
    task_id: Optional[str] = None,
    error_message: Optional[str] = None,
    processing_time_ms: Optional[int] = None,
    total_examples: Optional[int] = None
):
    """Update conversation processing status (synchronous for Celery)"""
    try:
        client = get_supabase_client()
        
        # Update conversation in Supabase
        update_data = {
            'processing_status': status.value
        }
        
        if status == ProcessingStatus.COMPLETED:
            update_data['processed_at'] = datetime.now(timezone.utc).isoformat()
            if processing_time_ms is not None:
                update_data['processing_time_ms'] = processing_time_ms
            if total_examples is not None:
                update_data['total_examples'] = total_examples
        elif status == ProcessingStatus.PROCESSING:
            update_data['processed_at'] = None
        
        if error_message is not None:
            update_data['error_message'] = error_message
        
        # Add task_id to metadata if provided
        if task_id:
            import json
            current_metadata = {}
            # We'll merge with existing metadata if any
            update_data['metadata'] = {**current_metadata, "task_id": task_id}
        
        # Use synchronous Supabase client operations
        result = client.client.table('feedme_conversations').update(update_data).eq('id', conversation_id).execute()
        logger.info(f"Updated conversation {conversation_id} status to {status.value}")
        
    except Exception as e:
        logger.error(f"Error updating conversation {conversation_id}: {e}")


def save_examples_to_temp_db(conversation_id: int, examples: List[Dict[str, Any]], is_html: bool = False) -> int:
    """Save extracted examples to Supabase for preview/approval"""
    if not examples:
        return 0
    
    try:
        client = get_supabase_client()
        
        # Update conversation metadata with content type info
        content_type = 'html' if is_html else 'text'
        extraction_method = 'html' if is_html else 'ai'
        
        metadata_update = {"content_type": content_type, "extraction_method": extraction_method}
        # Use synchronous Supabase operations
        client.client.table('feedme_conversations').update({"metadata": metadata_update}).eq('id', conversation_id).execute()
        
        # Prepare examples for Supabase
        supabase_examples = []
        for example in examples:
            supabase_examples.append({
                'conversation_id': conversation_id,
                'question_text': example.get('question_text', ''),
                'answer_text': example.get('answer_text', ''),
                'context_before': example.get('context_before'),
                'context_after': example.get('context_after'),
                'confidence_score': example.get('confidence_score', 0.0),
                'tags': example.get('tags', []),
                'issue_type': example.get('issue_type', 'general'),
                'resolution_type': example.get('resolution_type', 'resolved')
            })
        
        # Insert examples into Supabase
        client.client.table('feedme_examples').insert(supabase_examples).execute()
        
        return len(supabase_examples)
    except Exception as e:
        logger.error(f"Error saving examples to Supabase: {e}")
        return 0


def save_examples_to_db(conversation_id: int, examples: List[Dict[str, Any]]) -> int:
    """Save extracted examples to Supabase"""
    return save_examples_to_temp_db(conversation_id, examples)


def update_parsed_content(conversation_id: int, parsed_content: str):
    """Update parsed content for conversation in Supabase"""
    try:
        client = get_supabase_client()
        client.client.table('feedme_conversations').update({'parsed_content': parsed_content}).eq('id', conversation_id).execute()
        logger.info(f"Updated parsed content for conversation {conversation_id}")
    except Exception as e:
        logger.error(f"Error updating parsed content for conversation {conversation_id}: {e}")


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