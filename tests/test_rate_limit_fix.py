#!/usr/bin/env python3
"""
Test script to verify rate limiting endpoints are working correctly
"""

import asyncio
import aiohttp
import json

async def test_rate_limit_endpoints():
    """Test that rate limiting endpoints respond correctly"""
    
    base_url = "http://localhost:8000/api/v1/rate-limits"
    
    endpoints_to_test = [
        "/status",
        "/health", 
        "/config",
        "/usage",
        "/metrics"
    ]
    
    print("🧪 Testing Rate Limiting Endpoints")
    print("=" * 40)
    
    async with aiohttp.ClientSession() as session:
        for endpoint in endpoints_to_test:
            url = f"{base_url}{endpoint}"
            print(f"\n📍 Testing: {url}")
            
            try:
                async with session.get(url) as response:
                    status = response.status
                    
                    if status == 200:
                        print(f"✅ {endpoint}: 200 OK")
                        # Get response content for verification
                        content = await response.text()
                        if content.strip():
                            print(f"   📄 Response: {len(content)} characters")
                        else:
                            print(f"   ⚠️  Empty response body")
                    elif status == 404:
                        print(f"❌ {endpoint}: 404 Not Found")
                    elif status >= 500:
                        print(f"🔥 {endpoint}: {status} Server Error")
                        error_text = await response.text()
                        print(f"   Error: {error_text[:100]}...")
                    else:
                        print(f"⚠️  {endpoint}: {status} {response.reason}")
                        
            except aiohttp.ClientConnectorError:
                print(f"🔌 {endpoint}: Connection failed - Backend server not running?")
            except Exception as e:
                print(f"💥 {endpoint}: Unexpected error - {e}")

if __name__ == "__main__":
    print("Rate Limiting Endpoint Test")
    print("Make sure the backend server is running on localhost:8000")
    print()
    
    asyncio.run(test_rate_limit_endpoints())
    
    print("\n" + "=" * 40)
    print("✅ Test complete! Check results above.")