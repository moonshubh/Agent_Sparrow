#!/usr/bin/env python3
"""
Test FeedMe upload with HTML file to verify processing pipeline
"""

import requests
import json
import time
import os

# Configuration
API_BASE = "http://localhost:8000"
FEEDME_API = f"{API_BASE}/api/v1/feedme"

def create_test_html():
    """Create a test HTML file similar to email4.html"""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Support Ticket - Email Thread</title>
    </head>
    <body>
        <div class="conversation">
            <div class="message customer">
                <div class="sender">John Customer</div>
                <div class="timestamp">2025-01-15 10:30:00</div>
                <div class="content">
                    Hello, I'm having trouble with my email not syncing properly in Mailbird. 
                    How can I fix this issue?
                </div>
            </div>
            
            <div class="message agent">
                <div class="sender">Sarah Support</div>
                <div class="timestamp">2025-01-15 10:35:00</div>
                <div class="content">
                    Hi John! I can help you with the email sync issue. First, please try going to 
                    Account Settings > Synchronization and click "Force Sync". This often resolves 
                    most sync problems.
                </div>
            </div>
            
            <div class="message customer">
                <div class="sender">John Customer</div>
                <div class="timestamp">2025-01-15 10:40:00</div>
                <div class="content">
                    I tried that but it's still not working. What else can I do?
                </div>
            </div>
            
            <div class="message agent">
                <div class="sender">Sarah Support</div>
                <div class="timestamp">2025-01-15 10:45:00</div>
                <div class="content">
                    Let's try a more comprehensive solution. Please follow these steps:
                    1. Close Mailbird completely
                    2. Go to your Mailbird data folder
                    3. Delete the cache files
                    4. Restart Mailbird and re-add your account
                    This should resolve the sync issue completely.
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    
    with open("test_email.html", "w") as f:
        f.write(html_content)
    
    return "test_email.html"

def test_upload():
    """Test uploading HTML file"""
    print("🧪 Testing FeedMe HTML Upload & Processing")
    print("=" * 50)
    
    # Create test HTML file
    html_file = create_test_html()
    print(f"✅ Created test HTML file: {html_file}")
    
    try:
        # Upload the HTML file
        print(f"\n📤 Uploading to: {FEEDME_API}/conversations/upload")
        
        with open(html_file, 'rb') as f:
            files = {'transcript_file': (html_file, f, 'text/html')}
            data = {
                'title': 'Test HTML Email Thread',
                'uploaded_by': 'test_user',
                'auto_process': 'true'
            }
            
            response = requests.post(
                f"{FEEDME_API}/conversations/upload",
                files=files,
                data=data,
                timeout=30
            )
        
        print(f"📡 Response Status: {response.status_code}")
        print(f"📡 Response Headers: {dict(response.headers)}")
        
        if response.status_code in [200, 201, 202]:
            result = response.json()
            print(f"✅ Upload successful!")
            print(f"📋 Conversation ID: {result.get('id', 'N/A')}")
            print(f"📋 Processing Status: {result.get('processing_status', 'N/A')}")
            print(f"📋 Task ID: {result.get('metadata', {}).get('task_id', 'N/A')}")
            
            conversation_id = result.get('id')
            if conversation_id:
                # Monitor processing status
                print(f"\n⏳ Monitoring processing status...")
                for i in range(10):  # Check for 30 seconds
                    time.sleep(3)
                    try:
                        status_response = requests.get(
                            f"{FEEDME_API}/conversations/{conversation_id}/status",
                            timeout=10
                        )
                        if status_response.status_code == 200:
                            status_data = status_response.json()
                            current_status = status_data.get('processing_status', 'unknown')
                            print(f"⏰ Status check {i+1}: {current_status}")
                            
                            if current_status in ['completed', 'failed']:
                                break
                        else:
                            print(f"⚠️ Status check failed: {status_response.status_code}")
                    except Exception as e:
                        print(f"⚠️ Status check error: {e}")
                
                # Try to get preview examples
                print(f"\n🔍 Checking for extracted examples...")
                try:
                    preview_response = requests.get(
                        f"{FEEDME_API}/conversations/{conversation_id}/preview-examples",
                        timeout=10
                    )
                    if preview_response.status_code == 200:
                        examples = preview_response.json()
                        print(f"📊 Extracted {len(examples)} Q&A pairs:")
                        for i, example in enumerate(examples[:3], 1):  # Show first 3
                            print(f"  {i}. Q: {example.get('question_text', '')[:80]}...")
                            print(f"     A: {example.get('answer_text', '')[:80]}...")
                            print(f"     Confidence: {example.get('confidence_score', 0):.2f}")
                    else:
                        print(f"⚠️ No examples found or preview failed: {preview_response.status_code}")
                except Exception as e:
                    print(f"⚠️ Preview check error: {e}")
            
            return True
            
        else:
            print(f"❌ Upload failed!")
            print(f"📄 Response: {response.text}")
            return False
            
    except requests.RequestException as e:
        print(f"❌ Network error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False
    finally:
        # Clean up test file
        if os.path.exists(html_file):
            os.remove(html_file)
            print(f"🧹 Cleaned up test file: {html_file}")

def test_health():
    """Test health endpoint"""
    print("\n🏥 Testing FeedMe Health")
    print("=" * 30)
    
    try:
        response = requests.get(f"{FEEDME_API}/health", timeout=10)
        print(f"📡 Status: {response.status_code}")
        
        if response.status_code == 200:
            health = response.json()
            print(f"🔋 Overall Status: {health.get('status', 'unknown')}")
            
            components = health.get('components', {})
            for component, data in components.items():
                status = data.get('status', 'unknown') if isinstance(data, dict) else str(data)
                print(f"  - {component}: {status}")
        else:
            print(f"❌ Health check failed: {response.text}")
            
    except Exception as e:
        print(f"❌ Health check error: {e}")

if __name__ == "__main__":
    print("🚀 FeedMe Integration Test")
    print("=" * 40)
    
    # Test health first
    test_health()
    
    # Test upload
    test_upload()
    
    print("\n✨ Test completed!")