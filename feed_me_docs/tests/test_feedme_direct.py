#!/usr/bin/env python3
"""
Test FeedMe endpoints directly without FastAPI server
"""
import asyncio
import sys
import traceback
from dotenv import load_dotenv

load_dotenv()

async def test_feedme_function_directly():
    """Test the FeedMe upload function directly"""
    try:
        print("🔗 Testing FeedMe upload function directly...")
        
        # Import required modules
        from app.core.settings import settings
        from app.feedme.schemas import ConversationCreate, ProcessingStatus
        from app.api.v1.endpoints.feedme_endpoints import create_conversation_in_db
        
        print(f"   FEEDME_ENABLED: {settings.feedme_enabled}")
        print(f"   FEEDME_ASYNC_PROCESSING: {settings.feedme_async_processing}")
        
        # Create test conversation data
        conversation_data = ConversationCreate(
            title="Direct Test Upload",
            original_filename="test.txt",
            raw_transcript="Customer: Test message\nAgent: Test response",
            uploaded_by="test_user"
        )
        
        print("   ✅ Test data created")
        
        # Test database creation function
        conversation = await create_conversation_in_db(conversation_data)
        print(f"   ✅ Conversation created successfully! ID: {conversation.id}")
        
        return True
        
    except Exception as e:
        print(f"❌ Direct function test failed: {e}")
        traceback.print_exc()
        return False

async def test_async_processing_simulation():
    """Test the async processing logic in isolation"""
    try:
        print("\n🔗 Testing async processing simulation...")
        
        from app.core.settings import settings
        
        # Check if async processing is enabled
        if settings.feedme_async_processing:
            print("   Async processing is ENABLED")
            
            # Try the import that's causing issues
            try:
                from app.feedme.tasks import process_transcript
                print("   ✅ Task import successful (unexpected!)")
            except ImportError as e:
                print(f"   ❌ Task import failed (expected): {e}")
                print("   ✅ Graceful degradation should handle this")
            except Exception as e:
                print(f"   ❌ Task import failed with unexpected error: {e}")
                return False
        else:
            print("   Async processing is DISABLED")
        
        return True
        
    except Exception as e:
        print(f"❌ Async processing test failed: {e}")
        traceback.print_exc()
        return False

async def main():
    """Run all tests"""
    print("🧪 FeedMe Direct Function Testing\n")
    
    tests = [
        ("Direct Function Test", test_feedme_function_directly),
        ("Async Processing Simulation", test_async_processing_simulation),
    ]
    
    results = {}
    for test_name, test_func in tests:
        try:
            results[test_name] = await test_func()
        except Exception as e:
            print(f"❌ {test_name} crashed: {e}")
            results[test_name] = False
    
    print(f"\n📊 Test Results:")
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"   {test_name}: {status}")
    
    return all(results.values())

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)