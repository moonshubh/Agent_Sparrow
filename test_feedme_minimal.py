#!/usr/bin/env python3
"""
Test minimal FeedMe upload API call
"""
import os
import requests
from dotenv import load_dotenv

load_dotenv()

def test_minimal_upload():
    """Test the most basic upload call"""
    try:
        print("🔗 Testing minimal FeedMe upload API call...")
        
        # Simple form data
        files = {
            'title': (None, 'Minimal Test'),
            'transcript_content': (None, 'Customer: Test\nAgent: Response'),
            'auto_process': (None, 'false'),  # Disable auto processing to avoid Celery
            'uploaded_by': (None, 'minimal_test')
        }
        
        response = requests.post(
            'http://localhost:8000/api/v1/feedme/conversations/upload',
            files=files,
            timeout=10
        )
        
        print(f"   Status Code: {response.status_code}")
        print(f"   Response: {response.text}")
        
        if response.status_code in [200, 202]:
            print("   ✅ Upload successful!")
            return True
        else:
            print("   ❌ Upload failed")
            return False
        
    except Exception as e:
        print(f"❌ Minimal upload test failed: {e}")
        return False

if __name__ == "__main__":
    success = test_minimal_upload()
    print(f"\n📊 Test Result: {'✅ PASS' if success else '❌ FAIL'}")