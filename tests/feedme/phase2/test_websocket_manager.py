"""
TDD Tests for FeedMe v2.0 WebSocket Real-time Updates
Tests for connection management, broadcasting, and authentication
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
import asyncio
import json
from datetime import datetime

from fastapi import WebSocket, WebSocketDisconnect

from app.feedme.websocket.realtime_manager import (
    FeedMeRealtimeManager,
    ConnectionInfo,
    MessageType,
    WebSocketRoom
)
from app.feedme.websocket.schemas import (
    ProcessingUpdate,
    ApprovalUpdate,
    ConnectionRequest,
    BroadcastMessage
)


class TestFeedMeRealtimeManager:
    """Test suite for WebSocket real-time manager"""

    @pytest.fixture
    def realtime_manager(self):
        """Create real-time manager for testing"""
        return FeedMeRealtimeManager()

    @pytest.fixture
    def mock_websocket(self):
        """Mock WebSocket connection"""
        websocket = Mock(spec=WebSocket)
        websocket.accept = AsyncMock()
        websocket.send_json = AsyncMock()
        websocket.send_text = AsyncMock()
        websocket.receive_json = AsyncMock()
        websocket.close = AsyncMock()
        return websocket

    @pytest.fixture
    def connection_info(self):
        """Sample connection info"""
        return ConnectionInfo(
            user_id="user@example.com",
            room_id="conversation_123",
            permissions=["read", "write"],
            connected_at=datetime.now()
        )

    async def test_connect_websocket_success(self, realtime_manager, mock_websocket, connection_info):
        """Test successful WebSocket connection"""
        # Execute connection
        await realtime_manager.connect(
            websocket=mock_websocket,
            user_id=connection_info.user_id,
            room_id=connection_info.room_id,
            permissions=connection_info.permissions
        )
        
        # Verify WebSocket was accepted
        mock_websocket.accept.assert_called_once()
        
        # Verify connection was stored
        assert connection_info.room_id in realtime_manager.rooms
        room = realtime_manager.rooms[connection_info.room_id]
        assert mock_websocket in room.connections
        assert room.connections[mock_websocket].user_id == connection_info.user_id

    async def test_connect_multiple_users_same_room(self, realtime_manager):
        """Test multiple users connecting to same room"""
        # Create multiple mock websockets
        websocket1 = Mock(spec=WebSocket)
        websocket1.accept = AsyncMock()
        websocket2 = Mock(spec=WebSocket)
        websocket2.accept = AsyncMock()
        
        room_id = "conversation_123"
        
        # Connect both users
        await realtime_manager.connect(websocket1, "user1@example.com", room_id)
        await realtime_manager.connect(websocket2, "user2@example.com", room_id)
        
        # Verify both connections are in the same room
        room = realtime_manager.rooms[room_id]
        assert len(room.connections) == 2
        assert websocket1 in room.connections
        assert websocket2 in room.connections

    async def test_disconnect_websocket(self, realtime_manager, mock_websocket):
        """Test WebSocket disconnection cleanup"""
        room_id = "conversation_123"
        user_id = "user@example.com"
        
        # Connect first
        await realtime_manager.connect(mock_websocket, user_id, room_id)
        
        # Verify connection exists
        assert room_id in realtime_manager.rooms
        assert mock_websocket in realtime_manager.rooms[room_id].connections
        
        # Disconnect
        await realtime_manager.disconnect(mock_websocket)
        
        # Verify connection was removed
        if room_id in realtime_manager.rooms:
            assert mock_websocket not in realtime_manager.rooms[room_id].connections

    async def test_broadcast_to_room_success(self, realtime_manager):
        """Test broadcasting message to room"""
        room_id = "conversation_123"
        
        # Create multiple mock websockets
        websocket1 = Mock(spec=WebSocket)
        websocket1.accept = AsyncMock()
        websocket1.send_json = AsyncMock()
        
        websocket2 = Mock(spec=WebSocket)
        websocket2.accept = AsyncMock()
        websocket2.send_json = AsyncMock()
        
        # Connect both websockets
        await realtime_manager.connect(websocket1, "user1@example.com", room_id)
        await realtime_manager.connect(websocket2, "user2@example.com", room_id)
        
        # Create test message
        message = ProcessingUpdate(
            conversation_id=123,
            status="processing",
            stage="ai_extraction",
            progress=50,
            message="Extracting Q&A pairs..."
        )
        
        # Broadcast message
        await realtime_manager.broadcast_to_room(room_id, message.model_dump())
        
        # Verify both websockets received the message
        websocket1.send_json.assert_called_once()
        websocket2.send_json.assert_called_once()
        
        # Verify message content
        sent_message1 = websocket1.send_json.call_args[0][0]
        assert sent_message1['conversation_id'] == 123
        assert sent_message1['status'] == "processing"

    async def test_broadcast_with_failed_connections(self, realtime_manager):
        """Test broadcasting with some failed connections"""
        room_id = "conversation_123"
        
        # Create websockets - one will fail, one will succeed
        working_websocket = Mock(spec=WebSocket)
        working_websocket.accept = AsyncMock()
        working_websocket.send_json = AsyncMock()
        
        failing_websocket = Mock(spec=WebSocket)
        failing_websocket.accept = AsyncMock()
        failing_websocket.send_json = AsyncMock(side_effect=Exception("Connection lost"))
        
        # Connect both
        await realtime_manager.connect(working_websocket, "user1@example.com", room_id)
        await realtime_manager.connect(failing_websocket, "user2@example.com", room_id)
        
        # Create test message
        message = {"type": "test", "data": "test message"}
        
        # Broadcast message
        failed_connections = await realtime_manager.broadcast_to_room(room_id, message)
        
        # Verify working connection received message
        working_websocket.send_json.assert_called_once_with(message)
        
        # Verify failed connection was identified
        assert len(failed_connections) == 1
        assert failing_websocket in failed_connections

    async def test_broadcast_approval_update(self, realtime_manager):
        """Test broadcasting approval workflow updates"""
        room_id = "approval_updates"
        
        # Create websocket
        websocket = Mock(spec=WebSocket)
        websocket.accept = AsyncMock()
        websocket.send_json = AsyncMock()
        
        # Connect with approval permissions
        await realtime_manager.connect(
            websocket, 
            "reviewer@example.com", 
            room_id,
            permissions=["approval:read", "approval:write"]
        )
        
        # Create approval update
        update = ApprovalUpdate(
            temp_example_id=456,
            previous_status="pending",
            new_status="approved",
            reviewer_id="reviewer@example.com",
            timestamp=datetime.now()
        )
        
        # Broadcast approval update
        await realtime_manager.broadcast_approval_update(update)
        
        # Verify websocket received the update
        websocket.send_json.assert_called_once()
        sent_message = websocket.send_json.call_args[0][0]
        assert sent_message['temp_example_id'] == 456
        assert sent_message['new_status'] == "approved"

    async def test_permission_based_filtering(self, realtime_manager):
        """Test message filtering based on user permissions"""
        room_id = "mixed_permissions"
        
        # Create websockets with different permissions
        admin_websocket = Mock(spec=WebSocket)
        admin_websocket.accept = AsyncMock()
        admin_websocket.send_json = AsyncMock()
        
        readonly_websocket = Mock(spec=WebSocket)
        readonly_websocket.accept = AsyncMock()
        readonly_websocket.send_json = AsyncMock()
        
        # Connect with different permissions
        await realtime_manager.connect(
            admin_websocket, 
            "admin@example.com", 
            room_id,
            permissions=["approval:read", "approval:write", "admin"]
        )
        
        await realtime_manager.connect(
            readonly_websocket, 
            "viewer@example.com", 
            room_id,
            permissions=["approval:read"]
        )
        
        # Send admin-only message
        admin_message = {
            "type": "admin_notification",
            "required_permission": "admin",
            "data": "Sensitive admin data"
        }
        
        # Broadcast with permission filtering
        await realtime_manager.broadcast_to_room(
            room_id, 
            admin_message,
            required_permission="admin"
        )
        
        # Verify only admin received the message
        admin_websocket.send_json.assert_called_once()
        readonly_websocket.send_json.assert_not_called()

    async def test_room_cleanup_when_empty(self, realtime_manager, mock_websocket):
        """Test automatic room cleanup when last user disconnects"""
        room_id = "temporary_room"
        
        # Connect single user
        await realtime_manager.connect(mock_websocket, "user@example.com", room_id)
        
        # Verify room exists
        assert room_id in realtime_manager.rooms
        
        # Disconnect user
        await realtime_manager.disconnect(mock_websocket)
        
        # Verify room was cleaned up
        assert room_id not in realtime_manager.rooms

    async def test_get_room_users(self, realtime_manager):
        """Test getting list of users in a room"""
        room_id = "conversation_123"
        
        # Create multiple websockets
        websocket1 = Mock(spec=WebSocket)
        websocket1.accept = AsyncMock()
        websocket2 = Mock(spec=WebSocket)
        websocket2.accept = AsyncMock()
        
        # Connect users
        await realtime_manager.connect(websocket1, "user1@example.com", room_id)
        await realtime_manager.connect(websocket2, "user2@example.com", room_id)
        
        # Get room users
        users = realtime_manager.get_room_users(room_id)
        
        # Verify users list
        assert len(users) == 2
        user_ids = [user.user_id for user in users]
        assert "user1@example.com" in user_ids
        assert "user2@example.com" in user_ids

    async def test_heartbeat_mechanism(self, realtime_manager, mock_websocket):
        """Test WebSocket heartbeat/ping mechanism"""
        room_id = "conversation_123"
        
        # Connect websocket
        await realtime_manager.connect(mock_websocket, "user@example.com", room_id)
        
        # Send heartbeat
        await realtime_manager.send_heartbeat(room_id)
        
        # Verify ping was sent
        mock_websocket.send_json.assert_called_once()
        sent_message = mock_websocket.send_json.call_args[0][0]
        assert sent_message['type'] == 'ping'

    async def test_connection_authentication(self, realtime_manager):
        """Test WebSocket connection authentication"""
        # This would typically integrate with the authentication system
        # For now, test basic validation
        
        # Test invalid user_id
        with pytest.raises(ValueError):
            await realtime_manager.validate_connection(
                user_id="",  # Invalid: empty
                room_id="conversation_123",
                permissions=[]
            )
        
        # Test invalid room_id
        with pytest.raises(ValueError):
            await realtime_manager.validate_connection(
                user_id="user@example.com",
                room_id="",  # Invalid: empty
                permissions=[]
            )

    async def test_concurrent_connections(self, realtime_manager):
        """Test handling concurrent connections"""
        room_id = "high_traffic_room"
        
        # Create many websockets
        websockets = []
        for i in range(10):
            websocket = Mock(spec=WebSocket)
            websocket.accept = AsyncMock()
            websocket.send_json = AsyncMock()
            websockets.append(websocket)
        
        # Connect all websockets concurrently
        connect_tasks = [
            realtime_manager.connect(ws, f"user{i}@example.com", room_id)
            for i, ws in enumerate(websockets)
        ]
        await asyncio.gather(*connect_tasks)
        
        # Verify all connections
        room = realtime_manager.rooms[room_id]
        assert len(room.connections) == 10
        
        # Test broadcasting to all
        test_message = {"type": "test", "data": "concurrent test"}
        await realtime_manager.broadcast_to_room(room_id, test_message)
        
        # Verify all websockets received the message
        for websocket in websockets:
            websocket.send_json.assert_called_once_with(test_message)

    async def test_message_queuing_for_disconnected_users(self, realtime_manager):
        """Test message queuing when users are temporarily disconnected"""
        # This feature would queue messages for users who disconnect and reconnect
        room_id = "conversation_123"
        user_id = "user@example.com"
        
        # Connect user
        websocket = Mock(spec=WebSocket)
        websocket.accept = AsyncMock()
        websocket.send_json = AsyncMock()
        
        await realtime_manager.connect(websocket, user_id, room_id)
        
        # Disconnect user
        await realtime_manager.disconnect(websocket)
        
        # Send message while disconnected (should be queued)
        message = {"type": "queued_message", "data": "This should be queued"}
        await realtime_manager.queue_message_for_user(user_id, message)
        
        # Reconnect user
        new_websocket = Mock(spec=WebSocket)
        new_websocket.accept = AsyncMock()
        new_websocket.send_json = AsyncMock()
        
        await realtime_manager.connect(new_websocket, user_id, room_id)
        
        # Verify queued message was delivered
        # This would require implementation of message queuing
        # For now, just verify the reconnection worked
        assert room_id in realtime_manager.rooms
        assert new_websocket in realtime_manager.rooms[room_id].connections


class TestWebSocketRoom:
    """Test suite for WebSocket room management"""

    def test_room_creation(self):
        """Test room creation with basic properties"""
        room = WebSocketRoom(room_id="test_room")
        
        assert room.room_id == "test_room"
        assert len(room.connections) == 0
        assert room.created_at is not None

    def test_add_connection(self):
        """Test adding connection to room"""
        room = WebSocketRoom(room_id="test_room")
        websocket = Mock(spec=WebSocket)
        connection_info = ConnectionInfo(
            user_id="user@example.com",
            room_id="test_room",
            permissions=["read"],
            connected_at=datetime.now()
        )
        
        room.add_connection(websocket, connection_info)
        
        assert websocket in room.connections
        assert room.connections[websocket] == connection_info

    def test_remove_connection(self):
        """Test removing connection from room"""
        room = WebSocketRoom(room_id="test_room")
        websocket = Mock(spec=WebSocket)
        connection_info = ConnectionInfo(
            user_id="user@example.com",
            room_id="test_room",
            permissions=["read"],
            connected_at=datetime.now()
        )
        
        # Add then remove
        room.add_connection(websocket, connection_info)
        room.remove_connection(websocket)
        
        assert websocket not in room.connections

    def test_get_users_with_permission(self):
        """Test filtering users by permission"""
        room = WebSocketRoom(room_id="test_room")
        
        # Add users with different permissions
        websocket1 = Mock(spec=WebSocket)
        websocket2 = Mock(spec=WebSocket)
        
        admin_info = ConnectionInfo(
            user_id="admin@example.com",
            room_id="test_room",
            permissions=["read", "write", "admin"],
            connected_at=datetime.now()
        )
        
        user_info = ConnectionInfo(
            user_id="user@example.com",
            room_id="test_room",
            permissions=["read"],
            connected_at=datetime.now()
        )
        
        room.add_connection(websocket1, admin_info)
        room.add_connection(websocket2, user_info)
        
        # Test permission filtering
        admin_users = room.get_connections_with_permission("admin")
        assert len(admin_users) == 1
        assert websocket1 in admin_users
        
        read_users = room.get_connections_with_permission("read")
        assert len(read_users) == 2  # Both have read permission


if __name__ == "__main__":
    pytest.main([__file__, "-v"])