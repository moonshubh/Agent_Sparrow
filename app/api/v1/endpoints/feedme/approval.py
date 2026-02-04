"""
FeedMe Approval Endpoints

Approval workflow operations for conversations and examples.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.core.settings import settings
from app.feedme.schemas import (
    FeedMeConversation,
    ApprovalRequest,
    RejectionRequest,
    ApprovalResponse,
    ApprovalWorkflowStats,
)

from .helpers import get_feedme_supabase_client, supabase_client

logger = logging.getLogger(__name__)

router = APIRouter(tags=["FeedMe"])


@router.post(
    "/conversations/{conversation_id}/approve", response_model=ApprovalResponse
)
async def approve_conversation(conversation_id: int, approval_request: ApprovalRequest):
    """
    Approve a conversation for publication.

    Transitions the conversation from 'processed' to 'approved' status
    and marks all associated examples as approved for retrieval.
    """
    if not settings.feedme_enabled:
        raise HTTPException(
            status_code=503, detail="FeedMe service is currently disabled"
        )

    try:
        conversation = await supabase_client.get_conversation_by_id(conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")

        current_status = conversation.get("approval_status", "pending")
        if current_status not in ["processed", "pending", "completed"]:
            raise HTTPException(
                status_code=400,
                detail=f"Conversation is in '{current_status}' status and cannot be approved",
            )

        approval_time = datetime.now(timezone.utc).isoformat()
        update_data = {
            "approval_status": "approved",
            "approved_by": approval_request.approved_by,
            "approved_at": approval_time,
            "reviewer_notes": approval_request.approval_notes,
            "updated_at": approval_time,
        }

        updated_conversation = await supabase_client.update_conversation(
            conversation_id, update_data
        )
        if not updated_conversation:
            raise HTTPException(
                status_code=500, detail="Failed to update conversation approval status"
            )

        await supabase_client.approve_conversation_examples(
            conversation_id=conversation_id, approved_by=approval_request.approved_by
        )

        logger.info(
            f"Conversation {conversation_id} approved by {approval_request.approved_by}"
        )

        # Schedule PDF cleanup task after approval
        try:
            from app.feedme.tasks import cleanup_approved_pdf

            cleanup_approved_pdf.delay(conversation_id)
        except Exception as e:
            logger.warning(f"Failed to schedule PDF cleanup: {e}")

        return ApprovalResponse(
            conversation=FeedMeConversation(**updated_conversation),
            approval_status="approved",
            message="Conversation approved",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error approving conversation {conversation_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to approve conversation")


@router.post("/conversations/{conversation_id}/reject", response_model=ApprovalResponse)
async def reject_conversation(
    conversation_id: int, rejection_request: RejectionRequest
):
    """
    Reject a conversation.

    Transitions the conversation from 'processed' to 'rejected' status
    and marks all associated examples as rejected (inactive).
    """
    if not settings.feedme_enabled:
        raise HTTPException(
            status_code=503, detail="FeedMe service is currently disabled"
        )

    try:
        conversation = await supabase_client.get_conversation_by_id(conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")

        current_status = conversation.get("approval_status", "pending")
        if current_status not in ["processed", "pending", "completed"]:
            raise HTTPException(
                status_code=400,
                detail=f"Conversation is in '{current_status}' status and cannot be rejected",
            )

        rejection_time = datetime.now(timezone.utc).isoformat()
        update_data = {
            "approval_status": "rejected",
            "rejected_by": rejection_request.rejected_by,
            "rejected_at": rejection_time,
            "reviewer_notes": rejection_request.rejection_notes,
            "updated_at": rejection_time,
        }

        updated_conversation = await supabase_client.update_conversation(
            conversation_id, update_data
        )
        if not updated_conversation:
            raise HTTPException(
                status_code=500, detail="Failed to update conversation rejection status"
            )

        # Mark all examples as rejected (skip if examples table is retired)
        rejected_count = 0
        try:
            examples_update_response = await supabase_client._exec(
                lambda: supabase_client.client.table("feedme_examples")
                .update(
                    {
                        "review_status": "rejected",
                        "reviewed_by": rejection_request.rejected_by,
                        "reviewed_at": rejection_time,
                        "is_active": False,
                    }
                )
                .eq("conversation_id", conversation_id)
                .execute()
            )
            rejected_count = (
                len(examples_update_response.data)
                if examples_update_response.data
                else 0
            )
        except Exception as e:
            if not supabase_client._record_missing_table("feedme_examples", e):
                raise
        logger.info(
            f"Conversation {conversation_id} rejected. Rejected {rejected_count} examples."
        )

        return ApprovalResponse(
            conversation=FeedMeConversation(**updated_conversation),
            approval_status="rejected",
            message="Conversation rejected",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error rejecting conversation {conversation_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to reject conversation")


@router.get("/approval/stats", response_model=ApprovalWorkflowStats)
async def get_approval_workflow_stats():
    """
    Get approval workflow statistics.

    Returns comprehensive statistics about the approval workflow including
    conversation counts by status, quality metrics, and processing times.
    """
    if not settings.feedme_enabled:
        raise HTTPException(
            status_code=503, detail="FeedMe service is currently disabled"
        )

    try:
        client = get_feedme_supabase_client()
        if not client:
            raise HTTPException(status_code=503, detail="FeedMe service unavailable.")

        stats_data = await client.get_approval_workflow_stats()

        # The RPC returns conversation_stats (not conversation_approval)
        conversation_stats = stats_data.get("conversation_stats", {})

        # Map status values correctly:
        # - 'processed' = conversations that completed processing and are awaiting review
        # - 'pending' = conversations with approval_status pending (not yet processed)
        # - 'processing' = conversations currently being processed (processing_status)
        # - 'failed' = conversations that failed processing (processing_status)
        # - 'completed' = conversations with processing_status completed

        return ApprovalWorkflowStats(
            total_conversations=conversation_stats.get("total", 0),
            # pending_approval = approval_status 'pending' (not yet started)
            pending_approval=conversation_stats.get("pending", 0),
            # awaiting_review = approval_status 'processed' (completed, ready for review)
            awaiting_review=conversation_stats.get("processed", 0),
            approved=conversation_stats.get("approved", 0),
            rejected=conversation_stats.get("rejected", 0),
            published=0,  # Not used in current workflow
            # currently_processing = processing_status 'processing'
            currently_processing=conversation_stats.get("processing", 0),
            # processing_failed = processing_status 'failed'
            processing_failed=conversation_stats.get("failed", 0),
            avg_quality_score=None,
            avg_processing_time_ms=stats_data.get("avg_processing_time_ms"),
            # Platform breakdown from metadata tags
            windows_count=conversation_stats.get("windows_count", 0),
            macos_count=conversation_stats.get("macos_count", 0),
        )

    except Exception as e:
        logger.error(f"Error getting approval workflow stats: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to get approval workflow statistics"
        )
