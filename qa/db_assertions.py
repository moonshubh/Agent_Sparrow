#!/usr/bin/env python3
"""
Database Assertion Script
Agent-THREE QA Validation for Supabase Migration
"""

import asyncio
import os
import sys
from datetime import datetime
from typing import Dict, List, Any

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.core.database import async_session
from sqlalchemy import text
import asyncpg


async def check_table_exists(session, table_name: str) -> bool:
    """Check if a table exists in the database"""
    result = await session.execute(
        text("""
        SELECT EXISTS (
            SELECT FROM pg_tables
            WHERE schemaname = 'public'
            AND tablename = :table_name
        )
        """),
        {"table_name": table_name}
    )
    return result.scalar()


async def count_rows(session, table_name: str) -> int:
    """Count rows in a table"""
    result = await session.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
    return result.scalar()


async def check_indexes(session, table_name: str) -> List[Dict[str, Any]]:
    """Get all indexes for a table"""
    result = await session.execute(
        text("""
        SELECT indexname, indexdef
        FROM pg_indexes
        WHERE schemaname = 'public'
        AND tablename = :table_name
        """),
        {"table_name": table_name}
    )
    return [{"name": row[0], "definition": row[1]} for row in result.fetchall()]


async def check_columns(session, table_name: str) -> List[Dict[str, Any]]:
    """Get all columns for a table"""
    result = await session.execute(
        text("""
        SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema = 'public'
        AND table_name = :table_name
        ORDER BY ordinal_position
        """),
        {"table_name": table_name}
    )
    return [
        {
            "name": row[0],
            "type": row[1],
            "nullable": row[2] == 'YES',
            "default": row[3]
        }
        for row in result.fetchall()
    ]


async def check_constraints(session, table_name: str) -> List[Dict[str, Any]]:
    """Get all constraints for a table"""
    result = await session.execute(
        text("""
        SELECT conname, contype
        FROM pg_constraint
        WHERE conrelid = :table_name::regclass
        """),
        {"table_name": table_name}
    )
    constraint_types = {
        'p': 'PRIMARY KEY',
        'f': 'FOREIGN KEY',
        'u': 'UNIQUE',
        'c': 'CHECK'
    }
    return [
        {
            "name": row[0],
            "type": constraint_types.get(row[1], row[1])
        }
        for row in result.fetchall()
    ]


async def check_vector_extension(session) -> bool:
    """Check if pgvector extension is installed"""
    result = await session.execute(
        text("""
        SELECT EXISTS (
            SELECT 1 FROM pg_extension WHERE extname = 'vector'
        )
        """)
    )
    return result.scalar()


async def verify_supabase_sync_fields(session) -> Dict[str, Any]:
    """Verify Supabase sync metadata fields exist"""
    results = {}
    
    # Check conversations sync fields
    conv_columns = await check_columns(session, 'feedme_conversations')
    conv_sync_fields = [
        'supabase_sync_status',
        'supabase_sync_at',
        'supabase_conversation_id',
        'supabase_sync_error'
    ]
    results['conversations_sync_fields'] = all(
        any(col['name'] == field for col in conv_columns)
        for field in conv_sync_fields
    )
    
    # Check examples sync fields
    ex_columns = await check_columns(session, 'feedme_examples')
    ex_sync_fields = [
        'supabase_sync_status',
        'supabase_sync_at',
        'supabase_example_id',
        'supabase_sync_error'
    ]
    results['examples_sync_fields'] = all(
        any(col['name'] == field for col in ex_columns)
        for field in ex_sync_fields
    )
    
    return results


async def main():
    """Run all database assertions"""
    print("🔍 FeedMe Database Assertion Report")
    print("=" * 60)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print()
    
    async with async_session() as session:
        # Expected tables
        expected_tables = [
            'feedme_conversations',
            'feedme_examples',
            'feedme_folders',
            'feedme_examples_temp',
            'feedme_approval_stats'  # This is a view
        ]
        
        print("📊 Table Existence Check:")
        print("-" * 40)
        table_results = {}
        for table in expected_tables:
            exists = await check_table_exists(session, table)
            table_results[table] = exists
            status = "✅" if exists else "❌"
            print(f"{status} {table}: {'EXISTS' if exists else 'MISSING'}")
        
        print("\n📈 Row Counts:")
        print("-" * 40)
        for table, exists in table_results.items():
            if exists and table != 'feedme_approval_stats':  # Skip view
                count = await count_rows(session, table)
                print(f"   {table}: {count} rows")
        
        print("\n🔧 Vector Extension:")
        print("-" * 40)
        has_vector = await check_vector_extension(session)
        status = "✅" if has_vector else "❌"
        print(f"{status} pgvector extension: {'INSTALLED' if has_vector else 'NOT INSTALLED'}")
        
        print("\n🔄 Supabase Sync Metadata:")
        print("-" * 40)
        sync_results = await verify_supabase_sync_fields(session)
        for field, exists in sync_results.items():
            status = "✅" if exists else "❌"
            print(f"{status} {field}: {'PRESENT' if exists else 'MISSING'}")
        
        print("\n📑 Table Schemas:")
        print("-" * 40)
        
        # Check conversations table
        if table_results.get('feedme_conversations'):
            print("\nfeedme_conversations columns:")
            columns = await check_columns(session, 'feedme_conversations')
            important_cols = [
                'id', 'title', 'raw_transcript', 'parsed_content',
                'processing_status', 'approved_at', 'approved_by',
                'approval_status', 'quality_score', 'folder_id',
                'supabase_sync_status', 'supabase_conversation_id'
            ]
            for col in columns:
                if col['name'] in important_cols:
                    print(f"  - {col['name']}: {col['type']}")
        
        # Check examples table
        if table_results.get('feedme_examples'):
            print("\nfeedme_examples columns:")
            columns = await check_columns(session, 'feedme_examples')
            important_cols = [
                'id', 'conversation_id', 'question_text', 'answer_text',
                'question_embedding', 'answer_embedding', 'combined_embedding',
                'issue_type', 'usefulness_score', 'approved_at', 'approved_by',
                'supabase_sync_status', 'supabase_example_id'
            ]
            for col in columns:
                if col['name'] in important_cols:
                    print(f"  - {col['name']}: {col['type']}")
        
        # Check folders table
        if table_results.get('feedme_folders'):
            print("\nfeedme_folders columns:")
            columns = await check_columns(session, 'feedme_folders')
            for col in columns:
                print(f"  - {col['name']}: {col['type']}")
        
        print("\n🔐 Indexes:")
        print("-" * 40)
        
        # Check indexes for key tables
        for table in ['feedme_conversations', 'feedme_examples']:
            if table_results.get(table):
                indexes = await check_indexes(session, table)
                print(f"\n{table} indexes ({len(indexes)} total):")
                for idx in indexes[:5]:  # Show first 5
                    print(f"  - {idx['name']}")
                if len(indexes) > 5:
                    print(f"  ... and {len(indexes) - 5} more")
        
        print("\n✅ Database Assertion Summary:")
        print("-" * 40)
        
        # Calculate overall health
        total_checks = len(expected_tables) + 1 + len(sync_results)  # tables + vector + sync
        passed_checks = (
            sum(1 for exists in table_results.values() if exists) +
            (1 if has_vector else 0) +
            sum(1 for exists in sync_results.values() if exists)
        )
        
        health_percentage = (passed_checks / total_checks) * 100
        
        print(f"Database Health: {health_percentage:.1f}%")
        print(f"Passed Checks: {passed_checks}/{total_checks}")
        
        if health_percentage == 100:
            print("\n🎉 All database assertions passed!")
        else:
            print("\n⚠️  Some assertions failed. Please review the output above.")
        
        # Check for orphaned data
        print("\n🔍 Data Integrity Checks:")
        print("-" * 40)
        
        # Check for examples without conversations
        if table_results.get('feedme_examples') and table_results.get('feedme_conversations'):
            orphan_check = await session.execute(
                text("""
                SELECT COUNT(*) FROM feedme_examples e
                LEFT JOIN feedme_conversations c ON e.conversation_id = c.id
                WHERE c.id IS NULL
                """)
            )
            orphan_count = orphan_check.scalar()
            status = "✅" if orphan_count == 0 else "⚠️"
            print(f"{status} Orphaned examples: {orphan_count}")
        
        # Check for conversations without examples
        if table_results.get('feedme_examples') and table_results.get('feedme_conversations'):
            empty_conv_check = await session.execute(
                text("""
                SELECT COUNT(*) FROM feedme_conversations c
                LEFT JOIN feedme_examples e ON c.id = e.conversation_id
                WHERE e.id IS NULL AND c.processing_status = 'completed'
                """)
            )
            empty_count = empty_conv_check.scalar()
            print(f"ℹ️  Conversations without examples: {empty_count}")
        
        print("\n" + "=" * 60)
        print("Database assertion complete!")


if __name__ == "__main__":
    asyncio.run(main())