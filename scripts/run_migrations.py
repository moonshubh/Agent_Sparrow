#!/usr/bin/env python3
"""
Run database migrations for FeedMe system.
This script applies all SQL migration files in the correct order.
"""

import os
import sys
import logging
import asyncio
from pathlib import Path
from typing import List, Dict
import psycopg2
from datetime import datetime

# Add app to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from app.core.settings import get_settings

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class MigrationRunner:
    """Run database migrations for FeedMe system."""
    
    def __init__(self):
        self.settings = get_settings()
        self.migrations_dir = Path(__file__).parent.parent / "app" / "db" / "migrations"
        
    async def get_connection(self):
        """Get database connection from environment."""
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise ValueError("DATABASE_URL environment variable is required")
            
        return await asyncpg.connect(database_url)
    
    async def create_migrations_table(self, conn):
        """Create migrations tracking table if it doesn't exist."""
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version VARCHAR(255) PRIMARY KEY,
                applied_at TIMESTAMPTZ DEFAULT NOW(),
                filename VARCHAR(255),
                checksum VARCHAR(64)
            )
        """)
        logger.info("Ensured schema_migrations table exists")
    
    async def get_applied_migrations(self, conn) -> List[str]:
        """Get list of already applied migrations."""
        result = await conn.fetch("SELECT version FROM schema_migrations ORDER BY version")
        return [row['version'] for row in result]
    
    def get_migration_files(self) -> List[Dict[str, str]]:
        """Get list of migration files to apply."""
        migrations = []
        
        if not self.migrations_dir.exists():
            logger.warning(f"Migrations directory not found: {self.migrations_dir}")
            return migrations
            
        for file_path in sorted(self.migrations_dir.glob("*.sql")):
            version = file_path.stem  # filename without extension
            migrations.append({
                'version': version,
                'filename': file_path.name,
                'path': file_path
            })
        
        return migrations
    
    async def apply_migration(self, conn, migration: Dict[str, str]):
        """Apply a single migration."""
        logger.info(f"Applying migration: {migration['filename']}")
        
        try:
            # Read migration file
            with open(migration['path'], 'r') as f:
                sql_content = f.read()
            
            # Execute migration in a transaction
            async with conn.transaction():
                await conn.execute(sql_content)
                
                # Record migration as applied
                await conn.execute("""
                    INSERT INTO schema_migrations (version, filename, checksum)
                    VALUES ($1, $2, $3)
                """, migration['version'], migration['filename'], 'todo-checksum')
            
            logger.info(f"✅ Successfully applied: {migration['filename']}")
            
        except Exception as e:
            logger.error(f"❌ Failed to apply migration {migration['filename']}: {e}")
            raise
    
    async def run_migrations(self):
        """Run all pending migrations."""
        logger.info("Starting database migration...")
        
        conn = await self.get_connection()
        try:
            # Create migrations table
            await self.create_migrations_table(conn)
            
            # Get applied migrations
            applied_migrations = await self.get_applied_migrations(conn)
            logger.info(f"Found {len(applied_migrations)} already applied migrations")
            
            # Get all migration files
            migration_files = self.get_migration_files()
            logger.info(f"Found {len(migration_files)} migration files")
            
            # Filter pending migrations
            pending_migrations = [
                m for m in migration_files 
                if m['version'] not in applied_migrations
            ]
            
            if not pending_migrations:
                logger.info("✅ No pending migrations. Database is up to date!")
                return
            
            logger.info(f"Found {len(pending_migrations)} pending migrations:")
            for migration in pending_migrations:
                logger.info(f"  - {migration['filename']}")
            
            # Apply each migration
            for migration in pending_migrations:
                await self.apply_migration(conn, migration)
            
            logger.info("✅ All migrations applied successfully!")
            
        finally:
            await conn.close()

async def main():
    """Main entry point."""
    try:
        runner = MigrationRunner()
        await runner.run_migrations()
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())