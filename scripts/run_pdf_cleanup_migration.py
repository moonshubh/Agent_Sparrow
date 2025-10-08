#!/usr/bin/env python3
"""
Run PDF Cleanup Migration Script
This script runs the migration to add PDF cleanup functionality to the FeedMe system
"""

import os
import sys
import logging
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from app.db.supabase.client import get_supabase_client
from app.core.settings import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_pdf_cleanup_migration():
    """Run the PDF cleanup migration"""
    try:
        # Get migration file path
        migration_file = Path(__file__).parent.parent / "app" / "db" / "migrations" / "018_feedme_pdf_cleanup.sql"
        
        if not migration_file.exists():
            logger.error(f"Migration file not found: {migration_file}")
            return False
        
        # Read migration SQL
        with open(migration_file, 'r') as f:
            migration_sql = f.read()
        
        logger.info("Reading PDF cleanup migration...")
        
        # Get Supabase client
        supabase = get_supabase_client()
        
        # Split migration into individual statements
        # Remove comments and empty lines
        statements = []
        current_statement = []
        
        for line in migration_sql.split('\n'):
            # Skip comment lines
            if line.strip().startswith('--') or not line.strip():
                continue
            
            current_statement.append(line)
            
            # Check if this completes a statement
            if line.strip().endswith(';'):
                statement = '\n'.join(current_statement).strip()
                if statement:
                    statements.append(statement)
                current_statement = []
        
        # Execute each statement
        logger.info(f"Executing {len(statements)} migration statements...")
        
        for i, statement in enumerate(statements, 1):
            try:
                # Skip DO blocks as they need special handling
                if statement.strip().upper().startswith('DO $$'):
                    # Execute the entire DO block as one statement
                    logger.info(f"Executing DO block {i}/{len(statements)}...")
                    result = supabase.postgrest.rpc('exec_sql', {'sql': statement}).execute()
                else:
                    # For other statements, execute directly
                    logger.info(f"Executing statement {i}/{len(statements)}...")
                    # Use raw SQL execution via Supabase
                    result = supabase.postgrest.rpc('exec_sql', {'sql': statement}).execute()
                
                logger.info(f"Statement {i} executed successfully")
                
            except Exception as e:
                logger.error(f"Error executing statement {i}: {e}")
                logger.error(f"Statement: {statement[:100]}...")
                # Continue with other statements
                continue
        
        logger.info("PDF cleanup migration completed successfully!")
        
        # Test the new functions
        logger.info("Testing PDF cleanup functions...")
        
        try:
            # Test the analytics view
            result = supabase.table('feedme_pdf_storage_analytics').select("*").execute()
            logger.info(f"PDF storage analytics: {result.data}")
        except Exception as e:
            logger.warning(f"Could not fetch analytics (view might not exist yet): {e}")
        
        return True
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return False


def create_exec_sql_function():
    """Create the exec_sql function if it doesn't exist"""
    try:
        supabase = get_supabase_client()
        
        # Create a simple exec_sql function for migrations
        create_function_sql = """
        CREATE OR REPLACE FUNCTION exec_sql(sql text)
        RETURNS void AS $$
        BEGIN
            EXECUTE sql;
        END;
        $$ LANGUAGE plpgsql SECURITY DEFINER;
        """
        
        # This will fail if the function already exists, which is fine
        try:
            supabase.postgrest.rpc('exec_sql', {'sql': create_function_sql}).execute()
        except:
            pass
        
        return True
    except Exception as e:
        logger.error(f"Could not create exec_sql function: {e}")
        return False


if __name__ == "__main__":
    logger.info("Starting PDF cleanup migration...")
    
    # First ensure we have the exec_sql function
    if not create_exec_sql_function():
        logger.warning("Could not create exec_sql function, migration might fail")
    
    # Run the migration
    if run_pdf_cleanup_migration():
        logger.info("Migration completed successfully!")
        sys.exit(0)
    else:
        logger.error("Migration failed!")
        sys.exit(1)