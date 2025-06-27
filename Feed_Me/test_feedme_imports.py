#!/usr/bin/env python3
"""
Test script to isolate FeedMe import issues
"""
import sys
import traceback
from dotenv import load_dotenv

load_dotenv()

def test_feedme_module_imports():
    """Test all FeedMe module imports one by one"""
    try:
        print("🔗 Testing FeedMe module imports...")
        
        # Test schemas first
        print("   Testing schemas...")
        from app.feedme.schemas import ProcessingStatus, ConversationCreate, FeedMeConversation
        print("   ✅ Schemas import successful!")
        
        # Test settings
        print("   Testing settings...")
        from app.core.settings import settings
        print(f"   ✅ Settings import successful! FEEDME_ENABLED: {settings.feedme_enabled}")
        print(f"   FEEDME_ASYNC_PROCESSING: {settings.feedme_async_processing}")
        
        # Test database utils
        print("   Testing database utils...")
        from app.db.embedding_utils import get_db_connection
        print("   ✅ Database utils import successful!")
        
        # Test endpoint imports without running
        print("   Testing endpoint file imports...")
        from app.api.v1.endpoints import feedme_endpoints
        print("   ✅ FeedMe endpoints module import successful!")
        
        # Test the problematic function directly
        print("   Testing specific functions...")
        from app.api.v1.endpoints.feedme_endpoints import create_conversation_in_db
        print("   ✅ create_conversation_in_db import successful!")
        
        return True
        
    except Exception as e:
        print(f"❌ FeedMe import failed: {e}")
        print(f"   Full traceback:")
        traceback.print_exc()
        return False

def test_minimal_endpoint_call():
    """Test a minimal version of what the endpoint does"""
    try:
        print("\n🔗 Testing minimal endpoint simulation...")
        
        # Import what we need
        from app.core.settings import settings
        from app.feedme.schemas import ConversationCreate, ProcessingStatus
        
        # Create minimal test data
        conversation_data = ConversationCreate(
            title="Test",
            original_filename="test.txt",
            raw_transcript="test content",
            uploaded_by="test_user"
        )
        
        print("   ✅ Test data creation successful!")
        
        # Check async processing settings
        if settings.feedme_async_processing:
            print("   ⚠️  Async processing is enabled - checking import paths...")
            
            # This is where the error likely occurs
            try:
                from app.feedme.tasks import process_transcript
                print("   ✅ Task import successful!")
            except Exception as e:
                print(f"   ❌ Task import failed (expected): {e}")
                print("   ℹ️  This should be handled by graceful degradation")
        
        return True
        
    except Exception as e:
        print(f"❌ Minimal endpoint test failed: {e}")
        traceback.print_exc()
        return False

def main():
    """Run all tests"""
    print("🧪 FeedMe Import Testing\n")
    
    results = {
        "Module Imports": test_feedme_module_imports(),
        "Endpoint Simulation": test_minimal_endpoint_call()
    }
    
    print(f"\n📊 Test Results:")
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"   {test_name}: {status}")
    
    return all(results.values())

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)