#!/usr/bin/env python3
"""
Test list conversations function directly
"""
import asyncio
import sys
import traceback
from dotenv import load_dotenv

load_dotenv()

async def test_list_conversations():
    """Test the list conversations function directly"""
    try:
        print("🔗 Testing list_conversations function directly...")
        
        # Import required modules
        from app.core.settings import settings
        from app.feedme.schemas import ConversationListResponse, ProcessingStatus
        from app.db.embedding_utils import get_db_connection
        import psycopg2.extras as psycopg2_extras
        
        print(f"   FEEDME_ENABLED: {settings.feedme_enabled}")
        
        # Test the exact query from list_conversations
        with get_db_connection() as conn:
            print("   ✅ Database connection successful")
            
            # Build query with no filters (same as the endpoint)
            conditions = []
            params = []
            where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
            
            # Count total items
            count_query = f"SELECT COUNT(*) FROM feedme_conversations{where_clause}"
            print(f"   Count query: {count_query}")
            
            # Get paginated results
            page = 1
            page_size = 20
            offset = (page - 1) * page_size
            data_query = f"""
                SELECT * FROM feedme_conversations{where_clause}
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
            """
            print(f"   Data query: {data_query}")
            print(f"   Params: {params + [page_size, offset]}")
            
            with conn.cursor(cursor_factory=psycopg2_extras.RealDictCursor) as cur:
                # Get total count
                cur.execute(count_query, params)
                total_count = cur.fetchone()[0]
                print(f"   ✅ Total count: {total_count}")
                
                # Get paginated data
                cur.execute(data_query, params + [page_size, offset])
                rows = cur.fetchall()
                print(f"   ✅ Rows fetched: {len(rows)}")
                
                # Test FeedMeConversation creation
                if rows:
                    first_row = rows[0]
                    print(f"   First row keys: {list(first_row.keys())}")
                    print(f"   First row sample: {dict(first_row)}")
                    
                    try:
                        from app.feedme.schemas import FeedMeConversation
                        conversation = FeedMeConversation(**dict(first_row))
                        print(f"   ✅ FeedMeConversation creation successful: {conversation.id}")
                    except Exception as e:
                        print(f"   ❌ FeedMeConversation creation failed: {e}")
                        traceback.print_exc()
                        return False
                
                print(f"   ✅ Query execution successful")
        
        return True
        
    except Exception as e:
        print(f"❌ List conversations test failed: {e}")
        traceback.print_exc()
        return False

async def main():
    """Run test"""
    print("🧪 List Conversations Direct Test\n")
    
    success = await test_list_conversations()
    
    print(f"\n📊 Test Result: {'✅ PASS' if success else '❌ FAIL'}")
    
    return success

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)