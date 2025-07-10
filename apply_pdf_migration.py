#!/usr/bin/env python3
"""
Apply PDF Support Migration
Applies the PDF support migration to Supabase database
"""

import os
import asyncio
from pathlib import Path
import sys

# Add the app directory to the path
sys.path.insert(0, str(Path(__file__).parent / "app"))

from app.db.supabase_client import SupabaseClient

async def apply_pdf_migration():
    """Apply the PDF support migration"""
    
    print("🔄 Applying PDF support migration...")
    
    # Read migration file
    migration_file = Path(__file__).parent / "app" / "db" / "migrations" / "013_feedme_pdf_support.sql"
    
    if not migration_file.exists():
        print(f"❌ Migration file not found: {migration_file}")
        return False
    
    try:
        # Read migration SQL
        with open(migration_file, 'r') as f:
            sql_content = f.read()
        
        print(f"📄 Migration SQL content:")
        print("-" * 40)
        print(sql_content)
        print("-" * 40)
        
        # Create Supabase client
        client = SupabaseClient()
        
        # Apply migration
        print("🚀 Executing migration...")
        result = client.client.rpc('exec', {'sql': sql_content})
        
        if result.data:
            print("✅ Migration applied successfully!")
            print(f"📊 Result: {result.data}")
        else:
            print("✅ Migration applied successfully! (No data returned)")
        
        return True
        
    except Exception as e:
        print(f"❌ Error applying migration: {e}")
        return False

async def verify_migration():
    """Verify the migration was applied correctly"""
    
    print("\n🔍 Verifying migration...")
    
    try:
        client = SupabaseClient()
        
        # Check if new columns exist
        check_queries = [
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'feedme_conversations' AND column_name IN ('mime_type', 'pages', 'pdf_metadata')",
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'feedme_examples' AND column_name IN ('source_page', 'source_format')"
        ]
        
        for query in check_queries:
            result = client.client.rpc('exec', {'sql': query})
            if result.data:
                columns = [row['column_name'] for row in result.data]
                print(f"✅ Found columns: {columns}")
            else:
                print(f"⚠️ No columns found for query: {query}")
        
        # Check indexes
        index_query = "SELECT indexname FROM pg_indexes WHERE tablename = 'feedme_conversations' AND indexname = 'idx_feedme_conversations_mime_type'"
        result = client.client.rpc('exec', {'sql': index_query})
        
        if result.data:
            print("✅ Index 'idx_feedme_conversations_mime_type' exists")
        else:
            print("⚠️ Index 'idx_feedme_conversations_mime_type' not found")
        
        return True
        
    except Exception as e:
        print(f"❌ Error verifying migration: {e}")
        return False

async def main():
    """Main function"""
    
    print("🚀 PDF Support Migration Tool")
    print("=" * 50)
    
    # Check environment
    if not os.getenv('SUPABASE_URL') or not os.getenv('SUPABASE_SERVICE_KEY'):
        print("❌ Missing required environment variables:")
        print("   - SUPABASE_URL")
        print("   - SUPABASE_SERVICE_KEY")
        return 1
    
    # Apply migration
    migration_success = await apply_pdf_migration()
    
    if migration_success:
        # Verify migration
        verification_success = await verify_migration()
        
        if verification_success:
            print("\n🎉 PDF support migration completed successfully!")
            return 0
        else:
            print("\n⚠️ Migration applied but verification failed.")
            return 1
    else:
        print("\n❌ Migration failed.")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)