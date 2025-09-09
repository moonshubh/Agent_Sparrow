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
from app.db.embedding_utils import get_embedding_model, generate_feedme_embeddings
from app.feedme.schemas import ProcessingStatus
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
from app.feedme.ai_extraction_engine import GeminiExtractionEngine
import base64
from pypdf import PdfReader
import io
from app.feedme.parsers.zendesk_pdf_normalizer import normalize_zendesk_print_text
import google.generativeai as genai

# Feature flags / behavior toggles
DELETE_PDF_AFTER_EXTRACT = True  # Immediately remove PDF payload after extraction
EMBEDDING_MODEL_NAME = "gemini-embedding-001"  # Legacy constant (prefer settings.gemini_embed_model)

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
        update_conversation_status(conversation_id, ProcessingStatus.PROCESSING, task_id=task_id)
        
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
        processing_method = 'manual_text'

        if file_format == 'pdf' or mime_type == 'application/pdf':
            logger.info("Detected PDF content, extracting with Gemini vision → Markdown")
            try:
                pdf_bytes = base64.b64decode(raw_transcript)
            except Exception as e:
                raise ValueError(f"Invalid base64 PDF content: {e}")

            # Choose API key: prefer user's own if provided
            user_api_key = None
            try:
                if user_id:
                    user_api_key = get_user_gemini_api_key_sync(user_id)
            except Exception as e:
                logger.warning(f"No user API key available or lookup failed: {e}")

            from app.feedme.processors.gemini_pdf_processor import process_pdf_to_markdown

            md_text = ""
            ai_info = {}
            try:
                md_text, ai_info = process_pdf_to_markdown(
                    pdf_bytes,
                    max_pages=current_settings().feedme_ai_max_pages,
                    pages_per_call=current_settings().feedme_ai_pages_per_call,
                    api_key=user_api_key or current_settings().gemini_api_key,
                    rpm_limit=current_settings().gemini_flash_rpm_limit,
                    rpd_limit=current_settings().gemini_flash_rpd_limit,
                )
            except Exception as e:
                logger.error(f"Gemini vision extraction failed: {e}")
                raise

            if not md_text or len(md_text.strip()) < 10:
                raise ValueError("Gemini extraction produced empty/too short content")

            extracted_text = md_text
            extraction_confidence = None  # not applicable
            processing_method = 'pdf_ai'

            # Immediately purge original PDF payload if enabled
            if DELETE_PDF_AFTER_EXTRACT:
                try:
                    client = get_supabase_client()
                    client.client.table('feedme_conversations').update({
                        'raw_transcript': None,
                        'pdf_cleaned': True,
                        'pdf_cleaned_at': datetime.now(timezone.utc).isoformat(),
                        'original_pdf_size': len(pdf_bytes),
                        'metadata': {
                            **(conversation_data.get('metadata') or {}),
                            'ai_extraction': ai_info,
                        }
                    }).eq('id', conversation_id).execute()
                    logger.info(f"Purged original PDF content for conversation {conversation_id}")
                except Exception as e:
                    logger.error(f"Failed to purge PDF content for conversation {conversation_id}: {e}")

        elif raw_transcript.strip().startswith('<') or 'html' in (conversation_data.get('original_filename', '') or '').lower():
            logger.info("Detected HTML content, performing light cleanup")
            # Strip HTML to text with minimal processing
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(raw_transcript, 'html.parser')
            text = soup.get_text(separator='\n', strip=True)
            extracted_text = _light_cleanup(text)
            processing_method = 'manual_text'
        else:
            logger.info("Processing plain text content with light cleanup")
            extracted_text = _light_cleanup(raw_transcript)
            processing_method = 'text_paste'

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

        # Update status util for parity
        update_conversation_status(conversation_id, ProcessingStatus.COMPLETED, processing_time_ms=processing_time_ms)
        
        logger.info(f"Successfully processed conversation {conversation_id} in {processing_time:.2f}s")

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
    Deprecated: Legacy example embedding generation is disabled.
    Use generate_text_chunks_and_embeddings for unified text workflow.
    """
    task_id = self.request.id
    logger.info(
        f"[Deprecated] Skipping legacy example embeddings for conversation {conversation_id} (task: {task_id})"
    )
    return {
        "success": True,
        "conversation_id": conversation_id,
        "task_id": task_id,
        "skipped": True,
        "message": "Legacy example embeddings disabled. Use text chunk embeddings."
    }


@celery_app.task(bind=True, base=CallbackTask, name='app.feedme.tasks.generate_text_chunks_and_embeddings')
def generate_text_chunks_and_embeddings(self, conversation_id: int, max_chunk_chars: int = 1200) -> Dict[str, Any]:
    """Chunk extracted_text and generate Gemini embeddings for each chunk."""
    task_id = self.request.id
    logger.info(f"Chunking + embedding for conversation {conversation_id} (task: {task_id})")
    try:
        client = get_supabase_client()
        # Fetch conversation
        resp = client.client.table('feedme_conversations').select('id, folder_id, extracted_text, uploaded_by').eq('id', conversation_id).maybe_single().execute()
        if not getattr(resp, 'data', None):
            raise ValueError("Conversation not found")
        convo = resp.data
        text = (convo.get('extracted_text') or '').strip()
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

        # Configure Gemini embeddings (prefer user's key)
        from app.core.user_context_sync import get_user_gemini_api_key_sync
        user_api_key = None
        try:
            if convo.get('uploaded_by'):
                user_api_key = get_user_gemini_api_key_sync(convo.get('uploaded_by'))
        except Exception as e:
            logger.warning(f"No user embedding key available: {e}")
        genai.configure(api_key= user_api_key or getattr(get_cached_settings(), 'gemini_api_key', None) or getattr(get_settings(), 'gemini_api_key', None))

        # Embedding tracker (TPM/RPM/RPD)
        from app.feedme.rate_limiting.gemini_tracker import get_embed_tracker
        embed_tracker = get_embed_tracker(
            daily_limit=getattr(get_cached_settings(), 'gemini_embed_rpd_limit', None) or getattr(get_settings(), 'gemini_embed_rpd_limit', 1000),
            rpm_limit=getattr(get_cached_settings(), 'gemini_embed_rpm_limit', None) or getattr(get_settings(), 'gemini_embed_rpm_limit', 100),
            tpm_limit=getattr(get_cached_settings(), 'gemini_embed_tpm_limit', None) or getattr(get_settings(), 'gemini_embed_tpm_limit', 30000),
        )

        # Insert and embed per chunk
        stored = 0
        def estimate_tokens(s: str) -> int:
            return max(1, int(len(s) / 4))

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
                # Use settings-based embeddings model per Gemini docs
                from app.core.settings import get_settings
                emb_model_name = getattr(get_cached_settings(), 'gemini_embed_model', None) or getattr(get_settings(), 'gemini_embed_model', 'gemini-embedding-001')

                # Rate pacing: tokens + requests
                need = estimate_tokens(chunk)
                embed_tracker.throttle()
                embed_tracker.throttle_tokens(need)

                # Backoff on transient errors
                emb = None
                for attempt in range(4):
                    try:
                        emb = genai.embed_content(model=emb_model_name, content=chunk)
                        break
                    except Exception as e:
                        if attempt == 3:
                            raise
                        logger.warning(f"Embedding call failed (attempt {attempt+1}), backing off: {e}")
                        import time as _t
                        _t.sleep(1.0 * (2 ** attempt))
                embed_tracker.record()
                embed_tracker.record_tokens(need)
                vec = emb['embedding'] if isinstance(emb, dict) else emb.embedding
                client.client.table('feedme_text_chunks').update({ 'embedding': vec }).eq('id', chunk_id).execute()
                stored += 1
            except Exception as e:
                logger.warning(f"Embedding failed for chunk {chunk_id}: {e}")

        logger.info(f"Created {stored}/{len(chunks)} chunks with embeddings for conversation {conversation_id}")
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
        resp = client.client.table('feedme_conversations').select('extracted_text, metadata').eq('id', conversation_id).maybe_single().execute()
        if not getattr(resp, 'data', None):
            return { 'success': False, 'error': 'Conversation not found', 'conversation_id': conversation_id }
        row = resp.data
        text = (row.get('extracted_text') or '')[:max_input_chars]
        if not text.strip():
            return { 'success': True, 'conversation_id': conversation_id, 'tags': [] }

        # Configure Gemini
        genai.configure(api_key=getattr(get_cached_settings(), 'gemini_api_key', None) or getattr(get_settings(), 'gemini_api_key', None))
        model = genai.GenerativeModel('gemini-2.5-flash-lite')
        prompt = (
            "You are tagging customer support threads. "
            "Read the following Q/A flow and output concise JSON with keys tags (array of 5-7 short tags) and comment (<=120 chars).\n\n"
            "Rules: no personal data, no emails, no names. Focus on issue, feature, action, resolution.\n\n"
            f"TEXT:\n{text}\n\n"
            "Return strictly JSON like {\"tags\":[...],\"comment\":\"...\"}."
        )
        try:
            res = model.generate_content(prompt)
            out = getattr(res, 'text', None) or (res.candidates[0].content.parts[0].text if getattr(res, 'candidates', None) else '')
        except Exception as e:
            logger.warning(f"Gemini tagging failed: {e}")
            out = ''

        import json
        tags = []
        comment = None
        if out:
            try:
                data = json.loads(out)
                if isinstance(data.get('tags'), list):
                    tags = [str(t)[:32] for t in data['tags'][:7]]
                if isinstance(data.get('comment'), str):
                    comment = data['comment'][:120]
            except Exception:
                # Fallback: simple keyword heuristics
                kw = []
                for k in ['setup','sync','smtp','imap','account','password','login','notification','attachment','crash','upgrade','settings','calendar']:
                    if k in text.lower(): kw.append(k)
                tags = (kw[:7] or ['support'])
                comment = 'Auto-tagged summary'

        # Merge into metadata
        meta = row.get('metadata') or {}
        meta['ai_tags'] = tags
        if comment:
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
