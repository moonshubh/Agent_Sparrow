#!/usr/bin/env python3
"""
Test script to identify the exact issue with FeedMe API
"""
import os
import sys
import traceback
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_redis_connection():
    """Test Redis connection for Celery"""
    try:
        import redis
        
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        celery_broker = os.getenv("FEEDME_CELERY_BROKER", "redis://localhost:6379/1")
        
        print(f"🔗 Testing Redis connection...")
        print(f"   REDIS_URL: {redis_url}")
        print(f"   FEEDME_CELERY_BROKER: {celery_broker}")
        
        # Test main Redis connection
        r = redis.from_url(redis_url)
        r.ping()
        print("✅ Main Redis connection successful!")
        
        # Test Celery broker connection
        broker_client = redis.from_url(celery_broker)
        broker_client.ping()
        print("✅ Celery broker Redis connection successful!")
        
        return True
        
    except ImportError:
        print("❌ Redis library not installed")
        return False
    except Exception as e:
        print(f"❌ Redis connection failed: {e}")
        return False

def test_celery_import():
    """Test Celery app and task imports"""
    try:
        print(f"\n🔗 Testing Celery imports...")
        
        # Test Celery app import
        from app.feedme.celery_app import celery_app
        print("✅ Celery app import successful!")
        
        # Test task import
        from app.feedme.tasks import process_transcript
        print("✅ Celery task import successful!")
        
        # Test settings import
        from app.core.settings import settings
        print(f"✅ Settings import successful!")
        print(f"   FEEDME_ENABLED: {settings.feedme_enabled}")
        print(f"   FEEDME_ASYNC_PROCESSING: {settings.feedme_async_processing}")
        
        return True
        
    except Exception as e:
        print(f"❌ Celery import failed: {e}")
        print(f"   Full traceback:")
        traceback.print_exc()
        return False

def test_db_import():
    """Test database imports"""
    try:
        print(f"\n🔗 Testing database imports...")
        
        from app.db.connection_manager import get_connection_manager
        print("✅ Connection manager import successful!")
        
        from app.db.embedding_utils import get_db_connection
        print("✅ DB utils import successful!")
        
        from app.feedme.schemas import ProcessingStatus, ConversationCreate
        print("✅ FeedMe schemas import successful!")
        
        return True
        
    except Exception as e:
        print(f"❌ Database import failed: {e}")
        print(f"   Full traceback:")
        traceback.print_exc()
        return False

def test_feedme_endpoint_simulation():
    """Simulate what the FeedMe endpoint does"""
    try:
        print(f"\n🔗 Testing FeedMe endpoint simulation...")
        
        # Import everything the endpoint needs
        from app.core.settings import settings
        from app.feedme.schemas import ConversationCreate, ProcessingStatus
        from app.api.v1.endpoints.feedme_endpoints import create_conversation_in_db
        
        print("✅ All endpoint imports successful!")
        
        # Check if async processing is enabled
        if settings.feedme_async_processing:
            print("⚠️  Async processing is ENABLED - this requires Redis and Celery worker")
            
            # Try to import the task (this is where the error likely occurs)
            try:
                from app.feedme.tasks import process_transcript
                print("✅ Task import successful - but Celery worker might not be running")
            except Exception as e:
                print(f"❌ Task import failed - this is likely the 500 error cause: {e}")
                return False
        else:
            print("ℹ️  Async processing is DISABLED - uploads should work synchronously")
        
        return True
        
    except Exception as e:
        print(f"❌ Endpoint simulation failed: {e}")
        print(f"   Full traceback:")
        traceback.print_exc()
        return False

def main():
    """Run all tests"""
    print("🧪 FeedMe API Troubleshooting\n")
    
    tests = [
        ("Redis Connection", test_redis_connection),
        ("Database Imports", test_db_import),
        ("Celery Imports", test_celery_import),
        ("Endpoint Simulation", test_feedme_endpoint_simulation),
    ]
    
    results = {}
    for test_name, test_func in tests:
        try:
            results[test_name] = test_func()
        except Exception as e:
            print(f"❌ {test_name} crashed: {e}")
            results[test_name] = False
    
    print(f"\n📊 Test Results:")
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"   {test_name}: {status}")
    
    if all(results.values()):
        print(f"\n🎉 All tests passed! The issue might be:")
        print(f"   1. Celery worker not running")
        print(f"   2. Redis not accessible from FastAPI server")
        print(f"   3. FastAPI server not able to connect to database")
    else:
        print(f"\n🔍 Root cause identified! Check the failed tests above.")
    
    return all(results.values())

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)