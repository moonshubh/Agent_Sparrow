"""
MB-Sparrow Schemas Module

Centralized Pydantic models for data validation and API contracts.
"""

from .chat_schemas import (
    # Enums
    MessageType,
    AgentType,
    
    # Base Models
    ChatSessionBase,
    ChatMessageBase,
    
    # Create Models
    ChatSessionCreate,
    ChatMessageCreate,
    
    # Update Models
    ChatSessionUpdate,
    
    # Response Models
    ChatSession,
    ChatMessage,
    ChatSessionWithMessages,
    
    # List Response Models
    ChatSessionListResponse,
    ChatMessageListResponse,
    
    # Request Models
    ChatSessionListRequest,
    ChatMessageListRequest,
    
    # Statistics Models
    ChatSessionStats,
    UserChatStats,
    
    # Error Models
    ChatErrorResponse,
    
    # Bulk Operations
    BulkSessionUpdate,
    BulkSessionUpdateResponse,
)

__all__ = [
    # Enums
    "MessageType",
    "AgentType",
    
    # Base Models
    "ChatSessionBase", 
    "ChatMessageBase",
    
    # Create Models
    "ChatSessionCreate",
    "ChatMessageCreate",
    
    # Update Models
    "ChatSessionUpdate",
    
    # Response Models
    "ChatSession",
    "ChatMessage", 
    "ChatSessionWithMessages",
    
    # List Response Models
    "ChatSessionListResponse",
    "ChatMessageListResponse",
    
    # Request Models
    "ChatSessionListRequest",
    "ChatMessageListRequest",
    
    # Statistics Models
    "ChatSessionStats",
    "UserChatStats",
    
    # Error Models
    "ChatErrorResponse",
    
    # Bulk Operations
    "BulkSessionUpdate",
    "BulkSessionUpdateResponse",
]