"""
Script to import locally stored Firecrawl JSONL data into the PostgreSQL database.

This script reads data from specified JSONL files, extracts relevant fields,
and inserts/updates records in the 'mailbird_knowledge' table.

Assumes the database schema is already created (see migration 001_create_mailbird_knowledge.sql).
Requires a .env file in the project root with DATABASE_URL.

Example .env entry:
DATABASE_URL=postgresql://user:password@host:port/dbname

Usage:
cd /path/to/MB-Sparrow-main
python app/scripts/import_local_jsonl.py
"""

import os
import json
import logging
from pathlib import Path
from datetime import datetime, timezone

import psycopg2
from psycopg2.extras import execute_batch
from dotenv import load_dotenv
from dateutil import parser as date_parser

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Configuration ---
# Determine the project root by going up two levels from this script's directory
# (app/scripts/ -> app/ -> project_root)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Load environment variables from .env file in the project root
load_dotenv(PROJECT_ROOT / '.env')

DATABASE_URL = os.getenv("DATABASE_URL")

# Paths to the JSONL data files relative to the project root
JSONL_FILE_PATHS = [
    PROJECT_ROOT / "data" / "mailbird_content" / "mailbird_content.jsonl",
    PROJECT_ROOT / "data" / "mailbird_kb_articles" / "all_mailbird_articles.jsonl"
]

BATCH_SIZE = 100  # Number of records to insert/update in a single database transaction

# Fields to exclude from the 'metadata' JSONB column to avoid excessive data storage
# or redundant information already in dedicated columns.
METADATA_EXCLUDE_FIELDS = ["@context", "@type", "text", "articleBody", "content", "markdown", "url", "dateModified", "scraped_at", "embedding"]

# --- Database Connection ---
def get_db_connection():
    """Establishes a connection to the PostgreSQL database."""
    if not DATABASE_URL:
        logger.error("DATABASE_URL not found in environment variables. Please set it in your .env file.")
        raise ValueError("DATABASE_URL not configured.")
    try:
        conn = psycopg2.connect(DATABASE_URL)
        logger.info("Successfully connected to the PostgreSQL database.")
        return conn
    except psycopg2.Error as e:
        logger.error(f"Error connecting to PostgreSQL database: {e}")
        raise

# --- Data Processing ---
def parse_timestamp(date_string: str) -> datetime:
    """Parses a date string into a timezone-aware datetime object (UTC)."""
    if not date_string:
        return datetime.now(timezone.utc)
    try:
        dt = date_parser.parse(date_string)
        if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
            dt = dt.replace(tzinfo=timezone.utc) # Assume UTC if no timezone info
        else:
            dt = dt.astimezone(timezone.utc) # Convert to UTC
        return dt
    except (ValueError, TypeError) as e:
        logger.warning(f"Could not parse date string '{date_string}': {e}. Using current timestamp.")
        return datetime.now(timezone.utc)

def process_jsonl_file(file_path: Path, conn) -> tuple[int, int]:
    """Processes a single JSONL file and inserts/updates data into the database."""
    logger.info(f"Processing file: {file_path}")
    records_to_insert = []
    processed_lines = 0
    inserted_updated_count = 0

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line_number, line in enumerate(f, 1):
                processed_lines += 1
                try:
                    data = json.loads(line.strip())
                except json.JSONDecodeError as e:
                    logger.warning(f"Skipping malformed JSON line {line_number} in {file_path}: {e}")
                    continue

                url = data.get('url')
                if not url:
                    logger.warning(f"Skipping line {line_number} in {file_path} due to missing URL.")
                    continue

                # Determine content field (prefer 'articleBody' then 'text')
                content = data.get('articleBody') or data.get('text')
                if not content:
                    logger.warning(f"Skipping URL {url} from {file_path} due to missing content ('articleBody' or 'text').")
                    continue
                
                # Handle 'dateModified' for scraped_at, fallback to now if missing/invalid
                scraped_at_str = data.get('dateModified')
                scraped_at = parse_timestamp(scraped_at_str)

                # Prepare metadata: include all fields except excluded ones
                metadata = {k: v for k, v in data.items() if k not in METADATA_EXCLUDE_FIELDS}
                
                # Ensure metadata values are JSON serializable (basic check)
                for key, value in metadata.items():
                    if isinstance(value, (datetime, Path)):
                        metadata[key] = str(value)

                records_to_insert.append((
                    url,
                    content, # Storing raw content, markdown conversion can happen later if needed
                    None,    # markdown - will be generated later or if content is already markdown
                    scraped_at,
                    json.dumps(metadata), # metadata
                    None     # embedding - will be generated later
                ))

                if len(records_to_insert) >= BATCH_SIZE:
                    inserted_updated_count += _execute_batch_insert(conn, records_to_insert)
                    records_to_insert = []
            
            # Process any remaining records
            if records_to_insert:
                inserted_updated_count += _execute_batch_insert(conn, records_to_insert)

    except FileNotFoundError:
        logger.error(f"File not found: {file_path}")
        return 0, 0
    except Exception as e:
        logger.error(f"An error occurred while processing {file_path}: {e}")
        # Rollback in case of error during batch processing within this file
        if conn:
            conn.rollback()
        return processed_lines, 0 # Return lines processed so far, but 0 successful inserts for this file

    logger.info(f"Finished processing {file_path}. Processed {processed_lines} lines. Inserted/Updated {inserted_updated_count} records.")
    return processed_lines, inserted_updated_count

def _execute_batch_insert(conn, records: list) -> int:
    """
    Executes a batch insert/update into the mailbird_knowledge table.
    Uses ON CONFLICT to update existing records based on URL.
    When a conflict occurs (URL already exists), it updates content, scraped_at, and metadata,
    and importantly, sets embedding and markdown to NULL to signal they need re-processing.
    """
    if not records:
        return 0

    sql = """
    INSERT INTO mailbird_knowledge (url, content, markdown, scraped_at, metadata, embedding)
    VALUES (%s, %s, %s, %s, %s, %s)
    ON CONFLICT (url) DO UPDATE
    SET
        content = EXCLUDED.content,
        scraped_at = EXCLUDED.scraped_at,
        metadata = EXCLUDED.metadata,
        markdown = NULL,      -- Clear markdown to allow regeneration
        embedding = NULL,     -- Clear embedding to allow regeneration
        updated_at = NOW()    -- Update the 'updated_at' timestamp
    RETURNING id;
    """
    try:
        with conn.cursor() as cur:
            execute_batch(cur, sql, records, page_size=len(records))
            conn.commit()
            # execute_batch with psycopg2 doesn't directly return the number of affected rows in a way
            # that distinguishes inserts from updates easily or counts them from RETURNING.
            # We assume success if no exception, and the calling function tracks based on records submitted.
            # For more precise counting, one might need row-by-row inserts or more complex SQL.
            logger.debug(f"Successfully executed batch of {len(records)} records.")
            return len(records) # Assume all records in batch were processed (inserted or updated)
    except psycopg2.Error as e:
        logger.error(f"Database error during batch insert/update: {e}")
        conn.rollback()
        return 0
    except Exception as e:
        logger.error(f"Unexpected error during batch insert/update: {e}")
        conn.rollback()
        return 0

# --- Main Execution ---
def main():
    """Main function to orchestrate the data import process."""
    logger.info("Starting local JSONL data import process...")
    
    conn = None
    total_lines_processed = 0
    total_records_imported_updated = 0

    try:
        conn = get_db_connection()
        for file_path in JSONL_FILE_PATHS:
            if not file_path.exists():
                logger.warning(f"Data file not found: {file_path}. Skipping.")
                continue
            
            lines_in_file, imported_in_file = process_jsonl_file(file_path, conn)
            total_lines_processed += lines_in_file
            total_records_imported_updated += imported_in_file
        
        logger.info("Local JSONL data import process completed.")
        logger.info(f"Total lines processed across all files: {total_lines_processed}")
        logger.info(f"Total records inserted/updated in the database: {total_records_imported_updated}")

    except ValueError as e: # Specifically for DATABASE_URL not configured
        logger.error(f"Configuration error: {e}")
    except psycopg2.Error as e:
        logger.error(f"A database connection error occurred: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred during the import process: {e}")
    finally:
        if conn:
            conn.close()
            logger.info("Database connection closed.")

if __name__ == "__main__":
    main()
