"""
Utilities for generating embeddings for content in the mailbird_knowledge table
and FeedMe examples, and performing similarity searches using pgvector.

This script handles subtask 8.3 of Task 8 and FeedMe similarity search integration.

Prerequisites:
- PostgreSQL server running with the mailbird_knowledge and feedme_examples tables and pgvector.
- Data imported by data_importer.py (or similar).
- FeedMe tables created by migration 002_create_feedme_tables.sql
- Environment variables for DB connection and Gemini API Key set in a .env file
  at the project root:
  - DATABASE_URL (e.g., postgresql://user:password@host:port/dbname) OR
  - DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME (as fallback)
  - GEMINI_API_KEY
"""
import os
import logging
from functools import lru_cache

import psycopg2
import psycopg2.extras as psycopg2_extras # For NamedTupleCursor, aliased to avoid conflict
from pgvector.psycopg2 import register_vector
from dotenv import load_dotenv
from langchain_google_genai import embeddings as gen_embeddings
from langchain_core.embeddings import Embeddings
from langchain_core.embeddings.fake import FakeEmbeddings
from typing import List, Optional, Dict, Any # Removed Tuple
from pydantic import BaseModel, ConfigDict # Added Pydantic BaseModel

from app.core.settings import settings
from app.db.supabase.client import get_supabase_client
from app.db.embedding_config import MODEL_NAME as EMB_MODEL_NAME_SOT, EXPECTED_DIM as EXPECTED_EMBEDDING_DIM, assert_dim

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables from .env file in the project root
# Determine the project root by going up two levels from this script's directory
# (app/db/ -> app/ -> project_root)
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(PROJECT_ROOT / '.env')

# --- Configuration ---
GEMINI_API_KEY = settings.gemini_api_key
_cfg_name = settings.gemini_embed_model or EMB_MODEL_NAME_SOT
if _cfg_name != EMB_MODEL_NAME_SOT:
    raise ValueError(f"Embedding model must be '{EMB_MODEL_NAME_SOT}' but got '{_cfg_name}'")
EMBEDDING_MODEL_NAME = _cfg_name

# --- Helpers ---


def _prefer_fake_embeddings() -> bool:
    if os.getenv("USE_REAL_EMBEDDINGS", "").lower() in {"1", "true", "yes"}:
        return False
    if os.getenv("USE_FAKE_EMBEDDINGS", "").lower() in {"1", "true", "yes"}:
        return True
    return bool(settings.skip_auth)


def _allow_embedding_fallback() -> bool:
    if os.getenv("USE_FAKE_EMBEDDINGS", "").lower() in {"1", "true", "yes"}:
        return True
    if os.getenv("USE_REAL_EMBEDDINGS", "").lower() in {"1", "true", "yes"}:
        return False
    return bool(settings.skip_auth)


@lru_cache(maxsize=1)
def _fake_embeddings() -> Embeddings:
    return FakeEmbeddings(size=EXPECTED_EMBEDDING_DIM)


class ResilientEmbeddings(Embeddings):
    """Wrap an embedding model with a fallback implementation for resilience."""

    def __init__(self, primary: Embeddings, fallback: Embeddings, *, allow_fallback: bool, prefer_fallback: bool) -> None:
        self._primary = primary
        self._fallback = fallback
        self._allow_fallback = allow_fallback
        self._prefer_fallback = prefer_fallback

    def _should_use_fallback(self, exc: Exception, context: str) -> bool:
        if not self._allow_fallback:
            raise exc
        logger.warning("Primary embedding %s failed: %s -- using fallback", context, exc)
        return True

    def embed_query(self, text: str) -> List[float]:
        if self._prefer_fallback:
            return self._fallback.embed_query(text)
        try:
            return self._primary.embed_query(text)
        except Exception as exc:  # pragma: no cover - defensive
            if self._should_use_fallback(exc, "embed_query"):
                return self._fallback.embed_query(text)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        if self._prefer_fallback:
            return self._fallback.embed_documents(texts)
        try:
            return self._primary.embed_documents(texts)
        except Exception as exc:  # pragma: no cover - defensive
            if self._should_use_fallback(exc, "embed_documents"):
                return self._fallback.embed_documents(texts)

    async def aembed_documents(self, texts: List[str]) -> List[List[float]]:  # pragma: no cover - async path
        if self._prefer_fallback:
            fallback_async = getattr(self._fallback, "aembed_documents", None)
            if fallback_async is not None:
                return await fallback_async(texts)
            return self._fallback.embed_documents(texts)
        primary_async = getattr(self._primary, "aembed_documents", None)
        if primary_async is not None:
            try:
                return await primary_async(texts)
            except Exception as exc:
                if not self._should_use_fallback(exc, "aembed_documents"):
                    raise
        else:
            try:
                return self._primary.embed_documents(texts)
            except Exception as exc:
                if not self._should_use_fallback(exc, "embed_documents"):
                    raise

        fallback_async = getattr(self._fallback, "aembed_documents", None)
        if fallback_async is not None:
            return await fallback_async(texts)
        return self._fallback.embed_documents(texts)


# --- Database Connection (Updated for FeedMe v3.0 - Supabase Only) ---
def get_db_connection():
    """
    Legacy function - no longer supported.
    Use Supabase client for all database operations.
    """
    raise NotImplementedError("Local DB connections no longer supported. Use Supabase client instead.")

# --- Embedding Generation ---
@lru_cache(maxsize=1)
def get_embedding_model() -> Embeddings:
    """Initializes and returns the embedding model with local fallback support."""

    allow_fallback = _allow_embedding_fallback()
    prefer_fallback = _prefer_fake_embeddings()
    fallback = _fake_embeddings() if (allow_fallback or prefer_fallback) else None

    if not GEMINI_API_KEY:
        if not (allow_fallback or prefer_fallback):
            logger.error("GEMINI_API_KEY not found in environment variables.")
            raise ValueError("GEMINI_API_KEY not set.")
        logger.warning("GEMINI_API_KEY missing; using FakeEmbeddings fallback")
        return fallback  # type: ignore[return-value]

    try:
        primary = gen_embeddings.GoogleGenerativeAIEmbeddings(
            model=EMBEDDING_MODEL_NAME,
            google_api_key=GEMINI_API_KEY,
        )
        logger.info(
            "Initialized embedding model %s (expected_dim=%s)",
            EMBEDDING_MODEL_NAME,
            EXPECTED_EMBEDDING_DIM,
        )
    except Exception as exc:
        logger.error("Failed to initialize embedding model: %s", exc)
        if not (allow_fallback or prefer_fallback) or fallback is None:
            raise
        logger.warning("Using FakeEmbeddings fallback due to initialization failure")
        return fallback

    if fallback is None:
        return primary

    return ResilientEmbeddings(
        primary,
        fallback,
        allow_fallback=allow_fallback,
        prefer_fallback=prefer_fallback,
    )


def _embedding_has_expected_dim(vector: List[float], context: str) -> bool:
    try:
        assert_dim(vector, context)
        return True
    except Exception:
        return False

def generate_embeddings_for_pending_content(batch_size: int = 10) -> int:
    """Fetches content without embeddings, generates embeddings, and updates the DB."""
    logger.info("Starting embedding generation for pending content...")
    conn = None
    updated_count = 0
    failed_count = 0

    try:
        conn = get_db_connection()
        if not conn:
            return
        
        emb_model = get_embedding_model()

        with conn.cursor(cursor_factory=psycopg2_extras.NamedTupleCursor) as cur:
            # Fetch rows where embedding is NULL
            cur.execute("SELECT id, COALESCE(markdown, content) as text_content FROM mailbird_knowledge WHERE embedding IS NULL LIMIT %s;", (batch_size,))
            records_to_process = cur.fetchall()

            if not records_to_process:
                logger.info("No content found requiring embedding generation.")
                return

            logger.info(f"Found {len(records_to_process)} records to process for embeddings.")

            for record in records_to_process:
                try:
                    logger.debug(f"Processing record ID: {record.id}")
                    if not record.text_content or not isinstance(record.text_content, str) or not record.text_content.strip():
                        logger.warning(f"Skipping record ID {record.id} due to missing, invalid, or empty text_content.")
                        failed_count += 1 # Count as failed if we can't process it
                        continue

                    text_to_embed = record.text_content
                    MAX_CHARS_FOR_EMBEDDING = 15000 

                    if len(text_to_embed) > MAX_CHARS_FOR_EMBEDDING:
                        original_length = len(text_to_embed)
                        text_to_embed = text_to_embed[:MAX_CHARS_FOR_EMBEDDING]
                        logger.warning(f"Record ID {record.id}: Content truncated for embedding. Original: {original_length} chars, Truncated: {len(text_to_embed)} chars.")
                    
                    embedding_vector = emb_model.embed_query(text_to_embed)
                    if not _embedding_has_expected_dim(embedding_vector, "generate_embeddings_for_pending_content"):
                        conn.rollback()
                        logger.error(
                            "Skipping record %s due to embedding dimension mismatch",
                            record.id,
                        )
                        failed_count += 1
                        continue
                    
                    update_sql = "UPDATE mailbird_knowledge SET embedding = %s WHERE id = %s;"
                    # Use the main cursor 'cur' directly for the update, no need for 'update_cur'
                    cur.execute(update_sql, (embedding_vector, record.id))
                    conn.commit() # Commit after each successful update
                    logger.info(f"Successfully generated and stored embedding for record ID: {record.id}")
                    updated_count += 1
                
                except Exception as e:
                    conn.rollback() # Rollback on any error for this specific record
                    logger.error(f"Error processing record ID {record.id}: {e}")
                    failed_count += 1
        
        logger.info(f"--- Embedding Generation Summary ---")
        logger.info(f"Successfully updated: {updated_count} records")
        logger.info(f"Failed to update: {failed_count} records")
        logger.info(f"Total processed in this batch: {len(records_to_process)} records")
        return updated_count

    except Exception as e:
        logger.error(f"An error occurred during embedding generation: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()
            logger.info("Database connection closed after embedding generation.")

# --- Similarity Search ---
class SearchResult(BaseModel):
    id: int
    url: str
    markdown: Optional[str] = None
    content: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    similarity_score: float # Cosine similarity, not distance
    source_type: str = "knowledge_base"  # Source identifier

    model_config = ConfigDict(from_attributes=True)  # Updated for Pydantic v2


class FeedMeSearchResult(BaseModel):
    """Search result from FeedMe examples"""
    id: int
    conversation_id: int
    conversation_title: str
    question_text: str
    answer_text: str
    context_before: Optional[str] = None
    context_after: Optional[str] = None
    tags: List[str] = []
    issue_type: Optional[str] = None
    resolution_type: Optional[str] = None
    similarity_score: float # Cosine similarity, not distance
    confidence_score: float
    usefulness_score: float
    source_type: str = "feedme"  # Source identifier

    model_config = ConfigDict(from_attributes=True)  # Updated for Pydantic v2


class CombinedSearchResult(BaseModel):
    """Unified search result that can represent both KB and FeedMe results"""
    id: int
    source_type: str  # "knowledge_base" or "feedme"
    title: str
    content: str
    url: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    similarity_score: float
    additional_data: Optional[Dict[str, Any]] = None  # Source-specific extra data

    model_config = ConfigDict(from_attributes=True)  # Updated for Pydantic v2

def find_similar_documents(query: str, top_k: int = 5) -> List[SearchResult]:
    """Finds documents similar to the query using pgvector cosine similarity."""
    logger.info(f"Performing similarity search for query: '{query[:50]}...' with top_k={top_k}")
    conn = None
    results: List[SearchResult] = []

    if not query:
        logger.warning("Similarity search query is empty. Returning no results.")
        return results

    try:
        conn = get_db_connection()
        if not conn:
            return results
        
        emb_model = get_embedding_model()
        query_embedding = emb_model.embed_query(query)
        if not _embedding_has_expected_dim(query_embedding, "find_similar_feedme_examples"):
            return results
        if not _embedding_has_expected_dim(query_embedding, "find_similar_documents"):
            return results

        # <=> is cosine distance (0=identical, 1=orthogonal, 2=opposite)
        # 1 - (cosine distance) = cosine similarity (1=identical, 0=orthogonal, -1=opposite)
        # We want higher similarity scores to be better.
        sql = """
        SELECT 
            id, 
            url, 
            markdown, 
            content, 
            metadata, 
            1 - (embedding <=> %s::vector) AS similarity_score
        FROM mailbird_knowledge
        WHERE embedding IS NOT NULL
        ORDER BY similarity_score DESC
        LIMIT %s;
        """
        with conn.cursor(cursor_factory=psycopg2_extras.NamedTupleCursor) as cur:
            cur.execute(sql, (query_embedding, top_k))
            fetched_records = cur.fetchall()
            results = [SearchResult(**record._asdict()) for record in fetched_records]
            logger.info(f"Found {len(results)} similar documents.")
            for res in results:
                logger.debug(f"  ID: {res.id}, URL: {res.url}, Score: {res.similarity_score:.4f}")

    except Exception as e:
        logger.error(f"Error during similarity search: {e}")
    finally:
        if conn:
            conn.close()
            logger.info("Database connection closed after similarity search.")
    
    return results


def find_similar_feedme_examples(
    query: str, 
    top_k: int = 5,
    min_similarity: float = 0.7,
    issue_types: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
    include_inactive: bool = False
) -> List[FeedMeSearchResult]:
    """
    Finds FeedMe examples similar to the query using pgvector cosine similarity.
    
    Args:
        query: Search query text
        top_k: Maximum number of results to return
        min_similarity: Minimum similarity threshold (0.0 to 1.0)
        issue_types: Filter by specific issue types
        tags: Filter by specific tags
        include_inactive: Whether to include inactive examples
        
    Returns:
        List of FeedMe search results sorted by similarity score
    """
    logger.info(f"Performing FeedMe similarity search for query: '{query[:50]}...' with top_k={top_k}")
    conn = None
    results: List[FeedMeSearchResult] = []

    if not query:
        logger.warning("FeedMe similarity search query is empty. Returning no results.")
        return results

    try:
        conn = get_db_connection()
        if not conn:
            return results
        
        emb_model = get_embedding_model()
        query_embedding = emb_model.embed_query(query)

        # Build filter conditions
        conditions = ["fe.combined_embedding IS NOT NULL"]
        params = [query_embedding]
        
        if not include_inactive:
            conditions.append("fe.is_active = true")
        
        if issue_types:
            conditions.append("fe.issue_type = ANY(%s)")
            params.append(issue_types)
        
        if tags:
            conditions.append("fe.tags && %s")
            params.append(tags)
        
        # Add similarity threshold
        conditions.append("1 - (fe.combined_embedding <=> %s::vector) >= %s")
        params.extend([query_embedding, min_similarity])
        
        # Add top_k limit
        params.append(top_k)

        where_clause = " AND ".join(conditions)
        
        sql = f"""
        SELECT 
            fe.id,
            fe.conversation_id,
            fc.title as conversation_title,
            fe.question_text,
            fe.answer_text,
            fe.context_before,
            fe.context_after,
            fe.tags,
            fe.issue_type,
            fe.resolution_type,
            1 - (fe.combined_embedding <=> %s::vector) AS similarity_score,
            fe.confidence_score,
            fe.usefulness_score
        FROM feedme_examples fe
        JOIN feedme_conversations fc ON fe.conversation_id = fc.id
        WHERE {where_clause}
        ORDER BY similarity_score DESC
        LIMIT %s;
        """

        with conn.cursor(cursor_factory=psycopg2_extras.NamedTupleCursor) as cur:
            cur.execute(sql, params)
            fetched_records = cur.fetchall()
            
            for record in fetched_records:
                result = FeedMeSearchResult(
                    id=record.id,
                    conversation_id=record.conversation_id,
                    conversation_title=record.conversation_title,
                    question_text=record.question_text,
                    answer_text=record.answer_text,
                    context_before=record.context_before,
                    context_after=record.context_after,
                    tags=list(record.tags) if record.tags else [],
                    issue_type=record.issue_type,
                    resolution_type=record.resolution_type,
                    similarity_score=float(record.similarity_score),
                    confidence_score=float(record.confidence_score),
                    usefulness_score=float(record.usefulness_score)
                )
                results.append(result)
            
            logger.info(f"Found {len(results)} similar FeedMe examples.")
            for res in results:
                logger.debug(f"  ID: {res.id}, Conversation: {res.conversation_title}, Score: {res.similarity_score:.4f}")

    except Exception as e:
        logger.error(f"Error during FeedMe similarity search: {e}")
    finally:
        if conn:
            conn.close()
            logger.info("Database connection closed after FeedMe similarity search.")
    
    return results


def find_combined_similar_content(
    query: str,
    top_k_total: int = 10,
    kb_weight: float = 0.6,
    feedme_weight: float = 0.4,
    min_kb_similarity: float = 0.25,
    min_feedme_similarity: float = 0.7
) -> List[CombinedSearchResult]:
    """
    Performs combined similarity search across both knowledge base and FeedMe examples.
    
    Args:
        query: Search query text
        top_k_total: Total number of results to return
        kb_weight: Weight for knowledge base results (0.0 to 1.0)
        feedme_weight: Weight for FeedMe results (0.0 to 1.0)
        min_kb_similarity: Minimum similarity threshold for KB results
        min_feedme_similarity: Minimum similarity threshold for FeedMe results
        
    Returns:
        List of combined search results sorted by weighted similarity score
    """
    logger.info(f"Performing combined similarity search for query: '{query[:50]}...' with top_k_total={top_k_total}")
    
    combined_results: List[CombinedSearchResult] = []
    
    try:
        # Get knowledge base results
        kb_top_k = max(1, int(top_k_total * kb_weight * 1.5))  # Get a few extra to ensure variety
        kb_results = find_similar_documents(query, top_k=kb_top_k)
        
        # Convert KB results to combined format
        for kb_result in kb_results:
            if kb_result.similarity_score >= min_kb_similarity:
                combined_result = CombinedSearchResult(
                    id=kb_result.id,
                    source_type="knowledge_base",
                    title=kb_result.url,  # Use URL as title for KB results
                    content=kb_result.markdown or kb_result.content or "",
                    url=kb_result.url,
                    metadata=kb_result.metadata,
                    similarity_score=kb_result.similarity_score * kb_weight,  # Apply weight
                    additional_data={
                        "original_score": kb_result.similarity_score,
                        "markdown": kb_result.markdown,
                        "raw_content": kb_result.content
                    }
                )
                combined_results.append(combined_result)
        
        # Get FeedMe results if enabled
        if settings.feedme_enabled:
            feedme_top_k = max(1, int(top_k_total * feedme_weight * 1.5))  # Get a few extra
            feedme_results = find_similar_feedme_examples(
                query, 
                top_k=feedme_top_k,
                min_similarity=min_feedme_similarity
            )
            
            # Convert FeedMe results to combined format
            for feedme_result in feedme_results:
                combined_result = CombinedSearchResult(
                    id=feedme_result.id,
                    source_type="feedme",
                    title=f"Support Example: {feedme_result.conversation_title}",
                    content=f"Q: {feedme_result.question_text}\n\nA: {feedme_result.answer_text}",
                    url=None,  # FeedMe examples don't have URLs
                    metadata={
                        "conversation_id": feedme_result.conversation_id,
                        "tags": feedme_result.tags,
                        "issue_type": feedme_result.issue_type,
                        "resolution_type": feedme_result.resolution_type
                    },
                    similarity_score=feedme_result.similarity_score * feedme_weight,  # Apply weight
                    additional_data={
                        "original_score": feedme_result.similarity_score,
                        "confidence_score": feedme_result.confidence_score,
                        "usefulness_score": feedme_result.usefulness_score,
                        "question": feedme_result.question_text,
                        "answer": feedme_result.answer_text,
                        "context_before": feedme_result.context_before,
                        "context_after": feedme_result.context_after
                    }
                )
                combined_results.append(combined_result)
        
        # Sort by weighted similarity score and limit results
        combined_results.sort(key=lambda x: x.similarity_score, reverse=True)
        combined_results = combined_results[:top_k_total]
        
        logger.info(f"Combined search found {len(combined_results)} total results "
                   f"({len([r for r in combined_results if r.source_type == 'knowledge_base'])} KB, "
                   f"{len([r for r in combined_results if r.source_type == 'feedme'])} FeedMe)")
        
        for i, result in enumerate(combined_results[:5]):  # Log top 5
            logger.debug(f"  {i+1}. {result.source_type}: {result.title[:50]}... (Score: {result.similarity_score:.4f})")
    
    except Exception as e:
        logger.error(f"Error during combined similarity search: {e}")
    
    return combined_results


def generate_feedme_embeddings(
    conversation_id: Optional[int] = None,
    batch_size: int = 10,
    force_regenerate: bool = False
) -> int:
    """
    Generate embeddings for FeedMe examples that don't have them yet.
    
    Args:
        conversation_id: Optional specific conversation to process
        batch_size: Number of examples to process per batch
        force_regenerate: Whether to regenerate existing embeddings
        
    Returns:
        Number of examples processed
    """
    logger.info(f"Starting FeedMe embedding generation (batch_size={batch_size})")
    conn = None
    updated_count = 0
    failed_count = 0

    try:
        conn = get_db_connection()
        if not conn:
            return 0
        
        emb_model = get_embedding_model()

        # Build query conditions
        conditions = []
        params = []
        
        if conversation_id:
            conditions.append("conversation_id = %s")
            params.append(conversation_id)
        
        if not force_regenerate:
            conditions.append("(question_embedding IS NULL OR answer_embedding IS NULL OR combined_embedding IS NULL)")
        
        where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
        params.append(batch_size)

        with conn.cursor(cursor_factory=psycopg2_extras.NamedTupleCursor) as cur:
            # Fetch examples without embeddings
            query = f"""
            SELECT id, question_text, answer_text 
            FROM feedme_examples 
            {where_clause}
            AND is_active = true
            LIMIT %s
            """
            cur.execute(query, params)
            records_to_process = cur.fetchall()

            if not records_to_process:
                logger.info("No FeedMe examples found requiring embedding generation.")
                return 0

            logger.info(f"Found {len(records_to_process)} FeedMe examples to process for embeddings.")

            for record in records_to_process:
                try:
                    logger.debug(f"Processing FeedMe example ID: {record.id}")
                    
                    # Generate embeddings for question, answer, and combined
                    question_embedding = emb_model.embed_query(record.question_text)
                    if not _embedding_has_expected_dim(question_embedding, "generate_feedme_embeddings:question"):
                        raise ValueError("Question embedding dimension mismatch")

                    answer_embedding = emb_model.embed_query(record.answer_text)
                    if not _embedding_has_expected_dim(answer_embedding, "generate_feedme_embeddings:answer"):
                        raise ValueError("Answer embedding dimension mismatch")
                    
                    # Create combined text for better search
                    combined_text = f"Question: {record.question_text}\n\nAnswer: {record.answer_text}"
                    combined_embedding = emb_model.embed_query(combined_text)
                    if not _embedding_has_expected_dim(combined_embedding, "generate_feedme_embeddings:combined"):
                        raise ValueError("Combined embedding dimension mismatch")
                    
                    # Update the record
                    update_sql = """
                    UPDATE feedme_examples 
                    SET question_embedding = %s, 
                        answer_embedding = %s, 
                        combined_embedding = %s,
                        updated_at = NOW()
                    WHERE id = %s
                    """
                    cur.execute(update_sql, (question_embedding, answer_embedding, combined_embedding, record.id))
                    conn.commit()
                    
                    logger.info(f"Successfully generated embeddings for FeedMe example ID: {record.id}")
                    updated_count += 1
                
                except Exception as e:
                    conn.rollback()
                    logger.error(f"Error processing FeedMe example ID {record.id}: {e}")
                    failed_count += 1
        
        logger.info(f"--- FeedMe Embedding Generation Summary ---")
        logger.info(f"Successfully updated: {updated_count} examples")
        logger.info(f"Failed to update: {failed_count} examples")
        return updated_count

    except Exception as e:
        logger.error(f"An error occurred during FeedMe embedding generation: {e}")
        if conn:
            conn.rollback()
        return 0
    finally:
        if conn:
            conn.close()
            logger.info("Database connection closed after FeedMe embedding generation.")


## Removed: legacy alias find_similar_documents_legacy — use find_similar_documents


if __name__ == "__main__":
    # 1. Generate embeddings for all pending content in batches
    logger.info("Running embedding generation process...")
    total_records_embedded = 0
    batch_size = 10  # Define batch size for processing
    while True:
        logger.info(f"Processing next batch of up to {batch_size} records for embeddings...")
        try:
            processed_in_batch = generate_embeddings_for_pending_content(batch_size=batch_size)
            total_records_embedded += processed_in_batch
            # If fewer records were processed than the batch size, or zero, it implies all done or an issue.
            if processed_in_batch < batch_size:
                logger.info(f"Processed {processed_in_batch} records. Fewer than batch size ({batch_size}), assuming all pending records are done or no more found.")
                break
            if processed_in_batch == 0:
                logger.info("No records processed in this batch. All pending records should be done.")
                break
            logger.info(f"Successfully processed {processed_in_batch} records in this batch. Fetching next batch...")
        except Exception as e:
            logger.error(f"An error occurred during a batch of embedding generation: {e}", exc_info=True)
            logger.error("Stopping further batch processing due to error.")
            break
    logger.info(f"Embedding generation process finished. Total records for which embeddings were attempted/generated: {total_records_embedded}")

    # 2. Generate FeedMe embeddings if enabled
    if settings.feedme_enabled:
        logger.info("\nRunning FeedMe embedding generation...")
        feedme_embedded = generate_feedme_embeddings(batch_size=5)
        logger.info(f"FeedMe embedding generation finished. Total examples processed: {feedme_embedded}")

    # 3. Perform similarity searches (examples)
    logger.info("\nRunning example similarity searches...")
    sample_query = "How to set up an email account in Mailbird?"
    
    # Test knowledge base search
    similar_docs = find_similar_documents(sample_query, top_k=3)
    if similar_docs:
        logger.info(f"Top {len(similar_docs)} KB documents similar to '{sample_query}':")
        for doc in similar_docs:
            logger.info(f"  - URL: {doc.url} (Score: {doc.similarity_score:.4f})")
    else:
        logger.info("No similar KB documents found for the sample query.")
    
    # Test FeedMe search if enabled
    if settings.feedme_enabled:
        feedme_examples = find_similar_feedme_examples(sample_query, top_k=3, min_similarity=0.5)
        if feedme_examples:
            logger.info(f"Top {len(feedme_examples)} FeedMe examples similar to '{sample_query}':")
            for example in feedme_examples:
                logger.info(f"  - {example.conversation_title}: {example.question_text[:50]}... (Score: {example.similarity_score:.4f})")
        else:
            logger.info("No similar FeedMe examples found for the sample query.")
        
        # Test combined search
        combined_results = find_combined_similar_content(sample_query, top_k_total=5)
        if combined_results:
            logger.info(f"Top {len(combined_results)} combined results for '{sample_query}':")
            for result in combined_results:
                logger.info(f"  - [{result.source_type}] {result.title[:50]}... (Score: {result.similarity_score:.4f})")
        else:
            logger.info("No combined results found for the sample query.")
