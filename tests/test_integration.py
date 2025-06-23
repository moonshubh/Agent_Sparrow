#!/usr/bin/env python3
"""
Integration test script for MB-Sparrow system
Tests frontend-backend connectivity and core functionality
"""

import requests
import json
import time

def test_backend_health():
    """Test backend API health"""
    try:
        response = requests.get("http://localhost:8000/", timeout=5)
        if response.status_code == 200:
            print("✅ Backend API is healthy")
            return True
        else:
            print(f"❌ Backend API returned status {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Backend API connection failed: {e}")
        return False

def test_frontend_health():
    """Test frontend server health"""
    try:
        response = requests.get("http://localhost:3000/", timeout=5)
        if response.status_code == 200:
            print("✅ Frontend server is healthy")
            return True
        else:
            print(f"❌ Frontend server returned status {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Frontend server connection failed: {e}")
        return False

def test_primary_agent():
    """Test primary agent endpoint"""
    try:
        response = requests.post(
            "http://localhost:8000/api/v1/agent/chat/stream",
            json={"message": "Hello"},
            headers={"Content-Type": "application/json"},
            timeout=10,
            stream=True
        )
        if response.status_code == 200:
            print("✅ Primary Agent streaming endpoint works")
            return True
        else:
            print(f"❌ Primary Agent endpoint returned status {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Primary Agent endpoint failed: {e}")
        return False

def test_log_analysis():
    """Test log analysis endpoint"""
    try:
        response = requests.post(
            "http://localhost:8000/api/v1/agent/logs",
            json={"content": "test log content"},
            headers={"Content-Type": "application/json"},
            timeout=15
        )
        if response.status_code == 200:
            print("✅ Log Analysis endpoint works")
            return True
        else:
            print(f"❌ Log Analysis endpoint returned status {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Log Analysis endpoint failed: {e}")
        return False

def test_research_agent():
    """Test research agent endpoint"""
    try:
        response = requests.post(
            "http://localhost:8000/api/v1/agent/research/stream",
            json={"query": "test query"},
            headers={"Content-Type": "application/json"},
            timeout=10,
            stream=True
        )
        if response.status_code == 200:
            print("✅ Research Agent streaming endpoint works")
            return True
        else:
            print(f"❌ Research Agent endpoint returned status {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Research Agent endpoint failed: {e}")
        return False

def main():
    print("🔍 Testing MB-Sparrow Integration...\n")
    
    tests = [
        ("Backend Health", test_backend_health),
        ("Frontend Health", test_frontend_health),
        ("Primary Agent", test_primary_agent),
        ("Log Analysis", test_log_analysis),
        ("Research Agent", test_research_agent),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"Testing {test_name}...")
        if test_func():
            passed += 1
        print()
    
    print(f"📊 Integration Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All systems operational! Frontend and backend are fully integrated.")
        print("\n🌐 Access the application at:")
        print("   Frontend: http://localhost:3000")
        print("   Backend API: http://localhost:8000")
        print("   API Docs: http://localhost:8000/docs")
    else:
        print("⚠️  Some components have issues. Check the logs above.")

if __name__ == "__main__":
    main()