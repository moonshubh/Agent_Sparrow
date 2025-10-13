from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.services.global_knowledge import (
    Attachment,
    CorrectionSubmission,
    FeedbackSubmission,
    persist_correction,
    persist_feedback,
)

logger = logging.getLogger(__name__)

try:  # pragma: no cover - optional auth dependency
    from app.api.v1.endpoints.auth import get_current_user_id  # type: ignore
except Exception:  # pragma: no cover - fallback for tests or dev mode
    async def get_current_user_id() -> str:
        from app.core.settings import settings
        return getattr(settings, "development_user_id", "dev-user-12345")


router = APIRouter(prefix="/global-knowledge", tags=["Global Knowledge"])


class FeedbackRequest(BaseModel):
    feedback_text: str = Field(..., min_length=1, max_length=4000)
    selected_text: Optional[str] = Field(default=None, max_length=2000)
    attachments: List[Attachment] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CorrectionRequest(BaseModel):
    incorrect_text: str = Field(..., min_length=1, max_length=4000)
    corrected_text: str = Field(..., min_length=1, max_length=4000)
    explanation: Optional[str] = Field(default=None, max_length=4000)
    attachments: List[Attachment] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SubmissionResponse(BaseModel):
    success: bool
    submission_id: Optional[int] = None
    status: Optional[str] = None
    store_written: bool = False


def _extract_submission_details(row: Optional[Dict[str, Any]]) -> tuple[Optional[int], Optional[str]]:
    if not row:
        return None, None
    submission_id = row.get("id")
    try:
        submission_id = int(submission_id) if submission_id is not None else None
    except (ValueError, TypeError):  # pragma: no cover - defensive
        submission_id = None
    status_value = row.get("status")
    if isinstance(status_value, str):
        status_value = status_value.strip() or None
    else:
        status_value = None
    return submission_id, status_value


@router.post(
    "/feedback",
    response_model=SubmissionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_feedback(
    payload: FeedbackRequest,
    user_id: str = Depends(get_current_user_id),
) -> SubmissionResponse:
    """Persist a feedback submission originating from the /feedback slash command."""

    try:
        submission = FeedbackSubmission(
            user_id=user_id,
            feedback_text=payload.feedback_text,
            selected_text=payload.selected_text,
            attachments=payload.attachments,
            metadata=payload.metadata,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    try:
        result = await persist_feedback(submission)
    except Exception as exc:
        logger.error("Failed to persist feedback submission for user %s: %s", user_id, exc, exc_info=True)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to persist feedback submission") from exc

    submission_id, status_value = _extract_submission_details(result.supabase_row)
    if submission_id is None:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Feedback submission was not saved")

    return SubmissionResponse(
        success=True,
        submission_id=submission_id,
        status=status_value or "received",
        store_written=bool(result.store_written),
    )


@router.post(
    "/corrections",
    response_model=SubmissionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_correction(
    payload: CorrectionRequest,
    user_id: str = Depends(get_current_user_id),
) -> SubmissionResponse:
    """Persist a correction submission originating from the /correct slash command."""

    try:
        submission = CorrectionSubmission(
            user_id=user_id,
            incorrect_text=payload.incorrect_text,
            corrected_text=payload.corrected_text,
            explanation=payload.explanation,
            attachments=payload.attachments,
            metadata=payload.metadata,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    try:
        result = await persist_correction(submission)
    except Exception as exc:
        logger.error("Failed to persist correction submission for user %s: %s", user_id, exc, exc_info=True)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to persist correction submission") from exc

    submission_id, status_value = _extract_submission_details(result.supabase_row)
    if submission_id is None:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Correction submission was not saved")

    return SubmissionResponse(
        success=True,
        submission_id=submission_id,
        status=status_value or "received",
        store_written=bool(result.store_written),
    )
