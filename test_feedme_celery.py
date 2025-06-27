#!/usr/bin/env python3
"""
Test script for FeedMe Celery processing pipeline
"""

import sys
import os
import time
import logging
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_imports():
    """Test that all required modules can be imported"""
    logger.info("Testing imports...")
    
    try:
        import celery
        logger.info(f"✅ Celery version: {celery.VERSION}")
    except ImportError as e:
        logger.error(f"❌ Failed to import celery: {e}")
        return False
    
    try:
        import redis
        logger.info(f"✅ Redis client available")
    except ImportError as e:
        logger.error(f"❌ Failed to import redis: {e}")
        return False
    
    try:
        from bs4 import BeautifulSoup
        logger.info(f"✅ BeautifulSoup available")
    except ImportError as e:
        logger.error(f"❌ Failed to import BeautifulSoup: {e}")
        return False
    
    try:
        from app.feedme.celery_app import celery_app
        logger.info(f"✅ Celery app imported successfully")
        logger.info(f"   Broker: {celery_app.conf.broker_url}")
        logger.info(f"   Backend: {celery_app.conf.result_backend}")
    except ImportError as e:
        logger.error(f"❌ Failed to import celery_app: {e}")
        return False
    
    try:
        from app.feedme.html_parser import HTMLTranscriptParser
        logger.info(f"✅ HTML parser available")
    except ImportError as e:
        logger.error(f"❌ Failed to import HTML parser: {e}")
        return False
    
    return True

def test_redis_connection():
    """Test Redis connection"""
    logger.info("Testing Redis connection...")
    
    try:
        import redis
        
        # Test default Redis connection
        r = redis.Redis(host='localhost', port=6379, db=0)
        r.ping()
        logger.info("✅ Redis connection successful")
        return True
    except Exception as e:
        logger.error(f"❌ Redis connection failed: {e}")
        logger.info("   Make sure Redis is running:")
        logger.info("   - brew services start redis  # macOS")
        logger.info("   - sudo systemctl start redis  # Linux")
        logger.info("   - docker run -d -p 6379:6379 redis:7-alpine  # Docker")
        return False

def test_celery_worker():
    """Test Celery worker availability"""
    logger.info("Testing Celery worker...")
    
    try:
        from app.feedme.celery_app import celery_app, check_celery_health
        
        # Check health
        health = check_celery_health()
        logger.info(f"Celery health check: {health}")
        
        if health.get('status') == 'healthy':
            logger.info("✅ Celery workers are available")
            return True
        else:
            logger.error("❌ No Celery workers available")
            logger.info("   Start workers with: ./scripts/start-feedme-worker.sh")
            return False
            
    except Exception as e:
        logger.error(f"❌ Celery worker test failed: {e}")
        return False

def test_html_parsing():
    """Test HTML parsing functionality"""
    logger.info("Testing HTML parsing...")
    
    try:
        from app.feedme.html_parser import HTMLTranscriptParser
        
        # Sample HTML content
        html_content = '''
        <html>
        <body>
            <div class="zd-comment">
                <p>Customer: How do I set up my email in Mailbird?</p>
            </div>
            <div class="zd-comment">
                <p>Agent (Mailbird): To set up your email, go to Settings > Accounts and click Add Account.</p>
            </div>
        </body>
        </html>
        '''
        
        parser = HTMLTranscriptParser()
        examples = parser.parse_html_transcript(html_content)
        
        if examples:
            logger.info(f"✅ HTML parsing successful: {len(examples)} examples extracted")
            for i, example in enumerate(examples[:2]):  # Show first 2
                logger.info(f"   Example {i+1}:")
                logger.info(f"     Q: {example.get('question_text', '')[:50]}...")
                logger.info(f"     A: {example.get('answer_text', '')[:50]}...")
            return True
        else:
            logger.warning("⚠️ HTML parsing returned no examples")
            return False
            
    except Exception as e:
        logger.error(f"❌ HTML parsing test failed: {e}")
        return False

def test_task_submission():
    """Test submitting a Celery task"""
    logger.info("Testing Celery task submission...")
    
    try:
        from app.feedme.celery_app import celery_app
        from app.feedme.tasks import health_check
        
        # Submit health check task
        result = health_check.delay()
        logger.info(f"✅ Task submitted: {result.id}")
        
        # Wait for result (with timeout)
        try:
            task_result = result.get(timeout=10)
            logger.info(f"✅ Task completed: {task_result}")
            return True
        except Exception as e:
            logger.error(f"❌ Task execution failed: {e}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Task submission failed: {e}")
        return False

def main():
    """Run all tests"""
    logger.info("🚀 Starting FeedMe Celery Pipeline Tests")
    logger.info("=" * 50)
    
    tests = [
        ("Module Imports", test_imports),
        ("Redis Connection", test_redis_connection),
        ("HTML Parsing", test_html_parsing),
        ("Celery Workers", test_celery_worker),
        ("Task Submission", test_task_submission),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        logger.info(f"\n📋 Running: {test_name}")
        logger.info("-" * 30)
        
        try:
            if test_func():
                passed += 1
                logger.info(f"✅ {test_name}: PASSED")
            else:
                logger.error(f"❌ {test_name}: FAILED")
        except Exception as e:
            logger.error(f"❌ {test_name}: ERROR - {e}")
    
    logger.info("\n" + "=" * 50)
    logger.info(f"📊 Test Results: {passed}/{total} passed")
    
    if passed == total:
        logger.info("🎉 All tests passed! FeedMe Celery pipeline is ready.")
        return 0
    else:
        logger.error("❌ Some tests failed. Please check the logs above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())