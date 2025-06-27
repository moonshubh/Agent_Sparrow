#!/usr/bin/env python3
"""
Test FeedMe API Health Check

This script tests all FeedMe API endpoints to ensure they're working correctly after the database connection fixes.
"""

import requests
import json
import time
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from app.core.settings import settings

# API configuration
API_BASE_URL = "http://localhost:8000/api/v1/feedme"

# Test data
TEST_CONVERSATION_DATA = {
    "title": "Test API Health Check Conversation",
    "transcript_content": "Customer: I'm having issues with email sync.\nSupport: Let me help you with that.",
    "uploaded_by": "api_health_test",
    "auto_process": False
}

def print_test_header(test_name):
    """Print a formatted test header"""
    print(f"\n{'='*60}")
    print(f"🧪 {test_name}")
    print('='*60)

def check_feedme_enabled():
    """Check if FeedMe service is enabled"""
    if not settings.feedme_enabled:
        print("❌ FeedMe service is disabled. Enable it by setting FEEDME_ENABLED=true")
        return False
    print("✅ FeedMe service is enabled")
    return True

def test_list_conversations():
    """Test the GET /conversations endpoint"""
    print_test_header("Testing GET /conversations")
    
    try:
        response = requests.get(f"{API_BASE_URL}/conversations")
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Success! Found {data.get('total_count', 0)} conversations")
            print(f"   Page: {data.get('page', 1)}/{data.get('page_size', 20)}")
            return True
        else:
            print(f"❌ Failed with status {response.status_code}")
            print(f"   Error: {response.text}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to API. Is the server running on port 8000?")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def test_upload_conversation():
    """Test the POST /conversations/upload endpoint"""
    print_test_header("Testing POST /conversations/upload")
    
    try:
        # Prepare form data
        form_data = {
            'title': TEST_CONVERSATION_DATA['title'],
            'transcript_content': TEST_CONVERSATION_DATA['transcript_content'],
            'uploaded_by': TEST_CONVERSATION_DATA['uploaded_by'],
            'auto_process': str(TEST_CONVERSATION_DATA['auto_process']).lower()
        }
        
        response = requests.post(
            f"{API_BASE_URL}/conversations/upload",
            data=form_data
        )
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code in [200, 202]:
            data = response.json()
            print(f"✅ Success! Created conversation ID: {data.get('id')}")
            print(f"   Status: {data.get('processing_status')}")
            return data.get('id')
        else:
            print(f"❌ Failed with status {response.status_code}")
            print(f"   Error: {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return None

def test_get_conversation(conversation_id):
    """Test the GET /conversations/{id} endpoint"""
    print_test_header(f"Testing GET /conversations/{conversation_id}")
    
    try:
        response = requests.get(f"{API_BASE_URL}/conversations/{conversation_id}")
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Success! Retrieved conversation: {data.get('title')}")
            print(f"   Status: {data.get('processing_status')}")
            return True
        else:
            print(f"❌ Failed with status {response.status_code}")
            print(f"   Error: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def test_get_conversation_status(conversation_id):
    """Test the GET /conversations/{id}/status endpoint"""
    print_test_header(f"Testing GET /conversations/{conversation_id}/status")
    
    try:
        response = requests.get(f"{API_BASE_URL}/conversations/{conversation_id}/status")
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Success! Processing status: {data.get('status')}")
            print(f"   Progress: {data.get('progress_percentage', 0)}%")
            return True
        else:
            print(f"❌ Failed with status {response.status_code}")
            print(f"   Error: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def test_get_analytics():
    """Test the GET /analytics endpoint"""
    print_test_header("Testing GET /analytics")
    
    try:
        response = requests.get(f"{API_BASE_URL}/analytics")
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            conv_stats = data.get('conversation_stats', {})
            print(f"✅ Success! Analytics retrieved:")
            print(f"   Total conversations: {conv_stats.get('total_conversations', 0)}")
            print(f"   Processed: {conv_stats.get('processed_conversations', 0)}")
            return True
        else:
            print(f"❌ Failed with status {response.status_code}")
            print(f"   Error: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def test_delete_conversation(conversation_id):
    """Test the DELETE /conversations/{id} endpoint"""
    print_test_header(f"Testing DELETE /conversations/{conversation_id}")
    
    try:
        response = requests.delete(f"{API_BASE_URL}/conversations/{conversation_id}")
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Success! {data.get('message', 'Conversation deleted')}")
            return True
        else:
            print(f"❌ Failed with status {response.status_code}")
            print(f"   Error: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def run_health_check():
    """Run all health check tests"""
    print("\n🏥 FeedMe API Health Check")
    print("="*60)
    
    # Check if FeedMe is enabled
    if not check_feedme_enabled():
        return
    
    # Test results
    results = []
    
    # Test 1: List conversations
    results.append(("List Conversations", test_list_conversations()))
    
    # Test 2: Upload conversation
    conversation_id = test_upload_conversation()
    results.append(("Upload Conversation", conversation_id is not None))
    
    if conversation_id:
        # Test 3: Get specific conversation
        results.append(("Get Conversation", test_get_conversation(conversation_id)))
        
        # Test 4: Get processing status
        results.append(("Get Processing Status", test_get_conversation_status(conversation_id)))
        
        # Test 5: Delete conversation (cleanup)
        results.append(("Delete Conversation", test_delete_conversation(conversation_id)))
    
    # Test 6: Get analytics
    results.append(("Get Analytics", test_get_analytics()))
    
    # Summary
    print("\n" + "="*60)
    print("📊 Health Check Summary")
    print("="*60)
    
    total_tests = len(results)
    passed_tests = sum(1 for _, passed in results if passed)
    
    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{test_name:.<40} {status}")
    
    print(f"\nTotal: {passed_tests}/{total_tests} tests passed")
    
    if passed_tests == total_tests:
        print("\n🎉 All FeedMe API endpoints are working correctly!")
    else:
        print("\n⚠️  Some endpoints are failing. Check the logs above for details.")

def test_database_connection():
    """Test direct database connection"""
    print_test_header("Testing Database Connection")
    
    try:
        from app.db.connection_manager import get_connection_manager
        
        manager = get_connection_manager()
        with manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 as test")
                result = cur.fetchone()
                if result:
                    print("✅ Database connection successful")
                    
                    # Check if FeedMe tables exist
                    cur.execute("""
                        SELECT table_name 
                        FROM information_schema.tables 
                        WHERE table_schema = 'public' 
                        AND table_name LIKE 'feedme_%'
                    """)
                    tables = cur.fetchall()
                    print(f"   Found {len(tables)} FeedMe tables:")
                    for table in tables:
                        print(f"   - {table[0]}")
                    return True
                else:
                    print("❌ Database connection test failed")
                    return False
                    
    except Exception as e:
        print(f"❌ Database connection error: {e}")
        return False

if __name__ == "__main__":
    # First test database connection
    test_database_connection()
    
    # Then run API health checks
    run_health_check()