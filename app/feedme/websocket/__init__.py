"""
FeedMe v2.0 WebSocket Real-time Updates

This module provides real-time WebSocket communication for FeedMe processing
updates, approval notifications, and collaborative features.
"""

from .realtime_manager import FeedMeRealtimeManager, WebSocketRoom, ConnectionInfo
from .schemas import (
    ProcessingUpdate,
    ApprovalUpdate,
    ConnectionRequest,
    BroadcastMessage,
    MessageType,
)

__all__ = [
    "FeedMeRealtimeManager",
    "WebSocketRoom",
    "ConnectionInfo",
    "ProcessingUpdate",
    "ApprovalUpdate",
    "ConnectionRequest",
    "BroadcastMessage",
    "MessageType",
]
