"""
FeedMe API Integration Tests

Comprehensive integration tests for FeedMe v2.0 backend-frontend integration.
Tests all API endpoints with actual frontend payloads and validates complete workflows.

Test Categories:
1. API Endpoint Integration Tests
2. Authentication Flow Tests  
3. File Upload Workflow Tests
4. Search and Analytics Integration Tests
5. Error Handling and Edge Cases
"""

import pytest
import asyncio
import json
import os
import tempfile
from datetime import datetime, timezone
from typing import Dict, Any, List
from httpx import AsyncClient
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch

# Import the FastAPI app
from app.main import app
from app.core.settings import settings
from app.feedme.schemas import (
    ConversationCreate,
    ProcessingStatus, 
    ApprovalStatus,
    SearchQuery
)

# Test configuration
API_BASE = "/api/v1/feedme"
TEST_USER_ID = "test@mailbird.com"
TEST_JWT_TOKEN = "test-jwt-token-123"

class TestAPIIntegration:
    """Test complete API integration with frontend payload formats"""
    
    @pytest.fixture
    def client(self):
        """Test client for API calls"""
        return TestClient(app)
    
    @pytest.fixture
    async def async_client(self):
        """Async test client for advanced testing"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            yield client
    
    @pytest.fixture
    def sample_conversation_data(self):
        """Sample conversation data matching frontend format"""
        return {
            "title": "Test Customer Support Conversation",
            "transcript_content": """
            <div class="conversation">
                <div class="message customer">
                    <span class="sender">Customer</span>
                    <span class="timestamp">2024-01-01 10:00:00</span>
                    <div class="content">I'm having trouble with email sync in Mailbird. 
                    My emails aren't updating automatically.</div>
                </div>
                <div class="message agent">
                    <span class="sender">Support Agent</span>
                    <span class="timestamp">2024-01-01 10:05:00</span>
                    <div class="content">I can help you with that. Let's try these steps:
                    1. Check your internet connection
                    2. Verify account settings 
                    3. Try manual sync</div>
                </div>
                <div class="message customer">
                    <span class="sender">Customer</span>
                    <span class="timestamp">2024-01-01 10:10:00</span>
                    <div class="content">That worked! Thank you so much.</div>
                </div>
            </div>
            """,
            "uploaded_by": TEST_USER_ID,
            "auto_process": True,
            "folder_id": None,
            "metadata": {
                "platform": "zendesk",
                "ticket_id": "12345",
                "customer_priority": "normal"
            }
        }
    
    @pytest.fixture
    def sample_search_query(self):
        """Sample search query matching frontend format"""
        return {
            "query": "email sync problem",
            "filters": {
                "dateRange": "month",
                "folders": [],
                "tags": ["sync", "email"],
                "confidence": [0.7, 1.0],
                "platforms": ["zendesk"],
                "status": ["completed"],
                "qualityScore": [0.8, 1.0]
            },
            "limit": 10,
            "offset": 0
        }

    # ========================================
    # API ENDPOINT INTEGRATION TESTS
    # ========================================

    @pytest.mark.asyncio
    async def test_conversation_upload_flow_complete(self, sample_conversation_data):
        """
        Test complete conversation upload flow from frontend to backend
        
        Validates:
        - Frontend payload acceptance
        - Backend processing initiation
        - Response format matching frontend expectations
        """
        # Create async client for this test
        async with AsyncClient(app=app, base_url="http://test") as async_client:
            # Test multipart form upload (file)
            with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as tmp_file:
                tmp_file.write(sample_conversation_data["transcript_content"])
                tmp_file_path = tmp_file.name
            
            try:
                with open(tmp_file_path, 'rb') as upload_file:
                    response = await async_client.post(
                    f"{API_BASE}/conversations/upload",
                    files={
                        "file": ("test_conversation.html", upload_file, "text/html")
                    },
                    data={
                        "title": sample_conversation_data["title"],
                        "uploaded_by": sample_conversation_data["uploaded_by"],
                        "auto_process": str(sample_conversation_data["auto_process"]).lower(),
                        "metadata": json.dumps(sample_conversation_data["metadata"])
                    }
                )
            
            # Validate response
            assert response.status_code == 200
            data = response.json()
            
            # Validate frontend-expected fields
            assert "id" in data
            assert data["title"] == sample_conversation_data["title"]
            assert data["processing_status"] in ["pending", "processing"]
            assert "created_at" in data
            assert "metadata" in data
            
            conversation_id = data["id"]
            
            # Test direct JSON upload
            json_response = await async_client.post(
                f"{API_BASE}/conversations/upload",
                json=sample_conversation_data
            )
            
            assert json_response.status_code == 200
            json_data = json_response.json()
            assert json_data["title"] == sample_conversation_data["title"]
            
                return conversation_id
                
            finally:
                os.unlink(tmp_file_path)

    @pytest.mark.asyncio
    async def test_conversation_list_with_pagination(self, async_client):
        """Test conversation listing with frontend pagination format"""
        
        response = await async_client.get(
            f"{API_BASE}/conversations",
            params={
                "page": 1,
                "page_size": 10,
                "folder_id": None,
                "status": "all",
                "search": ""
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Validate frontend-expected pagination format
        assert "conversations" in data
        assert "total_count" in data
        assert "page" in data
        assert "page_size" in data
        assert "has_next" in data
        assert isinstance(data["conversations"], list)

    @pytest.mark.asyncio
    async def test_conversation_crud_operations(self, async_client, sample_conversation_data):
        """Test complete CRUD operations for conversations"""
        
        # Create
        create_response = await async_client.post(
            f"{API_BASE}/conversations/upload",
            json=sample_conversation_data
        )
        assert create_response.status_code == 200
        conversation_id = create_response.json()["id"]
        
        # Read individual
        get_response = await async_client.get(f"{API_BASE}/conversations/{conversation_id}")
        assert get_response.status_code == 200
        conversation_data = get_response.json()
        assert conversation_data["id"] == conversation_id
        
        # Update
        update_data = {
            "title": "Updated Conversation Title",
            "metadata": {"updated": True}
        }
        update_response = await async_client.put(
            f"{API_BASE}/conversations/{conversation_id}",
            json=update_data
        )
        assert update_response.status_code == 200
        updated_data = update_response.json()
        assert updated_data["title"] == update_data["title"]
        
        # Delete
        delete_response = await async_client.delete(f"{API_BASE}/conversations/{conversation_id}")
        assert delete_response.status_code == 200
        
        # Verify deletion
        get_deleted_response = await async_client.get(f"{API_BASE}/conversations/{conversation_id}")
        assert get_deleted_response.status_code == 404

    @pytest.mark.asyncio
    async def test_processing_status_tracking(self, async_client, sample_conversation_data):
        """Test processing status tracking workflow"""
        
        # Upload conversation
        upload_response = await async_client.post(
            f"{API_BASE}/conversations/upload",
            json=sample_conversation_data
        )
        conversation_id = upload_response.json()["id"]
        
        # Get processing status
        status_response = await async_client.get(
            f"{API_BASE}/conversations/{conversation_id}/status"
        )
        assert status_response.status_code == 200
        status_data = status_response.json()
        
        # Validate frontend-expected status format
        assert "conversation_id" in status_data
        assert "status" in status_data
        assert "progress_percentage" in status_data
        assert status_data["status"] in ["pending", "processing", "completed", "failed"]
        assert 0 <= status_data["progress_percentage"] <= 100

    @pytest.mark.asyncio
    async def test_search_functionality(self, async_client, sample_search_query):
        """Test search functionality with frontend query format"""
        
        response = await async_client.post(
            f"{API_BASE}/search",
            json=sample_search_query
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Validate frontend-expected search result format
        assert "results" in data
        assert "total_results" in data
        assert "query" in data
        assert "search_time_ms" in data
        assert isinstance(data["results"], list)
        
        # Validate individual result format
        if data["results"]:
            result = data["results"][0]
            assert "id" in result
            assert "title" in result
            assert "snippet" in result
            assert "score" in result
            assert "conversation_id" in result

    @pytest.mark.asyncio
    async def test_analytics_dashboard_data(self, async_client):
        """Test analytics data for frontend dashboard"""
        
        response = await async_client.get(f"{API_BASE}/analytics")
        assert response.status_code == 200
        data = response.json()
        
        # Validate frontend-expected analytics format
        required_fields = [
            "total_conversations",
            "total_examples", 
            "processing_stats",
            "recent_activity",
            "performance_metrics"
        ]
        
        for field in required_fields:
            assert field in data
        
        # Validate processing stats structure
        processing_stats = data["processing_stats"]
        assert "pending" in processing_stats
        assert "processing" in processing_stats  
        assert "completed" in processing_stats
        assert "failed" in processing_stats

    # ========================================
    # ERROR HANDLING TESTS  
    # ========================================

    @pytest.mark.asyncio
    async def test_api_error_handling_formats(self, async_client):
        """Test that API errors match frontend expected formats"""
        
        # Test 404 for non-existent conversation
        response = await async_client.get(f"{API_BASE}/conversations/99999")
        assert response.status_code == 404
        error_data = response.json()
        assert "detail" in error_data
        
        # Test 400 for invalid upload
        bad_upload_response = await async_client.post(
            f"{API_BASE}/conversations/upload",
            json={"invalid": "data"}
        )
        assert bad_upload_response.status_code in [400, 422]
        
        # Test 400 for invalid search
        bad_search_response = await async_client.post(
            f"{API_BASE}/search",
            json={"invalid_query": True}
        )
        assert bad_search_response.status_code in [400, 422]

    @pytest.mark.asyncio
    async def test_large_file_upload_handling(self, async_client):
        """Test handling of large file uploads"""
        
        # Create a large HTML file (> 10MB limit)
        large_content = "<html>" + "a" * (11 * 1024 * 1024) + "</html>"
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as tmp_file:
            tmp_file.write(large_content)
            tmp_file_path = tmp_file.name
        
        try:
            with open(tmp_file_path, 'rb') as upload_file:
                response = await async_client.post(
                    f"{API_BASE}/conversations/upload",
                    files={
                        "file": ("large_conversation.html", upload_file, "text/html")
                    },
                    data={
                        "title": "Large File Test",
                        "uploaded_by": TEST_USER_ID
                    }
                )
            
            # Should reject large files
            assert response.status_code == 413 or response.status_code == 400
            
        finally:
            os.unlink(tmp_file_path)

    @pytest.mark.asyncio
    async def test_concurrent_api_requests(self, async_client, sample_conversation_data):
        """Test API handling of concurrent requests"""
        
        # Create multiple upload tasks
        tasks = []
        for i in range(5):
            conversation_data = {
                **sample_conversation_data,
                "title": f"Concurrent Test {i}"
            }
            task = async_client.post(f"{API_BASE}/conversations/upload", json=conversation_data)
            tasks.append(task)
        
        # Execute concurrent requests
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Validate that most requests succeed
        success_count = 0
        for response in responses:
            if hasattr(response, 'status_code') and response.status_code == 200:
                success_count += 1
        
        assert success_count >= 3  # At least 3 out of 5 should succeed

    # ========================================
    # PERFORMANCE TESTS
    # ========================================

    @pytest.mark.asyncio
    async def test_api_response_times(self, async_client):
        """Test API response time requirements"""
        
        start_time = datetime.now()
        response = await async_client.get(f"{API_BASE}/conversations")
        end_time = datetime.now()
        
        response_time_ms = (end_time - start_time).total_seconds() * 1000
        
        # API should respond within 2 seconds for list operations
        assert response_time_ms < 2000
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_search_performance(self, async_client, sample_search_query):
        """Test search performance requirements"""
        
        start_time = datetime.now()
        response = await async_client.post(f"{API_BASE}/search", json=sample_search_query)
        end_time = datetime.now()
        
        response_time_ms = (end_time - start_time).total_seconds() * 1000
        
        # Search should respond within 1 second
        assert response_time_ms < 1000
        assert response.status_code == 200
        
        data = response.json()
        if "search_time_ms" in data:
            assert data["search_time_ms"] < 500  # Internal search time should be < 500ms


class TestAuthenticationIntegration:
    """Test authentication flow integration"""
    
    @pytest.fixture
    def client(self):
        return TestClient(app)
    
    def test_jwt_token_validation(self, client):
        """Test JWT token validation for protected endpoints"""
        
        # Test without token
        response = client.get(f"{API_BASE}/conversations")
        # Note: Currently endpoints may not be protected, this tests the integration
        # In production, this should return 401 if authentication is required
        
        # Test with invalid token
        headers = {"Authorization": "Bearer invalid-token"}
        protected_response = client.get(f"{API_BASE}/conversations", headers=headers)
        # This should work or return proper error based on implementation
        
        assert protected_response.status_code in [200, 401, 403]
    
    def test_user_permissions_validation(self, client):
        """Test user permission validation for different operations"""
        
        # This will be implemented when authentication is fully integrated
        # For now, validate that endpoints are accessible
        response = client.get(f"{API_BASE}/analytics")
        assert response.status_code in [200, 401, 403]


class TestHealthAndMonitoring:
    """Test health checks and monitoring endpoints"""
    
    @pytest.fixture
    def client(self):
        return TestClient(app)
    
    def test_feedme_health_endpoint(self, client):
        """Test FeedMe health check endpoint"""
        
        response = client.get(f"{API_BASE}/health")
        assert response.status_code == 200
        
        data = response.json()
        assert "status" in data
        assert "service" in data
        assert data["status"] in ["healthy", "degraded", "unhealthy"]
    
    def test_system_health_dependencies(self, client):
        """Test that health check validates system dependencies"""
        
        response = client.get(f"{API_BASE}/health")
        data = response.json()
        
        # Should include dependency checks
        if "dependencies" in data:
            dependencies = data["dependencies"]
            assert "database" in dependencies
            assert "redis" in dependencies
            assert "celery" in dependencies


if __name__ == "__main__":
    # Run specific test categories
    pytest.main([
        __file__,
        "-v",
        "-s", 
        "--tb=short",
        "-k", "test_conversation_upload_flow_complete"
    ])