"""
Chat Session Pydantic Models

Data structures for chat session persistence and message management.
Following the established MB-Sparrow patterns from FeedMe schemas.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field, validator


class MessageType(str, Enum):
    """Types of messages in a chat session"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class AgentType(str, Enum):
    """Types of agents that can handle chat sessions"""
    PRIMARY = "primary"
    LOG_ANALYSIS = "log_analysis"
    RESEARCH = "research"
    ROUTER = "router"


# Base Models

class ChatSessionBase(BaseModel):
    """Base model for chat sessions"""
    title: str = Field(..., min_length=1, max_length=255, description="Session title or topic")
    agent_type: AgentType = Field(default=AgentType.PRIMARY, description="Agent type handling this session")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    is_active: bool = Field(default=True, description="Whether session is active")

    @validator('title')
    def validate_title(cls, v):
        """Validate that title is not empty after stripping whitespace"""
        if not v or not v.strip():
            raise ValueError("Title cannot be empty")
        return v.strip()


class ChatMessageBase(BaseModel):
    """Base model for chat messages"""
    content: str = Field(..., min_length=1, description="Message content")
    message_type: MessageType = Field(default=MessageType.USER, description="Type of message")
    agent_type: Optional[AgentType] = Field(None, description="Agent that generated assistant messages")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata including follow-up questions")

    @validator('content')
    def validate_content(cls, v):
        """Validate that content is not empty after stripping whitespace"""
        if not v or not v.strip():
            raise ValueError("Message content cannot be empty")
        return v.strip()

    @validator('agent_type')
    def validate_agent_type_for_assistant(cls, v, values):
        """Validate that assistant messages have an agent_type"""
        if values.get('message_type') == MessageType.ASSISTANT and not v:
            raise ValueError("Assistant messages must specify an agent_type")
        return v


# Create Models (for API requests)

class ChatSessionCreate(ChatSessionBase):
    """Model for creating new chat sessions"""
    pass


class ChatMessageCreate(ChatMessageBase):
    """Model for creating new chat messages"""
    session_id: int = Field(..., description="ID of the parent chat session")


# Update Models

class ChatSessionUpdate(BaseModel):
    """Model for updating chat sessions"""
    title: Optional[str] = Field(None, min_length=1, max_length=255, description="Updated session title")
    is_active: Optional[bool] = Field(None, description="Updated active status")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Updated metadata")

    @validator('title')
    def validate_title(cls, v):
        """Validate that title is not empty after stripping whitespace"""
        if v is not None:
            if not v or not v.strip():
                raise ValueError("Title cannot be empty")
            return v.strip()
        return v


# Response Models

class ChatSession(ChatSessionBase):
    """Full chat session model for responses"""
    id: int
    user_id: str
    created_at: datetime
    last_message_at: datetime
    updated_at: datetime
    message_count: int = Field(default=0, description="Number of messages in this session")

    class Config:
        from_attributes = True


class ChatMessage(ChatMessageBase):
    """Full chat message model for responses"""
    id: int
    session_id: int
    created_at: datetime

    class Config:
        from_attributes = True


class ChatSessionWithMessages(ChatSession):
    """Chat session with embedded messages"""
    messages: List[ChatMessage] = Field(default_factory=list, description="Messages in this session")


# List Response Models

class ChatSessionListResponse(BaseModel):
    """Response model for listing chat sessions"""
    sessions: List[ChatSession]
    total_count: int
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=10, ge=1, le=100)
    has_next: bool = Field(default=False)
    has_previous: bool = Field(default=False)


class ChatMessageListResponse(BaseModel):
    """Response model for listing chat messages"""
    messages: List[ChatMessage]
    total_count: int
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)
    has_next: bool = Field(default=False)
    has_previous: bool = Field(default=False)


# Request Models

class ChatSessionListRequest(BaseModel):
    """Request model for listing chat sessions"""
    agent_type: Optional[AgentType] = Field(None, description="Filter by agent type")
    is_active: Optional[bool] = Field(None, description="Filter by active status")
    page: int = Field(default=1, ge=1, description="Page number")
    page_size: int = Field(default=10, ge=1, le=100, description="Number of sessions per page")
    search: Optional[str] = Field(None, description="Search in session titles")


class ChatMessageListRequest(BaseModel):
    """Request model for listing chat messages"""
    page: int = Field(default=1, ge=1, description="Page number")
    page_size: int = Field(default=50, ge=1, le=200, description="Number of messages per page")
    message_type: Optional[MessageType] = Field(None, description="Filter by message type")


# Statistics Models

class ChatSessionStats(BaseModel):
    """Statistics for chat sessions"""
    total_sessions: int
    active_sessions: int
    inactive_sessions: int
    sessions_by_agent_type: Dict[str, int]
    total_messages: int
    average_messages_per_session: float


class UserChatStats(BaseModel):
    """Chat statistics for a specific user"""
    user_id: str
    total_sessions: int
    active_sessions: int
    total_messages: int
    sessions_by_agent_type: Dict[str, int]
    most_recent_session: Optional[datetime]
    oldest_session: Optional[datetime]


# Error Response Models

class ChatErrorResponse(BaseModel):
    """Standard error response for chat endpoints"""
    error: str
    detail: Optional[str] = None
    error_code: Optional[str] = None


# Bulk Operations Models

class BulkSessionUpdate(BaseModel):
    """Model for bulk updating sessions"""
    session_ids: List[int] = Field(..., min_items=1, description="List of session IDs to update")
    updates: ChatSessionUpdate = Field(..., description="Updates to apply")


class BulkSessionUpdateResponse(BaseModel):
    """Response for bulk session updates"""
    updated_count: int
    failed_updates: List[Dict[str, Any]] = Field(default_factory=list)
    success: bool