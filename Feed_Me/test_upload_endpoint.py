#!/usr/bin/env python3
"""
Test upload endpoint logic directly
"""
import asyncio
import sys
import traceback
from dotenv import load_dotenv

load_dotenv()

async def test_upload_logic():
    """Test the upload endpoint logic step by step"""
    try:
        print("🔗 Testing upload endpoint logic directly...")
        
        # Import required modules
        from app.core.settings import settings
        from app.feedme.schemas import ConversationCreate, ProcessingStatus
        from app.api.v1.endpoints.feedme_endpoints import create_conversation_in_db
        
        print(f"   FEEDME_ENABLED: {settings.feedme_enabled}")
        print(f"   FEEDME_ASYNC_PROCESSING: {settings.feedme_async_processing}")
        
        # Simulate the upload data processing
        title = "API Test Upload"
        transcript_content = "Customer: API test message\nAgent: API test response"
        auto_process = True
        uploaded_by = "api_test_user"
        
        # Build conversation data (same as in endpoint)
        conversation_data = ConversationCreate(
            title=title,
            original_filename=None,
            raw_transcript=transcript_content,
            uploaded_by=uploaded_by,
            metadata={"auto_process": auto_process}
        )
        
        print("   ✅ ConversationCreate data built")
        
        # Test database creation
        conversation = await create_conversation_in_db(conversation_data)
        print(f"   ✅ Conversation created: ID {conversation.id}")
        
        # Test async processing logic
        async_processing_failed = False
        if auto_process and settings.feedme_async_processing:
            try:
                # Import Celery task and trigger async processing
                from app.feedme.tasks import process_transcript
                print("   ❌ Task import succeeded (unexpected!)")
            except ImportError as e:
                print(f"   ✅ Task import failed as expected: {e}")
                async_processing_failed = True
            except Exception as e:
                print(f"   ❌ Task import failed with unexpected error: {e}")
                async_processing_failed = True
        
        # Test response logic
        if auto_process and settings.feedme_async_processing and not async_processing_failed:
            print("   Should return 202 Accepted for async processing")
        else:
            print("   Should return 200 OK for manual/fallback processing")
            if async_processing_failed:
                print("   Message: Async processing unavailable, set to manual processing")
        
        return True
        
    except Exception as e:
        print(f"❌ Upload logic test failed: {e}")
        traceback.print_exc()
        return False

async def main():
    """Run test"""
    print("🧪 Upload Endpoint Logic Test\n")
    
    success = await test_upload_logic()
    
    print(f"\n📊 Test Result: {'✅ PASS' if success else '❌ FAIL'}")
    
    return success

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)