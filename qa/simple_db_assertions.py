#!/usr/bin/env python3
"""
Simple Database Assertion Script
Agent-THREE QA Validation for Supabase Migration
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

def run_assertions():
    """Run all database assertions"""
    print("🔍 FeedMe Database Assertion Report")
    print("=" * 60)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print()
    
    if not DATABASE_URL:
        print("❌ ERROR: DATABASE_URL not found in environment variables")
        return
    
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        print("✅ Database connection successful!")
        
        # Expected tables
        expected_tables = [
            'feedme_conversations',
            'feedme_examples',
            'feedme_folders',
            'feedme_examples_temp',
            'feedme_approval_stats'  # This is a view
        ]
        
        print("\n📊 Table Existence Check:")
        print("-" * 40)
        
        table_results = {}
        for table in expected_tables:
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM pg_tables
                    WHERE schemaname = 'public'
                    AND tablename = %s
                )
            """, (table,))
            exists = cursor.fetchone()['exists']
            table_results[table] = exists
            status = "✅" if exists else "❌"
            print(f"{status} {table}: {'EXISTS' if exists else 'MISSING'}")
        
        # Check row counts
        print("\n📈 Row Counts:")
        print("-" * 40)
        for table, exists in table_results.items():
            if exists and table != 'feedme_approval_stats':  # Skip view
                cursor.execute(f"SELECT COUNT(*) as count FROM {table}")
                count = cursor.fetchone()['count']
                print(f"   {table}: {count} rows")
        
        # Check pgvector extension
        print("\n🔧 Vector Extension:")
        print("-" * 40)
        cursor.execute("""
            SELECT EXISTS (
                SELECT 1 FROM pg_extension WHERE extname = 'vector'
            )
        """)
        has_vector = cursor.fetchone()['exists']
        status = "✅" if has_vector else "❌"
        print(f"{status} pgvector extension: {'INSTALLED' if has_vector else 'NOT INSTALLED'}")
        
        # Check Supabase sync metadata fields
        print("\n🔄 Supabase Sync Metadata:")
        print("-" * 40)
        
        # Check conversations sync fields
        if table_results.get('feedme_conversations'):
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns
                WHERE table_schema = 'public'
                AND table_name = 'feedme_conversations'
                AND column_name IN ('supabase_sync_status', 'supabase_sync_at', 
                                    'supabase_conversation_id', 'supabase_sync_error')
            """)
            conv_sync_cols = [row['column_name'] for row in cursor.fetchall()]
            expected = ['supabase_sync_status', 'supabase_sync_at', 
                       'supabase_conversation_id', 'supabase_sync_error']
            has_all = len(conv_sync_cols) == len(expected)
            status = "✅" if has_all else "❌"
            print(f"{status} conversations_sync_fields: {'PRESENT' if has_all else f'MISSING ({len(conv_sync_cols)}/{len(expected)})'}")
        
        # Check examples sync fields
        if table_results.get('feedme_examples'):
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns
                WHERE table_schema = 'public'
                AND table_name = 'feedme_examples'
                AND column_name IN ('supabase_sync_status', 'supabase_sync_at', 
                                    'supabase_example_id', 'supabase_sync_error')
            """)
            ex_sync_cols = [row['column_name'] for row in cursor.fetchall()]
            expected = ['supabase_sync_status', 'supabase_sync_at', 
                       'supabase_example_id', 'supabase_sync_error']
            has_all = len(ex_sync_cols) == len(expected)
            status = "✅" if has_all else "❌"
            print(f"{status} examples_sync_fields: {'PRESENT' if has_all else f'MISSING ({len(ex_sync_cols)}/{len(expected)})'}")
        
        # Check indexes
        print("\n🔐 Indexes:")
        print("-" * 40)
        
        for table in ['feedme_conversations', 'feedme_examples']:
            if table_results.get(table):
                cursor.execute("""
                    SELECT indexname
                    FROM pg_indexes
                    WHERE schemaname = 'public'
                    AND tablename = %s
                """, (table,))
                indexes = [row['indexname'] for row in cursor.fetchall()]
                print(f"\n{table} indexes ({len(indexes)} total):")
                for idx in indexes[:5]:  # Show first 5
                    print(f"  - {idx}")
                if len(indexes) > 5:
                    print(f"  ... and {len(indexes) - 5} more")
        
        # Data integrity checks
        print("\n🔍 Data Integrity Checks:")
        print("-" * 40)
        
        # Check for orphaned examples
        if table_results.get('feedme_examples') and table_results.get('feedme_conversations'):
            cursor.execute("""
                SELECT COUNT(*) as count FROM feedme_examples e
                LEFT JOIN feedme_conversations c ON e.conversation_id = c.id
                WHERE c.id IS NULL
            """)
            orphan_count = cursor.fetchone()['count']
            status = "✅" if orphan_count == 0 else "⚠️"
            print(f"{status} Orphaned examples: {orphan_count}")
        
        # Check for conversations without examples
        if table_results.get('feedme_examples') and table_results.get('feedme_conversations'):
            cursor.execute("""
                SELECT COUNT(*) as count FROM feedme_conversations c
                LEFT JOIN feedme_examples e ON c.id = e.conversation_id
                WHERE e.id IS NULL AND c.processing_status = 'completed'
            """)
            empty_count = cursor.fetchone()['count']
            print(f"ℹ️  Conversations without examples: {empty_count}")
        
        # Check folder hierarchy
        if table_results.get('feedme_folders'):
            cursor.execute("""
                SELECT COUNT(*) as count FROM feedme_folders
                WHERE parent_id IS NOT NULL
            """)
            subfolder_count = cursor.fetchone()['count']
            print(f"ℹ️  Subfolders: {subfolder_count}")
        
        print("\n✅ Database Assertion Summary:")
        print("-" * 40)
        
        # Calculate overall health
        total_checks = len(expected_tables) + 1 + 2  # tables + vector + sync fields
        passed_checks = sum(1 for exists in table_results.values() if exists)
        if has_vector:
            passed_checks += 1
        
        # Add sync field checks if tables exist
        if table_results.get('feedme_conversations'):
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM information_schema.columns
                WHERE table_schema = 'public'
                AND table_name = 'feedme_conversations'
                AND column_name IN ('supabase_sync_status', 'supabase_sync_at', 
                                    'supabase_conversation_id', 'supabase_sync_error')
            """)
            if cursor.fetchone()['count'] == 4:
                passed_checks += 1
        
        if table_results.get('feedme_examples'):
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM information_schema.columns
                WHERE table_schema = 'public'
                AND table_name = 'feedme_examples'
                AND column_name IN ('supabase_sync_status', 'supabase_sync_at', 
                                    'supabase_example_id', 'supabase_sync_error')
            """)
            if cursor.fetchone()['count'] == 4:
                passed_checks += 1
        
        health_percentage = (passed_checks / total_checks) * 100
        
        print(f"Database Health: {health_percentage:.1f}%")
        print(f"Passed Checks: {passed_checks}/{total_checks}")
        
        if health_percentage == 100:
            print("\n🎉 All database assertions passed!")
        else:
            print("\n⚠️  Some assertions failed. Please review the output above.")
        
        cursor.close()
        conn.close()
        
        print("\n" + "=" * 60)
        print("Database assertion complete!")
        
    except Exception as e:
        print(f"❌ Database connection failed: {e}")

if __name__ == "__main__":
    run_assertions()