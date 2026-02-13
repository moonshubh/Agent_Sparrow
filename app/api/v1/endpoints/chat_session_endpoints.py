# mypy: ignore-errors
"""
Chat Session API Endpoints

API endpoints for chat session persistence and message management.
Provides functionality for creating, managing, and retrieving chat sessions and messages.
Following the established MB-Sparrow patterns from FeedMe endpoints.
"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, Query, Request, Response
from psycopg2.extras import RealDictCursor
import psycopg2
import os
import uuid
import hashlib
import itertools
from collections import defaultdict

from app.core.constants import AGENT_SESSION_LIMITS

from app.core.settings import settings
from app.core.security import get_current_user, get_optional_current_user, TokenPayload
from app.db.supabase.client import get_supabase_client, SupabaseClient
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
    UserChatStats,
    AgentType,
    AgentMode,
    MessageType,
)
from pydantic import BaseModel, Field
from app.agents.unified.agent_modes import (
    DEFAULT_AGENT_MODE,
    resolve_agent_mode,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# Constants for guest user management
GUEST_USER_COOKIE_NAME = "guest_user_id"
GUEST_USER_COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 days
GUEST_USER_PREFIX = "guest_"

# Local in-memory fallback stores for development when Postgres is unavailable
LOCAL_CHAT_SESSIONS: dict[str, List[dict[str, Any]]] = defaultdict(list)
LOCAL_CHAT_MESSAGES: dict[int, List[dict[str, Any]]] = defaultdict(list)
LOCAL_MESSAGE_ID_COUNTER = itertools.count(1)


def _get_local_session(user_id: str, session_id: int) -> Optional[dict[str, Any]]:
    for session in LOCAL_CHAT_SESSIONS.get(user_id, []):
        if session["id"] == session_id:
            return session
    return None


def _persist_local_session(user_id: str, session: dict[str, Any]) -> dict[str, Any]:
    sessions = LOCAL_CHAT_SESSIONS[user_id]
    sessions[:] = [existing for existing in sessions if existing["id"] != session["id"]]
    sessions.append(session)
    sessions.sort(key=lambda s: s["last_message_at"], reverse=True)
    _enforce_local_session_limit(user_id, session["agent_type"])
    return session


def _enforce_local_session_limit(user_id: str, agent_type: str) -> None:
    sessions = LOCAL_CHAT_SESSIONS[user_id]
    limit = AGENT_SESSION_LIMITS.get(agent_type, AGENT_SESSION_LIMITS["primary"])
    active_sessions = [
        s for s in sessions if s["is_active"] and s["agent_type"] == agent_type
    ]
    display_user = hashlib.sha256(user_id.encode()).hexdigest()[:8]
    while len(active_sessions) > limit:
        oldest = min(active_sessions, key=lambda s: s["last_message_at"])
        sessions[:] = [s for s in sessions if s["id"] != oldest["id"]]
        LOCAL_CHAT_MESSAGES.pop(oldest["id"], None)
        logger.info(
            "Evicted local chat session %s for user %s (agent_type=%s limit=%s)",
            oldest["id"],
            display_user,
            agent_type,
            limit,
        )
        active_sessions = [
            s for s in sessions if s["is_active"] and s["agent_type"] == agent_type
        ]
    sessions.sort(key=lambda s: s["last_message_at"], reverse=True)


def _store_local_message(
    user_id: str,
    session_id: int,
    message: dict[str, Any],
) -> dict[str, Any]:
    session = _get_local_session(user_id, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Chat session not found")

    messages = LOCAL_CHAT_MESSAGES[session_id]
    messages.append(message)
    messages.sort(key=lambda m: m["created_at"])

    session["message_count"] = len(messages)
    session["last_message_at"] = message["created_at"]
    session["updated_at"] = message["created_at"]
    _persist_local_session(user_id, session)
    return message


def _enum_value(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


def _resolve_session_agent_mode(
    *,
    agent_type: Any,
    explicit_mode: Any = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    meta_mode = metadata.get("agent_mode") if isinstance(metadata, dict) else None
    return resolve_agent_mode(
        explicit_mode or meta_mode,
        legacy_agent_type=_enum_value(agent_type),
        default=DEFAULT_AGENT_MODE,
    )


def _metadata_with_agent_mode(
    metadata: Optional[Dict[str, Any]],
    *,
    mode: str,
) -> Dict[str, Any]:
    merged = dict(metadata or {})
    merged["agent_mode"] = mode
    return merged


def _annotate_session_with_mode(session: Dict[str, Any]) -> Dict[str, Any]:
    metadata = session.get("metadata")
    mode = _resolve_session_agent_mode(
        agent_type=session.get("agent_type"),
        explicit_mode=session.get("agent_mode"),
        metadata=metadata if isinstance(metadata, dict) else None,
    )
    session["agent_mode"] = mode
    session["metadata"] = _metadata_with_agent_mode(
        metadata if isinstance(metadata, dict) else {},
        mode=mode,
    )
    return session


class ChatMessageAppendRequest(BaseModel):
    """Payload for appending content to an existing chat message"""

    delta: str = Field(
        ..., min_length=1, description="Text to append to the message content"
    )


class ChatMessageUpdateRequest(BaseModel):
    """Payload for updating an existing chat message's content and metadata"""

    content: Optional[str] = Field(
        None, min_length=1, description="New content for the message"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None, description="Metadata updates for the message"
    )


# Database connection setup
def _has_database_credentials() -> bool:
    """Return True when Supabase/Postgres credentials are available."""
    if os.getenv("DATABASE_URL"):
        return True

    supabase_url = settings.supabase_url or os.getenv("SUPABASE_URL")
    service_key = (
        os.getenv("SUPABASE_SERVICE_KEY")
        or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("SUPABASE_SERVICE_ROLE")
    )
    anon_key = os.getenv("SUPABASE_ANON_KEY")

    return bool(supabase_url and (service_key or anon_key))


def get_db_connection():
    """Get a database connection using Supabase credentials.

    Falls back to None (mock mode) when authentication is skipped or a connection
    cannot be established. This keeps local development usable without requiring
    Postgres while preserving production behaviour.
    """

    skip_auth_flag = settings.skip_auth or os.getenv("SKIP_AUTH", "false").lower() in {
        "1",
        "true",
        "yes",
    }
    has_credentials = _has_database_credentials()

    if skip_auth_flag and not has_credentials:
        logger.info(
            "Skipping database connection in local auth bypass mode (no credentials configured)"
        )
        return None

    if skip_auth_flag and has_credentials:
        logger.info(
            "Auth bypass enabled but Supabase credentials detected; enabling persistent storage"
        )

    database_url = (
        os.getenv("DATABASE_URL")
        or settings.supabase_db_conn
        or os.getenv("SUPABASE_DB_CONN")
    )

    if not database_url:
        supabase_url = settings.supabase_url
        if supabase_url and supabase_url.startswith("https://"):
            project_id = supabase_url.split("//")[1].split(".")[0]
            supabase_db_password = os.getenv("SUPABASE_DB_PASSWORD")
            if supabase_db_password:
                database_url = f"postgresql://postgres:{supabase_db_password}@db.{project_id}.supabase.co:5432/postgres"
            elif not settings.is_production_mode():
                # Local dev fallback only. Railway/Supabase deployments should not attempt localhost.
                database_url = "postgresql://postgres:postgres@localhost:5432/postgres"

    if not database_url:
        logger.warning(
            "DATABASE_URL not configured; operating without persistent storage"
        )
        return None

    try:
        return psycopg2.connect(database_url, cursor_factory=RealDictCursor)
    except psycopg2.Error as exc:
        logger.error(
            "Failed to connect to database (%s). Falling back to mock mode.", exc
        )
        return None


def get_supabase_chat_storage() -> Optional[SupabaseClient]:
    """Return a Supabase client for chat persistence, or None when not configured."""

    try:
        client = get_supabase_client()
    except Exception as exc:
        logger.error("Failed to initialize Supabase client for chat sessions: %s", exc)
        return None

    if getattr(client, "mock_mode", False):
        return None

    return client


# Database helper functions


async def get_chat_session_by_id(
    conn, session_id: int, user_id: str
) -> Optional[Dict[str, Any]]:
    """Get a chat session by ID for a specific user"""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT * FROM chat_sessions 
            WHERE id = %s AND user_id = %s
        """,
            (session_id, user_id),
        )
        row = cur.fetchone()
        return dict(row) if row else None


async def get_chat_session_by_id_in_supabase(
    client: SupabaseClient,
    *,
    session_id: int,
    user_id: str,
) -> Optional[Dict[str, Any]]:
    """Get a chat session by ID for a specific user via Supabase REST."""

    response = await client._exec(
        lambda: client.client.table("chat_sessions")
        .select("*")
        .eq("id", session_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    return response.data if getattr(response, "data", None) else None


# @with_db_connection removed - using Supabase
def create_chat_session_in_db(
    conn, session_data: ChatSessionCreate, user_id: str
) -> Dict[str, Any]:
    """Create a new chat session in the database

    Args:
        conn: Database connection
        session_data: Session creation data
        user_id: User ID

    Returns:
        Created session data

    Raises:
        psycopg2.Error: Database errors
    """
    try:
        with conn.cursor() as cur:
            # Get agent-specific configuration with error handling
            try:
                cur.execute(
                    """
                    SELECT max_active_sessions 
                    FROM agent_configuration 
                    WHERE agent_type = %s
                """,
                    (session_data.agent_type.value,),
                )

                config_row = cur.fetchone()
                if config_row:
                    max_sessions = config_row["max_active_sessions"]
                    logger.debug(
                        f"Retrieved max_sessions={max_sessions} for agent_type={session_data.agent_type.value}"
                    )
                else:
                    # Fallback to centralized defaults
                    max_sessions = AGENT_SESSION_LIMITS.get(
                        session_data.agent_type.value, 5
                    )
                    logger.warning(
                        f"No config found for agent_type={session_data.agent_type.value}, "
                        f"using default limit={max_sessions}"
                    )
            except psycopg2.Error as e:
                # Log error and use fallback
                logger.error(f"Error fetching agent configuration: {e}")
                max_sessions = AGENT_SESSION_LIMITS.get(
                    session_data.agent_type.value, 5
                )
                logger.info(
                    f"Using fallback limit={max_sessions} for agent_type={session_data.agent_type.value}"
                )

            # Check if user has too many active sessions for this agent type
            cur.execute(
                """
                SELECT COUNT(*) as active_count
                FROM chat_sessions 
                WHERE user_id = %s AND agent_type = %s AND is_active = TRUE
            """,
                (user_id, session_data.agent_type.value),
            )

            active_count = cur.fetchone()["active_count"]
            if active_count >= max_sessions:
                # Deactivate the oldest active session
                cur.execute(
                    """
                    UPDATE chat_sessions 
                    SET is_active = FALSE 
                    WHERE user_id = %s AND agent_type = %s AND is_active = TRUE
                    AND id = (
                        SELECT id FROM chat_sessions 
                        WHERE user_id = %s AND agent_type = %s AND is_active = TRUE
                        ORDER BY last_message_at ASC 
                        LIMIT 1
                    )
                """,
                    (
                        user_id,
                        session_data.agent_type.value,
                        user_id,
                        session_data.agent_type.value,
                    ),
                )
                logger.info(
                    f"Deactivated oldest session for user={user_id}, agent_type={session_data.agent_type.value} "
                    f"(limit={max_sessions}, had={active_count})"
                )

            # Create the new session
            import json

            resolved_mode = _resolve_session_agent_mode(
                agent_type=session_data.agent_type,
                explicit_mode=session_data.agent_mode,
                metadata=session_data.metadata,
            )
            metadata_payload = _metadata_with_agent_mode(
                session_data.metadata,
                mode=resolved_mode,
            )
            metadata_json = json.dumps(metadata_payload) if metadata_payload else "{}"

            cur.execute(
                """
                INSERT INTO chat_sessions (user_id, title, agent_type, metadata, is_active)
                VALUES (%s, %s, %s, %s::jsonb, %s)
                RETURNING *
            """,
                (
                    user_id,
                    session_data.title,
                    session_data.agent_type.value,
                    metadata_json,
                    session_data.is_active,
                ),
            )

            conn.commit()
            session_dict = dict(cur.fetchone())
            session_dict["agent_mode"] = resolved_mode
            session_dict["metadata"] = metadata_payload
            logger.info(
                f"Created session id={session_dict.get('id')} for user={user_id}, "
                f"agent_type={session_data.agent_type.value}"
            )
            return _annotate_session_with_mode(session_dict)
    except psycopg2.Error as e:
        logger.error(f"Database error in create_chat_session_in_db: {e}")
        conn.rollback()
        raise
    except Exception as e:
        logger.error(f"Unexpected error in create_chat_session_in_db: {e}")
        conn.rollback()
        raise


async def create_chat_session_in_supabase(
    client: SupabaseClient,
    *,
    session_data: ChatSessionCreate,
    user_id: str,
) -> Dict[str, Any]:
    """Create a new chat session via Supabase REST."""

    resolved_mode = _resolve_session_agent_mode(
        agent_type=session_data.agent_type,
        explicit_mode=session_data.agent_mode,
        metadata=session_data.metadata,
    )
    metadata_payload = _metadata_with_agent_mode(
        session_data.metadata,
        mode=resolved_mode,
    )

    payload: Dict[str, Any] = {
        "user_id": user_id,
        "title": session_data.title,
        "agent_type": _enum_value(session_data.agent_type) or "primary",
        "metadata": metadata_payload,
        "is_active": bool(session_data.is_active),
    }

    response = await client._exec(
        lambda: client.client.table("chat_sessions").insert(payload).execute()
    )

    rows = getattr(response, "data", None) or []
    if not rows:
        raise RuntimeError("Supabase insert chat_sessions returned no rows")
    session = dict(rows[0])
    session["agent_mode"] = resolved_mode
    session["metadata"] = metadata_payload
    return _annotate_session_with_mode(session)


# @with_db_connection removed - using Supabase
def update_chat_session_in_db(
    conn, session_id: int, user_id: str, updates: ChatSessionUpdate
) -> Optional[Dict[str, Any]]:
    """Update a chat session in the database"""
    import json

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

        if updates.metadata is not None or updates.agent_mode is not None:
            cur.execute(
                """
                SELECT agent_type, metadata
                FROM chat_sessions
                WHERE id = %s AND user_id = %s
            """,
                (session_id, user_id),
            )
            existing_row = cur.fetchone()
            if not existing_row:
                return None

            existing_meta = dict(existing_row.get("metadata") or {})
            if updates.metadata is not None:
                existing_meta.update(updates.metadata)
            resolved_mode = _resolve_session_agent_mode(
                agent_type=existing_row.get("agent_type"),
                explicit_mode=updates.agent_mode,
                metadata=existing_meta,
            )
            merged_metadata = _metadata_with_agent_mode(
                existing_meta,
                mode=resolved_mode,
            )
            update_fields.append("metadata = %s::jsonb")
            update_values.append(json.dumps(merged_metadata))

        if not update_fields:
            return None

        # Add WHERE clause values
        update_values.extend([session_id, user_id])

        cur.execute(
            f"""
            UPDATE chat_sessions 
            SET {", ".join(update_fields)}
            WHERE id = %s AND user_id = %s
            RETURNING *
        """,
            update_values,
        )

        conn.commit()
        row = cur.fetchone()
        return _annotate_session_with_mode(dict(row)) if row else None


async def update_chat_session_in_supabase(
    client: SupabaseClient,
    *,
    session_id: int,
    user_id: str,
    updates: ChatSessionUpdate,
) -> Optional[Dict[str, Any]]:
    """Update a chat session via Supabase REST."""

    payload: Dict[str, Any] = {}

    if updates.title is not None:
        payload["title"] = updates.title
    if updates.is_active is not None:
        payload["is_active"] = updates.is_active
    if updates.metadata is not None or updates.agent_mode is not None:
        existing_response = await client._exec(
            lambda: client.client.table("chat_sessions")
            .select("agent_type, metadata")
            .eq("id", session_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        existing = getattr(existing_response, "data", None)
        if not existing:
            return None
        existing_meta = dict(existing.get("metadata") or {})
        if updates.metadata is not None:
            existing_meta.update(updates.metadata)
        resolved_mode = _resolve_session_agent_mode(
            agent_type=existing.get("agent_type"),
            explicit_mode=updates.agent_mode,
            metadata=existing_meta,
        )
        payload["metadata"] = _metadata_with_agent_mode(
            existing_meta,
            mode=resolved_mode,
        )

    if not payload:
        return None

    response = await client._exec(
        lambda: client.client.table("chat_sessions")
        .update(payload)
        .eq("id", session_id)
        .eq("user_id", user_id)
        .execute()
    )

    rows = getattr(response, "data", None) or []
    return _annotate_session_with_mode(dict(rows[0])) if rows else None


# @with_db_connection removed - using Supabase
def create_chat_message_in_db(
    conn, message_data: ChatMessageCreate, user_id: str
) -> Dict[str, Any]:
    """Create a new chat message in the database"""
    import json

    with conn.cursor() as cur:
        # Verify session ownership
        cur.execute(
            """
            SELECT id FROM chat_sessions 
            WHERE id = %s AND user_id = %s
        """,
            (message_data.session_id, user_id),
        )

        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Chat session not found")

        # Ensure metadata is properly serialized as JSON
        metadata_json = "{}"
        if message_data.metadata:
            metadata_json = (
                json.dumps(message_data.metadata)
                if isinstance(message_data.metadata, dict)
                else message_data.metadata
            )

        # Create the message - ensure full content is stored
        cur.execute(
            """
            INSERT INTO chat_messages (session_id, content, message_type, agent_type, metadata)
            VALUES (%s, %s, %s, %s, %s::jsonb)
            RETURNING *
        """,
            (
                message_data.session_id,
                message_data.content,  # Full content, no truncation
                message_data.message_type.value,
                message_data.agent_type.value if message_data.agent_type else None,
                metadata_json,
            ),
        )

        conn.commit()
        message_row = dict(cur.fetchone())
        if message_row.get("metadata") is None:
            message_row["metadata"] = {}
        return message_row


async def create_chat_message_in_supabase(
    client: SupabaseClient,
    *,
    message_data: ChatMessageCreate,
    user_id: str,
) -> Dict[str, Any]:
    """Create a new chat message via Supabase REST."""

    # Verify session ownership
    session_response = await client._exec(
        lambda: client.client.table("chat_sessions")
        .select("id")
        .eq("id", message_data.session_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    if not getattr(session_response, "data", None):
        raise HTTPException(status_code=404, detail="Chat session not found")

    payload: Dict[str, Any] = {
        "session_id": message_data.session_id,
        "content": message_data.content,
        "message_type": _enum_value(message_data.message_type),
        "agent_type": (
            _enum_value(message_data.agent_type) if message_data.agent_type else None
        ),
        "metadata": message_data.metadata or {},
    }

    response = await client._exec(
        lambda: client.client.table("chat_messages").insert(payload).execute()
    )

    rows = getattr(response, "data", None) or []
    if not rows:
        raise RuntimeError("Supabase insert chat_messages returned no rows")

    row = dict(rows[0])
    if row.get("metadata") is None:
        row["metadata"] = {}
    return row


def append_chat_message_content_in_db(
    conn, session_id: int, message_id: int, user_id: str, delta: str
) -> Dict[str, Any]:
    """Append text content to an existing chat message owned by the user"""
    with conn.cursor() as cur:
        # Verify session and message ownership
        cur.execute(
            """
            SELECT cm.id
            FROM chat_messages cm
            JOIN chat_sessions cs ON cm.session_id = cs.id
            WHERE cm.id = %s AND cm.session_id = %s AND cs.user_id = %s
            """,
            (message_id, session_id, user_id),
        )
        if not cur.fetchone():
            raise HTTPException(
                status_code=404, detail="Message not found for this user/session"
            )

        # Append delta to content
        cur.execute(
            """
            UPDATE chat_messages
            SET content = content || %s
            WHERE id = %s
            RETURNING *
            """,
            (delta, message_id),
        )
        conn.commit()
        return dict(cur.fetchone())


async def append_chat_message_content_in_supabase(
    client: SupabaseClient,
    *,
    session_id: int,
    message_id: int,
    user_id: str,
    delta: str,
) -> Dict[str, Any]:
    """Append text to an existing chat message via Supabase REST."""

    # Verify session ownership
    session_response = await client._exec(
        lambda: client.client.table("chat_sessions")
        .select("id")
        .eq("id", session_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    if not getattr(session_response, "data", None):
        raise HTTPException(status_code=404, detail="Chat session not found")

    # Fetch existing content
    message_response = await client._exec(
        lambda: client.client.table("chat_messages")
        .select("id, content")
        .eq("id", message_id)
        .eq("session_id", session_id)
        .maybe_single()
        .execute()
    )
    row = getattr(message_response, "data", None)
    if not row:
        raise HTTPException(
            status_code=404, detail="Message not found for this user/session"
        )

    new_content = f"{row.get('content', '')}{delta}"

    update_response = await client._exec(
        lambda: client.client.table("chat_messages")
        .update({"content": new_content})
        .eq("id", message_id)
        .execute()
    )
    rows = getattr(update_response, "data", None) or []
    if not rows:
        # Fallback to refetch
        refetch = await client._exec(
            lambda: client.client.table("chat_messages")
            .select("*")
            .eq("id", message_id)
            .maybe_single()
            .execute()
        )
        if getattr(refetch, "data", None):
            return dict(refetch.data)
        raise RuntimeError("Supabase update chat_messages returned no rows")

    return dict(rows[0])


def update_chat_message_in_db(
    conn,
    session_id: int,
    message_id: int,
    user_id: str,
    content: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Update content and/or metadata of an existing chat message owned by the user"""
    with conn.cursor() as cur:
        # Verify session and message ownership
        cur.execute(
            """
            SELECT cm.id
            FROM chat_messages cm
            JOIN chat_sessions cs ON cm.session_id = cs.id
            WHERE cm.id = %s AND cm.session_id = %s AND cs.user_id = %s
            """,
            (message_id, session_id, user_id),
        )
        if not cur.fetchone():
            raise HTTPException(
                status_code=404, detail="Message not found for this user/session"
            )

        updates: list[str] = []
        values: list[Any] = []

        if content is not None:
            updates.append("content = %s")
            values.append(content)

        if metadata is not None:
            import json

            metadata_json = (
                json.dumps(metadata) if isinstance(metadata, dict) else metadata
            )
            updates.append("metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb")
            values.append(metadata_json)

        if not updates:
            raise HTTPException(status_code=400, detail="No updates provided")

        query = f"""
            UPDATE chat_messages
            SET {", ".join(updates)}
            WHERE id = %s
            RETURNING *
        """
        values.append(message_id)
        cur.execute(query, values)
        conn.commit()
        return dict(cur.fetchone())


async def update_chat_message_in_supabase(
    client: SupabaseClient,
    *,
    session_id: int,
    message_id: int,
    user_id: str,
    content: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Update content and/or metadata of an existing chat message via Supabase REST."""

    # Verify session ownership
    session_response = await client._exec(
        lambda: client.client.table("chat_sessions")
        .select("id")
        .eq("id", session_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    if not getattr(session_response, "data", None):
        raise HTTPException(status_code=404, detail="Chat session not found")

    if content is None and metadata is None:
        raise HTTPException(status_code=400, detail="No updates provided")

    # Fetch existing message for metadata merge (and existence validation)
    msg_response = await client._exec(
        lambda: client.client.table("chat_messages")
        .select("id, metadata")
        .eq("id", message_id)
        .eq("session_id", session_id)
        .maybe_single()
        .execute()
    )
    existing = getattr(msg_response, "data", None)
    if not existing:
        raise HTTPException(
            status_code=404, detail="Message not found for this user/session"
        )

    payload: Dict[str, Any] = {}
    if content is not None:
        payload["content"] = content

    if metadata is not None:
        existing_meta = existing.get("metadata") or {}
        if not isinstance(existing_meta, dict):
            existing_meta = {}
        payload["metadata"] = {**existing_meta, **metadata}

    response = await client._exec(
        lambda: client.client.table("chat_messages")
        .update(payload)
        .eq("id", message_id)
        .execute()
    )
    rows = getattr(response, "data", None) or []
    if not rows:
        # Fallback to refetch
        refetch = await client._exec(
            lambda: client.client.table("chat_messages")
            .select("*")
            .eq("id", message_id)
            .maybe_single()
            .execute()
        )
        if getattr(refetch, "data", None):
            row = dict(refetch.data)
            if row.get("metadata") is None:
                row["metadata"] = {}
            return row
        raise RuntimeError("Supabase update chat_messages returned no rows")

    row = dict(rows[0])
    if row.get("metadata") is None:
        row["metadata"] = {}
    return row


# @with_db_connection removed - using Supabase
def get_chat_sessions_for_user(
    conn, user_id: str, request: ChatSessionListRequest
) -> Dict[str, Any]:
    """Get chat sessions for a user with filtering and pagination"""
    with conn.cursor() as cur:
        # Build WHERE clause
        where_conditions = ["user_id = %s"]
        where_values = [user_id]

        if request.agent_type:
            where_conditions.append("agent_type = %s")
            where_values.append(request.agent_type.value)
        if request.agent_mode:
            where_conditions.append("COALESCE(metadata->>'agent_mode', %s) = %s")
            where_values.extend([DEFAULT_AGENT_MODE, request.agent_mode.value])

        if request.is_active is not None:
            where_conditions.append("is_active = %s")
            where_values.append(request.is_active)

        if request.search:
            where_conditions.append("title ILIKE %s")
            where_values.append(f"%{request.search}%")

        where_clause = " AND ".join(where_conditions)

        # Get total count
        cur.execute(
            f"""
            SELECT COUNT(*) as total_count
            FROM chat_sessions
            WHERE {where_clause}
        """,
            where_values,
        )
        total_count = cur.fetchone()["total_count"]

        # Get paginated results
        offset = (request.page - 1) * request.page_size
        cur.execute(
            f"""
            SELECT * FROM chat_sessions
            WHERE {where_clause}
            ORDER BY last_message_at DESC
            LIMIT %s OFFSET %s
        """,
            where_values + [request.page_size, offset],
        )

        sessions = [_annotate_session_with_mode(dict(row)) for row in cur.fetchall()]

        return {
            "sessions": sessions,
            "total_count": total_count,
            "page": request.page,
            "page_size": request.page_size,
            "has_next": offset + request.page_size < total_count,
            "has_previous": request.page > 1,
        }


async def get_chat_sessions_for_user_in_supabase(
    client: SupabaseClient,
    *,
    user_id: str,
    request: ChatSessionListRequest,
) -> Dict[str, Any]:
    """Get chat sessions for a user via Supabase REST."""

    query = (
        client.client.table("chat_sessions")
        .select("*", count="exact")
        .eq("user_id", user_id)
    )

    if request.agent_type:
        query = query.eq("agent_type", request.agent_type.value)
    if request.agent_mode:
        query = query.contains("metadata", {"agent_mode": request.agent_mode.value})

    if request.is_active is not None:
        query = query.eq("is_active", request.is_active)

    if request.search:
        query = query.ilike("title", f"%{request.search}%")

    offset = (request.page - 1) * request.page_size
    query = query.order("last_message_at", desc=True).range(
        offset, offset + request.page_size - 1
    )

    response = await client._exec(lambda: query.execute())

    sessions = getattr(response, "data", None) or []
    total_count = (
        response.count
        if getattr(response, "count", None) is not None
        else len(sessions)
    )

    return {
        "sessions": [_annotate_session_with_mode(dict(row)) for row in sessions],
        "total_count": total_count,
        "page": request.page,
        "page_size": request.page_size,
        "has_next": offset + request.page_size < total_count,
        "has_previous": request.page > 1,
    }


# @with_db_connection removed - using Supabase
def get_chat_messages_for_session(
    conn, session_id: int, user_id: str, request: ChatMessageListRequest
) -> Dict[str, Any]:
    """Get chat messages for a session with pagination - returns FULL message content"""
    with conn.cursor() as cur:
        # Verify session ownership
        cur.execute(
            """
            SELECT id FROM chat_sessions 
            WHERE id = %s AND user_id = %s
        """,
            (session_id, user_id),
        )

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
        cur.execute(
            f"""
            SELECT COUNT(*) as total_count
            FROM chat_messages
            WHERE {where_clause}
        """,
            where_values,
        )
        total_count = cur.fetchone()["total_count"]

        # Get ALL messages without pagination to ensure full conversation is loaded
        # Frontend handles display pagination if needed
        cur.execute(
            f"""
            SELECT id, session_id, content, message_type, agent_type, metadata, created_at
            FROM chat_messages
            WHERE {where_clause}
            ORDER BY created_at ASC
        """,
            where_values,
        )

        messages = []
        for row in cur.fetchall():
            msg_dict = dict(row)
            # Ensure full content is preserved
            if msg_dict.get("content"):
                # Log if content seems truncated (for debugging)
                if len(msg_dict["content"]) > 1000 and msg_dict["content"].endswith(
                    "..."
                ):
                    logger.warning(
                        f"Message {msg_dict['id']} may be truncated: ends with '...'"
                    )
            messages.append(msg_dict)

        # Still return pagination info for compatibility, but send all messages
        # Use max(total_count, 1) to satisfy page_size >= 1 validation
        return {
            "messages": messages,
            "total_count": total_count,
            "page": 1,
            "page_size": max(total_count, 1),  # All messages, min 1 for validation
            "has_next": False,
            "has_previous": False,
        }


async def get_chat_messages_for_session_in_supabase(
    client: SupabaseClient,
    *,
    session_id: int,
    user_id: str,
    request: ChatMessageListRequest,
) -> Dict[str, Any]:
    """Get chat messages for a session via Supabase REST."""

    # Verify session ownership
    session_response = await client._exec(
        lambda: client.client.table("chat_sessions")
        .select("id")
        .eq("id", session_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    if not getattr(session_response, "data", None):
        raise HTTPException(status_code=404, detail="Chat session not found")

    query = (
        client.client.table("chat_messages")
        .select(
            "id, session_id, content, message_type, agent_type, metadata, created_at",
            count="exact",
        )
        .eq("session_id", session_id)
    )

    if request.message_type:
        query = query.eq("message_type", request.message_type.value)

    query = query.order("created_at", desc=False)

    response = await client._exec(lambda: query.execute())

    rows = getattr(response, "data", None) or []
    total_count = (
        response.count if getattr(response, "count", None) is not None else len(rows)
    )

    messages: list[dict[str, Any]] = []
    for row in rows:
        msg_dict = dict(row)
        if msg_dict.get("metadata") is None:
            msg_dict["metadata"] = {}
        messages.append(msg_dict)

    return {
        "messages": messages,
        "total_count": total_count,
        "page": 1,
        "page_size": max(total_count, 1),
        "has_next": False,
        "has_previous": False,
    }


# API Endpoints


@router.get("/chat-sessions/test", tags=["Chat Sessions"])
async def test_endpoint():
    """Test endpoint to verify API is working"""
    return {"status": "ok", "message": "Chat sessions API is working"}


def get_or_create_guest_user_id(request: Request, response: Response) -> str:
    """Get existing guest user ID from cookie or create a new one."""
    guest_id = request.cookies.get(GUEST_USER_COOKIE_NAME)

    if not guest_id or not guest_id.startswith(GUEST_USER_PREFIX):
        # Generate a new secure guest ID
        guest_id = f"{GUEST_USER_PREFIX}{uuid.uuid4().hex}"

        forwarded_proto = (
            (request.headers.get("x-forwarded-proto") or "")
            .split(",")[0]
            .strip()
            .lower()
        )
        is_https = (
            forwarded_proto == "https"
            if forwarded_proto
            else request.url.scheme == "https"
        )

        # Set secure HTTP-only cookie
        response.set_cookie(
            key=GUEST_USER_COOKIE_NAME,
            value=guest_id,
            max_age=GUEST_USER_COOKIE_MAX_AGE,
            httponly=True,
            secure=is_https,
            samesite="strict",
            path="/",
        )
        logger.info(
            f"Created new guest user ID: {hashlib.sha256(guest_id.encode()).hexdigest()[:8]}..."
        )
    else:
        logger.debug(
            f"Using existing guest user ID: {hashlib.sha256(guest_id.encode()).hexdigest()[:8]}..."
        )

    return guest_id


@router.post("/chat-sessions", response_model=ChatSession, tags=["Chat Sessions"])
async def create_chat_session(
    session_data: ChatSessionCreate,
    request: Request,
    response: Response,
    current_user: Optional[TokenPayload] = Depends(get_optional_current_user),
):
    """Create a new chat session (authentication optional)"""
    conn = None
    try:
        # Use authenticated user ID if available, otherwise use guest ID from cookie
        use_database = current_user is not None
        if current_user:
            user_id = current_user.sub
            logger.info(
                "Creating chat session for authenticated user: %s...",
                hashlib.sha256(user_id.encode()).hexdigest()[:8],
            )
        else:
            user_id = get_or_create_guest_user_id(request, response)
            logger.info(
                "Creating chat session for guest user: %s...",
                hashlib.sha256(user_id.encode()).hexdigest()[:8],
            )

        conn = get_db_connection() if use_database else None

        if conn is not None:
            try:
                session_dict = create_chat_session_in_db(conn, session_data, user_id)
                logger.info("Successfully created chat session: %s", session_dict["id"])
                return ChatSession(**_annotate_session_with_mode(session_dict))
            except psycopg2.Error as e:
                logger.error("Database error creating chat session: %s", e)
                logger.error(
                    "Error details - User: %s, Data: %s",
                    user_id if "user_id" in locals() else "unknown",
                    session_data,
                )
                conn.rollback()
                logger.warning(
                    "Database unavailable for chat persistence; attempting Supabase REST fallback"
                )
            finally:
                conn.close()

        if use_database:
            supabase = get_supabase_chat_storage()
            if supabase is not None:
                try:
                    session_dict = await create_chat_session_in_supabase(
                        supabase,
                        session_data=session_data,
                        user_id=user_id,
                    )
                    logger.info(
                        "Created chat session via Supabase REST: %s",
                        session_dict.get("id"),
                    )
                    return ChatSession(**_annotate_session_with_mode(session_dict))
                except Exception as exc:
                    logger.error("Supabase error creating chat session: %s", exc)
                    logger.warning("Falling back to in-memory chat session storage")

        # No database connection available (local or fallback mode)
        from datetime import datetime
        import uuid

        now = datetime.utcnow()
        resolved_mode = _resolve_session_agent_mode(
            agent_type=session_data.agent_type,
            explicit_mode=session_data.agent_mode,
            metadata=session_data.metadata,
        )
        metadata_payload = _metadata_with_agent_mode(
            session_data.metadata,
            mode=resolved_mode,
        )
        mock_session = {
            "id": abs(hash(str(uuid.uuid4()))) % (10**8),
            "user_id": user_id,
            "agent_type": _enum_value(session_data.agent_type) or "primary",
            "agent_mode": resolved_mode,
            "title": session_data.title or "New Chat",
            "metadata": metadata_payload,
            "is_active": True,
            "created_at": now,
            "updated_at": now,
            "last_message_at": now,
            "message_count": 0,
        }
        _persist_local_session(user_id, mock_session)
        logger.info("Created mock chat session in local mode: %s", mock_session["id"])
        return ChatSession(**_annotate_session_with_mode(mock_session))
    except Exception as e:
        logger.error("Error creating chat session: %s", e)
        logger.error("Error type: %s", type(e).__name__)
        logger.error(
            "Error details - User: %s, Data: %s",
            user_id if "user_id" in locals() else "unknown",
            session_data,
        )
        import traceback

        logger.error("Traceback: %s", traceback.format_exc())
        raise HTTPException(status_code=500, detail="Error creating chat session")
    finally:
        if conn:
            conn.close()


@router.get(
    "/chat-sessions", response_model=ChatSessionListResponse, tags=["Chat Sessions"]
)
async def list_chat_sessions(
    request: Request,
    response: Response,
    agent_type: Optional[AgentType] = Query(None, description="Filter by agent type"),
    agent_mode: Optional[AgentMode] = Query(None, description="Filter by agent mode"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(
        100, ge=1, le=100, description="Number of sessions per page"
    ),
    search: Optional[str] = Query(None, description="Search in session titles"),
    current_user: Optional[TokenPayload] = Depends(get_optional_current_user),
):
    """List chat sessions (authentication optional)"""
    conn = None
    try:
        # Use authenticated user ID if available, otherwise use guest ID from cookie
        use_database = current_user is not None
        if current_user:
            user_id = current_user.sub
        else:
            user_id = get_or_create_guest_user_id(request, response)

        effective_is_active = True if is_active is None else is_active

        conn = get_db_connection() if use_database else None

        if conn is not None:
            try:
                # Always fetch active sessions only by default unless explicitly requested otherwise
                is_active = effective_is_active

                request = ChatSessionListRequest(
                    agent_type=agent_type,
                    agent_mode=agent_mode,
                    is_active=is_active,
                    page=page,
                    page_size=page_size,
                    search=search,
                )

                result = get_chat_sessions_for_user(conn, user_id, request)
                sessions = [
                    ChatSession(**_annotate_session_with_mode(session))
                    for session in result["sessions"]
                ]

                logger.debug(
                    "Returning %s sessions, agent_type=%s", len(sessions), agent_type
                )

                return ChatSessionListResponse(
                    sessions=sessions,
                    total_count=result["total_count"],
                    page=result["page"],
                    page_size=result["page_size"],
                    has_next=result["has_next"],
                    has_previous=result["has_previous"],
                )
            except psycopg2.Error as e:
                logger.error("Database error listing chat sessions: %s", e)
                if conn:
                    conn.rollback()
                logger.warning(
                    "Database unavailable for chat persistence; attempting Supabase REST fallback"
                )
            finally:
                if conn:
                    conn.close()
                    conn = None

        if use_database:
            supabase = get_supabase_chat_storage()
            if supabase is not None:
                try:
                    request_model = ChatSessionListRequest(
                        agent_type=agent_type,
                        agent_mode=agent_mode,
                        is_active=effective_is_active,
                        page=page,
                        page_size=page_size,
                        search=search,
                    )
                    result = await get_chat_sessions_for_user_in_supabase(
                        supabase,
                        user_id=user_id,
                        request=request_model,
                    )
                    sessions = [
                        ChatSession(**_annotate_session_with_mode(session))
                        for session in result["sessions"]
                    ]
                    return ChatSessionListResponse(
                        sessions=sessions,
                        total_count=result["total_count"],
                        page=result["page"],
                        page_size=result["page_size"],
                        has_next=result["has_next"],
                        has_previous=result["has_previous"],
                    )
                except Exception as exc:
                    logger.error("Supabase error listing chat sessions: %s", exc)
                    logger.warning(
                        "Falling back to in-memory chat sessions for user %s", user_id
                    )

        sessions = LOCAL_CHAT_SESSIONS.get(user_id, [])
        agent_filter = agent_type.value if agent_type else None
        mode_filter = agent_mode.value if agent_mode else None
        filtered = [
            session
            for session in sessions
            if (agent_filter is None or session["agent_type"] == agent_filter)
            and (
                mode_filter is None
                or str((session.get("metadata") or {}).get("agent_mode") or DEFAULT_AGENT_MODE)
                == mode_filter
            )
            and (
                effective_is_active is None
                or session["is_active"] == effective_is_active
            )
        ]

        filtered.sort(key=lambda s: s["last_message_at"], reverse=True)

        start = (page - 1) * page_size
        end = start + page_size
        window = filtered[start:end]

        return ChatSessionListResponse(
            sessions=[
                ChatSession(**_annotate_session_with_mode(session)) for session in window
            ],
            total_count=len(filtered),
            page=page,
            page_size=page_size,
            has_next=end < len(filtered),
            has_previous=start > 0,
        )
    except Exception as e:
        logger.error(f"Error listing chat sessions: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        if conn:
            conn.close()


@router.get(
    "/chat-sessions/{session_id}",
    response_model=ChatSessionWithMessages,
    tags=["Chat Sessions"],
)
async def get_chat_session(
    session_id: int,
    include_messages: bool = Query(True, description="Include messages in response"),
    current_user: TokenPayload = Depends(get_current_user),
):
    """Get a specific chat session with optional messages"""
    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            supabase = get_supabase_chat_storage()
            if supabase is None:
                raise HTTPException(
                    status_code=503, detail="Persistent storage unavailable"
                )

            session_dict = await get_chat_session_by_id_in_supabase(
                supabase,
                session_id=session_id,
                user_id=current_user.sub,
            )
            if not session_dict:
                raise HTTPException(status_code=404, detail="Chat session not found")

            session = ChatSession(**_annotate_session_with_mode(session_dict))

            if include_messages:
                message_request = ChatMessageListRequest(page=1, page_size=200)
                messages_result = await get_chat_messages_for_session_in_supabase(
                    supabase,
                    session_id=session_id,
                    user_id=current_user.sub,
                    request=message_request,
                )
                messages = [ChatMessage(**msg) for msg in messages_result["messages"]]
                return ChatSessionWithMessages(
                    **session.model_dump(), messages=messages
                )

            return ChatSessionWithMessages(**session.model_dump(), messages=[])

        session_dict = await get_chat_session_by_id(conn, session_id, current_user.sub)
        if not session_dict:
            raise HTTPException(status_code=404, detail="Chat session not found")

        session = ChatSession(**_annotate_session_with_mode(session_dict))

        if include_messages:
            message_request = ChatMessageListRequest(page=1, page_size=200)
            messages_result = get_chat_messages_for_session(
                conn, session_id, current_user.sub, message_request
            )
            messages = [ChatMessage(**msg) for msg in messages_result["messages"]]
            return ChatSessionWithMessages(**session.model_dump(), messages=messages)

        return ChatSessionWithMessages(**session.model_dump(), messages=[])

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting chat session {session_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        if conn:
            conn.close()


@router.put(
    "/chat-sessions/{session_id}", response_model=ChatSession, tags=["Chat Sessions"]
)
async def update_chat_session(
    session_id: int,
    updates: ChatSessionUpdate,
    request: Request,
    response: Response,
    current_user: Optional[TokenPayload] = Depends(get_optional_current_user),
):
    """Update a chat session"""
    try:
        if current_user:
            conn = get_db_connection()
            if conn is not None:
                try:
                    updated_session = update_chat_session_in_db(
                        conn, session_id, current_user.sub, updates
                    )
                finally:
                    conn.close()
                if not updated_session:
                    raise HTTPException(
                        status_code=404, detail="Chat session not found"
                    )
                return ChatSession(**_annotate_session_with_mode(updated_session))

            supabase = get_supabase_chat_storage()
            if supabase is not None:
                updated_session = await update_chat_session_in_supabase(
                    supabase,
                    session_id=session_id,
                    user_id=current_user.sub,
                    updates=updates,
                )
                if not updated_session:
                    raise HTTPException(
                        status_code=404, detail="Chat session not found"
                    )
                return ChatSession(**_annotate_session_with_mode(updated_session))

            # Fallback for authenticated users when persistent storage is unavailable
            user_id = current_user.sub
        else:
            user_id = get_or_create_guest_user_id(request, response)

        session = _get_local_session(user_id, session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Chat session not found")

        if updates.title is not None:
            session["title"] = updates.title
        if updates.is_active is not None:
            session["is_active"] = updates.is_active
        if updates.metadata is not None or updates.agent_mode is not None:
            existing_metadata = dict(session.get("metadata") or {})
            if updates.metadata is not None:
                existing_metadata.update(updates.metadata)
            resolved_mode = _resolve_session_agent_mode(
                agent_type=session.get("agent_type"),
                explicit_mode=updates.agent_mode,
                metadata=existing_metadata,
            )
            session["agent_mode"] = resolved_mode
            session["metadata"] = _metadata_with_agent_mode(
                existing_metadata,
                mode=resolved_mode,
            )

        session["updated_at"] = datetime.utcnow()
        _persist_local_session(user_id, session)
        return ChatSession(**_annotate_session_with_mode(session))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating chat session {session_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/chat-sessions/{session_id}", tags=["Chat Sessions"])
async def delete_chat_session(
    session_id: int,
    request: Request,
    response: Response,
    current_user: Optional[TokenPayload] = Depends(get_optional_current_user),
):
    """Soft delete a chat session (mark as inactive)"""
    try:
        if current_user:
            user_id = current_user.sub
            conn = get_db_connection()
            if conn is None:
                supabase = get_supabase_chat_storage()
                if supabase is not None:
                    updates = ChatSessionUpdate(is_active=False)
                    updated_session = await update_chat_session_in_supabase(
                        supabase,
                        session_id=session_id,
                        user_id=user_id,
                        updates=updates,
                    )
                else:
                    session = _get_local_session(user_id, session_id)
                    if session is None:
                        raise HTTPException(
                            status_code=404, detail="Chat session not found"
                        )
                    session["is_active"] = False
                    session["updated_at"] = datetime.utcnow()
                    _persist_local_session(user_id, session)
                    updated_session = session
            else:
                try:
                    updates = ChatSessionUpdate(is_active=False)
                    updated_session = update_chat_session_in_db(
                        conn, session_id, user_id, updates
                    )
                finally:
                    if conn:
                        conn.close()
        else:
            user_id = get_or_create_guest_user_id(request, response)
            session = _get_local_session(user_id, session_id)
            if session is None:
                raise HTTPException(status_code=404, detail="Chat session not found")
            session["is_active"] = False
            session["updated_at"] = datetime.utcnow()
            _persist_local_session(user_id, session)
            updated_session = session

        if not updated_session:
            raise HTTPException(status_code=404, detail="Chat session not found")

        return {
            "message": "Chat session deleted successfully",
            "session_id": session_id,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting chat session {session_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post(
    "/chat-sessions/{session_id}/messages",
    response_model=ChatMessage,
    tags=["Chat Messages"],
)
async def create_chat_message(
    session_id: int,
    message_data: ChatMessageCreate,
    request: Request,
    response: Response,
    current_user: Optional[TokenPayload] = Depends(get_optional_current_user),
):
    """Add a message to a chat session - stores FULL message content (authentication optional)"""
    conn = None
    try:
        # Use authenticated user ID if available, otherwise use guest ID from cookie
        if current_user:
            user_id = current_user.sub
        else:
            user_id = get_or_create_guest_user_id(request, response)

        # Secure logging without exposing content
        logger.debug(f"[MESSAGE SAVE] Saving message for session: {session_id}")
        logger.debug(f"  - Message Type: {message_data.message_type}")
        logger.debug(f"  - Agent Type: {message_data.agent_type}")
        logger.debug(
            f"  - Content Length: {len(message_data.content) if message_data.content else 0}"
        )

        if message_data.content and len(message_data.content) > 5000:
            logger.debug(
                f"  - Large message detected: {len(message_data.content)} chars"
            )

        # Ensure session_id matches
        message_data.session_id = session_id

        use_database = current_user is not None
        conn = get_db_connection() if use_database else None

        if conn is not None:
            try:
                logger.debug("[MESSAGE SAVE] Database connection established")

                message_dict = create_chat_message_in_db(conn, message_data, user_id)
                logger.debug(
                    "[MESSAGE SAVE] Message saved to database with ID: %s",
                    message_dict.get("id"),
                )

                if message_data.content and len(message_data.content) != len(
                    message_dict.get("content", "")
                ):
                    logger.error("[MESSAGE SAVE] Content length mismatch detected")
                else:
                    logger.debug("[MESSAGE SAVE] Content verification passed")

                return ChatMessage(**message_dict)
            except psycopg2.Error as e:
                logger.error("[MESSAGE SAVE] Database error: %s", e)
                conn.rollback()
                logger.warning(
                    "[MESSAGE SAVE] Database unavailable; attempting Supabase REST fallback"
                )
            finally:
                conn.close()

        if use_database:
            supabase = get_supabase_chat_storage()
            if supabase is not None:
                try:
                    message_dict = await create_chat_message_in_supabase(
                        supabase,
                        message_data=message_data,
                        user_id=user_id,
                    )
                    logger.debug(
                        "[MESSAGE SAVE] Message saved via Supabase REST with ID: %s",
                        message_dict.get("id"),
                    )
                    return ChatMessage(**message_dict)
                except HTTPException:
                    raise
                except Exception as exc:
                    logger.error("[MESSAGE SAVE] Supabase error: %s", exc)
                    logger.warning(
                        "[MESSAGE SAVE] Falling back to in-memory store for session %s",
                        session_id,
                    )

        now = datetime.utcnow()
        message_dict = {
            "id": next(LOCAL_MESSAGE_ID_COUNTER),
            "session_id": session_id,
            "content": message_data.content,
            "message_type": _enum_value(message_data.message_type),
            "agent_type": _enum_value(message_data.agent_type),
            "metadata": message_data.metadata or {},
            "created_at": now,
        }
        stored = _store_local_message(user_id, session_id, message_dict)
        return ChatMessage(**stored)
    except HTTPException as e:
        logger.error("[MESSAGE SAVE] HTTP Exception: %s", e.detail)
        raise
    except Exception as e:
        logger.error("[MESSAGE SAVE] Unexpected error: %s", e)
        logger.error("[MESSAGE SAVE] Error type: %s", type(e).__name__)
        import traceback

        logger.error("[MESSAGE SAVE] Traceback: %s", traceback.format_exc())
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        if conn:
            conn.close()
            logger.debug("[MESSAGE SAVE] Database connection closed")


@router.patch(
    "/chat-sessions/{session_id}/messages/{message_id}/append",
    response_model=ChatMessage,
    tags=["Chat Messages"],
)
async def append_chat_message(
    session_id: int,
    message_id: int,
    append_data: "ChatMessageAppendRequest",
    request: Request,
    response: Response,
    current_user: Optional[TokenPayload] = Depends(get_optional_current_user),
):
    """Append text to an existing chat message (authentication optional)"""
    conn = None
    try:
        use_database = current_user is not None
        if current_user:
            user_id = current_user.sub
        else:
            user_id = get_or_create_guest_user_id(request, response)

        if not append_data.delta or not append_data.delta.strip():
            raise HTTPException(status_code=400, detail="Delta cannot be empty")

        conn = get_db_connection() if use_database else None

        if conn is None:
            if use_database:
                supabase = get_supabase_chat_storage()
                if supabase is not None:
                    message = await append_chat_message_content_in_supabase(
                        supabase,
                        session_id=session_id,
                        message_id=message_id,
                        user_id=user_id,
                        delta=append_data.delta,
                    )
                    return ChatMessage(**message)

            # Local storage fallback - verify session ownership first
            session = _get_local_session(user_id, session_id)
            if session is None:
                raise HTTPException(status_code=404, detail="Session not found")

            messages = LOCAL_CHAT_MESSAGES.get(session_id, [])
            target = next((m for m in messages if m["id"] == message_id), None)
            if target is None:
                raise HTTPException(status_code=404, detail="Message not found")

            target["content"] = f"{target.get('content', '')}{append_data.delta}"
            now = datetime.utcnow()
            session["last_message_at"] = now
            session["updated_at"] = now
            _persist_local_session(user_id, session)

            return ChatMessage(**target)

        message = append_chat_message_content_in_db(
            conn, session_id, message_id, user_id, append_data.delta
        )
        return ChatMessage(**message)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[MESSAGE APPEND] Error appending to message {message_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        if conn:
            conn.close()


@router.put(
    "/chat-sessions/{session_id}/messages/{message_id}",
    response_model=ChatMessage,
    tags=["Chat Messages"],
)
async def update_chat_message(
    session_id: int,
    message_id: int,
    update_data: "ChatMessageUpdateRequest",
    request: Request,
    response: Response,
    current_user: Optional[TokenPayload] = Depends(get_optional_current_user),
):
    """Update the content of an existing chat message (authentication optional)

    This endpoint allows editing a message's content after it has been created.
    Used by the frontend edit feature to persist changes.
    """
    conn = None
    try:
        use_database = current_user is not None
        if current_user:
            user_id = current_user.sub
        else:
            user_id = get_or_create_guest_user_id(request, response)

        content = update_data.content
        metadata = update_data.metadata

        if content is None and metadata is None:
            raise HTTPException(status_code=400, detail="No updates provided")

        if content is not None and not content.strip():
            raise HTTPException(status_code=400, detail="Content cannot be empty")

        logger.debug(
            f"[MESSAGE UPDATE] Updating message {message_id} in session {session_id}"
        )
        if content is not None:
            logger.debug(f"[MESSAGE UPDATE] New content length: {len(content)}")

        conn = get_db_connection() if use_database else None

        if conn is None:
            if use_database:
                supabase = get_supabase_chat_storage()
                if supabase is not None:
                    message = await update_chat_message_in_supabase(
                        supabase,
                        session_id=session_id,
                        message_id=message_id,
                        user_id=user_id,
                        content=content,
                        metadata=metadata,
                    )
                    logger.info(
                        f"[MESSAGE UPDATE] Updated message {message_id} via Supabase REST"
                    )
                    return ChatMessage(**message)

            # Local storage fallback - verify session ownership first
            session = _get_local_session(user_id, session_id)
            if session is None:
                raise HTTPException(status_code=404, detail="Session not found")

            messages = LOCAL_CHAT_MESSAGES.get(session_id, [])
            target = next((m for m in messages if m["id"] == message_id), None)
            if target is None:
                raise HTTPException(status_code=404, detail="Message not found")

            if content is not None:
                target["content"] = content
            if metadata is not None:
                existing_meta = target.get("metadata") or {}
                if not isinstance(existing_meta, dict):
                    existing_meta = {}
                target["metadata"] = {**existing_meta, **metadata}

            now = datetime.utcnow()
            session["updated_at"] = now
            _persist_local_session(user_id, session)

            logger.info(
                f"[MESSAGE UPDATE] Updated message {message_id} in local storage"
            )
            return ChatMessage(**target)

        message = update_chat_message_in_db(
            conn, session_id, message_id, user_id, content, metadata
        )
        logger.info(f"[MESSAGE UPDATE] Updated message {message_id} in database")
        return ChatMessage(**message)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[MESSAGE UPDATE] Error updating message {message_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        if conn:
            conn.close()


@router.get(
    "/chat-sessions/{session_id}/messages",
    response_model=ChatMessageListResponse,
    tags=["Chat Messages"],
)
async def list_chat_messages(
    session_id: int,
    request: Request,
    response: Response,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(
        200, ge=1, le=200, description="Number of messages per page"
    ),
    message_type: Optional[MessageType] = Query(
        None, description="Filter by message type"
    ),
    current_user: Optional[TokenPayload] = Depends(get_optional_current_user),
):
    """List messages for a specific chat session (authentication optional)"""
    conn = None
    try:
        # Use authenticated user ID if available, otherwise use guest ID from cookie
        use_database = current_user is not None
        if current_user:
            user_id = current_user.sub
        else:
            user_id = get_or_create_guest_user_id(request, response)

        conn = get_db_connection() if use_database else None

        if conn is None:
            if use_database:
                supabase = get_supabase_chat_storage()
                if supabase is not None:
                    request_model = ChatMessageListRequest(
                        page=page,
                        page_size=page_size,
                        message_type=message_type,
                    )
                    result = await get_chat_messages_for_session_in_supabase(
                        supabase,
                        session_id=session_id,
                        user_id=user_id,
                        request=request_model,
                    )

                    messages = [ChatMessage(**msg) for msg in result["messages"]]
                    return ChatMessageListResponse(
                        messages=messages,
                        total_count=result["total_count"],
                        page=result["page"],
                        page_size=result["page_size"],
                        has_next=result["has_next"],
                        has_previous=result["has_previous"],
                    )

            session = _get_local_session(user_id, session_id)
            if session is None:
                raise HTTPException(status_code=404, detail="Chat session not found")

            stored_messages = LOCAL_CHAT_MESSAGES.get(session_id, [])
            if message_type is not None:
                stored_messages = [
                    m
                    for m in stored_messages
                    if m["message_type"] == message_type.value
                ]

            total_count = len(stored_messages)
            start = (page - 1) * page_size
            end = start + page_size
            page_rows = stored_messages[start:end]
            chat_messages = [ChatMessage(**msg) for msg in page_rows]

            return ChatMessageListResponse(
                messages=chat_messages,
                total_count=total_count,
                page=page,
                page_size=page_size,
                has_next=end < total_count,
                has_previous=page > 1,
            )

        request = ChatMessageListRequest(
            page=page,
            page_size=page_size,  # Increased default to ensure all messages are loaded
            message_type=message_type,
        )

        result = get_chat_messages_for_session(conn, session_id, user_id, request)
        messages = [ChatMessage(**msg) for msg in result["messages"]]

        for msg in messages:
            if msg.content and len(msg.content) > 100 and msg.content.endswith("..."):
                logger.warning(f"Message {msg.id} may be truncated in retrieval")

        logger.info(
            f"Retrieved {len(messages)} messages for session {session_id} for user {user_id}"
        )

        return ChatMessageListResponse(
            messages=messages,
            total_count=result["total_count"],
            page=result["page"],
            page_size=result["page_size"],
            has_next=result["has_next"],
            has_previous=result["has_previous"],
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing chat messages: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        if conn:
            conn.close()


@router.get(
    "/chat-sessions/stats/user", response_model=UserChatStats, tags=["Chat Statistics"]
)
async def get_user_chat_stats(current_user: TokenPayload = Depends(get_current_user)):
    """Get chat statistics for the current user"""
    try:
        # @with_db_connection removed - using Supabase
        def get_user_stats(conn, user_id: str) -> Dict[str, Any]:
            with conn.cursor() as cur:
                # Get session stats
                cur.execute(
                    """
                    SELECT 
                        COUNT(*) as total_sessions,
                        COUNT(*) FILTER (WHERE is_active = TRUE) as active_sessions,
                        agent_type,
                        MAX(created_at) as most_recent_session,
                        MIN(created_at) as oldest_session
                    FROM chat_sessions 
                    WHERE user_id = %s
                    GROUP BY agent_type
                """,
                    (user_id,),
                )

                agent_stats = cur.fetchall()

                # Get total message count
                cur.execute(
                    """
                    SELECT COUNT(*) as total_messages
                    FROM chat_messages cm
                    JOIN chat_sessions cs ON cm.session_id = cs.id
                    WHERE cs.user_id = %s
                """,
                    (user_id,),
                )

                total_messages = cur.fetchone()["total_messages"]

                # Calculate aggregated stats
                total_sessions = sum(stat["total_sessions"] for stat in agent_stats)
                active_sessions = sum(stat["active_sessions"] for stat in agent_stats)
                sessions_by_agent_type = {
                    stat["agent_type"]: stat["total_sessions"] for stat in agent_stats
                }
                most_recent = max(
                    (stat["most_recent_session"] for stat in agent_stats), default=None
                )
                oldest = min(
                    (stat["oldest_session"] for stat in agent_stats), default=None
                )

                return {
                    "user_id": user_id,
                    "total_sessions": total_sessions,
                    "active_sessions": active_sessions,
                    "total_messages": total_messages,
                    "sessions_by_agent_type": sessions_by_agent_type,
                    "most_recent_session": most_recent,
                    "oldest_session": oldest,
                }

        conn = get_db_connection()
        if conn is not None:
            try:
                stats = get_user_stats(conn, current_user.sub)
                return UserChatStats(**stats)
            finally:
                conn.close()

        # Local fallback when persistent storage is unavailable.
        user_id = current_user.sub
        sessions = LOCAL_CHAT_SESSIONS.get(user_id, [])
        session_ids = {session["id"] for session in sessions}
        total_messages = sum(
            len(LOCAL_CHAT_MESSAGES.get(session_id, [])) for session_id in session_ids
        )
        sessions_by_agent_type: Dict[str, int] = defaultdict(int)
        most_recent = None
        oldest = None
        active_sessions = 0

        for session in sessions:
            agent_type = str(session.get("agent_type") or "primary")
            sessions_by_agent_type[agent_type] += 1
            if session.get("is_active") is True:
                active_sessions += 1
            created_at = session.get("created_at")
            if most_recent is None or (created_at and created_at > most_recent):
                most_recent = created_at
            if oldest is None or (created_at and created_at < oldest):
                oldest = created_at

        return UserChatStats(
            user_id=user_id,
            total_sessions=len(sessions),
            active_sessions=active_sessions,
            total_messages=total_messages,
            sessions_by_agent_type=dict(sessions_by_agent_type),
            most_recent_session=most_recent,
            oldest_session=oldest,
        )

    except Exception as e:
        logger.error(f"Error getting user chat stats: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
