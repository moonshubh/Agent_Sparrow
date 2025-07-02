"""
Basic tests for FeedMe v2.0 WebSocket Real-time Updates
Simplified tests to verify core functionality
"""

import pytest
import pytest_asyncio
from unittest.mock import Mock, AsyncMock
from datetime import datetime

from app.feedme.websocket.realtime_manager import (
    FeedMeRealtimeManager,
    WebSocketRoom,
    ConnectionInfo
)
from app.feedme.websocket.schemas import (
    ProcessingUpdate,
    ApprovalUpdate,
    MessageType,
    ProcessingStatus,
    ProcessingStage
)


class TestWebSocketRoomBasic:
    """Basic tests for WebSocket room management"""

    def test_room_creation(self):
        """Test room creation"""
        room = WebSocketRoom(room_id="test_room")
        
        assert room.room_id == "test_room"
        assert len(room.connections) == 0
        assert room.created_at is not None
        assert room.is_empty() == True

    def test_add_remove_connection(self):
        """Test adding and removing connections"""
        room = WebSocketRoom(room_id="test_room")
        websocket = Mock()
        connection_info = ConnectionInfo(
            user_id="user@example.com",
            room_id="test_room",
            permissions=["read"],
            connected_at=datetime.now()
        )
        
        # Add connection
        room.add_connection(websocket, connection_info)
        assert len(room.connections) == 1
        assert websocket in room.connections
        assert not room.is_empty()
        
        # Remove connection
        removed = room.remove_connection(websocket)
        assert removed == True
        assert len(room.connections) == 0
        assert websocket not in room.connections
        assert room.is_empty()

    def test_permission_filtering(self):
        """Test filtering connections by permission"""
        room = WebSocketRoom(room_id="test_room")
        
        # Add connections with different permissions
        websocket1 = Mock()
        websocket2 = Mock()
        
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
        admin_connections = room.get_connections_with_permission("admin")
        assert len(admin_connections) == 1
        assert websocket1 in admin_connections
        
        read_connections = room.get_connections_with_permission("read")
        assert len(read_connections) == 2


class TestRealtimeManagerBasic:
    """Basic tests for real-time manager"""

    @pytest.fixture
    def manager(self):
        """Create manager for testing"""
        return FeedMeRealtimeManager()

    @pytest.fixture
    def mock_websocket(self):
        """Create mock websocket"""
        websocket = Mock()
        websocket.accept = AsyncMock()
        websocket.send_json = AsyncMock()
        return websocket

    @pytest.mark.asyncio
    async def test_connect_websocket(self, manager, mock_websocket):
        """Test WebSocket connection"""
        connection_info = await manager.connect(
            websocket=mock_websocket,
            user_id="user@example.com",
            room_id="test_room",
            permissions=["read"]
        )
        
        # Verify connection was established
        mock_websocket.accept.assert_called_once()
        assert connection_info.user_id == "user@example.com"
        assert connection_info.room_id == "test_room"
        assert "read" in connection_info.permissions
        
        # Verify room was created
        assert "test_room" in manager.rooms
        room = manager.rooms["test_room"]
        assert mock_websocket in room.connections

    @pytest.mark.asyncio
    async def test_disconnect_websocket(self, manager, mock_websocket):
        """Test WebSocket disconnection"""
        # Connect first
        await manager.connect(
            websocket=mock_websocket,
            user_id="user@example.com",
            room_id="test_room"
        )
        
        # Verify connection exists
        assert "test_room" in manager.rooms
        assert mock_websocket in manager.rooms["test_room"].connections
        
        # Disconnect
        await manager.disconnect(mock_websocket)
        
        # Verify room was cleaned up (empty rooms are removed)
        assert "test_room" not in manager.rooms

    @pytest.mark.asyncio
    async def test_broadcast_to_room(self, manager):
        """Test broadcasting message to room"""
        # Create mock websockets
        websocket1 = Mock()
        websocket1.accept = AsyncMock()
        websocket1.send_json = AsyncMock()
        
        websocket2 = Mock()
        websocket2.accept = AsyncMock()
        websocket2.send_json = AsyncMock()
        
        # Connect both websockets
        await manager.connect(websocket1, "user1@example.com", "test_room")
        await manager.connect(websocket2, "user2@example.com", "test_room")
        
        # Broadcast message
        test_message = {"type": "test", "data": "hello"}
        failed_connections = await manager.broadcast_to_room("test_room", test_message)
        
        # Verify both websockets received the message (check last call)
        assert websocket1.send_json.call_count >= 1
        assert websocket2.send_json.call_count >= 1
        
        # Check that the test message was sent (last call should be our broadcast)
        last_call_1 = websocket1.send_json.call_args_list[-1][0][0]
        last_call_2 = websocket2.send_json.call_args_list[-1][0][0]
        assert last_call_1 == test_message
        assert last_call_2 == test_message
        assert len(failed_connections) == 0

    @pytest.mark.asyncio
    async def test_get_room_users(self, manager, mock_websocket):
        """Test getting room users"""
        # Connect user
        await manager.connect(
            websocket=mock_websocket,
            user_id="user@example.com",
            room_id="test_room",
            permissions=["read", "write"]
        )
        
        # Get users
        users = manager.get_room_users("test_room")
        
        assert len(users) == 1
        user = users[0]
        assert user.user_id == "user@example.com"
        assert user.room_id == "test_room"
        assert "read" in user.permissions
        assert "write" in user.permissions

    @pytest.mark.asyncio
    async def test_validation_errors(self, manager, mock_websocket):
        """Test validation errors"""
        # Test empty user_id
        with pytest.raises(ValueError, match="User ID cannot be empty"):
            await manager.connect(mock_websocket, "", "test_room")
        
        # Test empty room_id
        with pytest.raises(ValueError, match="Room ID cannot be empty"):
            await manager.connect(mock_websocket, "user@example.com", "")

    def test_metrics_collection(self, manager):
        """Test metrics collection"""
        metrics = manager.get_metrics()
        
        assert metrics.total_connections == 0
        assert metrics.active_rooms == 0
        assert metrics.messages_sent_per_minute >= 0
        assert metrics.connection_success_rate >= 0
        assert metrics.disconnection_rate >= 0


class TestWebSocketSchemas:
    """Basic tests for WebSocket schemas"""

    def test_processing_update_creation(self):
        """Test processing update creation"""
        update = ProcessingUpdate(
            conversation_id=123,
            status=ProcessingStatus.PROCESSING,
            stage=ProcessingStage.AI_EXTRACTION,
            progress=50,
            message="Extracting Q&A pairs..."
        )
        
        assert update.conversation_id == 123
        assert update.status == ProcessingStatus.PROCESSING
        assert update.stage == ProcessingStage.AI_EXTRACTION
        assert update.progress == 50
        assert update.message == "Extracting Q&A pairs..."
        assert update.timestamp is not None

    def test_approval_update_creation(self):
        """Test approval update creation"""
        update = ApprovalUpdate(
            temp_example_id=456,
            previous_status="pending",
            new_status="approved",
            reviewer_id="reviewer@example.com"
        )
        
        assert update.temp_example_id == 456
        assert update.previous_status == "pending"
        assert update.new_status == "approved"
        assert update.reviewer_id == "reviewer@example.com"
        assert update.timestamp is not None

    def test_connection_info_creation(self):
        """Test connection info creation"""
        info = ConnectionInfo(
            user_id="user@example.com",
            room_id="test_room",
            permissions=["read", "write"],
            connected_at=datetime.now()
        )
        
        assert info.user_id == "user@example.com"
        assert info.room_id == "test_room"
        assert "read" in info.permissions
        assert "write" in info.permissions
        assert info.connected_at is not None

    def test_processing_update_validation(self):
        """Test validation in processing update"""
        # Test invalid progress (> 100)
        with pytest.raises(ValueError):
            ProcessingUpdate(
                conversation_id=123,
                status=ProcessingStatus.PROCESSING,
                stage=ProcessingStage.AI_EXTRACTION,
                progress=150,  # Invalid: > 100
                message="Test"
            )
        
        # Test invalid progress (< 0)
        with pytest.raises(ValueError):
            ProcessingUpdate(
                conversation_id=123,
                status=ProcessingStatus.PROCESSING,
                stage=ProcessingStage.AI_EXTRACTION,
                progress=-10,  # Invalid: < 0
                message="Test"
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])