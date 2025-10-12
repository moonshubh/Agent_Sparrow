from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.transport.sse import format_sse_data
from app.core.settings import settings
from app.db import embedding_utils
from app.db.embedding_config import assert_dim
from app.db.supabase_client import SupabaseClient
from app.services.global_knowledge.observability import (
    compute_summary,
    recent_events,
    subscribe_events,
    attach_submission_id,
    publish_stage,
    start_trace,
)
from app.services.global_knowledge.store import get_async_store, upsert_enhanced_entry
from app.services.global_knowledge.models import EnhancedPayload

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/global-knowledge", tags=["Global Knowledge"])


class QueueItem(BaseModel):
    id: int
    kind: str
    status: str
    summary: str
    raw_text: str
    key_facts: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    attachments: List[Dict[str, Any]] = Field(default_factory=list)
    created_at: datetime
    user_id: Optional[str] = None


class QueueResponse(BaseModel):
    items: List[QueueItem]


class SummaryResponse(BaseModel):
    window_seconds: int
    total_submissions: int
    by_kind: Dict[str, int]
    enhancer_success_rate: Optional[float] = None
    store_write_success_rate: Optional[float] = None
    fallback_rate: Optional[float] = None
    stage_p95_ms: Dict[str, Optional[float]]


class TimelineEventModel(BaseModel):
    event_id: str
    timeline_id: str
    kind: str
    stage: str
    status: str
    created_at: datetime
    duration_ms: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    user_id: Optional[str] = None
    submission_id: Optional[int] = None
    fallback_used: Optional[bool] = None
    store_written: Optional[bool] = None


class TimelineBatchResponse(BaseModel):
    items: List[TimelineEventModel]


class PromoteCorrectionRequest(BaseModel):
    correction_id: int = Field(..., gt=0)


class PromoteFeedbackRequest(BaseModel):
    feedback_id: int = Field(..., gt=0)


class ActionResponse(BaseModel):
    success: bool
    status: str
    message: Optional[str] = None


def _safe_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=400, detail=f"Invalid datetime format: {value}") from exc


def _extract_queue_item(row: Dict[str, Any]) -> Optional[QueueItem]:
    if not row:
        return None

    metadata = row.get("metadata") or {}
    enhanced = metadata.get("enhanced") or {}

    summary = enhanced.get("summary") or metadata.get("summary") or row.get("feedback_text") or row.get("corrected_text") or ""
    raw_text = enhanced.get("raw_text") or row.get("feedback_text") or row.get("corrected_text") or ""
    key_facts = enhanced.get("key_facts") or metadata.get("key_facts") or []
    tags = enhanced.get("tags") or metadata.get("tags") or []
    attachments = row.get("attachments") or []

    created_at_raw = row.get("created_at")
    try:
        created_at = datetime.fromisoformat(created_at_raw.replace("Z", "+00:00")) if isinstance(created_at_raw, str) else created_at_raw
    except Exception:
        created_at = datetime.now(timezone.utc)

    try:
        return QueueItem(
            id=int(row["id"]),
            kind=row.get("kind", metadata.get("source", "feedback")),
            status=row.get("status", "received"),
            summary=summary,
            raw_text=raw_text,
            key_facts=list(key_facts) if isinstance(key_facts, list) else [],
            tags=list(tags) if isinstance(tags, list) else [],
            metadata=metadata,
            attachments=attachments if isinstance(attachments, list) else [],
            created_at=created_at if isinstance(created_at, datetime) else datetime.now(timezone.utc),
            user_id=row.get("user_id"),
        )
    except Exception as exc:  # pragma: no cover - defensive guard
        logger.error("Failed to parse queue row: %s", exc, exc_info=True)
        return None


@router.get("/queue", response_model=QueueResponse)
async def get_queue(
    kind: Optional[str] = Query(default=None, description="Filter by submission kind"),
    status: str = Query(default="received", description="Status filter"),
    limit: int = Query(default=30, ge=1, le=200),
):
    client = SupabaseClient()
    if getattr(client, "mock_mode", False):
        return QueueResponse(items=[])

    kinds: List[str]
    if not kind or kind == "all":
        kinds = ["feedback", "correction"]
    else:
        kinds = [kind]

    items: List[QueueItem] = []

    if "feedback" in kinds:
        rows = await client.list_sparrow_feedback(status=status, limit=limit)
        items.extend(filter(None, (_extract_queue_item(row) for row in rows)))

    if "correction" in kinds:
        rows = await client.list_sparrow_corrections(status=status, limit=limit)
        items.extend(filter(None, (_extract_queue_item(row) for row in rows)))

    items.sort(key=lambda item: item.created_at, reverse=True)
    if len(items) > limit:
        items = items[:limit]

    return QueueResponse(items=items)


@router.get("/observability/summary", response_model=SummaryResponse)
async def observability_summary(window_seconds: int = Query(default=86400, ge=60, le=604800)):
    window = timedelta(seconds=window_seconds)
    summary = compute_summary(window)
    by_kind = {key: int(value) for key, value in summary.get("by_kind", {}).items()}
    stage_p95 = {key: (float(value) if value is not None else None) for key, value in summary.get("stage_p95_ms", {}).items()}

    return SummaryResponse(
        window_seconds=summary.get("window_seconds", int(window.total_seconds())),
        total_submissions=summary.get("total_submissions", 0),
        by_kind=by_kind,
        enhancer_success_rate=summary.get("enhancer_success_rate"),
        store_write_success_rate=summary.get("store_write_success_rate"),
        fallback_rate=summary.get("fallback_rate"),
        stage_p95_ms=stage_p95,
    )


@router.get("/observability/events", response_model=TimelineBatchResponse)
async def latest_events(limit: int = Query(default=100, ge=1, le=500)):
    events = list(recent_events(limit=limit))
    payload = [TimelineEventModel(**event.model_dump()) for event in events]
    return TimelineBatchResponse(items=payload)


@router.post("/actions/add-to-kb", response_model=ActionResponse)
async def promote_correction(request: PromoteCorrectionRequest):
    client = SupabaseClient()
    if getattr(client, "mock_mode", False):
        raise HTTPException(status_code=503, detail="Supabase is not configured")

    row = await client.get_sparrow_correction(request.correction_id)
    if not row:
        raise HTTPException(status_code=404, detail="Correction not found")

    metadata = row.get("metadata") or {}
    enhanced_data = metadata.get("enhanced")
    if not enhanced_data:
        raise HTTPException(status_code=422, detail="Enhanced payload missing for correction")

    try:
        enhanced = EnhancedPayload.model_validate(enhanced_data)
    except Exception as exc:
        logger.error("Failed to validate enhanced payload for correction %s: %s", request.correction_id, exc)
        raise HTTPException(status_code=422, detail="Stored enhanced payload is invalid") from exc

    if not settings.has_global_store_configuration():
        raise HTTPException(status_code=503, detail="Global knowledge store is not configured")

    store = await get_async_store()
    if store is None:
        raise HTTPException(status_code=503, detail="Global knowledge store is unavailable")

    embed_model = embedding_utils.get_embedding_model()
    try:
        embedding_vector = embed_model.embed_query(enhanced.raw_text)
        assert_dim(embedding_vector, "global_knowledge_enhanced")
    except Exception as exc:
        logger.error("Embedding computation failed for correction %s: %s", request.correction_id, exc)
        raise HTTPException(status_code=500, detail="Failed to compute embedding for correction") from exc

    timeline_id = start_trace(
        kind="correction",
        user_id=row.get("user_id"),
        metadata={"action": "add_to_kb", "correction_id": request.correction_id},
    )
    attach_submission_id(timeline_id, int(row["id"]))
    publish_stage(
        timeline_id,
        stage="manual_promotion",
        status="in_progress",
        kind="correction",
        user_id=row.get("user_id"),
        metadata={"source_status": row.get("status")},
    )

    store_written = await upsert_enhanced_entry(enhanced, embedding_vector, store=store)
    publish_stage(
        timeline_id,
        stage="store_upserted",
        status="complete" if store_written else "error",
        kind="correction",
        user_id=row.get("user_id"),
        store_written=store_written,
        fallback_used=not store_written,
    )

    if not store_written:
        publish_stage(
            timeline_id,
            stage="completed",
            status="error",
            kind="correction",
            user_id=row.get("user_id"),
            metadata={"reason": "store_write_failed"},
        )
        raise HTTPException(status_code=503, detail="Failed to write correction to knowledge store")

    await client.update_sparrow_correction_status(request.correction_id, status="accepted")
    publish_stage(
        timeline_id,
        stage="status_updated",
        status="complete",
        kind="correction",
        user_id=row.get("user_id"),
        metadata={"status": "accepted"},
    )
    publish_stage(
        timeline_id,
        stage="completed",
        status="complete",
        kind="correction",
        user_id=row.get("user_id"),
        store_written=True,
    )

    return ActionResponse(success=True, status="accepted", message="Correction added to knowledge base")


@router.post("/actions/add-to-feedback", response_model=ActionResponse)
async def promote_feedback(request: PromoteFeedbackRequest):
    client = SupabaseClient()
    if getattr(client, "mock_mode", False):
        raise HTTPException(status_code=503, detail="Supabase is not configured")

    row = await client.get_sparrow_feedback(request.feedback_id)
    if not row:
        raise HTTPException(status_code=404, detail="Feedback not found")

    timeline_id = start_trace(
        kind="feedback",
        user_id=row.get("user_id"),
        metadata={"action": "add_to_feedback", "feedback_id": request.feedback_id},
    )
    attach_submission_id(timeline_id, int(row["id"]))
    publish_stage(
        timeline_id,
        stage="manual_feedback_listing",
        status="in_progress",
        kind="feedback",
        user_id=row.get("user_id"),
        metadata={"status": row.get("status")},
    )

    new_status = "listed"
    updated = await client.update_sparrow_feedback_status(request.feedback_id, status=new_status)

    publish_stage(
        timeline_id,
        stage="manual_feedback_listing",
        status="complete" if updated else "error",
        kind="feedback",
        user_id=row.get("user_id"),
        metadata={"status": new_status if updated else row.get("status")},
    )
    publish_stage(
        timeline_id,
        stage="completed",
        status="complete" if updated else "error",
        kind="feedback",
        user_id=row.get("user_id"),
    )

    if not updated:
        return ActionResponse(success=False, status=row.get("status", "received"), message="Failed to update feedback status")

    return ActionResponse(success=True, status=new_status, message="Feedback flagged for review")


@router.get("/observability/stream")
async def observability_stream(since: Optional[str] = None):
    since_dt: Optional[datetime] = None
    if since:
        since_dt = _safe_datetime(since)

    async def event_generator():
        async for event in subscribe_events(since_dt):
            payload = {
                "type": "timeline-step",
                "data": event.model_dump(),
            }
            yield format_sse_data(payload)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
