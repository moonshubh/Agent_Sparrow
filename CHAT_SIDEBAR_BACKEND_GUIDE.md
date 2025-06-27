# Chat Sidebar Backend Integration Guide

## Overview
This guide outlines the backend implementation needed to persist chat sessions across devices and users for the MB-Sparrow chat sidebar feature.

## Database Schema

### 1. Chat Sessions Table
```sql
CREATE TABLE chat_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(255) NOT NULL,  -- Will be linked to auth system
    title VARCHAR(255) NOT NULL,
    agent_type VARCHAR(20) NOT NULL CHECK (agent_type IN ('primary', 'log_analysis')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_message_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT true,
    metadata JSONB DEFAULT '{}',
    CONSTRAINT chat_sessions_user_agent_limit CHECK (
        (SELECT COUNT(*) FROM chat_sessions 
         WHERE user_id = NEW.user_id 
         AND agent_type = NEW.agent_type 
         AND is_active = true) <= 5
    )
);

-- Indexes for performance
CREATE INDEX idx_chat_sessions_user_id ON chat_sessions(user_id);
CREATE INDEX idx_chat_sessions_agent_type ON chat_sessions(agent_type);
CREATE INDEX idx_chat_sessions_last_message_at ON chat_sessions(last_message_at DESC);
```

### 2. Chat Messages Table
```sql
CREATE TABLE chat_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    message_type VARCHAR(20) NOT NULL CHECK (message_type IN ('user', 'agent', 'system')),
    content TEXT NOT NULL,
    agent_type VARCHAR(20),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    embedding VECTOR(768)  -- For future semantic search
);

-- Indexes
CREATE INDEX idx_chat_messages_session_id ON chat_messages(session_id);
CREATE INDEX idx_chat_messages_created_at ON chat_messages(created_at);
```

## API Endpoints Implementation

### 1. Create Chat Session
```python
# app/api/v1/endpoints/chat_sessions.py
from fastapi import APIRouter, Depends, HTTPException
from app.core.auth import get_current_user
from app.db.models import ChatSession, ChatMessage
from app.schemas.chat import ChatSessionCreate, ChatSessionResponse

router = APIRouter()

@router.post("/chat-sessions", response_model=ChatSessionResponse)
async def create_chat_session(
    session: ChatSessionCreate,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    # Check if user has reached limit for agent type
    existing_count = await db.query(ChatSession).filter(
        ChatSession.user_id == current_user.id,
        ChatSession.agent_type == session.agent_type,
        ChatSession.is_active == True
    ).count()
    
    if existing_count >= 5:
        # Deactivate oldest session
        oldest = await db.query(ChatSession).filter(
            ChatSession.user_id == current_user.id,
            ChatSession.agent_type == session.agent_type,
            ChatSession.is_active == True
        ).order_by(ChatSession.last_message_at.asc()).first()
        
        if oldest:
            oldest.is_active = False
            await db.commit()
    
    # Create new session
    new_session = ChatSession(
        user_id=current_user.id,
        title=session.title,
        agent_type=session.agent_type
    )
    db.add(new_session)
    await db.commit()
    
    return new_session
```

### 2. List User Sessions
```python
@router.get("/chat-sessions", response_model=List[ChatSessionResponse])
async def list_chat_sessions(
    agent_type: Optional[str] = None,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    query = db.query(ChatSession).filter(
        ChatSession.user_id == current_user.id,
        ChatSession.is_active == True
    )
    
    if agent_type:
        query = query.filter(ChatSession.agent_type == agent_type)
    
    sessions = await query.order_by(
        ChatSession.last_message_at.desc()
    ).limit(10).all()
    
    return sessions
```

### 3. Get Session with Messages
```python
@router.get("/chat-sessions/{session_id}", response_model=ChatSessionDetailResponse)
async def get_chat_session(
    session_id: UUID,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    session = await db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == current_user.id
    ).first()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Get messages
    messages = await db.query(ChatMessage).filter(
        ChatMessage.session_id == session_id
    ).order_by(ChatMessage.created_at.asc()).all()
    
    return {
        **session.__dict__,
        "messages": messages
    }
```

### 4. Update Session (Rename)
```python
@router.put("/chat-sessions/{session_id}", response_model=ChatSessionResponse)
async def update_chat_session(
    session_id: UUID,
    update: ChatSessionUpdate,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    session = await db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == current_user.id
    ).first()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if update.title:
        session.title = update.title
    
    await db.commit()
    return session
```

### 5. Delete Session
```python
@router.delete("/chat-sessions/{session_id}")
async def delete_chat_session(
    session_id: UUID,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    session = await db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == current_user.id
    ).first()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Soft delete
    session.is_active = False
    await db.commit()
    
    return {"message": "Session deleted successfully"}
```

### 6. Add Message to Session
```python
@router.post("/chat-sessions/{session_id}/messages", response_model=ChatMessageResponse)
async def add_message_to_session(
    session_id: UUID,
    message: ChatMessageCreate,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    # Verify session ownership
    session = await db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == current_user.id
    ).first()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Create message
    new_message = ChatMessage(
        session_id=session_id,
        message_type=message.message_type,
        content=message.content,
        agent_type=message.agent_type,
        metadata=message.metadata or {}
    )
    
    # Update session last_message_at
    session.last_message_at = datetime.utcnow()
    
    db.add(new_message)
    await db.commit()
    
    # Generate embedding asynchronously if needed
    if settings.ENABLE_EMBEDDINGS:
        asyncio.create_task(generate_message_embedding(new_message.id))
    
    return new_message
```

## Pydantic Schemas

```python
# app/schemas/chat.py
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID

class ChatSessionCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    agent_type: str = Field(..., regex="^(primary|log_analysis)$")
    initial_message: Optional[str] = None

class ChatSessionUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)

class ChatSessionResponse(BaseModel):
    id: UUID
    title: str
    agent_type: str
    created_at: datetime
    last_message_at: datetime
    message_count: Optional[int] = 0
    
    class Config:
        from_attributes = True

class ChatMessageCreate(BaseModel):
    message_type: str = Field(..., regex="^(user|agent|system)$")
    content: str = Field(..., min_length=1)
    agent_type: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class ChatMessageResponse(BaseModel):
    id: UUID
    session_id: UUID
    message_type: str
    content: str
    agent_type: Optional[str]
    metadata: Dict[str, Any]
    created_at: datetime
    
    class Config:
        from_attributes = True

class ChatSessionDetailResponse(ChatSessionResponse):
    messages: List[ChatMessageResponse]
```

## Integration with Existing System

### 1. Modify UnifiedChat Hook
```typescript
// Add session tracking to the existing chat system
const { sendMessage: originalSendMessage } = useUnifiedChat()

const sendMessage = async (content: string, files?: File[]) => {
  // Send to backend
  const response = await originalSendMessage(content, files)
  
  // Track in session if we have one
  if (currentSessionId && response.message) {
    await fetch(`/api/v1/chat-sessions/${currentSessionId}/messages`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message_type: 'user',
        content: content
      })
    })
    
    // Track agent response when it arrives
    if (response.agentMessage) {
      await fetch(`/api/v1/chat-sessions/${currentSessionId}/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message_type: 'agent',
          content: response.agentMessage.content,
          agent_type: response.agentMessage.agentType,
          metadata: response.agentMessage.metadata
        })
      })
    }
  }
  
  return response
}
```

### 2. Authentication Integration
```python
# app/core/auth.py
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    # For now, return a mock user ID
    # In production, validate JWT token and extract user info
    return {"id": "user_123", "email": "user@mailbird.com"}
```

## Migration Strategy

1. **Phase 1**: Deploy backend API with mock authentication
2. **Phase 2**: Update frontend to use API instead of localStorage
3. **Phase 3**: Implement real authentication system
4. **Phase 4**: Migrate existing localStorage data to backend

## Performance Optimizations

1. **Pagination**: Limit messages loaded per session
2. **Caching**: Redis cache for frequently accessed sessions
3. **Lazy Loading**: Load messages on demand
4. **Compression**: Compress old messages
5. **Archival**: Move old sessions to cold storage

## Security Considerations

1. **Authentication**: Require valid JWT token
2. **Authorization**: Users can only access their own sessions
3. **Rate Limiting**: Prevent abuse of API endpoints
4. **Input Validation**: Sanitize all user inputs
5. **Encryption**: Encrypt sensitive message content

---

**Created**: June 26, 2025
**Status**: Ready for Implementation
**Priority**: Medium (after authentication system)