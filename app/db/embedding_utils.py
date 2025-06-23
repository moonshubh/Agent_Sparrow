"""
Utilities for generating embeddings for content in the mailbird_knowledge table
and performing similarity searches using pgvector.

This script handles subtask 8.3 of Task 8.

Prerequisites:
- PostgreSQL server running with the mailbird_knowledge table and pgvector.
- Data imported by data_importer.py (or similar).
- Environment variables for DB connection and Gemini API Key set in a .env file
  at the project root:
  - DATABASE_URL (e.g., postgresql://user:password@host:port/dbname) OR
  - DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME (as fallback)
  - GEMINI_API_KEY
"""
import os
import logging
import psycopg2
import psycopg2.extras as psycopg2_extras # For NamedTupleCursor, aliased to avoid conflict
from pgvector.psycopg2 import register_vector
from dotenv import load_dotenv
from langchain_google_genai import embeddings as gen_embeddings
from typing import List, Optional, Dict, Any # Removed Tuple
from pydantic import BaseModel # Added Pydantic BaseModel

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
DATABASE_URL = os.getenv("DATABASE_URL") # Added for Supabase compatibility

# --- Configuration ---
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

EMBEDDING_MODEL_NAME = "models/embedding-001" # Google's embedding-001 has 768 dimensions

# --- Database Connection ---
def get_db_connection():
    """Establishes a connection to the PostgreSQL database.
    Prioritizes DATABASE_URL if set, otherwise uses individual DB_HOST, etc.
    """
    try:
        if DATABASE_URL:
            conn = psycopg2.connect(DATABASE_URL)
            logger.info(f"Successfully connected to database using DATABASE_URL.")
        else:
            logger.info(f"DATABASE_URL not found, attempting connection using DB_HOST: {DB_HOST}, DB_PORT: {DB_PORT}, DB_NAME: {DB_NAME}, DB_USER: {DB_USER}")
            conn = psycopg2.connect(
                host=DB_HOST,
                port=DB_PORT,
                user=DB_USER,
                password=DB_PASSWORD,
                dbname=DB_NAME
            )
            logger.info("Successfully connected to database using individual DB parameters.")
        
        # Register pgvector types
        register_vector(conn)
        logger.info("Registered pgvector type with the connection using pgvector.psycopg2.")
        return conn
    except psycopg2.Error as e:
        logger.error(f"Error connecting to PostgreSQL database: {e}")
        raise

# --- Embedding Generation ---
def get_embedding_model():
    """Initializes and returns the Google Generative AI embedding model."""
    if not GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY not found in environment variables.")
        raise ValueError("GEMINI_API_KEY not set.")
    try:
        emb_model = gen_embeddings.GoogleGenerativeAIEmbeddings(
            model=EMBEDDING_MODEL_NAME, 
            google_api_key=GEMINI_API_KEY
        )
        logger.info(f"Initialized embedding model: {EMBEDDING_MODEL_NAME}")
        return emb_model
    except Exception as e:
        logger.error(f"Failed to initialize embedding model: {e}")
        raise

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

    class Config:
        orm_mode = True # or from_attributes = True for Pydantic v2

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

    # 2. Perform a similarity search (example)
    logger.info("\nRunning example similarity search...")
    sample_query = "How to set up an email account in Mailbird?"
    similar_docs = find_similar_documents(sample_query, top_k=3)
    if similar_docs:
        logger.info(f"Top {len(similar_docs)} documents similar to '{sample_query}':")
        for doc in similar_docs:
            logger.info(f"  - URL: {doc.url} (Score: {doc.similarity_score:.4f})")
            # logger.info(f"    Markdown (excerpt): {doc.markdown[:200] if doc.markdown else 'N/A'}...")
    else:
        logger.info("No similar documents found for the sample query.")
