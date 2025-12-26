"""Message feedback endpoints for thumbs up/down rating."""
from __future__ import annotations

import logging
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.db.supabase.client import get_supabase_client

logger = logging.getLogger(__name__)

try:
    from app.api.v1.endpoints.auth import get_current_user_id
except Exception:
    async def get_current_user_id() -> str:
        from app.core.settings import settings
        return getattr(settings, "development_user_id", "dev-user-12345")


router = APIRouter(prefix="/feedback", tags=["Message Feedback"])


class MessageFeedbackRequest(BaseModel):
    """Request payload for message feedback."""
    message_id: str = Field(..., min_length=1)
    session_id: Optional[str] = Field(default=None)
    feedback_type: Literal["positive", "negative"] = Field(...)
    category: str = Field(..., min_length=1, max_length=100)


class MessageFeedbackResponse(BaseModel):
    """Response for message feedback submission."""
    success: bool
    message: str = "Feedback received"


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
    """
    try:
        supabase = get_supabase_client()

        result = supabase.table("sparrow_feedback").insert({
            "user_id": user_id,
            "kind": "message_rating",
            "feedback_text": payload.category,
            "metadata": {
                "message_id": payload.message_id,
                "session_id": payload.session_id,
                "feedback_type": payload.feedback_type,
                "category": payload.category,
            },
        }).execute()

        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to save feedback"
            )

        logger.info(
            "Message feedback submitted: user=%s, message=%s, type=%s, category=%s",
            user_id, payload.message_id, payload.feedback_type, payload.category
        )

        return MessageFeedbackResponse(success=True)

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to submit message feedback: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to submit feedback"
        ) from exc
