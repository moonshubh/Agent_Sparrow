"""
Temporary database helper for FeedMe endpoints
This provides a fallback for local database operations
"""
import os
import psycopg2
from contextlib import contextmanager
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

@contextmanager
def get_db_connection():
    """
    Context manager for database connections
    """
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL not configured")
    
    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL)
        yield conn
        conn.commit()
    except Exception as e:
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()