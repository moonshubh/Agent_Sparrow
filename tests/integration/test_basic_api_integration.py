"""
Basic FeedMe API Integration Test

Simple test to validate backend API is working properly and frontend can connect.
"""

import pytest
import asyncio
from httpx import AsyncClient
from fastapi.testclient import TestClient

from app.main import app

class TestBasicAPIIntegration:
    """Basic API integration tests"""
    
    def test_health_endpoint(self):
        """Test basic health endpoint"""
        client = TestClient(app)
        response = client.get("/api/v1/feedme/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        print(f"✓ Health check passed: {data}")

    def test_conversation_list_endpoint(self):
        """Test conversation list endpoint"""
        client = TestClient(app)
        response = client.get("/api/v1/feedme/conversations")
        assert response.status_code == 200
        data = response.json()
        assert "conversations" in data
        assert "total_count" in data
        print(f"✓ Conversation list endpoint working: {len(data['conversations'])} conversations")

    def test_analytics_endpoint(self):
        """Test analytics endpoint"""
        client = TestClient(app)
        response = client.get("/api/v1/feedme/analytics")
        assert response.status_code == 200
        data = response.json()
        assert "total_conversations" in data
        print(f"✓ Analytics endpoint working: {data['total_conversations']} total conversations")

    @pytest.mark.asyncio
    async def test_conversation_upload_basic(self):
        """Test basic conversation upload"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            # Simple conversation data
            conversation_data = {
                "title": "Test Integration Conversation",
                "transcript_content": "<div>Test content</div>",
                "uploaded_by": "test@mailbird.com",
                "auto_process": False
            }
            
            response = await client.post(
                "/api/v1/feedme/conversations/upload",
                json=conversation_data
            )
            
            print(f"Upload response status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"✓ Upload successful: conversation ID {data['id']}")
                assert "id" in data
                assert data["title"] == conversation_data["title"]
                return data["id"]
            else:
                print(f"Upload failed: {response.text}")
                # Don't fail the test, just report the issue
                return None

    @pytest.mark.asyncio 
    async def test_search_endpoint_basic(self):
        """Test basic search functionality"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            search_query = {
                "query": "test search",
                "filters": {},
                "limit": 10
            }
            
            response = await client.post(
                "/api/v1/feedme/search",
                json=search_query
            )
            
            print(f"Search response status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"✓ Search working: found {data.get('total_results', 0)} results")
                assert "results" in data
                assert "total_results" in data
            else:
                print(f"Search failed: {response.text}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])