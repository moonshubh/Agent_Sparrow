#!/usr/bin/env python3
"""
FeedMe v2.0 Phase 1: Database Initialization Script
Ensures all required tables, indexes, and functions exist in Supabase

This script:
1. Verifies database connection and extensions
2. Creates FeedMe tables if they don't exist
3. Sets up indexes and functions for optimal performance
4. Performs health checks and validation
5. Reports initialization status and next steps
"""

import os
import sys
import logging
import traceback
from pathlib import Path
import sqlparse
from typing import Dict, Any, List, Tuple

# Add the project root to the Python path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.db.connection_manager import get_connection_manager, health_check
from app.core.settings import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class FeedMeInitializer:
    """Initialize FeedMe v2.0 database schema and components"""
    
    def __init__(self):
        self.manager = get_connection_manager()
        self.initialization_steps = []
        self.errors = []
    
    def run_sql_file(self, file_path: Path) -> bool:
        """Execute SQL from a file using a proper parser to handle complex statements."""
        try:
            logger.info(f"Executing SQL file: {file_path}")
            
            with open(file_path, 'r') as f:
                sql_content = f.read()
            
            # Use sqlparse to split the content into individual, valid statements.
            # This correctly handles multi-line statements, comments, and strings.
            statements = sqlparse.split(sql_content)
            
            # Execute the statements within a single transaction
            with self.manager.get_connection() as conn:
                with conn.cursor() as cur:
                    try:
                        for statement in statements:
                            # sqlparse can return empty strings for comments or whitespace
                            if statement.strip():
                                cur.execute(statement)
                        
                        conn.commit()
                        logger.info(f"Successfully executed SQL file: {file_path}")
                        return True
                    except Exception as e:
                        conn.rollback()
                        # The "already exists" check is kept for compatibility.
                        if "already exists" in str(e).lower():
                            logger.warning(f"Objects in {file_path} may already exist, which is acceptable. Error: {e}")
                            return True
                        else:
                            logger.error(f"SQL execution failed in {file_path}: {e}")
                            logger.debug(traceback.format_exc())
                            return False
        
        except Exception as e:
            logger.error(f"Failed to read or process SQL file {file_path}: {e}")
            logger.debug(traceback.format_exc())
            return False
    
    def check_extensions(self) -> bool:
        """Verify required PostgreSQL extensions are available"""
        logger.info("Checking required database extensions...")
        
        try:
            with self.manager.get_connection() as conn:
                with conn.cursor() as cur:
                    # Check for vector extension
                    cur.execute("""
                        SELECT EXISTS (
                            SELECT 1 FROM pg_extension WHERE extname = 'vector'
                        ) as vector_exists
                    """)
                    result = cur.fetchone()
                    vector_exists = result['vector_exists']
                    
                    if not vector_exists:
                        logger.warning("Vector extension not found - attempting to create")
                        try:
                            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
                            conn.commit()
                            logger.info("Vector extension created successfully")
                        except Exception as e:
                            logger.error(f"Failed to create vector extension: {e}")
                            return False
                    else:
                        logger.info("Vector extension is available")
                    
                    # Check for uuid-ossp extension
                    cur.execute("""
                        SELECT EXISTS (
                            SELECT 1 FROM pg_extension WHERE extname = 'uuid-ossp'
                        ) as uuid_exists
                    """)
                    result = cur.fetchone()
                    uuid_exists = result['uuid_exists']
                    
                    if not uuid_exists:
                        try:
                            cur.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\"")
                            conn.commit()
                            logger.info("UUID extension created successfully")
                        except Exception as e:
                            logger.warning(f"Could not create uuid-ossp extension: {e}")
                    else:
                        logger.info("UUID extension is available")
            
            return True
            
        except Exception as e:
            logger.error(f"Extension check failed: {e}")
            return False
    
    def check_tables(self) -> Dict[str, bool]:
        """Check which FeedMe tables exist"""
        logger.info("Checking FeedMe table existence...")
        
        tables = {
            'feedme_conversations': False,
            'feedme_examples': False,
            'feedme_folders': False
        }
        
        try:
            with self.manager.get_connection() as conn:
                with conn.cursor() as cur:
                    for table_name in tables.keys():
                        cur.execute("""
                            SELECT EXISTS (
                                SELECT FROM information_schema.tables 
                                WHERE table_schema = 'public' 
                                AND table_name = %s
                            ) as table_exists
                        """, (table_name,))
                        result = cur.fetchone()
                        tables[table_name] = result['table_exists']
                        
                        if tables[table_name]:
                            logger.info(f"✓ Table {table_name} exists")
                        else:
                            logger.warning(f"✗ Table {table_name} missing")
            
            return tables
            
        except Exception as e:
            logger.error(f"Table check failed: {e}")
            return tables
    
    def create_schema(self) -> bool:
        """Create FeedMe schema using migration files"""
        logger.info("Creating FeedMe v2.0 schema...")
        
        # Run migrations in order
        migration_files = [
            "004_feedme_basic_tables.sql",
            "005_feedme_indexes.sql", 
            "006_feedme_functions.sql",
            "007_add_versioning_support.sql"
        ]
        
        for migration_file_name in migration_files:
            migration_file = PROJECT_ROOT / "app" / "db" / "migrations" / migration_file_name
            
            if not migration_file.exists():
                logger.error(f"Migration file not found: {migration_file}")
                return False
            
            logger.info(f"Running migration: {migration_file_name}")
            if not self.run_sql_file(migration_file):
                logger.error(f"Migration failed: {migration_file_name}")
                return False
        
        return True
    
    def verify_schema(self) -> bool:
        """Verify that all required schema components exist"""
        logger.info("Verifying FeedMe v2.0 schema...")
        
        try:
            with self.manager.get_connection() as conn:
                with conn.cursor() as cur:
                    # Check tables
                    tables_exist = self.check_tables()
                    if not all(tables_exist.values()):
                        logger.error("Some required tables are missing")
                        return False
                    
                    # Check for required columns in feedme_conversations
                    cur.execute("""
                        SELECT column_name FROM information_schema.columns 
                        WHERE table_schema = 'public' 
                        AND table_name = 'feedme_conversations'
                        ORDER BY column_name
                    """)
                    conv_columns = [row['column_name'] for row in cur.fetchall()]
                    
                    required_conv_columns = [
                        'id', 'uuid', 'title', 'raw_transcript', 'processing_status',
                        'version', 'is_active', 'folder_id', 'folder_color', 'created_at', 'updated_at'
                    ]
                    
                    missing_conv_columns = [col for col in required_conv_columns if col not in conv_columns]
                    if missing_conv_columns:
                        logger.error(f"Missing columns in feedme_conversations: {missing_conv_columns}")
                        return False
                    
                    # Check for required columns in feedme_examples
                    cur.execute("""
                        SELECT column_name FROM information_schema.columns 
                        WHERE table_schema = 'public' 
                        AND table_name = 'feedme_examples'
                        ORDER BY column_name
                    """)
                    ex_columns = [row['column_name'] for row in cur.fetchall()]
                    
                    required_ex_columns = [
                        'id', 'conversation_id', 'question_text', 'answer_text',
                        'confidence_score', 'usefulness_score', 'is_active', 'created_at', 'updated_at'
                    ]
                    
                    missing_ex_columns = [col for col in required_ex_columns if col not in ex_columns]
                    if missing_ex_columns:
                        logger.error(f"Missing columns in feedme_examples: {missing_ex_columns}")
                        return False
                    
                    # Check for views
                    cur.execute("""
                        SELECT viewname FROM pg_views 
                        WHERE schemaname = 'public' 
                        AND viewname IN ('feedme_active_examples', 'feedme_conversation_stats')
                    """)
                    views = [row['viewname'] for row in cur.fetchall()]
                    
                    if 'feedme_active_examples' not in views:
                        logger.warning("View feedme_active_examples not found")
                    if 'feedme_conversation_stats' not in views:
                        logger.warning("View feedme_conversation_stats not found")
                    
                    logger.info("Schema verification completed successfully")
                    return True
            
        except Exception as e:
            logger.error(f"Schema verification failed: {e}")
            return False
    
    def run_health_check(self) -> Dict[str, Any]:
        """Perform comprehensive health check"""
        logger.info("Running comprehensive health check...")
        return health_check()
    
    def initialize(self) -> bool:
        """Run complete FeedMe v2.0 initialization"""
        logger.info("=" * 60)
        logger.info("FeedMe v2.0 Phase 1: Database Initialization")
        logger.info("=" * 60)
        
        success = True
        
        # Step 1: Check extensions
        logger.info("\n1. Checking database extensions...")
        if not self.check_extensions():
            logger.error("Extension check failed")
            success = False
        
        # Step 2: Check existing tables
        logger.info("\n2. Checking existing tables...")
        existing_tables = self.check_tables()
        
        # Step 3: Create schema if needed
        if not all(existing_tables.values()):
            logger.info("\n3. Creating FeedMe schema...")
            if not self.create_schema():
                logger.error("Schema creation failed")
                success = False
        else:
            logger.info("\n3. Schema already exists, skipping creation")
        
        # Step 4: Verify schema
        logger.info("\n4. Verifying schema...")
        if not self.verify_schema():
            logger.error("Schema verification failed")
            success = False
        
        # Step 5: Health check
        logger.info("\n5. Running health check...")
        health = self.run_health_check()
        
        if health['status'] != 'healthy':
            logger.error(f"Health check failed: {health.get('error', 'Unknown error')}")
            success = False
        else:
            logger.info("✓ Health check passed")
        
        # Summary
        logger.info("\n" + "=" * 60)
        if success:
            logger.info("✓ FeedMe v2.0 Phase 1 initialization completed successfully!")
            logger.info("\nNext steps:")
            logger.info("- Phase 2: Implement async processing pipeline")
            logger.info("- Phase 3: Add edit & version UI components")
            logger.info("- Configure environment variables for production")
        else:
            logger.error("✗ FeedMe v2.0 Phase 1 initialization failed!")
            logger.error("Please check the errors above and retry")
        
        logger.info("=" * 60)
        
        return success


def main():
    """Main initialization function"""
    try:
        initializer = FeedMeInitializer()
        success = initializer.initialize()
        
        # Exit with appropriate code
        sys.exit(0 if success else 1)
        
    except Exception as e:
        logger.error(f"Initialization failed with exception: {e}")
        logger.debug(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()