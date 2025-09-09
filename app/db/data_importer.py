"""
Script to scrape specified URLs using Firecrawl and import the content into
the mailbird_knowledge PostgreSQL table.

This script handles subtask 8.2 of Task 8.

Prerequisites:
- PostgreSQL server running with the mailbird_knowledge table created (see migrations).
- pgvector extension enabled in PostgreSQL.
- Environment variables set for database connection and Firecrawl API key:
  - DB_HOST
  - DB_PORT
  - DB_USER
  - DB_PASSWORD
  - DB_NAME
  - FIRECRAWL_API_KEY
  - (Optional) MAILBIRD_URLS_TO_SCRAPE (comma-separated string)
"""
import os
import json
import logging
import time
from datetime import datetime

import psycopg2
from dotenv import load_dotenv
from firecrawl import FirecrawlApp
from psycopg2.extras import Json

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

# --- Configuration ---
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY")

# URLs to scrape - replace with your actual list or load from env var
DEFAULT_URLS = [
    "https://www.getmailbird.com/",
    "https://www.getmailbird.com/features/",
    "https://www.getmailbird.com/pricing/",
    "https://support.getmailbird.com/hc/en-us"
]
MAILBIRD_URLS_TO_SCRAPE = os.getenv("MAILBIRD_URLS_TO_SCRAPE")
if MAILBIRD_URLS_TO_SCRAPE:
    TARGET_URLS = [url.strip() for url in MAILBIRD_URLS_TO_SCRAPE.split(',')]
else:
    TARGET_URLS = DEFAULT_URLS


def get_db_connection():
    """Establishes a connection to the PostgreSQL database."""
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            dbname=DB_NAME
        )
        logger.info("Successfully connected to the database.")
        return conn
    except psycopg2.Error as e:
        logger.error(f"Error connecting to PostgreSQL database: {e}")
        raise

def scrape_url_with_firecrawl(fc_app: FirecrawlApp, url: str):
    """Scrapes a single URL using Firecrawl."""
    logger.info(f"Scraping URL: {url}")
    try:
        # FirecrawlApp.scrape_url params: url, page_options, crawler_options, timeout
        # Default page_options should be fine for now.
        scraped_data = fc_app.scrape_url(url=url, params={'pageOptions': {'onlyMainContent': True}})
        if scraped_data:
            logger.info(f"Successfully scraped: {url}")
            return scraped_data
        else:
            logger.warning(f"No data returned from Firecrawl for URL: {url}")
            return None
    except Exception as e:
        logger.error(f"Error scraping URL {url} with Firecrawl: {e}")
        return None

def insert_scraped_data(conn, url: str, scraped_content: dict):
    """Inserts or updates scraped data into the mailbird_knowledge table."""
    markdown_content = scraped_content.get('markdown')
    raw_content = scraped_content.get('content') # HTML or raw text
    page_metadata = scraped_content.get('metadata', {})

    if not markdown_content and not raw_content:
        logger.warning(f"No content (markdown or raw) found for URL: {url}. Skipping insertion.")
        return False

    sql = """
    INSERT INTO mailbird_knowledge (url, content, markdown, scraped_at, embedding, metadata)
    VALUES (%s, %s, %s, %s, %s, %s)
    ON CONFLICT (url) DO UPDATE SET
        content = EXCLUDED.content,
        markdown = EXCLUDED.markdown,
        scraped_at = EXCLUDED.scraped_at,
        embedding = NULL,  -- Reset embedding on update, to be re-generated
        metadata = EXCLUDED.metadata;
    """
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (
                url,
                raw_content, # Store raw_content as fallback
                markdown_content,
                datetime.now(psycopg2.tz.utc),
                None,  # Embedding is NULL initially
                Json(page_metadata) if page_metadata else None
            ))
        conn.commit()
        logger.info(f"Successfully inserted/updated data for URL: {url}")
        return True
    except psycopg2.Error as e:
        conn.rollback()
        logger.error(f"Database error for URL {url}: {e}")
        return False
    except Exception as e:
        conn.rollback()
        logger.error(f"An unexpected error occurred during data insertion for URL {url}: {e}")
        return False

def main():
    """Main function to orchestrate scraping and data import."""
    logger.info("Starting Mailbird knowledge base import process...")

    if not all([DB_USER, DB_PASSWORD, DB_NAME, FIRECRAWL_API_KEY]):
        logger.error("Database credentials or Firecrawl API key are not fully configured. Exiting.")
        logger.error("Please set DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME, FIRECRAWL_API_KEY.")
        return

    if not TARGET_URLS:
        logger.warning("No URLs configured for scraping. Exiting.")
        return

    fc_app = FirecrawlApp(api_key=FIRECRAWL_API_KEY)
    db_conn = None

    try:
        db_conn = get_db_connection()
        if not db_conn:
            return # Error already logged by get_db_connection

        successful_imports = 0
        failed_imports = 0

        for i, url in enumerate(TARGET_URLS):
            logger.info(f"Processing URL {i+1}/{len(TARGET_URLS)}: {url}")
            scraped_data = scrape_url_with_firecrawl(fc_app, url)
            if scraped_data:
                if insert_scraped_data(db_conn, url, scraped_data):
                    successful_imports += 1
                else:
                    failed_imports += 1
            else:
                failed_imports += 1
            
            # Add a small delay to be respectful to Firecrawl API, if needed
            # Firecrawl's Python SDK might handle rate limiting, but good practice.
            if i < len(TARGET_URLS) - 1: # Don't sleep after the last one
                time.sleep(1) # 1 second delay

        logger.info("--- Import Summary ---")
        logger.info(f"Successfully imported/updated: {successful_imports} URLs")
        logger.info(f"Failed to import/update: {failed_imports} URLs")

    except Exception as e:
        logger.error(f"An critical error occurred in the main process: {e}")
    finally:
        if db_conn:
            db_conn.close()
            logger.info("Database connection closed.")

    logger.info("Mailbird knowledge base import process finished.")

if __name__ == "__main__":
    main()
