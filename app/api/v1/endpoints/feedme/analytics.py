"""
FeedMe Analytics Endpoints

Analytics, usage statistics, and monitoring endpoints.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any

from fastapi import APIRouter, HTTPException, BackgroundTasks

from app.core.settings import settings
from app.core.rate_limiting.agent_wrapper import get_rate_limiter
from app.db.supabase.client import get_supabase_client
from app.feedme.schemas import (
    ProcessingStatus,
    ProcessingStage,
    AnalyticsResponse,
    ConversationStats,
)

from .helpers import (
    get_feedme_supabase_client,
    get_conversation_by_id,
    update_conversation_status,
    supabase_client,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["FeedMe"])


@router.get("/analytics/pdf-storage", response_model=Dict[str, Any])
async def get_pdf_storage_analytics():
    """Get PDF storage analytics and cleanup metrics."""
    if not settings.feedme_enabled:
        raise HTTPException(status_code=503, detail="FeedMe service is currently disabled")

    try:
        client = get_supabase_client()
        result = await client._exec(
            lambda: client.client.table('feedme_pdf_storage_analytics').select("*").execute()
        )

        if result.data and len(result.data) > 0:
            analytics = result.data[0]
            return {
                "pending_cleanup": analytics.get('pending_cleanup') or 0,
                "cleaned_count": analytics.get('cleaned_count') or 0,
                "total_mb_freed": float(analytics.get('total_mb_freed') or 0),
                "avg_pdf_size_mb": float(analytics.get('avg_pdf_size_mb') or 0),
                "total_pdf_conversations": analytics.get('total_pdf_conversations') or 0,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        else:
            return {
                "pending_cleanup": 0,
                "cleaned_count": 0,
                "total_mb_freed": 0.0,
                "avg_pdf_size_mb": 0.0,
                "total_pdf_conversations": 0,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

    except Exception as e:
        logger.error(f"Error getting PDF storage analytics: {e}")
        raise HTTPException(status_code=500, detail="Failed to get PDF storage analytics")


@router.post("/cleanup/pdfs/batch", response_model=Dict[str, Any])
async def trigger_pdf_cleanup_batch(limit: int = 100):
    """Trigger batch cleanup of approved PDFs."""
    if not settings.feedme_enabled:
        raise HTTPException(status_code=503, detail="FeedMe service is currently disabled")

    try:
        from app.feedme.tasks import cleanup_approved_pdfs_batch

        task = cleanup_approved_pdfs_batch.delay(limit)

        return {
            "task_id": task.id,
            "status": "scheduled",
            "limit": limit,
            "message": f"Batch PDF cleanup scheduled for up to {limit} conversations"
        }

    except Exception as e:
        logger.error(f"Error triggering batch PDF cleanup: {e}")
        raise HTTPException(status_code=500, detail="Failed to trigger batch PDF cleanup")


@router.get("/analytics", response_model=AnalyticsResponse)
async def get_analytics():
    """Retrieve aggregated analytics and statistics for FeedMe."""
    if not settings.feedme_enabled:
        raise HTTPException(status_code=503, detail="FeedMe service is currently disabled")

    try:
        analytics_data = await supabase_client.get_conversation_analytics()
        status_breakdown = analytics_data.get('status_breakdown', {})

        conversation_stats = ConversationStats(
            total_conversations=analytics_data.get('total_conversations', 0),
            total_examples=analytics_data.get('total_examples', 0),
            pending_processing=status_breakdown.get('processing', 0),
            processing_failed=status_breakdown.get('failed', 0),
            pending_approval=status_breakdown.get('pending_approval', 0),
            approved=status_breakdown.get('completed', 0),
            rejected=status_breakdown.get('rejected', 0)
        )

        quality_metrics = {
            'average_confidence_score': 0.0,
            'average_usefulness_score': 0.0,
            'processing_success_rate': float(
                conversation_stats.approved / max(conversation_stats.total_conversations, 1) * 100
            )
        }

        return AnalyticsResponse(
            conversation_stats=conversation_stats,
            top_tags={},
            issue_type_distribution={},
            quality_metrics=quality_metrics,
            last_updated=datetime.now(timezone.utc)
        )

    except Exception as e:
        logger.error(f"Error generating analytics: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate analytics")


@router.post("/conversations/{conversation_id}/reprocess")
async def reprocess_conversation(conversation_id: int, background_tasks: BackgroundTasks):
    """Schedules reprocessing of a conversation to extract examples."""
    if not settings.feedme_enabled:
        raise HTTPException(status_code=503, detail="FeedMe service is currently disabled")

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
            message="Queued for reprocessing"
        )

        task = process_transcript.delay(conversation_id, "reprocess")
        logger.info(f"Scheduled reprocessing for conversation {conversation_id}, task {task.id}")

        return {
            "conversation_id": conversation_id,
            "task_id": task.id,
            "status": "scheduled",
            "message": "Conversation scheduled for reprocessing"
        }

    except Exception as e:
        logger.error(f"Error scheduling reprocessing: {e}")
        raise HTTPException(status_code=500, detail="Failed to schedule reprocessing")


@router.get("/gemini-usage", response_model=Dict[str, Any])
async def get_gemini_usage():
    """Get current FeedMe model usage statistics (internal.feedme bucket)."""
    if not settings.feedme_enabled:
        raise HTTPException(status_code=503, detail="FeedMe service is currently disabled")

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
        raise HTTPException(status_code=503, detail="FeedMe service is currently disabled")

    try:
        limiter = get_rate_limiter()
        stats = await limiter.get_usage_stats()
        metadata = stats.buckets.get("internal.embedding")
        if metadata is None:
            raise HTTPException(status_code=404, detail="Embedding bucket not configured")

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
            "tpm": (metadata.tpm_used / max(1, metadata.tpm_limit)) if metadata.tpm_limit else 0.0,
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


@router.delete("/examples/{example_id}", response_model=Dict[str, Any])
async def delete_example(example_id: int):
    """Delete a specific Q&A example."""
    if not settings.feedme_enabled:
        raise HTTPException(status_code=503, detail="FeedMe service is currently disabled")

    try:
        client = get_supabase_client()

        example = await client.get_example_with_conversation(example_id)
        if not example:
            raise HTTPException(status_code=404, detail="Example not found")

        # Save data before deletion for response
        conversation_id = example.get('conversation_id')
        conversation_title = example.get('conversation_title', 'Unknown')
        question_text = example.get('question_text', '')

        success = await client.delete_example(example_id)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete example")

        # Update count - log but don't fail if this fails
        try:
            await client.update_conversation_example_count(conversation_id)
        except Exception as count_err:
            logger.warning(f"Failed to update example count for conversation {conversation_id}: {count_err}")

        logger.info(f"Deleted example {example_id} from conversation {conversation_id}")

        question_preview = question_text[:100] + "..." if len(question_text) > 100 else question_text

        return {
            "example_id": example_id,
            "conversation_id": conversation_id,
            "conversation_title": conversation_title,
            "question_preview": question_preview,
            "message": "Successfully deleted Q&A example"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete example {example_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete example")


@router.get("/health")
async def feedme_health_check():
    """FeedMe service health check endpoint."""
    if not settings.feedme_enabled:
        return {
            "status": "disabled",
            "message": "FeedMe service is currently disabled",
            "feedme_enabled": False
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
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except Exception as e:
        logger.error(f"Health check error: {e}", exc_info=True)
        return {
            "status": "unhealthy",
            "feedme_enabled": True,
            "error": "internal error",  # Don't expose error details
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
