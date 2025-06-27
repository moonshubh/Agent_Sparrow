#!/usr/bin/env python3
"""
Quick script to test database connection and check FeedMe tables
"""
import os
import sys
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

def test_db_connection():
    """Test database connection and check for FeedMe tables"""
    if not DATABASE_URL:
        print("❌ ERROR: DATABASE_URL not found in environment variables")
        return False
    
    try:
        print(f"🔗 Connecting to database...")
        print(f"   URL: {DATABASE_URL[:50]}...")
        
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        print("✅ Database connection successful!")
        
        # Check if FeedMe tables exist
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name LIKE 'feedme%'
            ORDER BY table_name;
        """)
        
        feedme_tables = cursor.fetchall()
        
        print(f"\n📊 FeedMe tables found: {len(feedme_tables)}")
        for table in feedme_tables:
            print(f"   - {table['table_name']}")
        
        # Check specifically for required tables
        required_tables = ['feedme_conversations', 'feedme_examples']
        missing_tables = []
        
        for table_name in required_tables:
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = %s
                );
            """, (table_name,))
            
            exists = cursor.fetchone()['exists']
            if exists:
                print(f"✅ Table '{table_name}' exists")
            else:
                print(f"❌ Table '{table_name}' MISSING")
                missing_tables.append(table_name)
        
        if missing_tables:
            print(f"\n⚠️  ISSUE FOUND: Missing required tables: {missing_tables}")
            print("   This is likely the cause of the 500 errors!")
            print("   SOLUTION: Run the FeedMe migrations to create the tables.")
        else:
            print(f"\n✅ All required FeedMe tables exist!")
            
            # Check if there's data in the tables
            for table_name in required_tables:
                cursor.execute(f"SELECT COUNT(*) as count FROM {table_name}")
                count = cursor.fetchone()['count']
                print(f"   - {table_name}: {count} records")
        
        cursor.close()
        conn.close()
        
        return len(missing_tables) == 0
        
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False

if __name__ == "__main__":
    success = test_db_connection()
    sys.exit(0 if success else 1)