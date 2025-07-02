"""
FeedMe v2.0 WebSocket API Endpoints

WebSocket endpoints for real-time communication in FeedMe processing and approval workflows.
"""

import logging
import asyncio
from typing import List, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query, HTTPException

from app.feedme.websocket.realtime_manager import realtime_manager
from app.feedme.websocket.schemas import (
    ConnectionRequest,
    ProcessingUpdate,
    ApprovalUpdate,
    WebSocketMetrics,
    RoomListResponse,
    RoomInfo
)

logger = logging.getLogger(__name__)

# Create router
router = APIRouter()


# ===========================
# Dependency Functions
# ===========================

async def get_current_user_from_token(token: Optional[str] = Query(None)) -> str:
    """
    Get current user from WebSocket token.
    
    This would typically validate a JWT token or session token.
    For now, return a placeholder user ID.
    """
    if not token:
        raise HTTPException(status_code=401, detail="Authentication token required")
    
    # In a real implementation, validate the token and extract user info
    # For now, return a mock user
    return "user@mailbird.com"


async def get_user_permissions(user_id: str) -> List[str]:
    """
    Get user permissions for WebSocket operations.
    
    This would typically query a user management system.
    """
    # In a real implementation, get permissions from database
    # For now, return default permissions
    return ["processing:read", "approval:read", "approval:write"]


# ===========================
# WebSocket Endpoints
# ===========================

@router.websocket("/feedme/processing/{conversation_id}")
async def websocket_processing_updates(
    websocket: WebSocket,
    conversation_id: int,
    token: Optional[str] = Query(None)
):
    """
    WebSocket endpoint for real-time processing updates for a specific conversation.
    
    Provides real-time updates on:
    - Processing status changes
    - Progress updates
    - Completion notifications
    - Error notifications
    """
    try:
        # Authenticate user (in real app, validate token)
        if not token:
            await websocket.close(code=1008, reason="Authentication required")
            return
        
        user_id = await get_current_user_from_token(token)
        permissions = await get_user_permissions(user_id)
        
        # Verify user has processing read permission
        if "processing:read" not in permissions:
            await websocket.close(code=1008, reason="Insufficient permissions")
            return
        
        # Connect to conversation-specific room
        room_id = f"conversation_{conversation_id}"
        
        connection_info = await realtime_manager.connect(
            websocket=websocket,
            user_id=user_id,
            room_id=room_id,
            permissions=permissions
        )
        
        logger.info(f"Processing WebSocket connected: user={user_id}, conversation={conversation_id}")
        
        try:
            # Keep connection alive and handle messages
            while True:
                # Wait for messages from client (e.g., ping, subscription changes)
                try:
                    message = await asyncio.wait_for(websocket.receive_json(), timeout=30.0)
                    
                    # Handle client messages
                    await _handle_client_message(websocket, message, user_id, room_id)
                    
                except asyncio.TimeoutError:
                    # Send heartbeat if no message received
                    await realtime_manager.send_heartbeat(room_id)
                
        except WebSocketDisconnect:
            logger.info(f"Processing WebSocket disconnected: user={user_id}, conversation={conversation_id}")
        
    except Exception as e:
        logger.error(f"Error in processing WebSocket: {e}")
        try:
            await websocket.close(code=1011, reason="Internal server error")
        except:
            pass
    
    finally:
        # Ensure cleanup
        await realtime_manager.disconnect(websocket)


@router.websocket("/feedme/approval")
async def websocket_approval_updates(
    websocket: WebSocket,
    token: Optional[str] = Query(None)
):
    """
    WebSocket endpoint for real-time approval workflow updates.
    
    Provides real-time updates on:
    - Approval decisions
    - Review assignments
    - Bulk operations
    - Workflow metrics
    """
    try:
        # Authenticate user
        if not token:
            await websocket.close(code=1008, reason="Authentication required")
            return
        
        user_id = await get_current_user_from_token(token)
        permissions = await get_user_permissions(user_id)
        
        # Verify user has approval read permission
        if "approval:read" not in permissions:
            await websocket.close(code=1008, reason="Insufficient permissions")
            return
        
        # Connect to approval updates room
        room_id = "approval_updates"
        
        connection_info = await realtime_manager.connect(
            websocket=websocket,
            user_id=user_id,
            room_id=room_id,
            permissions=permissions
        )
        
        logger.info(f"Approval WebSocket connected: user={user_id}")
        
        try:
            # Keep connection alive and handle messages
            while True:
                try:
                    message = await asyncio.wait_for(websocket.receive_json(), timeout=30.0)
                    await _handle_client_message(websocket, message, user_id, room_id)
                    
                except asyncio.TimeoutError:
                    await realtime_manager.send_heartbeat(room_id)
                
        except WebSocketDisconnect:
            logger.info(f"Approval WebSocket disconnected: user={user_id}")
        
    except Exception as e:
        logger.error(f"Error in approval WebSocket: {e}")
        try:
            await websocket.close(code=1011, reason="Internal server error")
        except:
            pass
    
    finally:
        await realtime_manager.disconnect(websocket)


@router.websocket("/feedme/global")
async def websocket_global_updates(
    websocket: WebSocket,
    token: Optional[str] = Query(None)
):
    """
    WebSocket endpoint for global FeedMe system updates.
    
    Provides real-time updates on:
    - System-wide notifications
    - Performance metrics
    - Administrative messages
    """
    try:
        # Authenticate user
        if not token:
            await websocket.close(code=1008, reason="Authentication required")
            return
        
        user_id = await get_current_user_from_token(token)
        permissions = await get_user_permissions(user_id)
        
        # Connect to global updates room
        room_id = "global_updates"
        
        connection_info = await realtime_manager.connect(
            websocket=websocket,
            user_id=user_id,
            room_id=room_id,
            permissions=permissions
        )
        
        logger.info(f"Global WebSocket connected: user={user_id}")
        
        try:
            while True:
                try:
                    message = await asyncio.wait_for(websocket.receive_json(), timeout=30.0)
                    await _handle_client_message(websocket, message, user_id, room_id)
                    
                except asyncio.TimeoutError:
                    await realtime_manager.send_heartbeat(room_id)
                
        except WebSocketDisconnect:
            logger.info(f"Global WebSocket disconnected: user={user_id}")
        
    except Exception as e:
        logger.error(f"Error in global WebSocket: {e}")
        try:
            await websocket.close(code=1011, reason="Internal server error")
        except:
            pass
    
    finally:
        await realtime_manager.disconnect(websocket)


# ===========================
# REST API for WebSocket Management
# ===========================

@router.get("/feedme/websocket/metrics", response_model=WebSocketMetrics)
async def get_websocket_metrics(
    current_user: str = Depends(get_current_user_from_token)
):
    """Get current WebSocket system metrics"""
    try:
        metrics = realtime_manager.get_metrics()
        return metrics
    except Exception as e:
        logger.error(f"Failed to get WebSocket metrics: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve metrics")


@router.get("/feedme/websocket/rooms", response_model=RoomListResponse)
async def list_websocket_rooms(
    current_user: str = Depends(get_current_user_from_token)
):
    """List all active WebSocket rooms"""
    try:
        rooms = []
        total_connections = 0
        
        for room_id, room in realtime_manager.rooms.items():
            room_info = RoomInfo(
                room_id=room_id,
                connection_count=len(room.connections),
                created_at=room.created_at,
                last_activity=room.last_activity,
                total_messages_sent=room.message_count,
                unique_users=len(set(conn.user_id for conn in room.connections.values())),
                room_type=room.room_type,
                metadata=room.metadata
            )
            rooms.append(room_info)
            total_connections += len(room.connections)
        
        return RoomListResponse(
            rooms=rooms,
            total_rooms=len(rooms),
            total_connections=total_connections
        )
        
    except Exception as e:
        logger.error(f"Failed to list WebSocket rooms: {e}")
        raise HTTPException(status_code=500, detail="Failed to list rooms")


@router.get("/feedme/websocket/rooms/{room_id}/users")
async def get_room_users(
    room_id: str,
    current_user: str = Depends(get_current_user_from_token)
):
    """Get list of users in a specific room"""
    try:
        users = realtime_manager.get_room_users(room_id)
        
        # Return user information (excluding sensitive data)
        user_list = [
            {
                "user_id": user.user_id,
                "connected_at": user.connected_at.isoformat(),
                "permissions": user.permissions,
                "message_count": user.message_count
            }
            for user in users
        ]
        
        return {
            "room_id": room_id,
            "user_count": len(user_list),
            "users": user_list
        }
        
    except Exception as e:
        logger.error(f"Failed to get room users: {e}")
        raise HTTPException(status_code=500, detail="Failed to get room users")


@router.post("/feedme/websocket/rooms/{room_id}/broadcast")
async def broadcast_to_room(
    room_id: str,
    message: dict,
    required_permission: Optional[str] = None,
    exclude_users: Optional[List[str]] = None,
    current_user: str = Depends(get_current_user_from_token)
):
    """Broadcast message to a specific room (admin only)"""
    try:
        # Check if user has admin permission
        user_permissions = await get_user_permissions(current_user)
        if "admin" not in user_permissions:
            raise HTTPException(status_code=403, detail="Admin permission required")
        
        # Add sender information to message
        message["sender"] = current_user
        message["timestamp"] = asyncio.get_event_loop().time()
        
        # Broadcast message
        failed_connections = await realtime_manager.broadcast_to_room(
            room_id=room_id,
            message=message,
            required_permission=required_permission,
            exclude_users=exclude_users or []
        )
        
        return {
            "success": True,
            "room_id": room_id,
            "failed_connections": len(failed_connections),
            "message_sent": True
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to broadcast to room: {e}")
        raise HTTPException(status_code=500, detail="Failed to broadcast message")


# ===========================
# Helper Functions
# ===========================

async def _handle_client_message(
    websocket: WebSocket,
    message: dict,
    user_id: str,
    room_id: str
):
    """Handle messages received from WebSocket clients"""
    try:
        message_type = message.get("type")
        
        if message_type == "ping":
            # Respond to ping with pong
            await websocket.send_json({"type": "pong", "timestamp": asyncio.get_event_loop().time()})
        
        elif message_type == "subscribe":
            # Handle subscription changes
            subscription_type = message.get("subscription_type")
            logger.info(f"User {user_id} subscribed to {subscription_type} in room {room_id}")
        
        elif message_type == "unsubscribe":
            # Handle unsubscription
            subscription_type = message.get("subscription_type")
            logger.info(f"User {user_id} unsubscribed from {subscription_type} in room {room_id}")
        
        else:
            logger.warning(f"Unknown message type from client: {message_type}")
    
    except Exception as e:
        logger.error(f"Error handling client message: {e}")
        # Send error response
        await websocket.send_json({
            "type": "error",
            "error": "Failed to process message",
            "details": str(e)
        })


# ===========================
# Integration Functions for Use by Other Systems
# ===========================

async def notify_processing_update(update: ProcessingUpdate):
    """
    Function for other systems to send processing updates.
    
    Args:
        update: Processing update to broadcast
    """
    try:
        await realtime_manager.broadcast_processing_update(update)
        logger.debug(f"Broadcasted processing update for conversation {update.conversation_id}")
    except Exception as e:
        logger.error(f"Failed to broadcast processing update: {e}")


async def notify_approval_update(update: ApprovalUpdate):
    """
    Function for other systems to send approval updates.
    
    Args:
        update: Approval update to broadcast
    """
    try:
        await realtime_manager.broadcast_approval_update(update)
        logger.debug(f"Broadcasted approval update for temp example {update.temp_example_id}")
    except Exception as e:
        logger.error(f"Failed to broadcast approval update: {e}")


async def send_notification(
    room_id: str,
    title: str,
    message: str,
    level: str = "info",
    required_permission: Optional[str] = None
):
    """
    Send notification to a room.
    
    Args:
        room_id: Room to send notification to
        title: Notification title
        message: Notification message
        level: Notification level (info, warning, error, success)
        required_permission: Optional permission requirement
    """
    try:
        notification = {
            "type": "notification",
            "title": title,
            "message": message,
            "level": level,
            "timestamp": asyncio.get_event_loop().time()
        }
        
        await realtime_manager.broadcast_to_room(
            room_id=room_id,
            message=notification,
            required_permission=required_permission
        )
        
        logger.debug(f"Sent notification to room {room_id}: {title}")
        
    except Exception as e:
        logger.error(f"Failed to send notification: {e}")


# Export integration functions for use by other modules
__all__ = [
    "router",
    "notify_processing_update",
    "notify_approval_update", 
    "send_notification"
]