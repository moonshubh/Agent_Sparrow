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
from app.db.supabase_client import get_supabase_client
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

async def get_chat_session_by_id(session_id: int, user_id: str) -> Optional[Dict[str, Any]]:
    """Get a chat session by ID for a specific user"""
    try:
        client = get_supabase_client()
        response = client.client.table('chat_sessions')\
            .select('*')\
            .eq('id', session_id)\
            .eq('user_id', user_id)\
            .maybe_single()\
            .execute()
        
        return response.data if response.data else None
    except Exception as e:
        logger.error(f"Error fetching chat session {session_id}: {e}")
        return None


async def create_chat_session_in_db(session_data: ChatSessionCreate, user_id: str) -> Dict[str, Any]:
    """Create a new chat session in the database"""
    # NOTE: Supabase doesn't support traditional transactions, but we can minimize
    # race conditions by combining operations where possible
    try:
        client = get_supabase_client()
        
        # Check if user has too many active sessions for this agent type
        count_response = client.client.table('chat_sessions')\
            .select('id', count='exact')\
            .eq('user_id', user_id)\
            .eq('agent_type', session_data.agent_type.value)\
            .eq('is_active', True)\
            .execute()
        
        active_count = count_response.count or 0
        
        if active_count >= getattr(settings, 'max_sessions_per_agent', 10):
            # Deactivate the oldest active session
            # This is best-effort - in rare cases concurrent requests might exceed limit temporarily
            oldest_response = client.client.table('chat_sessions')\
                .select('id')\
                .eq('user_id', user_id)\
                .eq('agent_type', session_data.agent_type.value)\
                .eq('is_active', True)\
                .order('last_message_at', asc=True)\
                .limit(1)\
                .execute()
            
            if oldest_response.data:
                client.client.table('chat_sessions')\
                    .update({'is_active': False})\
                    .eq('id', oldest_response.data[0]['id'])\
                    .execute()
        
        # Create the new session
        new_session_data = {
            'user_id': user_id,
            'title': session_data.title,
            'agent_type': session_data.agent_type.value,
            'metadata': session_data.metadata or {},
            'is_active': session_data.is_active
        }
        
        response = client.client.table('chat_sessions').insert(new_session_data).execute()
        
        if response.data:
            return response.data[0]
        else:
            raise Exception("Failed to create session")
            
    except Exception as e:
        logger.error(f"Error creating chat session: {e}")
        raise


async def update_chat_session_in_db(session_id: int, user_id: str, updates: ChatSessionUpdate) -> Optional[Dict[str, Any]]:
    """Update a chat session in the database"""
    try:
        client = get_supabase_client()
        
        # Build update data
        update_data = {}
        
        if updates.title is not None:
            update_data['title'] = updates.title
        
        if updates.is_active is not None:
            update_data['is_active'] = updates.is_active
        
        if updates.metadata is not None:
            update_data['metadata'] = updates.metadata
        
        if not update_data:
            return None
        
        # Don't manually set updated_at - let the database handle it
        
        response = client.client.table('chat_sessions')\
            .update(update_data)\
            .eq('id', session_id)\
            .eq('user_id', user_id)\
            .execute()
        
        return response.data[0] if response.data else None
        
    except Exception as e:
        logger.error(f"Error updating chat session {session_id}: {e}")
        return None


async def create_chat_message_in_db(message_data: ChatMessageCreate, user_id: str) -> Dict[str, Any]:
    """Create a new chat message in the database"""
    try:
        client = get_supabase_client()
        
        # Verify session ownership
        session_check = client.client.table('chat_sessions')\
            .select('id')\
            .eq('id', message_data.session_id)\
            .eq('user_id', user_id)\
            .maybe_single()\
            .execute()
        
        if not session_check.data:
            raise HTTPException(status_code=404, detail="Chat session not found")
        
        # Create the message
        message_data_dict = {
            'session_id': message_data.session_id,
            'content': message_data.content,
            'message_type': message_data.message_type.value,
            'agent_type': message_data.agent_type.value if message_data.agent_type else None,
            'metadata': message_data.metadata or {}
        }
        
        # Insert message first
        response = client.client.table('chat_messages').insert(message_data_dict).execute()
        
        if not response.data:
            raise Exception("Failed to create message")
        
        # Update session last_message_at after successful message creation
        # NOTE: This is best-effort - if it fails, the message is still created
        # which is preferable to losing the message
        try:
            client.client.table('chat_sessions')\
                .update({'last_message_at': datetime.now().isoformat()})\
                .eq('id', message_data.session_id)\
                .execute()
        except Exception as update_error:
            # Log but don't fail the request - message was created successfully
            logger.warning(f"Failed to update session last_message_at: {update_error}")
        
        return response.data[0]
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating chat message: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def get_chat_sessions_for_user(user_id: str, request: ChatSessionListRequest) -> Dict[str, Any]:
    """Get chat sessions for a user with filtering and pagination"""
    try:
        client = get_supabase_client()
        
        # Build query with filters
        query = client.client.table('chat_sessions').select('*').eq('user_id', user_id)
        count_query = client.client.table('chat_sessions').select('id', count='exact').eq('user_id', user_id)
        
        if request.agent_type:
            query = query.eq('agent_type', request.agent_type.value)
            count_query = count_query.eq('agent_type', request.agent_type.value)
        
        if request.is_active is not None:
            query = query.eq('is_active', request.is_active)
            count_query = count_query.eq('is_active', request.is_active)
        
        if request.search:
            query = query.ilike('title', f'%{request.search}%')
            count_query = count_query.ilike('title', f'%{request.search}%')
        
        # Get total count
        count_response = count_query.execute()
        total_count = count_response.count or 0
        
        # Get paginated results
        offset = (request.page - 1) * request.page_size
        query = query.order('last_message_at', desc=True).range(offset, offset + request.page_size - 1)
        
        response = query.execute()
        sessions = response.data or []
        
        return {
            "sessions": sessions,
            "total_count": total_count,
            "page": request.page,
            "page_size": request.page_size,
            "has_next": offset + request.page_size < total_count,
            "has_previous": request.page > 1
        }
        
    except Exception as e:
        logger.error(f"Error listing chat sessions: {e}")
        # Re-raise the exception instead of returning empty results
        raise


async def get_chat_messages_for_session(session_id: int, user_id: str, request: ChatMessageListRequest) -> Dict[str, Any]:
    """Get chat messages for a session with pagination and strict session filtering"""
    try:
        client = get_supabase_client()
        
        # Verify session ownership - CRITICAL for preventing cross-session contamination
        session_check = client.client.table('chat_sessions')\
            .select('id')\
            .eq('id', session_id)\
            .eq('user_id', user_id)\
            .maybe_single()\
            .execute()
        
        if not session_check.data:
            raise HTTPException(status_code=404, detail="Chat session not found")
        
        # Build query with strict session filter
        query = client.client.table('chat_messages').select('*').eq('session_id', session_id)
        count_query = client.client.table('chat_messages').select('id', count='exact').eq('session_id', session_id)
        
        if request.message_type:
            query = query.eq('message_type', request.message_type.value)
            count_query = count_query.eq('message_type', request.message_type.value)
        
        # Get total count
        count_response = count_query.execute()
        total_count = count_response.count or 0
        
        # Get paginated results
        offset = (request.page - 1) * request.page_size
        query = query.order('created_at', asc=True).range(offset, offset + request.page_size - 1)
        
        response = query.execute()
        messages = response.data or []
        
        return {
            "messages": messages,
            "total_count": total_count,
            "page": request.page,
            "page_size": request.page_size,
            "has_next": offset + request.page_size < total_count,
            "has_previous": request.page > 1
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing chat messages: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# API Endpoints

@router.post("/chat-sessions", response_model=ChatSession, tags=["Chat Sessions"])
async def create_chat_session(
    session_data: ChatSessionCreate,
    current_user: TokenPayload = Depends(get_current_user)
):
    """Create a new chat session"""
    try:
        session_dict = await create_chat_session_in_db(session_data, current_user.sub)
        return ChatSession(**session_dict)
    except HTTPException:
        raise
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
        
        result = await get_chat_sessions_for_user(current_user.sub, request)
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
            messages_result = await get_chat_messages_for_session(session_id, current_user.sub, message_request)
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
        updated_session = await update_chat_session_in_db(session_id, current_user.sub, updates)
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
        updated_session = await update_chat_session_in_db(session_id, current_user.sub, updates)
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
        
        message_dict = await create_chat_message_in_db(message_data, current_user.sub)
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
        
        result = await get_chat_messages_for_session(session_id, current_user.sub, request)
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
        client = get_supabase_client()
        
        # Get session stats
        sessions_response = client.client.table('chat_sessions')\
            .select('*')\
            .eq('user_id', current_user.sub)\
            .execute()
        
        sessions = sessions_response.data or []
        
        # Calculate session stats
        total_sessions = len(sessions)
        active_sessions = sum(1 for s in sessions if s.get('is_active', False))
        
        # Group by agent type
        sessions_by_agent_type = {}
        for session in sessions:
            agent_type = session.get('agent_type', 'unknown')
            sessions_by_agent_type[agent_type] = sessions_by_agent_type.get(agent_type, 0) + 1
        
        # Get date ranges
        if sessions:
            created_dates = [s.get('created_at') for s in sessions if s.get('created_at')]
            most_recent = max(created_dates) if created_dates else None
            oldest = min(created_dates) if created_dates else None
        else:
            most_recent = None
            oldest = None
        
        # Get total message count with a single aggregated query
        if sessions:
            session_ids = [session['id'] for session in sessions]
            messages_response = client.client.table('chat_messages')\
                .select('id', count='exact')\
                .in_('session_id', session_ids)\
                .execute()
            total_messages = messages_response.count or 0
        else:
            total_messages = 0
        
        stats = {
            "user_id": current_user.sub,
            "total_sessions": total_sessions,
            "active_sessions": active_sessions,
            "total_messages": total_messages,
            "sessions_by_agent_type": sessions_by_agent_type,
            "most_recent_session": most_recent,
            "oldest_session": oldest
        }
        
        return UserChatStats(**stats)
    
    except Exception as e:
        logger.error(f"Error getting user chat stats: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")