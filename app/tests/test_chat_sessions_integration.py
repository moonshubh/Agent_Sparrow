"""
Integration tests for Chat Session API endpoints

Tests the complete chat session persistence functionality including
database operations, API endpoints, and authentication integration.
"""

import pytest
from datetime import datetime
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch

from app.main import app
from app.schemas.chat_schemas import AgentType, MessageType


@pytest.fixture
def client():
    """Test client fixture"""
    return TestClient(app)


@pytest.fixture
def mock_user():
    """Mock authenticated user"""
    return Mock(sub="test_user_123", roles=["user"])


class TestChatSessionEndpoints:
    """Test suite for chat session API endpoints"""
    
    def test_create_chat_session_success(self, client, mock_user):
        """Test successful chat session creation"""
        with patch('app.api.v1.endpoints.chat_session_endpoints.get_current_user', return_value=mock_user):
            with patch('app.api.v1.endpoints.chat_session_endpoints.create_chat_session_in_db') as mock_create:
                # Mock database response
                mock_create.return_value = {
                    "id": 1,
                    "user_id": "test_user_123",
                    "title": "Test Session",
                    "agent_type": "primary",
                    "created_at": datetime.now(),
                    "last_message_at": datetime.now(),
                    "updated_at": datetime.now(),
                    "is_active": True,
                    "metadata": {},
                    "message_count": 0
                }
                
                response = client.post(
                    "/api/v1/chat-sessions",
                    json={
                        "title": "Test Session",
                        "agent_type": "primary",
                        "metadata": {"test": "data"},
                        "is_active": True
                    },
                    headers={"Authorization": "Bearer test_token"}
                )
                
                assert response.status_code == 200
                data = response.json()
                assert data["title"] == "Test Session"
                assert data["agent_type"] == "primary"
                assert data["user_id"] == "test_user_123"
    
    def test_list_chat_sessions_success(self, client, mock_user):
        """Test successful chat session listing"""
        with patch('app.api.v1.endpoints.chat_session_endpoints.get_current_user', return_value=mock_user):
            with patch('app.api.v1.endpoints.chat_session_endpoints.get_chat_sessions_for_user') as mock_list:
                # Mock database response
                mock_list.return_value = {
                    "sessions": [
                        {
                            "id": 1,
                            "user_id": "test_user_123",
                            "title": "Test Session 1",
                            "agent_type": "primary",
                            "created_at": datetime.now(),
                            "last_message_at": datetime.now(),
                            "updated_at": datetime.now(),
                            "is_active": True,
                            "metadata": {},
                            "message_count": 5
                        }
                    ],
                    "total_count": 1,
                    "page": 1,
                    "page_size": 10,
                    "has_next": False,
                    "has_previous": False
                }
                
                response = client.get(
                    "/api/v1/chat-sessions",
                    headers={"Authorization": "Bearer test_token"}
                )
                
                assert response.status_code == 200
                data = response.json()
                assert len(data["sessions"]) == 1
                assert data["total_count"] == 1
                assert data["sessions"][0]["title"] == "Test Session 1"
    
    def test_get_chat_session_with_messages(self, client, mock_user):
        """Test retrieving a specific chat session with messages"""
        with patch('app.api.v1.endpoints.chat_session_endpoints.get_current_user', return_value=mock_user):
            with patch('app.api.v1.endpoints.chat_session_endpoints.get_chat_session_by_id') as mock_get_session:
                with patch('app.api.v1.endpoints.chat_session_endpoints.get_chat_messages_for_session') as mock_get_messages:
                    # Mock session data
                    mock_get_session.return_value = {
                        "id": 1,
                        "user_id": "test_user_123",
                        "title": "Test Session",
                        "agent_type": "primary",
                        "created_at": datetime.now(),
                        "last_message_at": datetime.now(),
                        "updated_at": datetime.now(),
                        "is_active": True,
                        "metadata": {},
                        "message_count": 2
                    }
                    
                    # Mock messages data
                    mock_get_messages.return_value = {
                        "messages": [
                            {
                                "id": 1,
                                "session_id": 1,
                                "content": "Hello",
                                "message_type": "user",
                                "agent_type": None,
                                "created_at": datetime.now(),
                                "metadata": {}
                            },
                            {
                                "id": 2,
                                "session_id": 1,
                                "content": "Hi there! How can I help?",
                                "message_type": "assistant",
                                "agent_type": "primary",
                                "created_at": datetime.now(),
                                "metadata": {}
                            }
                        ],
                        "total_count": 2,
                        "page": 1,
                        "page_size": 200,
                        "has_next": False,
                        "has_previous": False
                    }
                    
                    response = client.get(
                        "/api/v1/chat-sessions/1?include_messages=true",
                        headers={"Authorization": "Bearer test_token"}
                    )
                    
                    assert response.status_code == 200
                    data = response.json()
                    assert data["id"] == 1
                    assert data["title"] == "Test Session"
                    assert len(data["messages"]) == 2
                    assert data["messages"][0]["content"] == "Hello"
                    assert data["messages"][1]["agent_type"] == "primary"
    
    def test_create_chat_message_success(self, client, mock_user):
        """Test successful chat message creation"""
        with patch('app.api.v1.endpoints.chat_session_endpoints.get_current_user', return_value=mock_user):
            with patch('app.api.v1.endpoints.chat_session_endpoints.create_chat_message_in_db') as mock_create:
                # Mock database response
                mock_create.return_value = {
                    "id": 1,
                    "session_id": 1,
                    "content": "Test message",
                    "message_type": "user",
                    "agent_type": None,
                    "created_at": datetime.now(),
                    "metadata": {}
                }
                
                response = client.post(
                    "/api/v1/chat-sessions/1/messages",
                    json={
                        "content": "Test message",
                        "message_type": "user",
                        "metadata": {"test": "data"}
                    },
                    headers={"Authorization": "Bearer test_token"}
                )
                
                assert response.status_code == 200
                data = response.json()
                assert data["content"] == "Test message"
                assert data["message_type"] == "user"
                assert data["session_id"] == 1
    
    def test_update_chat_session_success(self, client, mock_user):
        """Test successful chat session update"""
        with patch('app.api.v1.endpoints.chat_session_endpoints.get_current_user', return_value=mock_user):
            with patch('app.api.v1.endpoints.chat_session_endpoints.update_chat_session_in_db') as mock_update:
                # Mock database response
                mock_update.return_value = {
                    "id": 1,
                    "user_id": "test_user_123",
                    "title": "Updated Session Title",
                    "agent_type": "primary",
                    "created_at": datetime.now(),
                    "last_message_at": datetime.now(),
                    "updated_at": datetime.now(),
                    "is_active": True,
                    "metadata": {"updated": True},
                    "message_count": 5
                }
                
                response = client.put(
                    "/api/v1/chat-sessions/1",
                    json={
                        "title": "Updated Session Title",
                        "metadata": {"updated": True}
                    },
                    headers={"Authorization": "Bearer test_token"}
                )
                
                assert response.status_code == 200
                data = response.json()
                assert data["title"] == "Updated Session Title"
                assert data["metadata"]["updated"] == True
    
    def test_delete_chat_session_success(self, client, mock_user):
        """Test successful chat session deletion (soft delete)"""
        with patch('app.api.v1.endpoints.chat_session_endpoints.get_current_user', return_value=mock_user):
            with patch('app.api.v1.endpoints.chat_session_endpoints.update_chat_session_in_db') as mock_update:
                # Mock database response for soft delete
                mock_update.return_value = {
                    "id": 1,
                    "user_id": "test_user_123",
                    "title": "Test Session",
                    "agent_type": "primary",
                    "created_at": datetime.now(),
                    "last_message_at": datetime.now(),
                    "updated_at": datetime.now(),
                    "is_active": False,  # Marked as inactive
                    "metadata": {},
                    "message_count": 5
                }
                
                response = client.delete(
                    "/api/v1/chat-sessions/1",
                    headers={"Authorization": "Bearer test_token"}
                )
                
                assert response.status_code == 200
                data = response.json()
                assert data["message"] == "Chat session deleted successfully"
                assert data["session_id"] == 1
    
    def test_unauthorized_access(self, client):
        """Test that endpoints require authentication"""
        response = client.get("/api/v1/chat-sessions")
        assert response.status_code == 401
        
        response = client.post(
            "/api/v1/chat-sessions",
            json={"title": "Test Session"}
        )
        assert response.status_code == 401


class TestChatSessionValidation:
    """Test suite for chat session data validation"""
    
    def test_chat_session_title_validation(self):
        """Test chat session title validation"""
        from app.schemas.chat_schemas import ChatSessionCreate
        
        # Valid title
        session = ChatSessionCreate(title="Valid Title")
        assert session.title == "Valid Title"
        
        # Empty title should raise validation error
        with pytest.raises(ValueError):
            ChatSessionCreate(title="")
        
        # Whitespace-only title should raise validation error
        with pytest.raises(ValueError):
            ChatSessionCreate(title="   ")
    
    def test_chat_message_validation(self):
        """Test chat message validation"""
        from app.schemas.chat_schemas import ChatMessageCreate
        
        # Valid user message
        message = ChatMessageCreate(
            session_id=1,
            content="Hello",
            message_type=MessageType.USER
        )
        assert message.content == "Hello"
        assert message.agent_type is None
        
        # Assistant message must have agent_type
        with pytest.raises(ValueError):
            ChatMessageCreate(
                session_id=1,
                content="Response",
                message_type=MessageType.ASSISTANT
            )
        
        # Valid assistant message
        message = ChatMessageCreate(
            session_id=1,
            content="Response",
            message_type=MessageType.ASSISTANT,
            agent_type=AgentType.PRIMARY
        )
        assert message.agent_type == AgentType.PRIMARY
    
    def test_enum_validation(self):
        """Test enum validation for agent and message types"""
        from app.schemas.chat_schemas import AgentType, MessageType
        
        # Valid agent types
        assert AgentType.PRIMARY == "primary"
        assert AgentType.LOG_ANALYSIS == "log_analysis"
        assert AgentType.RESEARCH == "research"
        assert AgentType.ROUTER == "router"
        
        # Valid message types
        assert MessageType.USER == "user"
        assert MessageType.ASSISTANT == "assistant"
        assert MessageType.SYSTEM == "system"


if __name__ == "__main__":
    pytest.main([__file__])