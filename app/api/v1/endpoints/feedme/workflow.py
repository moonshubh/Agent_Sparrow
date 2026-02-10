"""
FeedMe workflow endpoints for KB-ready actions, AI note regeneration, and settings.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.core.security import TokenPayload
from app.core.settings import settings
from app.feedme.schemas import OSCategory

from .auth import require_feedme_admin
from .helpers import (
    get_feedme_settings,
    get_feedme_supabase_client,
    record_feedme_action_audit,
    update_feedme_settings,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["FeedMe"])


class MarkReadyRequest(BaseModel):
    confirm_move: bool = False
    reason: Optional[str] = None


class MarkReadyResponse(BaseModel):
    conversation_id: int
    kb_ready_folder_id: int
    folder_id: int
    os_category: OSCategory
    approval_status: str
    message: str


class RegenerateAiNoteResponse(BaseModel):
    conversation_id: int
    generation_status: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    message: str


class FeedMeSettingsResponse(BaseModel):
    tenant_id: str
    kb_ready_folder_id: Optional[int] = None
    sla_warning_minutes: int
    sla_breach_minutes: int
    updated_at: Optional[str] = None


class FeedMeSettingsUpdateRequest(BaseModel):
    kb_ready_folder_id: Optional[int] = None
    sla_warning_minutes: Optional[int] = Field(default=None, gt=0)
    sla_breach_minutes: Optional[int] = Field(default=None, gt=0)


@router.post(
    "/conversations/{conversation_id}/mark-ready",
    response_model=MarkReadyResponse,
)
async def mark_conversation_ready_for_kb(
    conversation_id: int,
    request: MarkReadyRequest,
    current_user: TokenPayload = Depends(require_feedme_admin),
):
    """Atomically mark a conversation as KB-ready and move to configured KB folder."""
    if not settings.feedme_enabled:
        raise HTTPException(
            status_code=503, detail="FeedMe service is currently disabled"
        )

    client = get_feedme_supabase_client()
    if client is None:
        raise HTTPException(
            status_code=503, detail="FeedMe service is temporarily unavailable."
        )

    conversation_response = await client._exec(
        lambda: client.client.table("feedme_conversations")
        .select("id,folder_id,os_category,approval_status,metadata")
        .eq("id", conversation_id)
        .limit(1)
        .execute()
    )
    if not conversation_response.data:
        raise HTTPException(status_code=404, detail="Conversation not found")
    conversation = conversation_response.data[0]
    os_value = str(conversation.get("os_category") or "uncategorized")
    if os_value not in {item.value for item in OSCategory}:
        os_value = OSCategory.UNCATEGORIZED.value
    if os_value == OSCategory.UNCATEGORIZED.value:
        raise HTTPException(
            status_code=400,
            detail="OS category is required before marking ready for knowledge base",
        )

    settings_row = await get_feedme_settings()
    kb_ready_folder_id = settings_row.get("kb_ready_folder_id")

    current_folder_id = conversation.get("folder_id")
    if not isinstance(kb_ready_folder_id, int):
        fallback_folder_id = (
            current_folder_id
            if isinstance(current_folder_id, int) and current_folder_id > 0
            else None
        )
        if fallback_folder_id is None:
            raise HTTPException(
                status_code=409,
                detail=(
                    "KB folder is not configured. Update FeedMe settings first, "
                    "or assign this conversation to a folder before marking ready."
                ),
            )

        folder_check = await client._exec(
            lambda: client.client.table("feedme_folders")
            .select("id")
            .eq("id", fallback_folder_id)
            .limit(1)
            .execute()
        )
        if not folder_check.data:
            raise HTTPException(
                status_code=409,
                detail=(
                    "KB folder is not configured and the conversation folder could "
                    "not be resolved. Update FeedMe settings first."
                ),
            )

        updated_settings = await update_feedme_settings(
            {"kb_ready_folder_id": fallback_folder_id},
            updated_by=current_user.sub,
        )
        await record_feedme_action_audit(
            action="auto_configure_kb_folder",
            actor_id=current_user.sub,
            folder_id=fallback_folder_id,
            reason="Auto-configured during mark-ready",
            before_state=settings_row,
            after_state=updated_settings,
        )
        settings_row = updated_settings
        kb_ready_folder_id = fallback_folder_id

    if (
        current_folder_id is not None
        and current_folder_id != kb_ready_folder_id
        and not request.confirm_move
    ):
        raise HTTPException(
            status_code=409,
            detail="Conversation is in a non-KB folder. Re-submit with confirm_move=true.",
        )

    metadata = conversation.get("metadata") if isinstance(conversation, dict) else {}
    metadata = metadata if isinstance(metadata, dict) else {}
    metadata["review_status"] = "ready_for_kb"
    metadata["kb_ready_at"] = datetime.now(timezone.utc).isoformat()

    update_payload = {
        "folder_id": kb_ready_folder_id,
        "approval_status": "approved",
        "metadata": metadata,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    update_response = await client._exec(
        lambda: client.client.table("feedme_conversations")
        .update(update_payload)
        .eq("id", conversation_id)
        .execute()
    )
    if not update_response.data:
        raise HTTPException(status_code=500, detail="Failed to mark conversation ready")

    await record_feedme_action_audit(
        action="mark_ready_for_kb",
        actor_id=current_user.sub,
        conversation_id=conversation_id,
        folder_id=kb_ready_folder_id,
        reason=request.reason,
        before_state=conversation,
        after_state=update_response.data[0],
    )

    return MarkReadyResponse(
        conversation_id=conversation_id,
        kb_ready_folder_id=kb_ready_folder_id,
        folder_id=kb_ready_folder_id,
        os_category=OSCategory(os_value),
        approval_status="approved",
        message="Conversation marked ready and moved to KB folder",
    )


@router.post(
    "/conversations/{conversation_id}/ai-note/regenerate",
    response_model=RegenerateAiNoteResponse,
)
async def regenerate_ai_note(
    conversation_id: int,
    current_user: TokenPayload = Depends(require_feedme_admin),
):
    """Regenerate AI note and return current note metadata snapshot."""
    if not settings.feedme_enabled:
        raise HTTPException(
            status_code=503, detail="FeedMe service is currently disabled"
        )

    client = get_feedme_supabase_client()
    if client is None:
        raise HTTPException(
            status_code=503, detail="FeedMe service is temporarily unavailable."
        )

    existing = await client.get_conversation_by_id(conversation_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Conversation not found")

    generation_status = "failed"
    try:
        from app.feedme.tasks import generate_ai_tags

        # Run sync Celery task body in a worker thread to avoid nested-event-loop
        # errors when task internals use asyncio helpers.
        result = await run_in_threadpool(generate_ai_tags.run, conversation_id)
        if isinstance(result, dict) and result.get("success"):
            generation_status = "completed"
        else:
            generation_status = "failed"
    except Exception as e:
        logger.error("AI note regeneration failed for conversation %s: %s", conversation_id, e)
        generation_status = "failed"

    refreshed = await client.get_conversation_by_id(conversation_id)
    if not refreshed:
        raise HTTPException(status_code=500, detail="Failed to reload conversation")
    metadata = refreshed.get("metadata") if isinstance(refreshed, dict) else {}
    metadata = metadata if isinstance(metadata, dict) else {}
    if generation_status == "completed":
        metadata["ai_note_updated_at"] = datetime.now(timezone.utc).isoformat()
        await client.update_conversation(
            conversation_id=conversation_id,
            updates={"metadata": metadata},
        )

    await record_feedme_action_audit(
        action="regenerate_ai_note",
        actor_id=current_user.sub,
        conversation_id=conversation_id,
        before_state=existing,
        after_state={"metadata": metadata, "generation_status": generation_status},
    )

    message = (
        "AI note regenerated successfully"
        if generation_status == "completed"
        else "AI note regeneration failed"
    )
    return RegenerateAiNoteResponse(
        conversation_id=conversation_id,
        generation_status=generation_status,
        metadata=metadata,
        message=message,
    )


@router.get("/settings", response_model=FeedMeSettingsResponse)
async def get_feedme_settings_endpoint(
    current_user: TokenPayload = Depends(require_feedme_admin),
):
    """Get FeedMe workflow settings."""
    row = await get_feedme_settings()
    return FeedMeSettingsResponse(
        tenant_id=str(row.get("tenant_id") or "default"),
        kb_ready_folder_id=row.get("kb_ready_folder_id"),
        sla_warning_minutes=int(row.get("sla_warning_minutes") or 60),
        sla_breach_minutes=int(row.get("sla_breach_minutes") or 180),
        updated_at=row.get("updated_at"),
    )


@router.put("/settings", response_model=FeedMeSettingsResponse)
async def update_feedme_settings_endpoint(
    request: FeedMeSettingsUpdateRequest,
    current_user: TokenPayload = Depends(require_feedme_admin),
):
    """Update FeedMe workflow settings (KB folder + SLA thresholds)."""
    updates = request.model_dump(exclude_unset=True)
    if not updates:
        row = await get_feedme_settings()
        return FeedMeSettingsResponse(
            tenant_id=str(row.get("tenant_id") or "default"),
            kb_ready_folder_id=row.get("kb_ready_folder_id"),
            sla_warning_minutes=int(row.get("sla_warning_minutes") or 60),
            sla_breach_minutes=int(row.get("sla_breach_minutes") or 180),
            updated_at=row.get("updated_at"),
        )

    warning = updates.get("sla_warning_minutes")
    breach = updates.get("sla_breach_minutes")
    if warning is not None and breach is not None and breach <= warning:
        raise HTTPException(
            status_code=400,
            detail="sla_breach_minutes must be greater than sla_warning_minutes",
        )

    client = get_feedme_supabase_client()
    if client is None:
        raise HTTPException(
            status_code=503, detail="FeedMe service is temporarily unavailable."
        )
    if "kb_ready_folder_id" in updates and updates["kb_ready_folder_id"] is not None:
        folder_check = await client._exec(
            lambda: client.client.table("feedme_folders")
            .select("id")
            .eq("id", updates["kb_ready_folder_id"])
            .limit(1)
            .execute()
        )
        if not folder_check.data:
            raise HTTPException(status_code=404, detail="KB folder not found")

    before_row = await get_feedme_settings()
    row = await update_feedme_settings(
        updates,
        updated_by=current_user.sub,
    )
    await record_feedme_action_audit(
        action="update_feedme_settings",
        actor_id=current_user.sub,
        before_state=before_row,
        after_state=row,
    )

    return FeedMeSettingsResponse(
        tenant_id=str(row.get("tenant_id") or "default"),
        kb_ready_folder_id=row.get("kb_ready_folder_id"),
        sla_warning_minutes=int(row.get("sla_warning_minutes") or 60),
        sla_breach_minutes=int(row.get("sla_breach_minutes") or 180),
        updated_at=row.get("updated_at"),
    )
