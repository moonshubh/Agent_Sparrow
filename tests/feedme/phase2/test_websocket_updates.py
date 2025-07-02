"""
TDD Tests for FeedMe v2.0 WebSocket Real-time Updates
Tests for real-time processing status updates and client notification system
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime
import json
from typing import List, Dict, Any

from fastapi import WebSocket, WebSocketDisconnect
from app.feedme.websocket.realtime_manager import FeedMeRealtimeManager
from app.feedme.websocket.connection_handler import ConnectionHandler


class TestFeedMeRealtimeManager:
    """Test suite for real-time WebSocket manager"""

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
        websocket.close = AsyncMock()
        return websocket

    @pytest.fixture
    def sample_processing_update(self):
        """Sample processing update message"""
        return {
            'conversation_id': 123,
            'status': 'processing',
            'stage': 'ai_extraction',
            'progress': 65,
            'message': 'Extracting Q&A pairs...',
            'estimated_completion': 30,  # seconds
            'timestamp': datetime.now().isoformat()
        }

    @pytest.mark.asyncio
    async def test_websocket_connection_establishment(self, realtime_manager, mock_websocket):
        """Test WebSocket connection establishment"""
        conversation_id = 123
        user_id = "user123"
        
        await realtime_manager.connect(mock_websocket, conversation_id, user_id)
        
        # Verify WebSocket was accepted
        mock_websocket.accept.assert_called_once()
        
        # Verify connection was registered
        assert conversation_id in realtime_manager.active_connections
        assert mock_websocket in realtime_manager.active_connections[conversation_id]

    @pytest.mark.asyncio
    async def test_multiple_clients_same_conversation(self, realtime_manager):
        """Test multiple clients connecting to same conversation"""
        conversation_id = 123
        websocket1 = Mock(spec=WebSocket)
        websocket1.accept = AsyncMock()
        websocket2 = Mock(spec=WebSocket)
        websocket2.accept = AsyncMock()
        
        # Connect two clients to same conversation
        await realtime_manager.connect(websocket1, conversation_id, "user1")
        await realtime_manager.connect(websocket2, conversation_id, "user2")
        
        # Verify both connections are tracked
        assert len(realtime_manager.active_connections[conversation_id]) == 2
        assert websocket1 in realtime_manager.active_connections[conversation_id]
        assert websocket2 in realtime_manager.active_connections[conversation_id]

    @pytest.mark.asyncio
    async def test_broadcast_processing_update(self, realtime_manager, mock_websocket, 
                                             sample_processing_update):
        """Test broadcasting processing updates to connected clients"""
        conversation_id = 123
        
        # Setup connection
        await realtime_manager.connect(mock_websocket, conversation_id, "user123")
        
        # Broadcast update
        await realtime_manager.broadcast_processing_update(
            conversation_id, sample_processing_update
        )
        
        # Verify message was sent
        mock_websocket.send_json.assert_called_once()
        
        # Verify message content
        call_args = mock_websocket.send_json.call_args[0][0]
        assert call_args['type'] == 'processing_update'
        assert call_args['conversation_id'] == conversation_id
        assert call_args['data'] == sample_processing_update

    @pytest.mark.asyncio
    async def test_broadcast_to_multiple_clients(self, realtime_manager, sample_processing_update):
        """Test broadcasting to multiple connected clients"""
        conversation_id = 123
        websocket1 = Mock(spec=WebSocket)
        websocket1.accept = AsyncMock()
        websocket1.send_json = AsyncMock()
        websocket2 = Mock(spec=WebSocket)
        websocket2.accept = AsyncMock()
        websocket2.send_json = AsyncMock()
        
        # Connect multiple clients
        await realtime_manager.connect(websocket1, conversation_id, "user1")
        await realtime_manager.connect(websocket2, conversation_id, "user2")
        
        # Broadcast update
        await realtime_manager.broadcast_processing_update(
            conversation_id, sample_processing_update
        )
        
        # Verify both clients received the message
        websocket1.send_json.assert_called_once()
        websocket2.send_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_websocket_disconnection_handling(self, realtime_manager):
        """Test handling of WebSocket disconnections"""
        conversation_id = 123
        websocket = Mock(spec=WebSocket)
        websocket.accept = AsyncMock()
        websocket.send_json = AsyncMock(side_effect=WebSocketDisconnect())
        
        # Connect client
        await realtime_manager.connect(websocket, conversation_id, "user123")
        
        # Attempt to broadcast (should handle disconnection)
        await realtime_manager.broadcast_processing_update(
            conversation_id, {'status': 'test'}
        )
        
        # Verify disconnected client was removed
        assert len(realtime_manager.active_connections[conversation_id]) == 0

    @pytest.mark.asyncio
    async def test_conversation_lock_management(self, realtime_manager, mock_websocket):
        """Test conversation lock management"""
        conversation_id = 123
        user_id = "user123"
        
        # Connect and acquire lock
        await realtime_manager.connect(mock_websocket, conversation_id, user_id)
        
        # Request lock
        lock_acquired = await realtime_manager.acquire_conversation_lock(
            conversation_id, user_id
        )
        
        assert lock_acquired is True
        assert realtime_manager.conversation_locks[conversation_id] == user_id

    @pytest.mark.asyncio
    async def test_conversation_lock_conflict(self, realtime_manager):
        """Test conversation lock conflict handling"""
        conversation_id = 123
        
        # First user acquires lock
        await realtime_manager.acquire_conversation_lock(conversation_id, "user1")
        
        # Second user tries to acquire same lock
        lock_acquired = await realtime_manager.acquire_conversation_lock(
            conversation_id, "user2"
        )
        
        assert lock_acquired is False
        assert realtime_manager.conversation_locks[conversation_id] == "user1"

    @pytest.mark.asyncio
    async def test_release_conversation_lock(self, realtime_manager):
        """Test releasing conversation lock"""
        conversation_id = 123
        user_id = "user123"
        
        # Acquire and then release lock
        await realtime_manager.acquire_conversation_lock(conversation_id, user_id)
        await realtime_manager.release_conversation_lock(conversation_id, user_id)
        
        # Verify lock was released
        assert conversation_id not in realtime_manager.conversation_locks

    @pytest.mark.asyncio
    async def test_unauthorized_lock_release(self, realtime_manager):
        """Test unauthorized lock release attempt"""
        conversation_id = 123
        
        # User1 acquires lock
        await realtime_manager.acquire_conversation_lock(conversation_id, "user1")
        
        # User2 tries to release lock
        with pytest.raises(ValueError, match="not authorized"):
            await realtime_manager.release_conversation_lock(conversation_id, "user2")

    @pytest.mark.asyncio
    async def test_send_status_update(self, realtime_manager, mock_websocket):
        """Test sending current status to newly connected client"""
        conversation_id = 123
        
        # Mock current status
        with patch.object(realtime_manager, 'get_current_status') as mock_status:
            mock_status.return_value = {
                'conversation_id': conversation_id,
                'status': 'completed',
                'progress': 100
            }
            
            await realtime_manager.connect(mock_websocket, conversation_id, "user123")
            
            # Verify status was sent
            mock_websocket.send_json.assert_called()
            call_args = mock_websocket.send_json.call_args[0][0]
            assert call_args['type'] == 'status_update'

    @pytest.mark.asyncio
    async def test_error_message_broadcasting(self, realtime_manager, mock_websocket):
        """Test broadcasting error messages"""
        conversation_id = 123
        await realtime_manager.connect(mock_websocket, conversation_id, "user123")
        
        error_update = {
            'conversation_id': conversation_id,
            'status': 'failed',
            'error': 'AI extraction failed',
            'error_code': 'EXTRACTION_ERROR'
        }
        
        await realtime_manager.broadcast_error(conversation_id, error_update)
        
        # Verify error message was sent
        mock_websocket.send_json.assert_called()
        call_args = mock_websocket.send_json.call_args[0][0]
        assert call_args['type'] == 'error'
        assert call_args['data']['error'] == 'AI extraction failed'

    @pytest.mark.asyncio
    async def test_completion_notification(self, realtime_manager, mock_websocket):
        """Test completion notification"""
        conversation_id = 123
        await realtime_manager.connect(mock_websocket, conversation_id, "user123")
        
        completion_data = {
            'conversation_id': conversation_id,
            'status': 'completed',
            'total_examples_extracted': 15,
            'processing_time_seconds': 45
        }
        
        await realtime_manager.broadcast_completion(conversation_id, completion_data)
        
        # Verify completion message was sent
        mock_websocket.send_json.assert_called()
        call_args = mock_websocket.send_json.call_args[0][0]
        assert call_args['type'] == 'completion'
        assert call_args['data']['total_examples_extracted'] == 15

    @pytest.mark.asyncio
    async def test_heartbeat_mechanism(self, realtime_manager, mock_websocket):
        """Test WebSocket heartbeat mechanism"""
        conversation_id = 123
        await realtime_manager.connect(mock_websocket, conversation_id, "user123")
        
        # Send heartbeat
        await realtime_manager.send_heartbeat(conversation_id)
        
        # Verify heartbeat was sent
        mock_websocket.send_json.assert_called()
        call_args = mock_websocket.send_json.call_args[0][0]
        assert call_args['type'] == 'heartbeat'

    @pytest.mark.asyncio
    async def test_connection_cleanup_on_error(self, realtime_manager):
        """Test connection cleanup when error occurs"""
        conversation_id = 123
        websocket = Mock(spec=WebSocket)
        websocket.accept = AsyncMock()
        websocket.send_json = AsyncMock(side_effect=Exception("Connection error"))
        
        await realtime_manager.connect(websocket, conversation_id, "user123")
        
        # Attempt operation that fails
        await realtime_manager.broadcast_processing_update(
            conversation_id, {'status': 'test'}
        )
        
        # Verify connection was cleaned up
        assert len(realtime_manager.active_connections[conversation_id]) == 0


class TestConnectionHandler:
    """Test suite for WebSocket connection handler"""

    @pytest.fixture
    def connection_handler(self):
        """Create connection handler for testing"""
        handler = ConnectionHandler()
        handler.realtime_manager = Mock()
        return handler

    @pytest.fixture
    def mock_websocket(self):
        """Mock WebSocket for connection handler tests"""
        websocket = Mock(spec=WebSocket)
        websocket.accept = AsyncMock()
        websocket.receive_text = AsyncMock()
        websocket.send_json = AsyncMock()
        return websocket

    @pytest.mark.asyncio
    async def test_websocket_endpoint_connection(self, connection_handler, mock_websocket):
        """Test WebSocket endpoint connection handling"""
        conversation_id = 123
        user_id = "user123"
        
        # Mock the connection establishment
        connection_handler.realtime_manager.connect = AsyncMock()
        
        await connection_handler.handle_websocket_connection(
            websocket=mock_websocket,
            conversation_id=conversation_id,
            user_id=user_id
        )
        
        # Verify connection was established
        connection_handler.realtime_manager.connect.assert_called_with(
            mock_websocket, conversation_id, user_id
        )

    @pytest.mark.asyncio
    async def test_message_handling(self, connection_handler, mock_websocket):
        """Test handling of incoming WebSocket messages"""
        # Mock incoming message
        mock_websocket.receive_text.return_value = json.dumps({
            'type': 'subscribe',
            'conversation_id': 123
        })
        
        connection_handler.realtime_manager.connect = AsyncMock()
        connection_handler.handle_message = AsyncMock()
        
        # Simulate connection lifecycle
        with patch.object(connection_handler, '_message_loop') as mock_loop:
            mock_loop.return_value = None  # Exit loop immediately
            
            await connection_handler.handle_websocket_connection(
                websocket=mock_websocket,
                conversation_id=123,
                user_id="user123"
            )

    @pytest.mark.asyncio
    async def test_connection_authentication(self, connection_handler, mock_websocket):
        """Test WebSocket connection authentication"""
        # Mock authentication check
        with patch.object(connection_handler, 'authenticate_user') as mock_auth:
            mock_auth.return_value = True
            
            result = await connection_handler.authenticate_websocket_connection(
                websocket=mock_websocket,
                token="valid_token"
            )
            
            assert result is True
            mock_auth.assert_called_with("valid_token")

    @pytest.mark.asyncio
    async def test_connection_authorization(self, connection_handler, mock_websocket):
        """Test WebSocket connection authorization"""
        # Mock authorization check
        with patch.object(connection_handler, 'authorize_conversation_access') as mock_authz:
            mock_authz.return_value = True
            
            result = await connection_handler.authorize_websocket_access(
                user_id="user123",
                conversation_id=123
            )
            
            assert result is True
            mock_authz.assert_called_with("user123", 123)

    @pytest.mark.asyncio
    async def test_rate_limiting(self, connection_handler):
        """Test WebSocket rate limiting"""
        user_id = "user123"
        
        # Mock rate limiter
        with patch.object(connection_handler, 'check_rate_limit') as mock_rate_limit:
            mock_rate_limit.return_value = True
            
            result = await connection_handler.check_connection_rate_limit(user_id)
            
            assert result is True
            mock_rate_limit.assert_called_with(user_id, 'websocket_connection')

    @pytest.mark.asyncio
    async def test_connection_metrics_tracking(self, connection_handler, mock_websocket):
        """Test connection metrics tracking"""
        with patch.object(connection_handler, 'track_connection_metrics') as mock_metrics:
            connection_handler.realtime_manager.connect = AsyncMock()
            
            await connection_handler.handle_websocket_connection(
                websocket=mock_websocket,
                conversation_id=123,
                user_id="user123"
            )
            
            # Verify metrics were tracked
            mock_metrics.assert_called()

    @pytest.mark.asyncio
    async def test_graceful_disconnection(self, connection_handler, mock_websocket):
        """Test graceful WebSocket disconnection"""
        conversation_id = 123
        user_id = "user123"
        
        # Mock disconnect handling
        connection_handler.realtime_manager.disconnect = AsyncMock()
        
        await connection_handler.handle_disconnection(
            websocket=mock_websocket,
            conversation_id=conversation_id,
            user_id=user_id
        )
        
        # Verify disconnection was handled
        connection_handler.realtime_manager.disconnect.assert_called_with(
            mock_websocket, conversation_id, user_id
        )


class TestWebSocketIntegration:
    """Integration tests for WebSocket system"""

    @pytest.mark.asyncio
    async def test_end_to_end_processing_updates(self):
        """Test end-to-end processing updates flow"""
        # Mock the complete flow from processing to client notification
        realtime_manager = FeedMeRealtimeManager()
        mock_websocket = Mock(spec=WebSocket)
        mock_websocket.accept = AsyncMock()
        mock_websocket.send_json = AsyncMock()
        
        conversation_id = 123
        
        # 1. Client connects
        await realtime_manager.connect(mock_websocket, conversation_id, "user123")
        
        # 2. Processing starts
        await realtime_manager.broadcast_processing_update(conversation_id, {
            'status': 'processing',
            'stage': 'extraction',
            'progress': 25
        })
        
        # 3. Processing continues
        await realtime_manager.broadcast_processing_update(conversation_id, {
            'status': 'processing',
            'stage': 'embedding',
            'progress': 75
        })
        
        # 4. Processing completes
        await realtime_manager.broadcast_completion(conversation_id, {
            'status': 'completed',
            'total_examples_extracted': 10
        })
        
        # Verify all updates were sent
        assert mock_websocket.send_json.call_count >= 3

    @pytest.mark.asyncio
    async def test_concurrent_connections_performance(self):
        """Test performance with multiple concurrent connections"""
        realtime_manager = FeedMeRealtimeManager()
        
        # Create multiple mock connections
        connections = []
        for i in range(50):  # 50 concurrent connections
            websocket = Mock(spec=WebSocket)
            websocket.accept = AsyncMock()
            websocket.send_json = AsyncMock()
            connections.append(websocket)
        
        conversation_id = 123
        
        # Connect all clients
        tasks = []
        for i, ws in enumerate(connections):
            task = realtime_manager.connect(ws, conversation_id, f"user{i}")
            tasks.append(task)
        
        await asyncio.gather(*tasks)
        
        # Broadcast to all
        start_time = asyncio.get_event_loop().time()
        await realtime_manager.broadcast_processing_update(conversation_id, {
            'status': 'test_broadcast'
        })
        end_time = asyncio.get_event_loop().time()
        
        # Verify broadcast completed in reasonable time (< 100ms)
        assert (end_time - start_time) < 0.1
        
        # Verify all connections received the message
        for ws in connections:
            ws.send_json.assert_called()

    @pytest.mark.asyncio
    async def test_websocket_error_recovery(self):
        """Test WebSocket error recovery mechanisms"""
        realtime_manager = FeedMeRealtimeManager()
        
        # Create connection that will fail
        failing_websocket = Mock(spec=WebSocket)
        failing_websocket.accept = AsyncMock()
        failing_websocket.send_json = AsyncMock(side_effect=WebSocketDisconnect())
        
        # Create working connection
        working_websocket = Mock(spec=WebSocket)
        working_websocket.accept = AsyncMock()
        working_websocket.send_json = AsyncMock()
        
        conversation_id = 123
        
        # Connect both
        await realtime_manager.connect(failing_websocket, conversation_id, "user1")
        await realtime_manager.connect(working_websocket, conversation_id, "user2")
        
        # Broadcast update (should handle failure gracefully)
        await realtime_manager.broadcast_processing_update(conversation_id, {
            'status': 'test'
        })
        
        # Verify working connection still works
        working_websocket.send_json.assert_called()
        
        # Verify failed connection was removed
        assert failing_websocket not in realtime_manager.active_connections[conversation_id]
        assert working_websocket in realtime_manager.active_connections[conversation_id]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])