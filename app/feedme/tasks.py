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
import os
import time
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import logging
import json
import re

from app.feedme.celery_app import celery_app, BaseTaskWithRetry
from app.db.supabase.client import get_supabase_client
from app.feedme.transcript_parser import TranscriptParser
from app.db.embedding.utils import get_embedding_model, generate_feedme_embeddings
from app.feedme.schemas import ProcessingStatus, ProcessingStage
from app.feedme.websocket.schemas import ProcessingUpdate
from app.api.v1.websocket.feedme_websocket import notify_processing_update
from app.core.config import get_models_config
from app.core.settings import get_settings
from functools import lru_cache

# Use cached settings accessor for dynamic reload capability
@lru_cache(maxsize=1)
def get_cached_settings():
    """Get cached settings instance. Clear cache to reload settings."""
    return get_settings()

# Helper to access current settings dynamically
def current_settings():
    """Get current settings, allows for dynamic reload without restart."""
    # Clear cache and reload if needed (can be triggered externally)
    return get_cached_settings()

from app.core.user_context_sync import get_user_gemini_api_key_sync
import base64
from pypdf import PdfReader
import io
try:  # Prefer modern google-genai package when available
    from google import genai  # type: ignore
    GENAI_SDK = "google.genai"
except ImportError:  # pragma: no cover
    import google.generativeai as genai  # type: ignore
    GENAI_SDK = "google.generativeai"

# Module-level client for google.genai SDK
_genai_client = None

def _init_genai_client(api_key: str):
    """Initialize or get the Gemini client."""
    global _genai_client
    if GENAI_SDK == "google.genai":
        if _genai_client is None or getattr(_genai_client, '_api_key', None) != api_key:
            _genai_client = genai.Client(api_key=api_key)
            _genai_client._api_key = api_key  # Track for reinitialization
        return _genai_client
    else:
        genai.configure(api_key=api_key)
        return genai

def _generate_content(api_key: str, model_name: str, prompt: str) -> str:
    """Generate content using the appropriate SDK method."""
    if GENAI_SDK == "google.genai":
        client = _init_genai_client(api_key)
        resp = client.models.generate_content(model=model_name, contents=prompt)
        if hasattr(resp, 'text'):
            return resp.text or ""
        elif hasattr(resp, 'candidates') and resp.candidates:
            candidate = resp.candidates[0]
            if hasattr(candidate, 'content') and candidate.content:
                if hasattr(candidate.content, 'parts') and candidate.content.parts:
                    return candidate.content.parts[0].text or ""
        return ""
    else:
        _init_genai_client(api_key)
        model = genai.GenerativeModel(model_name)
        resp = model.generate_content(prompt)
        text = getattr(resp, 'text', None)
        if text:
            return text
        candidates = getattr(resp, 'candidates', None)
        if candidates and len(candidates) > 0:
            try:
                return candidates[0].content.parts[0].text or ""
            except (AttributeError, IndexError):
                return ""
        return ""

def _embed_content(api_key: str, model_name: str, content: str) -> list:
    """Generate embedding using the appropriate SDK method."""
    if GENAI_SDK == "google.genai":
        client = _init_genai_client(api_key)
        resp = client.models.embed_content(model=model_name, contents=content)
        # New SDK returns embeddings differently
        if hasattr(resp, 'embeddings') and resp.embeddings:
            return resp.embeddings[0].values
        return []
    else:
        _init_genai_client(api_key)
        emb = genai.embed_content(model=model_name, content=content)
        return emb['embedding'] if isinstance(emb, dict) else emb.embedding

# Feature flags / behavior toggles
DELETE_PDF_AFTER_EXTRACT = True  # Immediately remove PDF payload after extraction
from app.db.embedding_config import MODEL_NAME as EMBEDDING_MODEL_NAME, EXPECTED_DIM as EXPECTED_EMBEDDING_DIM, assert_dim

def _light_cleanup(text: str) -> str:
    """Perform minimal cleanup to improve readability without changing content semantics."""
    if not text:
        return text
    # Normalize Windows/Mac newlines
    cleaned = text.replace('\r\n', '\n').replace('\r', '\n')
    # Collapse excessive blank lines
    lines = [line.strip() for line in cleaned.split('\n')]
    # Join soft hyphenation breaks: e.g., "confi-\ndence" -> "confidence"
    joined = []
    skip_next_space = False
    for i, line in enumerate(lines):
        if line.endswith('-') and i + 1 < len(lines) and lines[i + 1][:1].islower():
            # Drop trailing hyphen and concatenate with next line
            joined.append(line[:-1])
            lines[i + 1] = lines[i + 1].lstrip()
            skip_next_space = True
        else:
            joined.append(line)
            skip_next_space = False
    cleaned = '\n'.join(joined)
    # Collapse 3+ newlines to max 2
    while '\n\n\n' in cleaned:
        cleaned = cleaned.replace('\n\n\n', '\n\n')
    return cleaned.strip()

def _extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    """Extract text from a PDF using pypdf. No OCR fallback by design."""
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        parts = []
        for page in reader.pages:
            try:
                txt = page.extract_text() or ""
            except Exception:
                txt = ""
            if txt:
                parts.append(txt)
        return '\n\n'.join(parts)
    except Exception as e:
        logger.error(f"PDF text extraction failed: {e}")
        return ""


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
        update_conversation_status(
            conversation_id,
            ProcessingStatus.PROCESSING,
            task_id=task_id,
            stage=ProcessingStage.PARSING,
            progress=10,
            message="Preparing transcript for extraction"
        )
        
        # Get conversation data
        conversation_data = get_conversation_data(conversation_id)
        if not conversation_data:
            raise ValueError(f"Conversation {conversation_id} not found")
        
        raw_transcript = conversation_data['raw_transcript']
        logger.info(f"Processing transcript of {len(raw_transcript)} characters")
        
        # New simplified flow: produce unified extracted_text and purge original PDF immediately
        metadata = conversation_data.get('metadata', {})
        file_format = metadata.get('file_format', 'text')
        mime_type = conversation_data.get('mime_type', 'text/plain')

        extracted_text = ""
        extraction_confidence = None
        processing_method = 'pdf_ai'

        if file_format == 'pdf' or mime_type == 'application/pdf':
            logger.info("Detected PDF content")
            
            # Validate PDF size before decoding
            # Base64 increases size by ~33%, so check encoded size first
            max_pdf_size_mb = getattr(current_settings(), 'feedme_max_pdf_size_mb', 50)
            max_encoded_size = int(max_pdf_size_mb * 1024 * 1024 * 1.4)  # 1.4x for base64 overhead
            
            if len(raw_transcript) > max_encoded_size:
                raise ValueError(f"PDF too large: {len(raw_transcript) / (1024*1024):.1f}MB encoded (max {max_pdf_size_mb}MB)")
            
            try:
                pdf_bytes = base64.b64decode(raw_transcript)
            except Exception as e:
                raise ValueError(f"Invalid base64 PDF content: {e}")
            
            # Double-check decoded size
            if len(pdf_bytes) > max_pdf_size_mb * 1024 * 1024:
                raise ValueError(f"PDF too large: {len(pdf_bytes) / (1024*1024):.1f}MB (max {max_pdf_size_mb}MB)")

            # Check if AI PDF extraction is enabled
            if current_settings().feedme_ai_pdf_enabled:
                logger.info("Using Gemini vision API for PDF extraction")
                try:
                    # Get user's API key if available
                    user_api_key = None
                    if user_id:
                        try:
                            user_api_key = get_user_gemini_api_key_sync(user_id)
                        except Exception as e:
                            logger.debug(f"Could not get user API key: {e}")
                    
                    # Use Gemini vision processor
                    from app.feedme.processors.gemini_pdf_processor import process_pdf_to_markdown
                    
                    update_conversation_status(
                        conversation_id,
                        ProcessingStatus.PROCESSING,
                        stage=ProcessingStage.AI_EXTRACTION,
                        progress=40,
                        message="Running AI extraction"
                    )

                    markdown_text, extraction_info = process_pdf_to_markdown(
                        pdf_bytes,
                        max_pages=current_settings().feedme_ai_max_pages,
                        pages_per_call=current_settings().feedme_ai_pages_per_call,
                        api_key=user_api_key or current_settings().gemini_api_key,
                    )
                    
                    if markdown_text:
                        extracted_text = markdown_text
                        extraction_confidence = 0.98  # High confidence for AI extraction
                        processing_method = 'pdf_ai'
                        
                        # Store extraction info in metadata
                        metadata.update({
                            'extraction_info': extraction_info,
                            'extraction_method': 'gemini_vision'
                        })
                        logger.info(f"Successfully extracted {extraction_info['pages_processed']} pages using Gemini vision")
                    else:
                        raise ValueError("Gemini extraction returned empty result")
                except Exception as e:
                    logger.error(f"Gemini vision extraction failed: {e}")
                    raise
            else:
                # Strict mode: AI extraction must be enabled
                raise ValueError("AI PDF extraction is disabled in settings")

            # Immediately purge original PDF payload if enabled
            if DELETE_PDF_AFTER_EXTRACT:
                try:
                    client = get_supabase_client()
                    # Do not null raw_transcript if the column is NOT NULL; just mark cleaned
                    client.client.table('feedme_conversations').update({
                        'pdf_cleaned': True,
                        'pdf_cleaned_at': datetime.now(timezone.utc).isoformat(),
                        'original_pdf_size': len(pdf_bytes)
                    }).eq('id', conversation_id).execute()
                    logger.info(f"Marked PDF content as cleaned for conversation {conversation_id}")
                except Exception as e:
                    logger.error(f"Failed to mark PDF cleaned for conversation {conversation_id}: {e}")

        else:
            # Non-PDF content is not supported in strict AI mode
            raise ValueError("Only PDF content is supported for FeedMe processing")

        # Q&A example extraction deprecated – unified text canvas only
        
        # Update status to completed
        processing_time = time.time() - start_time
        processing_time_ms = int(processing_time * 1000)
        # Persist unified text and metadata
        try:
            client = get_supabase_client()
            update = {
                'extracted_text': extracted_text,
                'processing_status': ProcessingStatus.COMPLETED.value,
                'processed_at': datetime.now(timezone.utc).isoformat(),
                'processing_time_ms': processing_time_ms,
                'processing_method': processing_method,
            }
            if extraction_confidence is not None:
                update['extraction_confidence'] = extraction_confidence

            # Fetch current record to decide whether to overwrite title (only on first extraction)
            try:
                current = client.client.table('feedme_conversations') \
                    .select('metadata, processed_at, title') \
                    .eq('id', conversation_id) \
                    .maybe_single() \
                    .execute()
                row = getattr(current, 'data', None) or {}
                current_meta = row.get('metadata') or {}
                already_processed = bool(row.get('processed_at'))
            except Exception:
                row = {}
                current_meta = {}
                already_processed = False

            if 'meta' in locals() and isinstance(meta, dict):
                cm = current_meta or {}
                # Merge ticket_id (non-editable)
                if meta.get('ticket_id'):
                    cm['ticket_id'] = meta.get('ticket_id')
                # Overwrite title with extracted subject only on first processing
                if not already_processed and meta.get('subject'):
                    update['title'] = meta['subject'][:255]
                    cm['title_overridden_on_extract'] = True
                update['metadata'] = cm

            client.client.table('feedme_conversations').update(update).eq('id', conversation_id).execute()
        except Exception as e:
            logger.error(f"Failed to persist extracted_text/metadata for conversation {conversation_id}: {e}")

        update_conversation_status(
            conversation_id,
            ProcessingStatus.PROCESSING,
            stage=ProcessingStage.QUALITY_ASSESSMENT,
            progress=80,
            message="Generating embeddings and quality metrics"
        )

        # Schedule chunking + embeddings (Gemini embeddings) for unified text
        try:
            generate_text_chunks_and_embeddings.delay(conversation_id)
        except Exception as e:
            logger.warning(f"Failed to schedule chunk+embed task: {e}")

        # Schedule AI tags/comments generation (low token usage)
        try:
            generate_ai_tags.delay(conversation_id)
        except Exception as e:
            logger.warning(f"Failed to schedule AI tags task: {e}")

        # Keep status as PROCESSING since downstream tasks are still running
        # The downstream tasks should mark as COMPLETED when they finish
        update_conversation_status(
            conversation_id,
            ProcessingStatus.PROCESSING,
            processing_time_ms=processing_time_ms,
            stage=ProcessingStage.QUALITY_ASSESSMENT,
            progress=90,
            message="Finalizing embeddings and metadata"
        )

        logger.info(f"Successfully processed conversation {conversation_id} in {processing_time:.2f}s")

        return {
            'success': True,
            'conversation_id': conversation_id,
            'processing_time': processing_time
        }
        
    except Exception as e:
        logger.error(f"Error processing transcript for conversation {conversation_id}: {e}")
        update_conversation_status(
            conversation_id,
            ProcessingStatus.FAILED,
            error_message=str(e),
            stage=ProcessingStage.FAILED,
            progress=100,
            message="Processing failed"
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


# Deprecated task removed: parse_conversation (example-based)
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
        
        # HTML parsing functionality removed - using text parser only
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
        # Generate embeddings using existing utility with dynamic settings
        embeddings_generated = generate_feedme_embeddings(
            conversation_id=conversation_id,
            batch_size=current_settings().feedme_embedding_batch_size
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


@celery_app.task(bind=True, base=CallbackTask, name='app.feedme.tasks.generate_text_chunks_and_embeddings')
def generate_text_chunks_and_embeddings(self, conversation_id: int, max_chunk_chars: int = 1200) -> Dict[str, Any]:
    """Chunk extracted_text and generate Gemini embeddings for each chunk."""
    task_id = self.request.id
    logger.info(f"Chunking + embedding for conversation {conversation_id} (task: {task_id})")
    try:
        client = get_supabase_client()
        # Fetch conversation
        resp = client.client.table('feedme_conversations').select('id, folder_id, extracted_text').eq('id', conversation_id).maybe_single().execute()
        if not getattr(resp, 'data', None):
            raise ValueError("Conversation not found")
        convo = resp.data
        raw_text = (convo.get('extracted_text') or '').strip()
        if not raw_text:
            return { 'success': True, 'conversation_id': conversation_id, 'chunks': 0 }

        # Normalize content for embeddings: prefer plain text without markdown/HTML
        def markdown_to_text(md: str) -> str:
            # Remove code fences
            import re
            s = re.sub(r"```[\s\S]*?```", lambda m: m.group(0).strip('`').strip(), md)
            # Inline code
            s = re.sub(r"`([^`]+)`", r"\1", s)
            # Bold/italic
            s = re.sub(r"\*\*([^*]+)\*\*", r"\1", s)
            s = re.sub(r"__([^_]+)__", r"\1", s)
            s = re.sub(r"\*([^*]+)\*", r"\1", s)
            s = re.sub(r"_([^_]+)_", r"\1", s)
            # Headings
            s = re.sub(r"^#{1,6}\s+", "", s, flags=re.MULTILINE)
            # Links [text](url) -> text (url)
            s = re.sub(r"\[([^\]]+)\]\((https?[^)]+)\)", r"\1 (\2)", s)
            # Images ![alt](url) -> alt (url)
            s = re.sub(r"!\[([^\]]*)\]\((https?[^)]+)\)", r"\1 (\2)", s)
            # Lists markers
            s = re.sub(r"^[\t ]*[-*]\s+", "• ", s, flags=re.MULTILINE)
            s = re.sub(r"^[\t ]*\d+\.\s+", lambda m: f"{m.group(0).strip()} ", s, flags=re.MULTILINE)
            # HTML line breaks
            s = re.sub(r"<br\s*/?>", "\n", s, flags=re.IGNORECASE)
            # Remove remaining HTML tags
            s = re.sub(r"<[^>]+>", "", s)
            # Normalize whitespace
            s = re.sub(r"\r", "\n", s)
            s = re.sub(r"\n{3,}", "\n\n", s)
            return s.strip()

        text = markdown_to_text(raw_text)
        if not text:
            return { 'success': True, 'conversation_id': conversation_id, 'chunks': 0 }

        # Simple chunking by paragraph groups
        paras = [p.strip() for p in text.split('\n\n') if p.strip()]
        chunks: list[str] = []
        buf = []
        cur = 0
        for p in paras:
            if cur + len(p) + 2 > max_chunk_chars and buf:
                chunks.append('\n\n'.join(buf))
                buf = [p]
                cur = len(p)
            else:
                buf.append(p)
                cur += len(p) + 2
        if buf:
            chunks.append('\n\n'.join(buf))

        # Clear existing chunks
        try:
            import asyncio
            # Use sync client; call async wrapper not available here, using direct table ops handled above in sync
            client.client.table('feedme_text_chunks').delete().eq('conversation_id', conversation_id).execute()
        except Exception as e:
            logger.warning(f"Failed to clear old chunks: {e}")

        # Get user's API key if available (from conversation uploader)
        user_api_key = None
        try:
            uploader_resp = client.client.table('feedme_conversations').select('uploaded_by').eq('id', conversation_id).maybe_single().execute()
            if uploader_resp.data and uploader_resp.data.get('uploaded_by'):
                user_api_key = get_user_gemini_api_key_sync(uploader_resp.data['uploaded_by'])
        except Exception as e:
            logger.debug(f"Could not get user API key: {e}")
        
        # Configure Gemini embeddings with user key or fallback to system key
        api_key = user_api_key or current_settings().gemini_api_key
        if not api_key:
            raise ValueError("No Gemini API key available")
        # Initialize Gemini client (handled by _embed_content helper)
        
        from app.core.rate_limiting.agent_wrapper import get_rate_limiter
        from app.core.rate_limiting.exceptions import RateLimitExceededException
        limiter = get_rate_limiter()

        # Insert and embed per chunk with rate limiting
        stored = 0
        model_name = EMBEDDING_MODEL_NAME
        if model_name != EMBEDDING_MODEL_NAME:
            raise ValueError(f"Embedding model must be '{EMBEDDING_MODEL_NAME}' but got '{model_name}'")
        
        for idx, chunk in enumerate(chunks):
            ins = client.client.table('feedme_text_chunks').insert({
                'conversation_id': conversation_id,
                'folder_id': convo.get('folder_id'),
                'chunk_index': idx,
                'content': chunk,
                'metadata': {}
            }).execute()
            if not ins.data:
                continue
            chunk_id = ins.data[0]['id']

            try:
                # Estimate tokens (rough approximation: 1 token per 4 chars)
                estimated_tokens = max(1, len(chunk) // 4)

                # Generate embedding with bucket-based rate limiting
                try:
                    vec = asyncio.run(
                        limiter.execute_with_protection(
                            "internal.embedding",
                            _embed_content,
                            api_key,
                            model_name,
                            chunk,
                            token_count=estimated_tokens,
                        )
                    )
                except RateLimitExceededException as exc:
                    logger.warning(
                        "Embedding rate limit reached, stopping at chunk %s: %s",
                        idx,
                        exc,
                    )
                    break
                
                # Verify dimension based on model
                try:
                    assert_dim(vec, "feedme_text_chunks.embedding")
                except Exception as e:
                    logger.warning(str(e))
                
                # Store embedding
                client.client.table('feedme_text_chunks').update({ 'embedding': vec }).eq('id', chunk_id).execute()
                stored += 1
                
            except Exception as e:
                logger.warning(f"Embedding failed for chunk {chunk_id}: {e}")

        logger.info(f"Created {stored}/{len(chunks)} chunks with embeddings for conversation {conversation_id}")

        # Mark conversation as COMPLETED after embeddings are done
        # (AI tags task runs in parallel and is optional)
        update_conversation_status(
            conversation_id,
            ProcessingStatus.COMPLETED,
            stage=ProcessingStage.COMPLETED,
            progress=100,
            message="Processing completed"
        )

        return { 'success': True, 'conversation_id': conversation_id, 'chunks': stored }
    except Exception as e:
        logger.error(f"Chunk+embed task failed: {e}")
        return { 'success': False, 'conversation_id': conversation_id, 'error': str(e) }


@celery_app.task(bind=True, base=CallbackTask, name='app.feedme.tasks.generate_ai_tags')
def generate_ai_tags(self, conversation_id: int, max_input_chars: int = 4000) -> Dict[str, Any]:
    """Generate concise AI tags and a short comment for a conversation."""
    task_id = self.request.id
    logger.info(f"Generating AI tags for conversation {conversation_id} (task: {task_id})")
    try:
        client = get_supabase_client()
        resp = client.client.table('feedme_conversations').select('extracted_text, metadata, uploaded_by').eq('id', conversation_id).maybe_single().execute()
        if not getattr(resp, 'data', None):
            return { 'success': False, 'error': 'Conversation not found', 'conversation_id': conversation_id }
        row = resp.data
        # Use the full extracted_text to summarize the entire conversation (no hard truncation)
        text = (row.get('extracted_text') or '')
        if not text.strip():
            return { 'success': True, 'conversation_id': conversation_id, 'tags': [] }

        # Configure Gemini
        cached_settings = get_cached_settings()
        fallback_settings = get_settings()
        # Prefer uploader's Gemini key when available
        api_key = None
        try:
            uploader_id = row.get('uploaded_by')
            if uploader_id:
                api_key = get_user_gemini_api_key_sync(uploader_id)
        except Exception as e:
            logger.debug(f"Could not resolve uploader API key: {e}")
        if not api_key:
            api_key = (
                getattr(cached_settings, 'gemini_api_key', None)
                or getattr(fallback_settings, 'gemini_api_key', None)
            )
        if not api_key:
            logger.error("Gemini API key missing for AI tag generation task")
            raise MissingAPIKeyError("Gemini API key missing for AI tag generation")
        # Gemini client initialization handled by _generate_content helper

        config = get_models_config()
        model_name = config.internal["feedme"].model_id

        # Chunked map-reduce summarization to capture the entire conversation
        # Map: summarize each chunk into 3-6 bullet points (no PII). Reduce: produce final JSON with tags and a concise multi-sentence comment.
        def chunk_text(s: str, max_chars: int = 24000) -> list[str]:
            s = s.strip()
            if not s:
                return []
            paras = [p.strip() for p in re.split(r"\n\n+", s) if p.strip()]
            chunks: list[str] = []
            buf: list[str] = []
            cur = 0
            for p in paras:
                # +2 for paragraph spacing preservation
                if cur + len(p) + 2 > max_chars and buf:
                    chunks.append("\n\n".join(buf))
                    buf = [p]
                    cur = len(p)
                else:
                    buf.append(p)
                    cur += len(p) + 2
            if buf:
                chunks.append("\n\n".join(buf))
            return chunks

        # Derive a conservative per-call char budget from token settings (~4 chars per token)
        try:
            per_chunk_chars = int(getattr(fallback_settings, 'feedme_max_tokens_per_chunk', 8000)) * 4
        except Exception:
            per_chunk_chars = 24000
        per_chunk_chars = max(8000, min(per_chunk_chars, 32000))

        from app.core.rate_limiting.agent_wrapper import get_rate_limiter
        from app.core.rate_limiting.exceptions import RateLimitExceededException
        limiter = get_rate_limiter()

        chunks = chunk_text(text, per_chunk_chars)
        map_summaries: list[str] = []

        if len(chunks) <= 1:
            # Single pass with improved strict prompt (concise, no hard length cap)
            single_prompt = (
                "You are summarizing a complete customer-support conversation.\n"
                "Write JSON with: tags (5-7 short keywords) and comment (2-4 sentences, concise) capturing the entire conversation: primary issue, key actions/attempts, and current outcome/follow-ups.\n"
                "Rules: no personal data (names, emails, phone, ticket IDs), neutral tone, no quotes/markdown/citations.\n\n"
                f"TEXT:\n{text}\n\n"
                "Return STRICT JSON only: {\"tags\":[...],\"comment\":\"...\"}."
            )
            try:
                out = asyncio.run(
                    limiter.execute_with_protection(
                        "internal.feedme",
                        _generate_content,
                        api_key,
                        model_name,
                        single_prompt,
                    )
                )
            except RateLimitExceededException as exc:
                logger.warning("Gemini tagging rate limited: %s", exc)
                out = ''
            except Exception as e:
                logger.warning(f"Gemini tagging (single-pass) failed: {e}")
                out = ''
        else:
            # Map stage
            map_prompt = (
                "Summarize the following excerpt of a customer-support conversation into 3-6 concise bullet points that capture issue/context, actions, and outcome.\n"
                "Avoid PII (no names/emails/IDs). Output ONLY bullet points, one per line starting with '- ', no preface or trailing text.\n\n"
            )
            for idx, ck in enumerate(chunks):
                try:
                    txt = asyncio.run(
                        limiter.execute_with_protection(
                            "internal.feedme",
                            _generate_content,
                            api_key,
                            model_name,
                            map_prompt + ck,
                        )
                    )
                    if txt and txt.strip():
                        # Normalize to lines starting with '- '
                        lines = [ln.strip() for ln in txt.strip().splitlines() if ln.strip()]
                        norm = []
                        for ln in lines:
                            if not ln.startswith('- '):
                                ln = f"- {ln.lstrip('-• ')}"
                            norm.append(ln)
                        map_summaries.append("\n".join(norm))
                except RateLimitExceededException as exc:
                    logger.warning("Gemini map stage rate limited: %s", exc)
                    break
                except Exception as e:
                    logger.warning(f"Map summarization failed for chunk {idx+1}/{len(chunks)}: {e}")

            reduce_source = "\n".join(map_summaries).strip()
            reduce_prompt = (
                "You are consolidating bullet points from ALL parts of a single customer-support conversation.\n"
                "Produce STRICT JSON with: tags (5-7 short, lowercase keywords) and comment (2-4 sentences, concise) that captures the entire conversation: primary issue, key actions/attempts, final outcome or current status, and clear follow-ups if any.\n"
                "Rules: no PII (no names/emails/IDs), neutral tone, no markdown/quotes/citations.\n\n"
                f"BULLETS:\n{reduce_source}\n\n"
                "Return only: {\"tags\":[...],\"comment\":\"...\"}."
            )
            try:
                out = asyncio.run(
                    limiter.execute_with_protection(
                        "internal.feedme",
                        _generate_content,
                        api_key,
                        model_name,
                        reduce_prompt,
                    )
                )
            except RateLimitExceededException as exc:
                logger.warning("Gemini reduce stage rate limited: %s", exc)
                out = ''
            except Exception as e:
                logger.warning(f"Gemini tagging (reduce stage) failed: {e}")
                out = ''

        import json
        tags = []
        comment = None
        if out:
            try:
                # Strip common code fences and extract the first JSON object if present
                s = out.strip()
                if s.startswith('```'):
                    s = re.sub(r"^```(?:json|JSON)?\s*", "", s)
                    s = re.sub(r"\s*```$", "", s)
                # Try direct parse; if it fails, attempt to isolate JSON object region
                try:
                    data = json.loads(s)
                except Exception:
                    start = s.find('{')
                    end = s.rfind('}')
                    if start != -1 and end != -1 and end > start:
                        data = json.loads(s[start:end+1])
                    else:
                        raise

                if isinstance(data.get('tags'), list):
                    tags = [str(t)[:32] for t in data['tags'][:7]]
                # If comment missing or not a string, derive a brief note from the text
                raw_comment = data.get('comment') if isinstance(data, dict) else None
                if isinstance(raw_comment, str) and raw_comment.strip():
                    comment = re.sub(r"\s+", " ", raw_comment).strip()
                else:
                    # Derive a short note from the consolidated map summaries if available, else from the text
                    derived = None
                    try:
                        if map_summaries:
                            joined = " ".join(map_summaries)
                            derived = re.sub(r"\s+", " ", joined).strip()
                        else:
                            first_para = re.split(r"\n\n+", text.strip())[0] if text.strip() else ''
                            derived = re.sub(r"\s+", " ", first_para).strip()
                    except Exception:
                        derived = None
                    comment = (derived or 'Auto-tagged summary')
            except Exception:
                # Fallback: simple keyword heuristics
                kw = []
                for k in ['setup','sync','smtp','imap','account','password','login','notification','attachment','crash','upgrade','settings','calendar']:
                    if k in text.lower(): kw.append(k)
                tags = (kw[:7] or ['support'])
                # Use reduce_source if available; otherwise default
                try:
                    fallback_note = None
                    if 'reduce_source' in locals() and reduce_source:
                        fallback_note = re.sub(r"\s+", " ", reduce_source).strip()
                    comment = (fallback_note or 'Auto-tagged summary')
                except Exception:
                    comment = 'Auto-tagged summary'

        # Merge into metadata
        meta = row.get('metadata') or {}
        meta['ai_tags'] = tags
        if comment:
            # Write both keys for compatibility (UI prefers ai_note)
            meta['ai_note'] = comment
            meta['ai_comment'] = comment
        client.client.table('feedme_conversations').update({ 'metadata': meta }).eq('id', conversation_id).execute()

        return { 'success': True, 'conversation_id': conversation_id, 'tags': tags, 'comment': comment }
    except Exception as e:
        logger.error(f"AI tagging task failed: {e}")
        return { 'success': False, 'conversation_id': conversation_id, 'error': str(e) }


@celery_app.task(bind=True, base=CallbackTask, name='app.feedme.tasks.cleanup_approved_pdf')
def cleanup_approved_pdf(self, conversation_id: int) -> Dict[str, Any]:
    """
    Remove PDF content after text has been extracted and approved
    
    Args:
        conversation_id: ID of the conversation to clean up
        
    Returns:
        Dict with cleanup status and size freed
    """
    try:
        logger.info(f"Starting PDF cleanup for conversation {conversation_id}")
        
        # Get Supabase client
        supabase = get_supabase_client()
        
        # Call the cleanup function
        result = supabase.rpc(
            'cleanup_approved_pdf',
            {'conversation_id': conversation_id}
        ).execute()
        
        if result.data:
            logger.info(f"Successfully cleaned PDF for conversation {conversation_id}")
            return {
                'success': True,
                'conversation_id': conversation_id,
                'cleaned': True
            }
        else:
            logger.warning(f"PDF cleanup returned no result for conversation {conversation_id}")
            return {
                'success': False,
                'conversation_id': conversation_id,
                'error': 'No cleanup performed'
            }
            
    except Exception as e:
        logger.error(f"Error cleaning PDF for conversation {conversation_id}: {str(e)}")
        return {
            'success': False,
            'conversation_id': conversation_id,
            'error': str(e)
        }


@celery_app.task(bind=True, base=CallbackTask, name='app.feedme.tasks.cleanup_approved_pdfs_batch')
def cleanup_approved_pdfs_batch(self, limit: int = 100) -> Dict[str, Any]:
    """
    Batch cleanup of approved PDFs
    
    Args:
        limit: Maximum number of PDFs to clean in this batch
        
    Returns:
        Dict with batch cleanup statistics
    """
    try:
        logger.info(f"Starting batch PDF cleanup with limit {limit}")
        
        # Get Supabase client
        supabase = get_supabase_client()
        
        # Call the batch cleanup function
        result = supabase.rpc(
            'cleanup_approved_pdfs_batch',
            {'limit_count': limit}
        ).execute()
        
        if result.data and len(result.data) > 0:
            stats = result.data[0]
            cleaned_count = stats.get('cleaned_count', 0)
            total_size_freed = stats.get('total_size_freed', 0)
            
            logger.info(f"Batch cleanup completed: {cleaned_count} PDFs cleaned, {total_size_freed / 1024 / 1024:.2f} MB freed")
            
            return {
                'success': True,
                'cleaned_count': cleaned_count,
                'total_size_freed': total_size_freed,
                'size_freed_mb': total_size_freed / 1024 / 1024
            }
        else:
            return {
                'success': True,
                'cleaned_count': 0,
                'total_size_freed': 0,
                'size_freed_mb': 0
            }
            
    except Exception as e:
        logger.error(f"Error in batch PDF cleanup: {str(e)}")
        return {
            'success': False,
            'error': str(e)
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
            assert_dim(test_embedding, "health_check")
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
    total_examples: Optional[int] = None,
    stage: Optional[ProcessingStage] = None,
    progress: Optional[int] = None,
    message: Optional[str] = None
):
    """Update conversation processing status and broadcast changes"""
    client = get_supabase_client()

    stage = stage or (
        ProcessingStage.COMPLETED if status == ProcessingStatus.COMPLETED else
        ProcessingStage.FAILED if status == ProcessingStatus.FAILED else
        ProcessingStage.AI_EXTRACTION if status == ProcessingStatus.PROCESSING else
        ProcessingStage.QUEUED
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
        ProcessingStatus.FAILED: "Processing failed"
    }
    message = message or default_messages.get(status, "Processing update")

    metadata_overrides: Dict[str, Any] = {}
    if total_examples is not None:
        metadata_overrides['total_examples'] = total_examples
    if task_id:
        metadata_overrides['task_id'] = task_id

    processed_at = datetime.now(timezone.utc) if status == ProcessingStatus.COMPLETED else None

    try:
        asyncio.run(client.record_processing_update(
            conversation_id=conversation_id,
            status=status.value,
            stage=stage.value,
            progress=progress,
            message=message,
            error_message=error_message,
            processing_time_ms=processing_time_ms,
            metadata_overrides=metadata_overrides,
            processed_at=processed_at
        ))
        logger.info(f"Updated conversation {conversation_id} status to {status.value}")
    except Exception as e:
        logger.error(f"Error recording processing update for conversation {conversation_id}: {e}")

    try:
        asyncio.run(notify_processing_update(ProcessingUpdate(
            conversation_id=conversation_id,
            status=status,
            stage=stage,
            progress=progress,
            message=message,
            processing_time_ms=processing_time_ms,
            error_details=error_message
        )))
    except Exception as e:
        logger.error(f"Failed to broadcast processing update for conversation {conversation_id}: {e}")


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


# =============================================================================
# Zendesk MB_playbook Import (Memory UI)
# =============================================================================

ZENDESK_IMPORT_IMAGE_BUCKET = os.getenv("ZENDESK_MEMORY_BUCKET", "memory-assets").strip() or "memory-assets"


def _strip_html(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"<[^>]+>", " ", text).strip()


def _extract_public_comment_text(comment: dict[str, Any]) -> str:
    body = comment.get("body") or comment.get("html_body") or ""
    if not isinstance(body, str):
        return ""
    return _strip_html(body)


def _extract_last_public_comment_at(comments: list[dict[str, Any]]) -> str | None:
    latest = None
    for comment in comments:
        if not isinstance(comment, dict):
            continue
        if comment.get("public") is not True:
            continue
        created_at = comment.get("created_at")
        if not isinstance(created_at, str):
            continue
        try:
            dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except ValueError:
            continue
        if latest is None or dt > latest[0]:
            latest = (dt, created_at)
    if latest is None:
        return None
    return latest[1]


async def _summarize_ticket_with_llm(
    *,
    ticket_id: str,
    subject: str,
    public_conversation: str,
    log_summary: str,
) -> str:
    from app.agents.unified.provider_factory import build_chat_model, build_summarization_model
    from app.agents.unified.minimax_tools import is_minimax_available

    prompt = (
        "You are summarizing a resolved Zendesk ticket for internal playbook memory.\n"
        "Summarize the public conversation and key troubleshooting details in detailed bullet points.\n"
        "Use as many bullet points as needed to capture important steps, observations, and the resolution.\n"
        "Include concrete troubleshooting actions, errors, settings, and outcomes when present.\n"
        "If a resolution is evident, include it.\n"
        "Do NOT include personal data or email addresses.\n\n"
        f"Ticket ID: {ticket_id}\n"
        f"Subject: {subject}\n\n"
        f"Public conversation:\n{public_conversation}\n\n"
        f"Log findings:\n{log_summary}\n"
    ).strip()

    try:
        if is_minimax_available():
            model = build_chat_model("minimax", "minimax/MiniMax-M2.1", role="summarization")
        else:
            model = build_summarization_model()
        response = await model.ainvoke(prompt)
        text = getattr(response, "content", "") if response is not None else ""
        if isinstance(text, list):
            parts = []
            for part in text:
                if isinstance(part, dict) and part.get("type") == "text":
                    parts.append(str(part.get("text") or ""))
                elif isinstance(part, str):
                    parts.append(part)
            return "\n".join(p for p in parts if p).strip()
        return str(text).strip()
    except Exception as exc:
        logger.debug("zendesk_import_summary_failed ticket_id=%s error=%s", ticket_id, str(exc)[:180])
        return ""


async def _analyze_log_file(
    *,
    file_name: str,
    content: str,
    question: str,
) -> dict[str, Any]:
    from app.agents.unified.tools import log_diagnoser_tool

    result = await log_diagnoser_tool(
        file_name=file_name,
        log_content=content,
        question=question,
    )
    return result if isinstance(result, dict) else {}


@celery_app.task(bind=True, base=CallbackTask, name='app.feedme.tasks.import_zendesk_tagged')
def import_zendesk_tagged(self, tag: str = "mb_playbook", limit: int = 200) -> dict[str, Any]:
    """Queue ingestion of solved/closed Zendesk tickets tagged for MB_playbook learning."""
    async def _run() -> dict[str, Any]:
        from app.integrations.zendesk.client import ZendeskClient, ZendeskRateLimitError
        from app.integrations.zendesk.attachments import (
            fetch_ticket_attachments,
            cleanup_attachments,
        )
        from app.agents.unified.image_store import store_image_bytes
        from app.agents.harness.store import SparrowWorkspaceStore
        from app.memory.title import ensure_memory_title
        from app.memory.memory_ui_service import get_memory_ui_service
        from app.security.pii_redactor import redact_pii, redact_pii_from_dict
        from uuid import uuid5, NAMESPACE_URL

        settings = current_settings()
        if not (settings.zendesk_subdomain and settings.zendesk_email and settings.zendesk_api_token):
            raise RuntimeError("Zendesk credentials missing")

        zc = ZendeskClient(
            subdomain=str(settings.zendesk_subdomain),
            email=str(settings.zendesk_email),
            api_token=str(settings.zendesk_api_token),
            dry_run=bool(getattr(settings, "zendesk_dry_run", True)),
        )

        tag_value = (tag or "mb_playbook").strip()
        ticket_limit = max(1, int(limit))

        queries = [
            f"type:ticket tags:{tag_value} status:solved",
            f"type:ticket tags:{tag_value} status:closed",
        ]
        tickets: list[dict[str, Any]] = []
        for q in queries:
            try:
                batch = await asyncio.to_thread(zc.search_tickets, q, per_page=100, max_pages=10)
                if batch:
                    tickets.extend(batch)
            except ZendeskRateLimitError:
                raise
            except Exception as exc:
                logger.warning("zendesk_search_failed query=%s error=%s", q, str(exc)[:180])

        deduped: dict[str, dict[str, Any]] = {}
        for item in tickets:
            tid = item.get("id")
            if tid is None:
                continue
            deduped[str(tid)] = item
        ticket_rows = list(deduped.values())[:ticket_limit]

        supabase = get_supabase_client()
        service = get_memory_ui_service()
        agent_id = getattr(settings, "memory_ui_agent_id", "sparrow") or "sparrow"
        tenant_id = getattr(settings, "memory_ui_tenant_id", "mailbot") or "mailbot"

        imported = skipped = failed = 0

        for row in ticket_rows:
            ticket_id = str(row.get("id") or "")
            if not ticket_id:
                continue

            memory_id = str(uuid5(NAMESPACE_URL, f"zendesk-ticket:{ticket_id}"))

            try:
                ticket = await asyncio.to_thread(zc.get_ticket, ticket_id)
            except Exception:
                ticket = row if isinstance(row, dict) else {}

            subject = str(ticket.get("subject") or row.get("subject") or "").strip()
            description = str(ticket.get("description") or "").strip()
            tags = ticket.get("tags") if isinstance(ticket, dict) else None
            tags_list = [t for t in tags if isinstance(t, str)] if isinstance(tags, list) else []

            try:
                comments = await asyncio.to_thread(zc.get_ticket_comments_all, ticket_id, public_only=True)
            except Exception:
                comments = []
            last_public_comment_at = _extract_last_public_comment_at(comments or [])

            public_comments: list[str] = []
            for comment in comments or []:
                if not isinstance(comment, dict):
                    continue
                text = _extract_public_comment_text(comment)
                if text:
                    public_comments.append(text)

            public_conversation_lines: list[str] = []
            for idx, comment_text in enumerate(public_comments, start=1):
                cleaned = redact_pii(comment_text).strip()
                if cleaned:
                    public_conversation_lines.append(f"### Public Comment {idx}\n{cleaned}")
            if not public_conversation_lines and description:
                cleaned_description = redact_pii(description).strip()
                if cleaned_description:
                    public_conversation_lines = [f"### Ticket Description\n{cleaned_description}"]

            public_conversation = "\n\n".join(public_conversation_lines).strip()

            attachments = []
            image_assets: list[dict[str, Any]] = []
            log_findings: list[dict[str, Any]] = []
            try:
                attachments = await asyncio.to_thread(
                    fetch_ticket_attachments,
                    ticket_id,
                    allowed_extensions=(".log", ".txt", ".png", ".jpg", ".jpeg", ".gif", ".webp"),
                    public_only=True,
                )

                for att in attachments:
                    if not att.local_path:
                        continue
                    name = att.file_name or "attachment"
                    ext = (name or "").lower()
                    if att.content_type and att.content_type.startswith("image/"):
                        try:
                            with open(att.local_path, "rb") as f:
                                data = f.read()
                            stored = await store_image_bytes(
                                data,
                                mime_type=att.content_type or "image/png",
                                bucket=ZENDESK_IMPORT_IMAGE_BUCKET,
                                public=False,
                                path_prefix=f"zendesk/{ticket_id}",
                            )
                            image_assets.append(
                                {
                                    "file_name": name,
                                    "bucket": stored.bucket,
                                    "path": stored.path,
                                    "mime_type": stored.mime_type,
                                    "width": stored.width,
                                    "height": stored.height,
                                }
                            )
                        except Exception as exc:
                            logger.warning("zendesk_import_image_store_failed ticket_id=%s file=%s error=%s", ticket_id, name, str(exc)[:180])
                    elif ext.endswith((".log", ".txt")):
                        try:
                            with open(att.local_path, "r", encoding="utf-8", errors="ignore") as f:
                                raw = f.read(12000)
                            if raw:
                                question = f"Summarize the most relevant errors for ticket {ticket_id}: {subject}"
                                analysis = await _analyze_log_file(
                                    file_name=name,
                                    content=raw,
                                    question=question,
                                )
                                summary = str(analysis.get("overall_summary") or "").strip()
                                if summary:
                                    log_findings.append(
                                        {
                                            "file_name": name,
                                            "summary": redact_pii(summary),
                                            "priority_concerns": analysis.get("priority_concerns") or [],
                                            "relevant_log_sections": analysis.get("relevant_log_sections") or [],
                                        }
                                    )
                        except Exception as exc:
                            logger.warning("zendesk_import_log_analyze_failed ticket_id=%s file=%s error=%s", ticket_id, name, str(exc)[:180])
            finally:
                if attachments:
                    cleanup_attachments(attachments)

            log_summary_lines = []
            for item in log_findings:
                line = f"- {item.get('file_name')}: {item.get('summary')}"
                log_summary_lines.append(line)
            log_summary = "\n".join(log_summary_lines).strip()

            summary_text = await _summarize_ticket_with_llm(
                ticket_id=ticket_id,
                subject=subject,
                public_conversation=public_conversation,
                log_summary=log_summary,
            )
            summary_text = redact_pii(summary_text)

            subdomain = str(settings.zendesk_subdomain).strip()
            zendesk_url = (
                f"https://{subdomain}.zendesk.com/agent/tickets/{ticket_id}" if subdomain else ""
            )

            lines: list[str] = []
            if subject:
                lines.append(f"Zendesk Ticket {ticket_id}: {subject}")
            else:
                lines.append(f"Zendesk Ticket {ticket_id}")
            if zendesk_url:
                lines.append(f"Zendesk URL: {zendesk_url}")
            lines.append("")
            if summary_text:
                lines.append("## Summary")
                lines.append(summary_text)
                lines.append("")

            if public_conversation:
                lines.append("## Public conversation (full)")
                lines.append(public_conversation)
                lines.append("")

            if log_findings:
                lines.append("## Log findings")
                for finding in log_findings:
                    lines.append(f"- **{finding.get('file_name')}**: {finding.get('summary')}")
                    sections = finding.get("relevant_log_sections") or []
                    for section in sections[:2]:
                        if isinstance(section, dict):
                            content = section.get("content")
                            line_nums = section.get("line_numbers")
                            if content:
                                snippet = redact_pii(str(content))
                                if line_nums:
                                    lines.append(f"  - ({line_nums}) {snippet}")
                                else:
                                    lines.append(f"  - {snippet}")
                lines.append("")

            if image_assets:
                lines.append("## Images (admin-only)")
                for asset in image_assets:
                    bucket = asset.get("bucket")
                    path = asset.get("path")
                    name = asset.get("file_name") or "attachment"
                    if bucket and path:
                        lines.append(f"- {name}")
                        lines.append(f"![{name}](memory-asset://{bucket}/{path})")
                lines.append("")

            content = "\n".join(lines).strip()
            if not content:
                skipped += 1
                continue

            metadata = {
                "source": "zendesk_mb_playbook",
                "zendesk_ticket_id": ticket_id,
                "zendesk_url": zendesk_url,
                "tags": tags_list,
                "image_assets": image_assets,
                "log_findings": log_findings,
                "last_public_comment_at": last_public_comment_at,
                "imported_at": datetime.now(timezone.utc).isoformat(),
            }

            metadata = redact_pii_from_dict(metadata)
            metadata = ensure_memory_title(metadata, content=content)

            try:
                embedding = await service.generate_embedding(content)
            except Exception as exc:
                logger.warning("zendesk_import_embedding_failed ticket_id=%s error=%s", ticket_id, str(exc)[:180])
                failed += 1
                continue

            payload = {
                "id": memory_id,
                "content": redact_pii(content),
                "metadata": metadata,
                "source_type": "manual",
                "agent_id": agent_id,
                "tenant_id": tenant_id,
                "review_status": "pending_review",
                "confidence_score": 0.6,
                "embedding": embedding,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }

            try:
                await supabase._exec(
                    lambda: supabase.client.table("memories").insert(payload).execute()
                )
            except Exception as exc:
                msg = str(exc).lower()
                if "duplicate key" in msg or "unique constraint" in msg or "23505" in msg:
                    skipped += 1
                    continue
                logger.warning("zendesk_import_insert_failed ticket_id=%s error=%s", ticket_id, str(exc)[:180])
                failed += 1
                continue

            try:
                store = SparrowWorkspaceStore(session_id=f"zendesk-{ticket_id}")
                await store.cleanup_session_data()
            except Exception as exc:
                logger.debug("zendesk_import_cleanup_failed ticket_id=%s error=%s", ticket_id, str(exc)[:180])

            imported += 1

        return {
            "imported": imported,
            "skipped": skipped,
            "failed": failed,
            "tag": tag_value,
        }

    return asyncio.run(_run())


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
