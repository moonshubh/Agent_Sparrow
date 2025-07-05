"""
FeedMe v2.0 Real-time WebSocket Manager

Manages WebSocket connections, room-based broadcasting, and real-time updates
for FeedMe processing and approval workflows.
"""

import asyncio
import logging
import json
from datetime import datetime, timedelta
from typing import Dict, List, Set, Optional, Any
from collections import defaultdict
import weakref

from fastapi import WebSocket, WebSocketDisconnect
import redis.asyncio as redis

from .schemas import (
    ConnectionInfo,
    ProcessingUpdate,
    ApprovalUpdate,
    MessageType,
    BroadcastMessage,
    QueuedMessage,
    MessageQueue,
    ConnectionEvent,
    HeartbeatMessage,
    ErrorMessage,
    WebSocketMetrics
)

logger = logging.getLogger(__name__)


class WebSocketRoom:
    """
    Manages a room of WebSocket connections with permission-based access.
    """
    
    def __init__(self, room_id: str):
        self.room_id = room_id
        self.connections: Dict[WebSocket, ConnectionInfo] = {}
        self.created_at = datetime.now()
        self.last_activity = datetime.now()
        self.message_count = 0
        
        # Room metadata
        self.room_type: Optional[str] = None
        self.metadata: Dict[str, Any] = {}

    def add_connection(self, websocket: WebSocket, connection_info: ConnectionInfo):
        """Add a WebSocket connection to the room"""
        self.connections[websocket] = connection_info
        self.last_activity = datetime.now()
        
        logger.info(
            f"Added connection to room {self.room_id}: "
            f"user={connection_info.user_id}, total_connections={len(self.connections)}"
        )

    def remove_connection(self, websocket: WebSocket) -> bool:
        """Remove a WebSocket connection from the room"""
        if websocket in self.connections:
            connection_info = self.connections[websocket]
            del self.connections[websocket]
            
            logger.info(
                f"Removed connection from room {self.room_id}: "
                f"user={connection_info.user_id}, remaining_connections={len(self.connections)}"
            )
            return True
        return False

    def get_connections_with_permission(self, permission: str) -> List[WebSocket]:
        """Get connections that have a specific permission"""
        filtered_connections = []
        for websocket, connection_info in self.connections.items():
            if permission in connection_info.permissions:
                filtered_connections.append(websocket)
        return filtered_connections

    def get_user_connections(self, user_id: str) -> List[WebSocket]:
        """Get all connections for a specific user"""
        user_connections = []
        for websocket, connection_info in self.connections.items():
            if connection_info.user_id == user_id:
                user_connections.append(websocket)
        return user_connections

    def is_empty(self) -> bool:
        """Check if room has no connections"""
        return len(self.connections) == 0

    def get_connection_info(self, websocket: WebSocket) -> Optional[ConnectionInfo]:
        """Get connection info for a specific websocket"""
        return self.connections.get(websocket)


class FeedMeRealtimeManager:
    """
    Main WebSocket manager for FeedMe real-time communications.
    
    Handles connection management, room-based broadcasting, and message queuing.
    Features Redis-backed persistence with graceful fallback to in-memory storage.
    """
    
    def __init__(self, redis_url: Optional[str] = None):
        # Room management
        self.rooms: Dict[str, WebSocketRoom] = {}
        self.connection_to_room: Dict[WebSocket, str] = {}
        
        # Message queuing for offline users
        self.message_queues: Dict[str, MessageQueue] = {}
        
        # Metrics and monitoring
        self.connection_events: List[ConnectionEvent] = []
        self.metrics_window = timedelta(minutes=5)
        
        # Redis connection (optional)
        self.redis_client: Optional[redis.Redis] = None
        self.redis_enabled = False
        if redis_url:
            try:
                self.redis_client = redis.from_url(redis_url)
                self.redis_enabled = True
                logger.info("Redis enabled for WebSocket persistence")
            except Exception as e:
                logger.warning(f"Failed to connect to Redis: {e}. Using in-memory storage only.")
        
        # Background task management
        self.heartbeat_interval = 30  # seconds
        self.cleanup_interval = 300  # 5 minutes
        self.heartbeat_task: Optional[asyncio.Task] = None
        self.cleanup_task: Optional[asyncio.Task] = None
        self.heartbeat_task: Optional[asyncio.Task] = None
        
        # Configuration
        self.max_connections_per_room = 100
        self.max_message_queue_size = 100
        self.cleanup_interval = 300  # 5 minutes

    async def connect(
        self,
        websocket: WebSocket,
        user_id: str,
        room_id: str,
        permissions: List[str] = None
    ) -> ConnectionInfo:
        """
        Accept a WebSocket connection and add to specified room.
        
        Args:
            websocket: WebSocket connection
            user_id: User identifier
            room_id: Room to join
            permissions: User permissions for filtering
            
        Returns:
            Connection information
            
        Raises:
            ValueError: If validation fails
        """
        # Validate connection parameters
        await self._validate_connection(user_id, room_id, permissions or [])
        
        try:
            # Accept the WebSocket connection
            await websocket.accept()
            
            # Create connection info
            connection_info = ConnectionInfo(
                user_id=user_id,
                room_id=room_id,
                permissions=permissions or [],
                connected_at=datetime.now()
            )
            
            # Create room if it doesn't exist
            if room_id not in self.rooms:
                self.rooms[room_id] = WebSocketRoom(room_id)
            
            room = self.rooms[room_id]
            
            # Check room capacity
            if len(room.connections) >= self.max_connections_per_room:
                await websocket.close(code=1008, reason="Room capacity exceeded")
                raise ValueError(f"Room {room_id} has reached maximum capacity")
            
            # Add connection to room
            room.add_connection(websocket, connection_info)
            self.connection_to_room[websocket] = room_id
            
            # Send initial connection status
            await self._send_connection_status(websocket, connection_info, "connected")
            
            # Deliver any queued messages
            await self._deliver_queued_messages(user_id, websocket)
            
            # Log connection event
            self._log_connection_event("connect", user_id, room_id)
            
            # Start background tasks if this is the first connection
            if not self.heartbeat_task:
                await self.start_background_tasks()
            
            logger.info(f"WebSocket connected: user={user_id}, room={room_id}")
            return connection_info
            
        except Exception as e:
            logger.error(f"Failed to connect WebSocket: {e}")
            try:
                await websocket.close()
            except:
                pass
            raise

    async def disconnect(self, websocket: WebSocket):
        """
        Handle WebSocket disconnection and cleanup.
        
        Args:
            websocket: WebSocket connection to disconnect
        """
        try:
            room_id = self.connection_to_room.get(websocket)
            if not room_id:
                return
            
            room = self.rooms.get(room_id)
            if not room:
                return
            
            # Get connection info before removal
            connection_info = room.get_connection_info(websocket)
            
            # Remove connection from room
            room.remove_connection(websocket)
            del self.connection_to_room[websocket]
            
            # Clean up empty room
            if room.is_empty():
                del self.rooms[room_id]
                logger.info(f"Cleaned up empty room: {room_id}")
            
            # Log disconnection event
            if connection_info:
                self._log_connection_event("disconnect", connection_info.user_id, room_id)
                
            # Stop heartbeat if no connections remain
            if not self.rooms and self.heartbeat_task:
                self.heartbeat_task.cancel()
                self.heartbeat_task = None
            
            logger.info(f"WebSocket disconnected: room={room_id}")
            
        except Exception as e:
            logger.error(f"Error during WebSocket disconnection: {e}")

    async def broadcast_to_room(
        self,
        room_id: str,
        message: Dict[str, Any],
        required_permission: Optional[str] = None,
        exclude_users: List[str] = None
    ) -> List[WebSocket]:
        """
        Broadcast message to all connections in a room.
        
        Args:
            room_id: Room to broadcast to
            message: Message to send
            required_permission: Optional permission requirement
            exclude_users: Users to exclude from broadcast
            
        Returns:
            List of failed connections
        """
        room = self.rooms.get(room_id)
        if not room:
            logger.warning(f"Attempted to broadcast to non-existent room: {room_id}")
            return []
        
        exclude_users = exclude_users or []
        failed_connections = []
        
        # Get target connections based on permissions and exclusions
        target_connections = []
        for websocket, connection_info in room.connections.items():
            # Skip excluded users
            if connection_info.user_id in exclude_users:
                continue
            
            # Check permission requirement
            if required_permission and required_permission not in connection_info.permissions:
                continue
            
            target_connections.append(websocket)
        
        # Send message to all target connections
        send_tasks = []
        for websocket in target_connections:
            task = asyncio.create_task(self._send_message_safe(websocket, message))
            send_tasks.append((websocket, task))
        
        # Wait for all sends to complete
        for websocket, task in send_tasks:
            try:
                await task
            except Exception as e:
                logger.error(f"Failed to send message to connection: {e}")
                failed_connections.append(websocket)
        
        # Update room statistics
        room.message_count += len(target_connections) - len(failed_connections)
        room.last_activity = datetime.now()
        
        logger.debug(
            f"Broadcast to room {room_id}: "
            f"sent={len(target_connections) - len(failed_connections)}, "
            f"failed={len(failed_connections)}"
        )
        
        return failed_connections

    async def broadcast_processing_update(self, update: ProcessingUpdate):
        """
        Broadcast processing status update to relevant rooms.
        
        Args:
            update: Processing update to broadcast
        """
        # Create message
        message = {
            "type": MessageType.PROCESSING_UPDATE,
            **update.model_dump()
        }
        
        # Broadcast to conversation-specific room
        conversation_room = f"conversation_{update.conversation_id}"
        await self.broadcast_to_room(conversation_room, message)
        
        # Also broadcast to global processing room
        await self.broadcast_to_room("processing_updates", message, required_permission="processing:read")

    async def broadcast_approval_update(self, update: ApprovalUpdate):
        """
        Broadcast approval workflow update to relevant rooms.
        
        Args:
            update: Approval update to broadcast
        """
        # Create message
        message = {
            "type": MessageType.APPROVAL_UPDATE,
            **update.model_dump()
        }
        
        # Broadcast to approval workflow room
        await self.broadcast_to_room("approval_updates", message, required_permission="approval:read")
        
        # Also broadcast to temp example specific room if it exists
        temp_example_room = f"temp_example_{update.temp_example_id}"
        await self.broadcast_to_room(temp_example_room, message)

    async def send_heartbeat(self, room_id: Optional[str] = None):
        """
        Send heartbeat/ping to connections.
        
        Args:
            room_id: Specific room to ping, or None for all rooms
        """
        heartbeat_message = HeartbeatMessage().model_dump(mode='json')
        
        if room_id:
            await self.broadcast_to_room(room_id, heartbeat_message)
        else:
            # Send to all rooms
            for room_id in list(self.rooms.keys()):
                await self.broadcast_to_room(room_id, heartbeat_message)

    async def queue_message_for_user(self, user_id: str, message: Dict[str, Any], ttl_seconds: int = 3600):
        """
        Queue message for offline user with Redis persistence fallback.
        
        Args:
            user_id: User to queue message for
            message: Message to queue
            ttl_seconds: Time to live for queued message
        """
        if user_id not in self.message_queues:
            self.message_queues[user_id] = MessageQueue(user_id=user_id)
        
        queued_message = QueuedMessage(
            user_id=user_id,
            message=message,
            ttl_seconds=ttl_seconds
        )
        
        # Try to persist to Redis first
        if self.redis_enabled and self.redis_client:
            try:
                redis_key = f"feedme:websocket:queue:{user_id}"
                message_data = {
                    'message': message,
                    'created_at': queued_message.created_at.isoformat(),
                    'ttl_seconds': ttl_seconds
                }
                await self.redis_client.lpush(redis_key, json.dumps(message_data))
                await self.redis_client.expire(redis_key, ttl_seconds)
                logger.debug(f"Queued message for user {user_id} in Redis")
            except Exception as e:
                logger.error(f"Failed to queue message in Redis: {e}. Using in-memory queue.")
                # Fall back to in-memory queue
                self.message_queues[user_id].add_message(queued_message)
        else:
            # Use in-memory queue
            self.message_queues[user_id].add_message(queued_message)
            logger.debug(f"Queued message for user {user_id} in memory")

    def get_room_users(self, room_id: str) -> List[ConnectionInfo]:
        """
        Get list of users in a room.
        
        Args:
            room_id: Room to query
            
        Returns:
            List of connection information
        """
        room = self.rooms.get(room_id)
        if not room:
            return []
        
        return list(room.connections.values())

    def get_metrics(self) -> WebSocketMetrics:
        """
        Get current WebSocket system metrics.
        
        Returns:
            Current metrics
        """
        now = datetime.now()
        window_start = now - self.metrics_window
        
        # Count connections and rooms
        total_connections = sum(len(room.connections) for room in self.rooms.values())
        active_rooms = len(self.rooms)
        
        # Calculate message rate from recent events
        recent_events = [
            event for event in self.connection_events 
            if event.timestamp >= window_start and event.event_type == "message"
        ]
        messages_per_minute = len(recent_events) / self.metrics_window.total_seconds() * 60
        
        # Calculate success rates
        connect_events = [
            event for event in self.connection_events 
            if event.timestamp >= window_start and event.event_type == "connect"
        ]
        disconnect_events = [
            event for event in self.connection_events 
            if event.timestamp >= window_start and event.event_type == "disconnect"
        ]
        
        connection_success_rate = 1.0  # Would need error tracking for real calculation
        disconnection_rate = len(disconnect_events) / max(1, len(connect_events))
        
        return WebSocketMetrics(
            total_connections=total_connections,
            active_rooms=active_rooms,
            messages_sent_per_minute=messages_per_minute,
            connection_success_rate=connection_success_rate,
            disconnection_rate=disconnection_rate,
            period_start=window_start,
            period_end=now
        )

    # ===========================
    # Private Helper Methods
    # ===========================

    async def _validate_connection(self, user_id: str, room_id: str, permissions: List[str]):
        """Validate connection parameters"""
        if not user_id or not user_id.strip():
            raise ValueError("User ID cannot be empty")
        
        if not room_id or not room_id.strip():
            raise ValueError("Room ID cannot be empty")
        
        # Additional validation could be added here
        # e.g., check user exists, has permissions, etc.

    async def _send_connection_status(self, websocket: WebSocket, connection_info: ConnectionInfo, status: str):
        """Send connection status message"""
        room = self.rooms.get(connection_info.room_id)
        user_count = len(room.connections) if room else 0
        
        status_message = {
            "type": MessageType.CONNECTION_STATUS,
            "user_id": connection_info.user_id,
            "room_id": connection_info.room_id,
            "status": status,
            "permissions": connection_info.permissions,
            "user_count": user_count,
            "timestamp": datetime.now().isoformat()
        }
        
        await self._send_message_safe(websocket, status_message)

    async def _deliver_queued_messages(self, user_id: str, websocket: WebSocket):
        """Deliver queued messages to reconnected user with selective removal"""
        delivered_messages = []
        
        # Try to get messages from Redis first
        if self.redis_enabled and self.redis_client:
            try:
                redis_key = f"feedme:websocket:queue:{user_id}"
                redis_messages = await self.redis_client.lrange(redis_key, 0, -1)
                
                for redis_msg in redis_messages:
                    try:
                        message_data = json.loads(redis_msg)
                        await self._send_message_safe(websocket, message_data['message'])
                        delivered_messages.append(redis_msg)
                    except Exception as e:
                        logger.error(f"Failed to deliver Redis queued message: {e}")
                
                # Remove successfully delivered messages from Redis
                if delivered_messages:
                    for msg in delivered_messages:
                        await self.redis_client.lrem(redis_key, 1, msg)
                    logger.debug(f"Delivered and removed {len(delivered_messages)} messages from Redis for user {user_id}")
                        
            except Exception as e:
                logger.error(f"Failed to access Redis message queue: {e}")
        
        # Handle in-memory queue
        if user_id in self.message_queues:
            message_queue = self.message_queues[user_id]
            pending_messages = message_queue.get_pending_messages()
            successfully_delivered = []
            
            for queued_message in pending_messages:
                try:
                    await self._send_message_safe(websocket, queued_message.message)
                    successfully_delivered.append(queued_message)
                    queued_message.attempts += 1
                except Exception as e:
                    logger.error(f"Failed to deliver queued message: {e}")
            
            # Remove only successfully delivered messages
            for delivered_msg in successfully_delivered:
                if delivered_msg in message_queue.messages:
                    message_queue.messages.remove(delivered_msg)
            
            if successfully_delivered:
                logger.debug(f"Delivered and removed {len(successfully_delivered)} messages from memory for user {user_id}")

    async def _send_message_safe(self, websocket: WebSocket, message: Dict[str, Any]):
        """Send message with error handling"""
        try:
            await websocket.send_json(message)
        except WebSocketDisconnect:
            # Connection was closed, handle cleanup
            await self.disconnect(websocket)
            raise
        except Exception as e:
            # Other send errors
            logger.error(f"Failed to send WebSocket message: {e}")
            raise

    def _log_connection_event(self, event_type: str, user_id: str, room_id: str, details: Dict[str, Any] = None):
        """Log connection event for metrics"""
        event = ConnectionEvent(
            event_type=event_type,
            user_id=user_id,
            room_id=room_id,
            details=details or {}
        )
        
        self.connection_events.append(event)
        
        # Keep only recent events to prevent memory growth
        cutoff = datetime.now() - timedelta(hours=1)
        self.connection_events = [
            e for e in self.connection_events if e.timestamp >= cutoff
        ]

    async def _heartbeat_loop(self):
        """Background task for sending heartbeats"""
        try:
            while True:
                await asyncio.sleep(self.heartbeat_interval)
                
                if not self.rooms:
                    # No active connections, stop heartbeat
                    break
                
                try:
                    await self.send_heartbeat()
                except Exception as e:
                    logger.error(f"Error in heartbeat loop: {e}")
        
        except asyncio.CancelledError:
            logger.info("Heartbeat loop cancelled")
        
        finally:
            self.heartbeat_task = None
    
    async def _cleanup_loop(self):
        """Background cleanup loop for stale connections"""
        try:
            while True:
                await asyncio.sleep(self.cleanup_interval)
                try:
                    await self.cleanup_stale_connections()
                    logger.debug("Completed cleanup of stale connections")
                except Exception as e:
                    logger.error(f"Error in cleanup loop: {e}")
        
        except asyncio.CancelledError:
            logger.info("Cleanup loop cancelled")
        
        finally:
            self.cleanup_task = None
    
    async def start_background_tasks(self):
        """Start all background tasks"""
        await self.start_heartbeat()
        await self.start_cleanup_task()
    
    async def start_heartbeat(self):
        """Start periodic heartbeat to all connections"""
        if self.heartbeat_task is not None:
            return
        
        self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        logger.info("Started WebSocket heartbeat")
    
    async def start_cleanup_task(self):
        """Start periodic cleanup of stale connections"""
        if self.cleanup_task is not None:
            return
        
        self.cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("Started WebSocket cleanup task")
    
    async def stop_background_tasks(self):
        """Stop all background tasks"""
        await self.stop_heartbeat()
        await self.stop_cleanup_task()
    
    async def stop_heartbeat(self):
        """Stop heartbeat task"""
        if self.heartbeat_task:
            self.heartbeat_task.cancel()
            try:
                await self.heartbeat_task
            except asyncio.CancelledError:
                pass
            self.heartbeat_task = None
            logger.info("Stopped WebSocket heartbeat")
    
    async def stop_cleanup_task(self):
        """Stop cleanup task"""
        if self.cleanup_task:
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass
            self.cleanup_task = None
            logger.info("Stopped WebSocket cleanup task")

    async def cleanup_stale_connections(self):
        """Clean up stale connections and empty rooms"""
        stale_cutoff = datetime.now() - timedelta(minutes=30)
        
        for room_id, room in list(self.rooms.items()):
            stale_connections = []
            
            for websocket, connection_info in room.connections.items():
                # Check if connection is stale (no recent activity)
                if connection_info.last_activity and connection_info.last_activity < stale_cutoff:
                    stale_connections.append(websocket)
            
            # Remove stale connections
            for websocket in stale_connections:
                await self.disconnect(websocket)
            
            # Remove empty rooms
            if room.is_empty():
                del self.rooms[room_id]


# Global instance
realtime_manager = FeedMeRealtimeManager()