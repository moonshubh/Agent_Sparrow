"""
FeedMe v2.0 WebSocket Schemas

Pydantic models for WebSocket message types and communication protocols.
"""

from datetime import datetime
from typing import List, Dict, Optional, Any
from enum import Enum

from pydantic import BaseModel, Field, ConfigDict

from app.feedme.schemas import ProcessingStatus, ProcessingStage


class MessageType(str, Enum):
    """WebSocket message types"""
    PROCESSING_UPDATE = "processing_update"
    APPROVAL_UPDATE = "approval_update"
    CONNECTION_STATUS = "connection_status"
    HEARTBEAT = "heartbeat"
    ERROR = "error"
    NOTIFICATION = "notification"




# ===========================
# Core Message Types
# ===========================

class ProcessingUpdate(BaseModel):
    """Real-time processing status update"""
    model_config = ConfigDict(from_attributes=True)
    
    conversation_id: int
    status: ProcessingStatus
    stage: ProcessingStage
    progress: int = Field(..., ge=0, le=100, description="Progress percentage")
    message: str
    
    # Detailed progress information
    total_steps: Optional[int] = None
    current_step: Optional[int] = None
    estimated_time_remaining: Optional[int] = None  # seconds
    
    # Processing statistics
    extracted_qa_count: Optional[int] = None
    quality_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    
    # Error information
    error_code: Optional[str] = None
    error_details: Optional[str] = None
    
    # Metadata
    processing_time_ms: Optional[int] = None
    ai_model_used: Optional[str] = None
    
    timestamp: datetime = Field(default_factory=datetime.now)


class ApprovalUpdate(BaseModel):
    """Approval workflow status update"""
    model_config = ConfigDict(from_attributes=True)
    
    temp_example_id: int
    previous_status: str
    new_status: str
    reviewer_id: Optional[str] = None
    
    # Review details
    review_notes: Optional[str] = None
    confidence_assessment: Optional[float] = Field(None, ge=0.0, le=1.0)
    
    # Bulk operation information
    is_bulk_operation: bool = False
    bulk_operation_id: Optional[str] = None
    total_items: Optional[int] = None
    
    timestamp: datetime = Field(default_factory=datetime.now)


class ConnectionStatus(BaseModel):
    """Connection status information"""
    user_id: str
    room_id: str
    status: str  # "connected", "disconnected", "reconnected"
    permissions: List[str]
    user_count: int
    timestamp: datetime = Field(default_factory=datetime.now)


class HeartbeatMessage(BaseModel):
    """Heartbeat/ping message"""
    message_type: MessageType = MessageType.HEARTBEAT
    timestamp: datetime = Field(default_factory=datetime.now)
    server_time: datetime = Field(default_factory=datetime.now)


class ErrorMessage(BaseModel):
    """Error message for WebSocket communication"""
    message_type: MessageType = MessageType.ERROR
    error_code: str
    error_message: str
    details: Optional[Dict[str, Any]] = None
    timestamp: datetime = Field(default_factory=datetime.now)


class NotificationMessage(BaseModel):
    """General notification message"""
    message_type: MessageType = MessageType.NOTIFICATION
    title: str
    message: str
    level: str = Field(default="info")  # "info", "warning", "error", "success"
    action_url: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.now)


# ===========================
# Connection Management
# ===========================

class ConnectionRequest(BaseModel):
    """WebSocket connection request"""
    model_config = ConfigDict(str_strip_whitespace=True)
    
    room_id: str = Field(..., min_length=1, max_length=100)
    permissions: List[str] = Field(default_factory=list)
    
    # Optional connection metadata
    client_info: Optional[Dict[str, str]] = None
    reconnection_token: Optional[str] = None


class ConnectionInfo(BaseModel):
    """Information about a WebSocket connection"""
    user_id: str
    room_id: str
    permissions: List[str]
    connected_at: datetime
    
    # Connection metadata
    client_info: Optional[Dict[str, str]] = None
    last_activity: Optional[datetime] = None
    message_count: int = 0


class BroadcastMessage(BaseModel):
    """Message for broadcasting to rooms"""
    room_id: str
    message_type: MessageType
    content: Dict[str, Any]
    
    # Filtering options
    required_permission: Optional[str] = None
    exclude_users: List[str] = Field(default_factory=list)
    
    # Message options
    persistent: bool = False  # Whether to queue for offline users
    ttl_seconds: Optional[int] = None  # Time to live for queued messages
    
    timestamp: datetime = Field(default_factory=datetime.now)


# ===========================
# Room Management
# ===========================

class RoomInfo(BaseModel):
    """Information about a WebSocket room"""
    room_id: str
    connection_count: int
    created_at: datetime
    last_activity: datetime
    
    # Room statistics
    total_messages_sent: int = 0
    unique_users: int = 0
    
    # Room metadata
    room_type: Optional[str] = None  # "conversation", "approval", "global"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RoomListResponse(BaseModel):
    """Response for listing rooms"""
    rooms: List[RoomInfo]
    total_rooms: int
    total_connections: int
    server_uptime: Optional[float] = None


# ===========================
# Analytics and Monitoring
# ===========================

class WebSocketMetrics(BaseModel):
    """WebSocket system metrics"""
    # Connection metrics
    total_connections: int
    active_rooms: int
    messages_sent_per_minute: float
    
    # Performance metrics
    avg_message_latency_ms: Optional[float] = None
    connection_success_rate: float
    disconnection_rate: float
    
    # Resource usage
    memory_usage_mb: Optional[float] = None
    cpu_usage_percent: Optional[float] = None
    
    # Time period
    period_start: datetime
    period_end: datetime


class ConnectionEvent(BaseModel):
    """Event for connection tracking"""
    event_type: str  # "connect", "disconnect", "message", "error"
    user_id: str
    room_id: str
    timestamp: datetime = Field(default_factory=datetime.now)
    
    # Event details
    details: Optional[Dict[str, Any]] = None
    duration_ms: Optional[int] = None
    error_message: Optional[str] = None


# ===========================
# Message Queuing
# ===========================

class QueuedMessage(BaseModel):
    """Message queued for offline users"""
    user_id: str
    message: Dict[str, Any]
    queued_at: datetime = Field(default_factory=datetime.now)
    
    # Queue options
    ttl_seconds: int = 3600  # 1 hour default
    priority: int = 0  # Higher number = higher priority
    attempts: int = 0
    max_attempts: int = 3


class MessageQueue(BaseModel):
    """Message queue for a user"""
    user_id: str
    messages: List[QueuedMessage] = Field(default_factory=list)
    max_queue_size: int = 100
    
    def add_message(self, message: QueuedMessage) -> bool:
        """Add message to queue"""
        if len(self.messages) >= self.max_queue_size:
            # Remove oldest message
            self.messages.pop(0)
        
        self.messages.append(message)
        return True
    
    def get_pending_messages(self) -> List[QueuedMessage]:
        """Get messages that haven't expired"""
        now = datetime.now()
        valid_messages = []
        
        for msg in self.messages:
            age_seconds = (now - msg.queued_at).total_seconds()
            if age_seconds < msg.ttl_seconds:
                valid_messages.append(msg)
        
        # Update queue with only valid messages
        self.messages = valid_messages
        return valid_messages


# ===========================
# Authentication
# ===========================

class WebSocketAuthToken(BaseModel):
    """Authentication token for WebSocket connections"""
    user_id: str
    permissions: List[str]
    expires_at: datetime
    issued_at: datetime = Field(default_factory=datetime.now)
    
    # Token metadata
    token_id: str
    session_id: Optional[str] = None
    
    def is_expired(self) -> bool:
        """Check if token is expired"""
        return datetime.now() > self.expires_at
    
    def has_permission(self, permission: str) -> bool:
        """Check if token has specific permission"""
        return permission in self.permissions


class AuthenticationResponse(BaseModel):
    """Response from WebSocket authentication"""
    success: bool
    user_id: Optional[str] = None
    permissions: List[str] = Field(default_factory=list)
    error_message: Optional[str] = None
    token: Optional[WebSocketAuthToken] = None
