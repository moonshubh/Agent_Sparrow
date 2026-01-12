"""Message feedback endpoints for thumbs up/down rating.

This module handles user feedback on AI-generated messages. When feedback is
submitted, it's stored in the sparrow_feedback table AND propagated to any
memories that were used to generate the response (for feedback attribution).
"""
from __future__ import annotations

import logging
from typing import List, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.db.supabase.client import get_supabase_client

logger = logging.getLogger(__name__)

from app.core.settings import settings

try:
    from app.api.v1.endpoints.auth import get_current_user_id
except ImportError:
    # Only allow fallback in development mode - fail loudly in production
    if settings.is_production_mode():
        raise ImportError(
            "Authentication module required in production. "
            "Cannot import get_current_user_id from app.api.v1.endpoints.auth"
        )

    async def get_current_user_id() -> str:
        """Development-only fallback for auth."""
        return getattr(settings, "development_user_id", "dev-user-12345")


router = APIRouter(prefix="/feedback", tags=["Message Feedback"])


class MessageFeedbackRequest(BaseModel):
    """Request payload for message feedback."""
    message_id: str = Field(..., min_length=1)
    session_id: Optional[str] = Field(default=None)
    feedback_type: Literal["positive", "negative"] = Field(...)
    category: str = Field(..., min_length=1, max_length=100)
    # Optional: Memory IDs that were used to generate this response
    # If provided, feedback will be propagated to these memories
    used_memory_ids: Optional[List[str]] = Field(
        default=None,
        description="Memory IDs used to generate this response for feedback attribution"
    )


class MessageFeedbackResponse(BaseModel):
    """Response for message feedback submission."""
    success: bool
    message: str = "Feedback received"
    memories_updated: int = 0


async def _propagate_feedback_to_memories(
    supabase,
    memory_ids: List[str],
    user_id: Optional[str],
    feedback_type: str,
    session_id: Optional[str],
    message_id: str,
) -> int:
    """
    Propagate message feedback to the memories that were used to generate the response.

    Updates memory confidence scores based on feedback:
    - positive feedback: increases confidence
    - negative feedback: decreases confidence

    Returns the number of memories updated.
    """
    if not memory_ids:
        return 0

    updated_count = 0
    # Map message feedback types to memory feedback types
    memory_feedback_type = "thumbs_up" if feedback_type == "positive" else "thumbs_down"

    for memory_id in memory_ids:
        try:
            # Validate UUID format
            try:
                validated_id = UUID(memory_id)
            except ValueError:
                logger.warning(f"Invalid memory ID format: {memory_id}")
                continue

            # Call the record_memory_feedback RPC to update confidence
            # This handles the confidence score update atomically
            result = await supabase._exec(
                lambda: supabase.rpc(
                    "record_memory_feedback",
                    {
                        "p_memory_id": str(validated_id),
                        "p_user_id": user_id,
                        "p_feedback_type": memory_feedback_type,
                        "p_session_id": session_id,
                        "p_ticket_id": None,
                        "p_notes": f"Propagated from message feedback on message {message_id}",
                    },
                ).execute()
            )

            if result.data:
                updated_count += 1
                logger.debug(
                    "Propagated feedback to memory %s: type=%s, new_confidence=%s",
                    memory_id,
                    memory_feedback_type,
                    result.data.get("new_confidence") if isinstance(result.data, dict) else None,
                )
        except Exception as exc:
            # Log but don't fail - memory feedback propagation is best-effort
            logger.warning(
                "Failed to propagate feedback to memory %s: %s",
                memory_id, str(exc)
            )
            continue

    return updated_count


async def _get_memory_ids_from_message(
    supabase,
    message_id: str,
    session_id: Optional[str],
    user_id: str,
) -> List[str]:
    """
    Retrieve memory IDs from message metadata if available.

    Looks up the chat message and extracts used_memory_ids from its metadata.
    """
    try:
        # Try to parse message_id as integer (chat_messages uses serial ID)
        try:
            msg_id_int = int(message_id)
        except ValueError:
            # Message ID might be a string/UUID format
            return []

        # Query message metadata
        query = supabase.table("chat_messages").select("metadata")

        if session_id:
            try:
                session_id_int = int(session_id)
                query = query.eq("session_id", session_id_int)
            except ValueError:
                pass

        query = query.eq("id", msg_id_int)
        result = await supabase._exec(lambda: query.maybe_single().execute())

        if result.data and isinstance(result.data.get("metadata"), dict):
            memory_ids = result.data["metadata"].get("used_memory_ids", [])
            if isinstance(memory_ids, list):
                return [str(mid) for mid in memory_ids if mid]

    except Exception as exc:
        logger.debug("Could not retrieve memory IDs from message: %s", exc)

    return []


@router.post(
    "/message",
    response_model=MessageFeedbackResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_message_feedback(
    payload: MessageFeedbackRequest,
    user_id: str = Depends(get_current_user_id),
) -> MessageFeedbackResponse:
    """
    Submit feedback (thumbs up/down) for a specific message.

    The feedback is stored in the sparrow_feedback table with:
    - feedback_text: The category label
    - kind: 'message_rating'
    - metadata: Contains message_id, session_id, feedback_type

    If used_memory_ids are provided (or found in message metadata), feedback
    is also propagated to those memories to update their confidence scores.
    """
    try:
        supabase = get_supabase_client()

        memory_user_id: Optional[str]
        try:
            memory_user_id = str(UUID(user_id))
        except Exception:
            memory_user_id = None

        # Store the message feedback
        result = await supabase._exec(
            lambda: supabase.table("sparrow_feedback")
            .insert(
                {
                    "user_id": user_id,
                    "kind": "message_rating",
                    "feedback_text": payload.category,
                    "metadata": {
                        "message_id": payload.message_id,
                        "session_id": payload.session_id,
                        "feedback_type": payload.feedback_type,
                        "category": payload.category,
                        "used_memory_ids": payload.used_memory_ids or [],
                    },
                }
            )
            .execute()
        )

        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save feedback"
            )

        # Get memory IDs to propagate feedback to
        memory_ids = payload.used_memory_ids or []

        # If no memory IDs provided, try to get them from message metadata
        if not memory_ids:
            memory_ids = await _get_memory_ids_from_message(
                supabase, payload.message_id, payload.session_id, user_id
            )

        # Propagate feedback to memories (best-effort)
        memories_updated = 0
        if memory_ids:
            memories_updated = await _propagate_feedback_to_memories(
                supabase,
                memory_ids,
                memory_user_id,
                payload.feedback_type,
                payload.session_id,
                payload.message_id,
            )
            logger.info(
                "Propagated message feedback to %d memories: user=%s, message=%s",
                memories_updated, user_id, payload.message_id
            )

        logger.info(
            "Message feedback submitted: user=%s, message=%s, type=%s, category=%s, memories_updated=%d",
            user_id, payload.message_id, payload.feedback_type, payload.category, memories_updated
        )

        return MessageFeedbackResponse(
            success=True,
            memories_updated=memories_updated,
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to submit message feedback: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to submit feedback"
        ) from exc
