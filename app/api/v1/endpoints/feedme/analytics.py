"""
FeedMe Analytics Endpoints

Analytics, usage statistics, and monitoring endpoints.
"""

import logging
from datetime import datetime, timedelta, timezone
import math
from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from postgrest.base_request_builder import CountMethod

from app.core.security import TokenPayload
from app.core.settings import settings
from app.core.rate_limiting.agent_wrapper import get_rate_limiter
from app.db.supabase.client import get_supabase_client
from app.feedme.schemas import (
    ProcessingStatus,
    ProcessingStage,
    AnalyticsResponse,
    ConversationStats,
    FeedMeStatsOverviewResponse,
    TaskScheduleResponse,
    ReprocessResponse,
)

from .helpers import (
    get_feedme_settings,
    get_feedme_supabase_client,
    get_conversation_by_id,
    update_conversation_status,
    supabase_client,
)
from .auth import require_feedme_admin

logger = logging.getLogger(__name__)

router = APIRouter(tags=["FeedMe"])
COUNT_EXACT: CountMethod = CountMethod.exact


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    if len(sorted_values) == 1:
        return float(sorted_values[0])

    rank = (len(sorted_values) - 1) * percentile
    lower_index = int(math.floor(rank))
    upper_index = int(math.ceil(rank))
    if lower_index == upper_index:
        return float(sorted_values[lower_index])
    lower_value = sorted_values[lower_index]
    upper_value = sorted_values[upper_index]
    weight = rank - lower_index
    return float(lower_value + (upper_value - lower_value) * weight)


@router.get("/stats/overview", response_model=FeedMeStatsOverviewResponse)
async def get_feedme_stats_overview(
    range_days: int = Query(7, ge=1, le=90, description="Relative time range in days"),
    folder_id: Optional[int] = Query(None, description="Filter by folder id"),
    os_category: Optional[str] = Query(
        None, description="Filter by os_category (windows|macos|both|uncategorized)"
    ),
) -> FeedMeStatsOverviewResponse:
    """Canonical FeedMe stats endpoint backed directly by DB truth."""
    if not settings.feedme_enabled:
        raise HTTPException(
            status_code=503, detail="FeedMe service is currently disabled"
        )

    client = get_feedme_supabase_client()
    if client is None:
        raise HTTPException(
            status_code=503, detail="FeedMe service is temporarily unavailable."
        )

    now = datetime.now(timezone.utc)
    start_at = now - timedelta(days=range_days)
    start_iso = start_at.isoformat()
    end_iso = now.isoformat()

    query = (
        client.client.table("feedme_conversations")
        .select(
            "id,processing_status,processing_time_ms,os_category,created_at,updated_at,folder_id"
        )
        .gte("created_at", start_iso)
        .lte("created_at", end_iso)
    )

    if folder_id is not None:
        if folder_id == 0:
            query = query.is_("folder_id", "null")
        else:
            query = query.eq("folder_id", folder_id)

    if os_category:
        query = query.eq("os_category", os_category)

    conversations_response = await client._exec(lambda: query.execute())
    rows = conversations_response.data or []

    total_count = len(rows)
    queue_depth = 0
    failed_count = 0
    latencies_ms: list[float] = []
    os_distribution = {
        "windows": 0,
        "macos": 0,
        "both": 0,
        "uncategorized": 0,
    }
    warning_count = 0
    breach_count = 0

    settings_row = await get_feedme_settings()
    sla_warning_minutes = int(settings_row.get("sla_warning_minutes") or 60)
    sla_breach_minutes = int(settings_row.get("sla_breach_minutes") or 180)

    for row in rows:
        status = str(row.get("processing_status") or "pending").lower()
        if status in {"pending", "processing"}:
            queue_depth += 1
        if status == "failed":
            failed_count += 1

        processing_time = row.get("processing_time_ms")
        if isinstance(processing_time, (int, float)) and processing_time > 0:
            latencies_ms.append(float(processing_time))

        os_value = str(row.get("os_category") or "uncategorized").lower()
        if os_value not in os_distribution:
            os_value = "uncategorized"
        os_distribution[os_value] += 1

        if status in {"pending", "processing"}:
            created_at_raw = row.get("created_at")
            if isinstance(created_at_raw, str):
                try:
                    created_at = datetime.fromisoformat(
                        created_at_raw.replace("Z", "+00:00")
                    )
                except ValueError:
                    created_at = now
                age_minutes = (now - created_at).total_seconds() / 60
                if age_minutes >= sla_breach_minutes:
                    breach_count += 1
                elif age_minutes >= sla_warning_minutes:
                    warning_count += 1

    failure_rate = (failed_count / total_count * 100) if total_count > 0 else 0.0
    p50_latency = _percentile(latencies_ms, 0.50)
    p95_latency = _percentile(latencies_ms, 0.95)

    assign_audit = await client._exec(
        lambda: (
            client.client.table("feedme_action_audit")
            .select("id", count=COUNT_EXACT)
            .eq("action", "assign_folder")
            .gte("created_at", start_iso)
            .lte("created_at", end_iso)
            .execute()
        )
    )
    kb_ready_audit = await client._exec(
        lambda: (
            client.client.table("feedme_action_audit")
            .select("id", count=COUNT_EXACT)
            .eq("action", "mark_ready_for_kb")
            .gte("created_at", start_iso)
            .lte("created_at", end_iso)
            .execute()
        )
    )

    assign_throughput = assign_audit.count or 0
    kb_ready_throughput = kb_ready_audit.count or 0

    return {
        "time_range": {
            "start_at": start_iso,
            "end_at": end_iso,
            "range_days": range_days,
        },
        "filters": {
            "folder_id": folder_id,
            "os_category": os_category,
        },
        "cards": {
            "queue_depth": queue_depth,
            "failure_rate": round(failure_rate, 2),
            "p50_latency_ms": round(p50_latency, 2),
            "p95_latency_ms": round(p95_latency, 2),
            "assign_throughput": assign_throughput,
            "kb_ready_throughput": kb_ready_throughput,
            "sla_warning_count": warning_count,
            "sla_breach_count": breach_count,
        },
        "os_distribution": os_distribution,
        "sla_thresholds": {
            "warning_minutes": sla_warning_minutes,
            "breach_minutes": sla_breach_minutes,
        },
        "total_conversations": total_count,
        "generated_at": now.isoformat(),
    }


@router.get("/analytics/pdf-storage", response_model=Dict[str, Any])
async def get_pdf_storage_analytics():
    """Get PDF storage analytics and cleanup metrics."""
    if not settings.feedme_enabled:
        raise HTTPException(
            status_code=503, detail="FeedMe service is currently disabled"
        )

    try:
        client = get_supabase_client()
        result = await client._exec(
            lambda: (
                client.client.table("feedme_pdf_storage_analytics")
                .select("*")
                .execute()
            )
        )

        if result.data and len(result.data) > 0:
            analytics = result.data[0]
            return {
                "pending_cleanup": analytics.get("pending_cleanup") or 0,
                "cleaned_count": analytics.get("cleaned_count") or 0,
                "total_mb_freed": float(analytics.get("total_mb_freed") or 0),
                "avg_pdf_size_mb": float(analytics.get("avg_pdf_size_mb") or 0),
                "total_pdf_conversations": analytics.get("total_pdf_conversations")
                or 0,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        else:
            return {
                "pending_cleanup": 0,
                "cleaned_count": 0,
                "total_mb_freed": 0.0,
                "avg_pdf_size_mb": 0.0,
                "total_pdf_conversations": 0,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

    except Exception as e:
        logger.error(f"Error getting PDF storage analytics: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to get PDF storage analytics"
        )


@router.post("/cleanup/pdfs/batch", response_model=TaskScheduleResponse)
async def trigger_pdf_cleanup_batch(
    limit: int = 100,
    current_user: TokenPayload = Depends(require_feedme_admin),
) -> TaskScheduleResponse:
    """Trigger batch cleanup of approved PDFs."""
    if not settings.feedme_enabled:
        raise HTTPException(
            status_code=503, detail="FeedMe service is currently disabled"
        )

    try:
        from app.feedme.tasks import cleanup_approved_pdfs_batch

        task = cleanup_approved_pdfs_batch.delay(limit)

        return {
            "task_id": task.id,
            "status": "scheduled",
            "limit": limit,
            "message": f"Batch PDF cleanup scheduled for up to {limit} conversations",
        }

    except Exception as e:
        logger.error(f"Error triggering batch PDF cleanup: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to trigger batch PDF cleanup"
        )


@router.get("/analytics", response_model=AnalyticsResponse)
async def get_analytics():
    """Retrieve aggregated analytics and statistics for FeedMe."""
    if not settings.feedme_enabled:
        raise HTTPException(
            status_code=503, detail="FeedMe service is currently disabled"
        )

    try:
        analytics_data = await supabase_client.get_conversation_analytics()
        status_breakdown = analytics_data.get("status_breakdown", {})

        conversation_stats = ConversationStats(
            total_conversations=analytics_data.get("total_conversations", 0),
            total_examples=analytics_data.get("total_examples", 0),
            pending_processing=status_breakdown.get("processing", 0),
            processing_failed=status_breakdown.get("failed", 0),
            pending_approval=status_breakdown.get("pending_approval", 0),
            approved=status_breakdown.get("completed", 0),
            rejected=status_breakdown.get("rejected", 0),
        )

        quality_metrics = {
            "average_confidence_score": 0.0,
            "average_usefulness_score": 0.0,
            "processing_success_rate": float(
                conversation_stats.approved
                / max(conversation_stats.total_conversations, 1)
                * 100
            ),
        }

        return AnalyticsResponse(
            conversation_stats=conversation_stats,
            top_tags={},
            issue_type_distribution={},
            quality_metrics=quality_metrics,
            last_updated=datetime.now(timezone.utc),
        )

    except Exception as e:
        logger.error(f"Error generating analytics: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate analytics")


@router.post(
    "/conversations/{conversation_id}/reprocess",
    response_model=ReprocessResponse,
)
async def reprocess_conversation(
    conversation_id: int,
    current_user: TokenPayload = Depends(require_feedme_admin),
) -> ReprocessResponse:
    """Schedules reprocessing of a conversation to extract examples."""
    if not settings.feedme_enabled:
        raise HTTPException(
            status_code=503, detail="FeedMe service is currently disabled"
        )

    conversation = await get_conversation_by_id(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    try:
        from app.feedme.tasks import process_transcript

        await update_conversation_status(
            conversation_id,
            ProcessingStatus.PENDING,
            stage=ProcessingStage.QUEUED,
            progress=0,
            message="Queued for reprocessing",
        )

        task = process_transcript.delay(conversation_id, "reprocess")
        logger.info(
            f"Scheduled reprocessing for conversation {conversation_id}, task {task.id}"
        )

        return {
            "conversation_id": conversation_id,
            "task_id": task.id,
            "status": "scheduled",
            "message": "Conversation scheduled for reprocessing",
        }

    except Exception as e:
        logger.error(f"Error scheduling reprocessing: {e}")
        raise HTTPException(status_code=500, detail="Failed to schedule reprocessing")


@router.get("/gemini-usage", response_model=Dict[str, Any])
async def get_gemini_usage():
    """Get current FeedMe model usage statistics (internal.feedme bucket)."""
    if not settings.feedme_enabled:
        raise HTTPException(
            status_code=503, detail="FeedMe service is currently disabled"
        )

    try:
        limiter = get_rate_limiter()
        stats = await limiter.get_usage_stats()
        metadata = stats.buckets.get("internal.feedme")
        if metadata is None:
            raise HTTPException(status_code=404, detail="FeedMe bucket not configured")

        now = datetime.utcnow()
        window_remaining = max(0, int((metadata.reset_time_rpm - now).total_seconds()))
        utilization = {
            "daily": metadata.rpd_used / max(1, metadata.rpd_limit),
            "rpm": metadata.rpm_used / max(1, metadata.rpm_limit),
        }

        return {
            "daily_used": metadata.rpd_used,
            "daily_limit": metadata.rpd_limit,
            "rpm_limit": metadata.rpm_limit,
            "calls_in_window": metadata.rpm_used,
            "window_seconds_remaining": window_remaining,
            "utilization": utilization,
            "status": "healthy" if utilization["daily"] < 0.9 else "warning",
            "day": now.strftime("%Y-%m-%d"),
        }

    except Exception as e:
        logger.error(f"Error fetching Gemini usage: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch usage statistics")


@router.get("/embedding-usage", response_model=Dict[str, Any])
async def get_embedding_usage():
    """Get current embedding API usage statistics (internal.embedding bucket)."""
    if not settings.feedme_enabled:
        raise HTTPException(
            status_code=503, detail="FeedMe service is currently disabled"
        )

    try:
        limiter = get_rate_limiter()
        stats = await limiter.get_usage_stats()
        metadata = stats.buckets.get("internal.embedding")
        if metadata is None:
            raise HTTPException(
                status_code=404, detail="Embedding bucket not configured"
            )

        now = datetime.utcnow()
        window_remaining = max(0, int((metadata.reset_time_rpm - now).total_seconds()))
        token_window_remaining = (
            max(0, int((metadata.reset_time_tpm - now).total_seconds()))
            if metadata.reset_time_tpm
            else 0
        )
        utilization = {
            "daily": metadata.rpd_used / max(1, metadata.rpd_limit),
            "rpm": metadata.rpm_used / max(1, metadata.rpm_limit),
            "tpm": (
                (metadata.tpm_used / max(1, metadata.tpm_limit))
                if metadata.tpm_limit
                else 0.0
            ),
        }
        utilization_max = max(utilization.values(), default=0)

        return {
            "daily_used": metadata.rpd_used,
            "daily_limit": metadata.rpd_limit,
            "rpm_limit": metadata.rpm_limit,
            "tpm_limit": metadata.tpm_limit,
            "calls_in_window": metadata.rpm_used,
            "tokens_in_window": metadata.tpm_used,
            "window_seconds_remaining": window_remaining,
            "token_window_seconds_remaining": token_window_remaining,
            "utilization": utilization,
            "status": "healthy" if utilization_max < 0.9 else "warning",
            "day": now.strftime("%Y-%m-%d"),
        }

    except Exception as e:
        logger.error(f"Error fetching embedding usage: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch usage statistics")


@router.get("/health")
async def feedme_health_check():
    """FeedMe service health check endpoint."""
    if not settings.feedme_enabled:
        return {
            "status": "disabled",
            "message": "FeedMe service is currently disabled",
            "feedme_enabled": False,
        }

    try:
        client = get_feedme_supabase_client()
        db_status = "connected" if client else "unavailable"
        celery_status: Dict[str, Any] = {"status": "unknown"}
        try:
            # Lightweight Celery worker presence check (do not expose broker URL/credentials)
            from app.feedme.celery_app import celery_app

            inspect = celery_app.control.inspect(
                timeout=min(2.0, float(settings.node_timeout_sec))
            )
            stats = inspect.stats() or {}
            celery_status = {
                "status": "healthy" if stats else "unhealthy",
                "workers": len(stats) if stats else 0,
            }
        except Exception as e:
            celery_status = {"status": "unhealthy", "error": type(e).__name__}

        return {
            "status": "healthy" if client else "degraded",
            "feedme_enabled": True,
            "database": db_status,
            "pdf_processing": settings.feedme_pdf_enabled,
            "celery": celery_status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        logger.error(f"Health check error: {e}", exc_info=True)
        return {
            "status": "unhealthy",
            "feedme_enabled": True,
            "error": "internal error",  # Don't expose error details
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
