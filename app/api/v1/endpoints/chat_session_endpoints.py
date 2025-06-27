"""
Chat Session API Endpoints

API endpoints for chat session persistence and message management.
Provides functionality for creating, managing, and retrieving chat sessions and messages.
Following the established MB-Sparrow patterns from FeedMe endpoints.
"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import JSONResponse
from psycopg2.extras import RealDictCursor
import psycopg2

from app.core.settings import settings
from app.core.security import get_current_user, TokenPayload
from app.db.connection_manager import with_db_connection
from app.schemas.chat_schemas import (
    ChatSession,
    ChatMessage,
    ChatSessionCreate,
    ChatMessageCreate,
    ChatSessionUpdate,
    ChatSessionWithMessages,
    ChatSessionListResponse,
    ChatMessageListResponse,
    ChatSessionListRequest,
    ChatMessageListRequest,
    ChatSessionStats,
    UserChatStats,
    ChatErrorResponse,
    BulkSessionUpdate,
    BulkSessionUpdateResponse,
    AgentType,
    MessageType
)

logger = logging.getLogger(__name__)
router = APIRouter()


# Database helper functions

@with_db_connection(cursor_factory=RealDictCursor)
def get_chat_session_by_id(conn, session_id: int, user_id: str) -> Optional[Dict[str, Any]]:
    """Get a chat session by ID for a specific user"""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT * FROM chat_sessions 
            WHERE id = %s AND user_id = %s
        """, (session_id, user_id))
        row = cur.fetchone()
        return dict(row) if row else None


@with_db_connection(cursor_factory=RealDictCursor)
def create_chat_session_in_db(conn, session_data: ChatSessionCreate, user_id: str) -> Dict[str, Any]:
    """Create a new chat session in the database"""
    with conn.cursor() as cur:
        # Check if user has too many active sessions for this agent type
        cur.execute("""
            SELECT COUNT(*) as active_count
            FROM chat_sessions 
            WHERE user_id = %s AND agent_type = %s AND is_active = TRUE
        """, (user_id, session_data.agent_type.value))
        
        active_count = cur.fetchone()['active_count']
        if active_count >= settings.max_sessions_per_agent:
            # Deactivate the oldest active session
            cur.execute("""
                UPDATE chat_sessions 
                SET is_active = FALSE 
                WHERE user_id = %s AND agent_type = %s AND is_active = TRUE
                AND id = (
                    SELECT id FROM chat_sessions 
                    WHERE user_id = %s AND agent_type = %s AND is_active = TRUE
                    ORDER BY last_message_at ASC 
                    LIMIT 1
                )
            """, (user_id, session_data.agent_type.value, user_id, session_data.agent_type.value))
        
        # Create the new session
        cur.execute("""
            INSERT INTO chat_sessions (user_id, title, agent_type, metadata, is_active)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING *
        """, (
            user_id,
            session_data.title,
            session_data.agent_type.value,
            session_data.metadata,
            session_data.is_active
        ))
        
        conn.commit()
        return dict(cur.fetchone())


@with_db_connection(cursor_factory=RealDictCursor)
def update_chat_session_in_db(conn, session_id: int, user_id: str, updates: ChatSessionUpdate) -> Optional[Dict[str, Any]]:
    """Update a chat session in the database"""
    with conn.cursor() as cur:
        # Build dynamic update query
        update_fields = []
        update_values = []
        
        if updates.title is not None:
            update_fields.append("title = %s")
            update_values.append(updates.title)
        
        if updates.is_active is not None:
            update_fields.append("is_active = %s")
            update_values.append(updates.is_active)
        
        if updates.metadata is not None:
            update_fields.append("metadata = %s")
            update_values.append(updates.metadata)
        
        if not update_fields:
            return None
        
        # Add WHERE clause values
        update_values.extend([session_id, user_id])
        
        cur.execute(f"""
            UPDATE chat_sessions 
            SET {', '.join(update_fields)}
            WHERE id = %s AND user_id = %s
            RETURNING *
        """, update_values)
        
        conn.commit()
        row = cur.fetchone()
        return dict(row) if row else None


@with_db_connection(cursor_factory=RealDictCursor)
def create_chat_message_in_db(conn, message_data: ChatMessageCreate, user_id: str) -> Dict[str, Any]:
    """Create a new chat message in the database"""
    with conn.cursor() as cur:
        # Verify session ownership
        cur.execute("""
            SELECT id FROM chat_sessions 
            WHERE id = %s AND user_id = %s
        """, (message_data.session_id, user_id))
        
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Chat session not found")
        
        # Create the message
        cur.execute("""
            INSERT INTO chat_messages (session_id, content, message_type, agent_type, metadata)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING *
        """, (
            message_data.session_id,
            message_data.content,
            message_data.message_type.value,
            message_data.agent_type.value if message_data.agent_type else None,
            message_data.metadata
        ))
        
        conn.commit()
        return dict(cur.fetchone())


@with_db_connection(cursor_factory=RealDictCursor)
def get_chat_sessions_for_user(conn, user_id: str, request: ChatSessionListRequest) -> Dict[str, Any]:
    """Get chat sessions for a user with filtering and pagination"""
    with conn.cursor() as cur:
        # Build WHERE clause
        where_conditions = ["user_id = %s"]
        where_values = [user_id]
        
        if request.agent_type:
            where_conditions.append("agent_type = %s")
            where_values.append(request.agent_type.value)
        
        if request.is_active is not None:
            where_conditions.append("is_active = %s")
            where_values.append(request.is_active)
        
        if request.search:
            where_conditions.append("title ILIKE %s")
            where_values.append(f"%{request.search}%")
        
        where_clause = " AND ".join(where_conditions)
        
        # Get total count
        cur.execute(f"""
            SELECT COUNT(*) as total_count
            FROM chat_sessions
            WHERE {where_clause}
        """, where_values)
        total_count = cur.fetchone()['total_count']
        
        # Get paginated results
        offset = (request.page - 1) * request.page_size
        cur.execute(f"""
            SELECT * FROM chat_sessions
            WHERE {where_clause}
            ORDER BY last_message_at DESC
            LIMIT %s OFFSET %s
        """, where_values + [request.page_size, offset])
        
        sessions = [dict(row) for row in cur.fetchall()]
        
        return {
            "sessions": sessions,
            "total_count": total_count,
            "page": request.page,
            "page_size": request.page_size,
            "has_next": offset + request.page_size < total_count,
            "has_previous": request.page > 1
        }


@with_db_connection(cursor_factory=RealDictCursor)
def get_chat_messages_for_session(conn, session_id: int, user_id: str, request: ChatMessageListRequest) -> Dict[str, Any]:
    """Get chat messages for a session with pagination"""
    with conn.cursor() as cur:
        # Verify session ownership
        cur.execute("""
            SELECT id FROM chat_sessions 
            WHERE id = %s AND user_id = %s
        """, (session_id, user_id))
        
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Chat session not found")
        
        # Build WHERE clause
        where_conditions = ["session_id = %s"]
        where_values = [session_id]
        
        if request.message_type:
            where_conditions.append("message_type = %s")
            where_values.append(request.message_type.value)
        
        where_clause = " AND ".join(where_conditions)
        
        # Get total count
        cur.execute(f"""
            SELECT COUNT(*) as total_count
            FROM chat_messages
            WHERE {where_clause}
        """, where_values)
        total_count = cur.fetchone()['total_count']
        
        # Get paginated results
        offset = (request.page - 1) * request.page_size
        cur.execute(f"""
            SELECT * FROM chat_messages
            WHERE {where_clause}
            ORDER BY created_at ASC
            LIMIT %s OFFSET %s
        """, where_values + [request.page_size, offset])
        
        messages = [dict(row) for row in cur.fetchall()]
        
        return {
            "messages": messages,
            "total_count": total_count,
            "page": request.page,
            "page_size": request.page_size,
            "has_next": offset + request.page_size < total_count,
            "has_previous": request.page > 1
        }


# API Endpoints

@router.post("/chat-sessions", response_model=ChatSession, tags=["Chat Sessions"])
async def create_chat_session(
    session_data: ChatSessionCreate,
    current_user: TokenPayload = Depends(get_current_user)
):
    """Create a new chat session"""
    try:
        session_dict = create_chat_session_in_db(session_data, current_user.sub)
        return ChatSession(**session_dict)
    except psycopg2.Error as e:
        logger.error(f"Database error creating chat session: {e}")
        raise HTTPException(status_code=500, detail="Error creating chat session")
    except Exception as e:
        logger.error(f"Error creating chat session: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/chat-sessions", response_model=ChatSessionListResponse, tags=["Chat Sessions"])
async def list_chat_sessions(
    agent_type: Optional[AgentType] = Query(None, description="Filter by agent type"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=100, description="Number of sessions per page"),
    search: Optional[str] = Query(None, description="Search in session titles"),
    current_user: TokenPayload = Depends(get_current_user)
):
    """List chat sessions for the current user"""
    try:
        request = ChatSessionListRequest(
            agent_type=agent_type,
            is_active=is_active,
            page=page,
            page_size=page_size,
            search=search
        )
        
        result = get_chat_sessions_for_user(current_user.sub, request)
        sessions = [ChatSession(**session) for session in result["sessions"]]
        
        return ChatSessionListResponse(
            sessions=sessions,
            total_count=result["total_count"],
            page=result["page"],
            page_size=result["page_size"],
            has_next=result["has_next"],
            has_previous=result["has_previous"]
        )
    except Exception as e:
        logger.error(f"Error listing chat sessions: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/chat-sessions/{session_id}", response_model=ChatSessionWithMessages, tags=["Chat Sessions"])
async def get_chat_session(
    session_id: int,
    include_messages: bool = Query(True, description="Include messages in response"),
    current_user: TokenPayload = Depends(get_current_user)
):
    """Get a specific chat session with optional messages"""
    try:
        session_dict = get_chat_session_by_id(session_id, current_user.sub)
        if not session_dict:
            raise HTTPException(status_code=404, detail="Chat session not found")
        
        session = ChatSession(**session_dict)
        
        if include_messages:
            message_request = ChatMessageListRequest(page=1, page_size=200)
            messages_result = get_chat_messages_for_session(session_id, current_user.sub, message_request)
            messages = [ChatMessage(**msg) for msg in messages_result["messages"]]
            return ChatSessionWithMessages(**session.model_dump(), messages=messages)
        else:
            return ChatSessionWithMessages(**session.model_dump(), messages=[])
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting chat session {session_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/chat-sessions/{session_id}", response_model=ChatSession, tags=["Chat Sessions"])
async def update_chat_session(
    session_id: int,
    updates: ChatSessionUpdate,
    current_user: TokenPayload = Depends(get_current_user)
):
    """Update a chat session"""
    try:
        updated_session = update_chat_session_in_db(session_id, current_user.sub, updates)
        if not updated_session:
            raise HTTPException(status_code=404, detail="Chat session not found")
        
        return ChatSession(**updated_session)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating chat session {session_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/chat-sessions/{session_id}", tags=["Chat Sessions"])
async def delete_chat_session(
    session_id: int,
    current_user: TokenPayload = Depends(get_current_user)
):
    """Soft delete a chat session (mark as inactive)"""
    try:
        updates = ChatSessionUpdate(is_active=False)
        updated_session = update_chat_session_in_db(session_id, current_user.sub, updates)
        if not updated_session:
            raise HTTPException(status_code=404, detail="Chat session not found")
        
        return {"message": "Chat session deleted successfully", "session_id": session_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting chat session {session_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/chat-sessions/{session_id}/messages", response_model=ChatMessage, tags=["Chat Messages"])
async def create_chat_message(
    session_id: int,
    message_data: ChatMessageCreate,
    current_user: TokenPayload = Depends(get_current_user)
):
    """Add a message to a chat session"""
    try:
        # Ensure session_id matches
        message_data.session_id = session_id
        
        message_dict = create_chat_message_in_db(message_data, current_user.sub)
        return ChatMessage(**message_dict)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating chat message: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/chat-sessions/{session_id}/messages", response_model=ChatMessageListResponse, tags=["Chat Messages"])
async def list_chat_messages(
    session_id: int,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=200, description="Number of messages per page"),
    message_type: Optional[MessageType] = Query(None, description="Filter by message type"),
    current_user: TokenPayload = Depends(get_current_user)
):
    """List messages for a specific chat session"""
    try:
        request = ChatMessageListRequest(
            page=page,
            page_size=page_size,
            message_type=message_type
        )
        
        result = get_chat_messages_for_session(session_id, current_user.sub, request)
        messages = [ChatMessage(**msg) for msg in result["messages"]]
        
        return ChatMessageListResponse(
            messages=messages,
            total_count=result["total_count"],
            page=result["page"],
            page_size=result["page_size"],
            has_next=result["has_next"],
            has_previous=result["has_previous"]
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing chat messages: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/chat-sessions/stats/user", response_model=UserChatStats, tags=["Chat Statistics"])
async def get_user_chat_stats(
    current_user: TokenPayload = Depends(get_current_user)
):
    """Get chat statistics for the current user"""
    try:
        @with_db_connection(cursor_factory=RealDictCursor)
        def get_user_stats(conn, user_id: str) -> Dict[str, Any]:
            with conn.cursor() as cur:
                # Get session stats
                cur.execute("""
                    SELECT 
                        COUNT(*) as total_sessions,
                        COUNT(*) FILTER (WHERE is_active = TRUE) as active_sessions,
                        agent_type,
                        MAX(created_at) as most_recent_session,
                        MIN(created_at) as oldest_session
                    FROM chat_sessions 
                    WHERE user_id = %s
                    GROUP BY agent_type
                """, (user_id,))
                
                agent_stats = cur.fetchall()
                
                # Get total message count
                cur.execute("""
                    SELECT COUNT(*) as total_messages
                    FROM chat_messages cm
                    JOIN chat_sessions cs ON cm.session_id = cs.id
                    WHERE cs.user_id = %s
                """, (user_id,))
                
                total_messages = cur.fetchone()['total_messages']
                
                # Calculate aggregated stats
                total_sessions = sum(stat['total_sessions'] for stat in agent_stats)
                active_sessions = sum(stat['active_sessions'] for stat in agent_stats)
                sessions_by_agent_type = {stat['agent_type']: stat['total_sessions'] for stat in agent_stats}
                most_recent = max((stat['most_recent_session'] for stat in agent_stats), default=None)
                oldest = min((stat['oldest_session'] for stat in agent_stats), default=None)
                
                return {
                    "user_id": user_id,
                    "total_sessions": total_sessions,
                    "active_sessions": active_sessions,
                    "total_messages": total_messages,
                    "sessions_by_agent_type": sessions_by_agent_type,
                    "most_recent_session": most_recent,
                    "oldest_session": oldest
                }
        
        stats = get_user_stats(current_user.sub)
        return UserChatStats(**stats)
    
    except Exception as e:
        logger.error(f"Error getting user chat stats: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")