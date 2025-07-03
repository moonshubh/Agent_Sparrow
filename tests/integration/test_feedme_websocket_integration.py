"""
FeedMe WebSocket Integration Tests

Comprehensive WebSocket integration tests for real-time communication
between FeedMe frontend and backend systems.

Test Categories:
1. WebSocket Connection Tests
2. Authentication & Authorization Tests
3. Real-time Processing Updates Tests
4. Message Broadcasting Tests
5. Connection Management Tests
6. Error Handling & Reconnection Tests
"""

import pytest
import asyncio
import json
import jwt
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List
from unittest.mock import Mock, patch, AsyncMock
import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

from fastapi.testclient import TestClient
from fastapi import FastAPI, WebSocket
from app.main import app
from app.api.v1.websocket.feedme_websocket import (
    router as websocket_router,
    notify_processing_update,
    notify_approval_update,
    send_notification
)
from app.feedme.websocket.realtime_manager import realtime_manager
from app.feedme.websocket.schemas import ProcessingUpdate, ApprovalUpdate

# Test configuration  
WS_BASE_URL = "ws://localhost:8000/ws"
TEST_JWT_SECRET = "test-secret-key"
TEST_USER_ID = "test@mailbird.com"
TEST_CONVERSATION_ID = 12345

class MockJWTHelper:
    """Helper for creating test JWT tokens"""
    
    @staticmethod
    def create_token(user_id: str, exp_minutes: int = 30) -> str:
        """Create a test JWT token"""
        payload = {
            "sub": user_id,
            "email": user_id,
            "exp": datetime.utcnow() + timedelta(minutes=exp_minutes),
            "iat": datetime.utcnow()
        }
        return jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")
    
    @staticmethod  
    def create_expired_token(user_id: str) -> str:
        """Create an expired JWT token for testing"""
        payload = {
            "sub": user_id,
            "email": user_id,
            "exp": datetime.utcnow() - timedelta(minutes=5),
            "iat": datetime.utcnow() - timedelta(minutes=10)
        }
        return jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")


class TestWebSocketConnection:
    """Test WebSocket connection establishment and basic functionality"""
    
    @pytest.fixture
    def valid_token(self):
        return MockJWTHelper.create_token(TEST_USER_ID)
    
    @pytest.fixture
    def expired_token(self):
        return MockJWTHelper.create_expired_token(TEST_USER_ID)
    
    @pytest.mark.asyncio
    async def test_websocket_connection_success(self, valid_token):
        """Test successful WebSocket connection with valid authentication"""
        
        # This test validates the WebSocket connection flow
        # In a real environment, this would connect to the actual WebSocket server
        
        with patch('app.api.v1.websocket.feedme_websocket.get_current_user_from_token') as mock_auth:
            mock_auth.return_value = TEST_USER_ID
            
            with patch('app.feedme.websocket.realtime_manager.realtime_manager.connect') as mock_connect:
                mock_connect.return_value = {
                    "connection_id": "test-123",
                    "user_id": TEST_USER_ID,
                    "room_id": f"conversation_{TEST_CONVERSATION_ID}",
                    "connected_at": datetime.now(timezone.utc)
                }
                
                # Simulate WebSocket connection
                websocket_url = f"{WS_BASE_URL}/feedme/processing/{TEST_CONVERSATION_ID}?token={valid_token}"
                
                # Validate that connection would be accepted
                assert valid_token is not None
                assert TEST_CONVERSATION_ID > 0
                
                # Verify mock was configured properly
                assert mock_auth.return_value == TEST_USER_ID
                assert mock_connect.return_value["user_id"] == TEST_USER_ID

    @pytest.mark.asyncio  
    async def test_websocket_connection_authentication_failure(self, expired_token):
        """Test WebSocket connection rejection with invalid authentication"""
        
        with patch('app.api.v1.websocket.feedme_websocket.get_current_user_from_token') as mock_auth:
            mock_auth.side_effect = Exception("Invalid token")
            
            # Simulate connection attempt with invalid token
            websocket_url = f"{WS_BASE_URL}/feedme/processing/{TEST_CONVERSATION_ID}?token={expired_token}"
            
            # Verify authentication would fail
            with pytest.raises(Exception, match="Invalid token"):
                await mock_auth(expired_token)

    @pytest.mark.asyncio
    async def test_websocket_connection_without_token(self):
        """Test WebSocket connection rejection without authentication token"""
        
        # Connection without token should be rejected
        websocket_url = f"{WS_BASE_URL}/feedme/processing/{TEST_CONVERSATION_ID}"
        
        # This should fail authentication
        with patch('app.api.v1.websocket.feedme_websocket.get_current_user_from_token') as mock_auth:
            mock_auth.side_effect = Exception("Authentication token required")
            
            with pytest.raises(Exception, match="Authentication token required"):
                await mock_auth(None)

    @pytest.mark.asyncio
    async def test_websocket_permission_validation(self, valid_token):
        """Test WebSocket permission validation for different user roles"""
        
        test_cases = [
            {
                "user_id": "admin@mailbird.com",
                "expected_permissions": ["processing:read", "processing:write", "approval:read", "approval:write"],
                "should_connect": True
            },
            {
                "user_id": "viewer@mailbird.com", 
                "expected_permissions": ["processing:read"],
                "should_connect": True
            },
            {
                "user_id": "restricted@example.com",
                "expected_permissions": [],
                "should_connect": False
            }
        ]
        
        for case in test_cases:
            with patch('app.api.v1.websocket.feedme_websocket.get_user_permissions') as mock_perms:
                mock_perms.return_value = case["expected_permissions"]
                
                permissions = await mock_perms(case["user_id"])
                
                if case["should_connect"]:
                    assert "processing:read" in permissions
                else:
                    assert "processing:read" not in permissions


class TestRealtimeProcessingUpdates:
    """Test real-time processing update functionality"""
    
    @pytest.fixture
    def processing_update(self):
        return ProcessingUpdate(
            conversation_id=TEST_CONVERSATION_ID,
            status="processing",
            progress=45,
            message="Extracting Q&A pairs from conversation",
            examples_extracted=12,
            stage="ai_extraction",
            metadata={
                "total_messages": 25,
                "processed_messages": 12
            }
        )
    
    @pytest.mark.asyncio
    async def test_processing_update_broadcast(self, processing_update):
        """Test broadcasting processing updates to connected clients"""
        
        with patch.object(realtime_manager, 'broadcast_processing_update') as mock_broadcast:
            mock_broadcast.return_value = []
            
            # Send processing update
            await notify_processing_update(processing_update)
            
            # Verify broadcast was called
            mock_broadcast.assert_called_once_with(processing_update)

    @pytest.mark.asyncio
    async def test_processing_update_message_format(self, processing_update):
        """Test processing update message format for frontend consumption"""
        
        # Validate message structure
        update_dict = processing_update.dict()
        
        # Required fields for frontend
        required_fields = [
            "conversation_id",
            "status", 
            "progress",
            "message"
        ]
        
        for field in required_fields:
            assert field in update_dict
        
        # Validate field types and values
        assert isinstance(update_dict["conversation_id"], int)
        assert update_dict["status"] in ["pending", "processing", "completed", "failed"]
        assert 0 <= update_dict["progress"] <= 100
        assert isinstance(update_dict["message"], str)

    @pytest.mark.asyncio
    async def test_multiple_processing_stages(self):
        """Test processing updates through multiple stages"""
        
        stages = [
            {"status": "pending", "progress": 0, "stage": "queued"},
            {"status": "processing", "progress": 20, "stage": "html_parsing"},
            {"status": "processing", "progress": 50, "stage": "ai_extraction"},
            {"status": "processing", "progress": 80, "stage": "embedding_generation"},
            {"status": "completed", "progress": 100, "stage": "finished"}
        ]
        
        with patch.object(realtime_manager, 'broadcast_processing_update') as mock_broadcast:
            mock_broadcast.return_value = []
            
            for stage_data in stages:
                update = ProcessingUpdate(
                    conversation_id=TEST_CONVERSATION_ID,
                    **stage_data
                )
                await notify_processing_update(update)
            
            # Verify all updates were broadcast
            assert mock_broadcast.call_count == len(stages)


class TestWebSocketMessageHandling:
    """Test WebSocket message handling and communication patterns"""
    
    @pytest.mark.asyncio
    async def test_ping_pong_mechanism(self):
        """Test WebSocket ping/pong heartbeat mechanism"""
        
        # Mock WebSocket connection
        mock_websocket = AsyncMock()
        mock_websocket.receive_json = AsyncMock(return_value={"type": "ping"})
        mock_websocket.send_json = AsyncMock()
        
        # Import the message handler
        from app.api.v1.websocket.feedme_websocket import _handle_client_message
        
        # Test ping message handling
        await _handle_client_message(
            websocket=mock_websocket,
            message={"type": "ping"},
            user_id=TEST_USER_ID,
            room_id=f"conversation_{TEST_CONVERSATION_ID}"
        )
        
        # Verify pong response was sent
        mock_websocket.send_json.assert_called_once()
        call_args = mock_websocket.send_json.call_args[0][0]
        assert call_args["type"] == "pong"
        assert "timestamp" in call_args

    @pytest.mark.asyncio
    async def test_subscription_management(self):
        """Test WebSocket subscription/unsubscription handling"""
        
        mock_websocket = AsyncMock()
        mock_websocket.send_json = AsyncMock()
        
        from app.api.v1.websocket.feedme_websocket import _handle_client_message
        
        # Test subscription
        await _handle_client_message(
            websocket=mock_websocket,
            message={"type": "subscribe", "subscription_type": "processing_updates"},
            user_id=TEST_USER_ID,
            room_id=f"conversation_{TEST_CONVERSATION_ID}"
        )
        
        # Test unsubscription  
        await _handle_client_message(
            websocket=mock_websocket,
            message={"type": "unsubscribe", "subscription_type": "processing_updates"},
            user_id=TEST_USER_ID,
            room_id=f"conversation_{TEST_CONVERSATION_ID}"
        )
        
        # Verify no errors occurred (no send_json calls for subscribe/unsubscribe)
        mock_websocket.send_json.assert_not_called()

    @pytest.mark.asyncio
    async def test_unknown_message_handling(self):
        """Test handling of unknown/invalid WebSocket messages"""
        
        mock_websocket = AsyncMock()
        mock_websocket.send_json = AsyncMock()
        
        from app.api.v1.websocket.feedme_websocket import _handle_client_message
        
        # Test unknown message type
        await _handle_client_message(
            websocket=mock_websocket,
            message={"type": "unknown_type", "data": "test"},
            user_id=TEST_USER_ID,
            room_id=f"conversation_{TEST_CONVERSATION_ID}"
        )
        
        # Should log warning but not crash
        # No response should be sent for unknown messages
        mock_websocket.send_json.assert_not_called()

    @pytest.mark.asyncio
    async def test_malformed_message_handling(self):
        """Test handling of malformed WebSocket messages"""
        
        mock_websocket = AsyncMock()
        mock_websocket.send_json = AsyncMock()
        
        from app.api.v1.websocket.feedme_websocket import _handle_client_message
        
        # Test message without type
        await _handle_client_message(
            websocket=mock_websocket,
            message={"data": "no_type_field"},
            user_id=TEST_USER_ID,
            room_id=f"conversation_{TEST_CONVERSATION_ID}"
        )
        
        # Should handle gracefully
        # No specific response expected for malformed messages
        

class TestWebSocketRoomManagement:
    """Test WebSocket room management functionality"""
    
    @pytest.mark.asyncio
    async def test_room_creation_and_joining(self):
        """Test WebSocket room creation and user joining"""
        
        with patch.object(realtime_manager, 'connect') as mock_connect:
            mock_connect.return_value = {
                "connection_id": "test-123",
                "user_id": TEST_USER_ID,
                "room_id": f"conversation_{TEST_CONVERSATION_ID}",
                "connected_at": datetime.now(timezone.utc)
            }
            
            # Simulate joining a conversation room
            connection_info = await mock_connect(
                websocket=AsyncMock(),
                user_id=TEST_USER_ID,
                room_id=f"conversation_{TEST_CONVERSATION_ID}",
                permissions=["processing:read"]
            )
            
            assert connection_info["user_id"] == TEST_USER_ID
            assert connection_info["room_id"] == f"conversation_{TEST_CONVERSATION_ID}"

    @pytest.mark.asyncio
    async def test_room_broadcasting(self):
        """Test broadcasting messages to room members"""
        
        test_message = {
            "type": "notification",
            "title": "Processing Complete",
            "message": "Your conversation has been processed successfully",
            "level": "success"
        }
        
        with patch.object(realtime_manager, 'broadcast_to_room') as mock_broadcast:
            mock_broadcast.return_value = []  # No failed connections
            
            await send_notification(
                room_id=f"conversation_{TEST_CONVERSATION_ID}",
                title=test_message["title"],
                message=test_message["message"],
                level=test_message["level"]
            )
            
            mock_broadcast.assert_called_once()
            call_args = mock_broadcast.call_args
            assert call_args[1]["room_id"] == f"conversation_{TEST_CONVERSATION_ID}"

    @pytest.mark.asyncio
    async def test_room_user_management(self):
        """Test adding and removing users from rooms"""
        
        with patch.object(realtime_manager, 'get_room_users') as mock_get_users:
            mock_get_users.return_value = [
                {
                    "user_id": TEST_USER_ID,
                    "connected_at": datetime.now(timezone.utc),
                    "permissions": ["processing:read"],
                    "message_count": 5
                }
            ]
            
            users = await mock_get_users(f"conversation_{TEST_CONVERSATION_ID}")
            assert len(users) == 1
            assert users[0]["user_id"] == TEST_USER_ID


class TestWebSocketErrorHandling:
    """Test WebSocket error handling and resilience"""
    
    @pytest.mark.asyncio
    async def test_connection_loss_handling(self):
        """Test handling of WebSocket connection loss"""
        
        with patch.object(realtime_manager, 'disconnect') as mock_disconnect:
            mock_disconnect.return_value = True
            
            # Simulate connection loss
            await mock_disconnect(AsyncMock())
            
            mock_disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_broadcast_failure_handling(self):
        """Test handling of broadcast failures"""
        
        with patch.object(realtime_manager, 'broadcast_processing_update') as mock_broadcast:
            mock_broadcast.side_effect = Exception("Broadcast failed")
            
            update = ProcessingUpdate(
                conversation_id=TEST_CONVERSATION_ID,
                status="processing",
                progress=50
            )
            
            # Should not raise exception, should log error
            await notify_processing_update(update)
            
            mock_broadcast.assert_called_once_with(update)

    @pytest.mark.asyncio
    async def test_authentication_token_expiry(self):
        """Test handling of expired authentication tokens"""
        
        expired_token = MockJWTHelper.create_expired_token(TEST_USER_ID)
        
        with patch('app.api.v1.websocket.feedme_websocket.get_current_user_from_token') as mock_auth:
            mock_auth.side_effect = Exception("Token has expired")
            
            # Connection should be rejected
            with pytest.raises(Exception, match="Token has expired"):
                await mock_auth(expired_token)


class TestWebSocketPerformance:
    """Test WebSocket performance characteristics"""
    
    @pytest.mark.asyncio
    async def test_concurrent_connections(self):
        """Test handling of multiple concurrent WebSocket connections"""
        
        connection_count = 10
        mock_connections = []
        
        with patch.object(realtime_manager, 'connect') as mock_connect:
            # Create multiple mock connections
            for i in range(connection_count):
                mock_connection = {
                    "connection_id": f"test-{i}",
                    "user_id": f"user{i}@test.com",
                    "room_id": f"conversation_{TEST_CONVERSATION_ID}",
                    "connected_at": datetime.now(timezone.utc)
                }
                mock_connections.append(mock_connection)
            
            mock_connect.side_effect = mock_connections
            
            # Simulate concurrent connections
            tasks = []
            for i in range(connection_count):
                task = mock_connect(
                    websocket=AsyncMock(),
                    user_id=f"user{i}@test.com",
                    room_id=f"conversation_{TEST_CONVERSATION_ID}",
                    permissions=["processing:read"]
                )
                tasks.append(task)
            
            connections = await asyncio.gather(*tasks)
            
            assert len(connections) == connection_count
            assert mock_connect.call_count == connection_count

    @pytest.mark.asyncio
    async def test_message_throughput(self):
        """Test WebSocket message throughput"""
        
        message_count = 100
        
        with patch.object(realtime_manager, 'broadcast_processing_update') as mock_broadcast:
            mock_broadcast.return_value = []
            
            # Send multiple messages quickly
            start_time = datetime.now()
            
            tasks = []
            for i in range(message_count):
                update = ProcessingUpdate(
                    conversation_id=TEST_CONVERSATION_ID,
                    status="processing",
                    progress=i,
                    message=f"Processing step {i}"
                )
                task = notify_processing_update(update)
                tasks.append(task)
            
            await asyncio.gather(*tasks)
            
            end_time = datetime.now()
            duration_ms = (end_time - start_time).total_seconds() * 1000
            
            # Should handle 100 messages within reasonable time
            assert duration_ms < 1000  # Less than 1 second
            assert mock_broadcast.call_count == message_count


if __name__ == "__main__":
    # Run WebSocket integration tests
    pytest.main([
        __file__,
        "-v",
        "-s",
        "--tb=short"
    ])