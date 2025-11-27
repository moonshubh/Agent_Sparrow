"""
FeedMe Approval Endpoints

Approval workflow operations for conversations and examples.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.core.settings import settings
from app.db.supabase.client import get_supabase_client
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


@router.post("/conversations/{conversation_id}/approve", response_model=ApprovalResponse)
async def approve_conversation(conversation_id: int, approval_request: ApprovalRequest):
    """
    Approve a conversation for publication.

    Transitions the conversation from 'processed' to 'approved' status
    and marks all associated examples as approved for retrieval.
    """
    if not settings.feedme_enabled:
        raise HTTPException(status_code=503, detail="FeedMe service is currently disabled")

    try:
        conversation = await supabase_client.get_conversation_by_id(conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")

        current_status = conversation.get('approval_status', 'pending')
        if current_status not in ['processed', 'pending', 'completed']:
            raise HTTPException(
                status_code=400,
                detail=f"Conversation is in '{current_status}' status and cannot be approved"
            )

        approval_time = datetime.now(timezone.utc).isoformat()
        update_data = {
            'approval_status': 'approved',
            'approved_by': approval_request.approved_by,
            'approved_at': approval_time,
            'reviewer_notes': approval_request.approval_notes,
            'updated_at': approval_time
        }

        updated_conversation = await supabase_client.update_conversation(conversation_id, update_data)
        if not updated_conversation:
            raise HTTPException(status_code=500, detail="Failed to update conversation approval status")

        approval_result = await supabase_client.approve_conversation_examples(
            conversation_id=conversation_id,
            approved_by=approval_request.approved_by
        )

        logger.info(f"Conversation {conversation_id} approved by {approval_request.approved_by}")

        # Schedule PDF cleanup task after approval
        try:
            from app.feedme.tasks import cleanup_approved_pdf
            cleanup_approved_pdf.delay(conversation_id)
        except Exception as e:
            logger.warning(f"Failed to schedule PDF cleanup: {e}")

        return ApprovalResponse(
            conversation=FeedMeConversation(**updated_conversation),
            action="approved",
            timestamp=datetime.fromisoformat(approval_time.replace('Z', '+00:00'))
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error approving conversation {conversation_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to approve conversation")


@router.post("/conversations/{conversation_id}/reject", response_model=ApprovalResponse)
async def reject_conversation(conversation_id: int, rejection_request: RejectionRequest):
    """
    Reject a conversation.

    Transitions the conversation from 'processed' to 'rejected' status
    and marks all associated examples as rejected (inactive).
    """
    if not settings.feedme_enabled:
        raise HTTPException(status_code=503, detail="FeedMe service is currently disabled")

    try:
        conversation = await supabase_client.get_conversation_by_id(conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")

        current_status = conversation.get('approval_status', 'pending')
        if current_status not in ['processed', 'pending', 'completed']:
            raise HTTPException(
                status_code=400,
                detail=f"Conversation is in '{current_status}' status and cannot be rejected"
            )

        rejection_time = datetime.now(timezone.utc).isoformat()
        update_data = {
            'approval_status': 'rejected',
            'rejected_by': rejection_request.rejected_by,
            'rejected_at': rejection_time,
            'reviewer_notes': rejection_request.rejection_notes,
            'updated_at': rejection_time
        }

        updated_conversation = await supabase_client.update_conversation(conversation_id, update_data)
        if not updated_conversation:
            raise HTTPException(status_code=500, detail="Failed to update conversation rejection status")

        # Mark all examples as rejected
        examples_update_response = await supabase_client._exec(
            lambda: supabase_client.client.table('feedme_examples')
            .update({
                'review_status': 'rejected',
                'reviewed_by': rejection_request.rejected_by,
                'reviewed_at': rejection_time,
                'is_active': False
            })
            .eq('conversation_id', conversation_id)
            .execute()
        )

        rejected_count = len(examples_update_response.data) if examples_update_response.data else 0
        logger.info(f"Conversation {conversation_id} rejected. Rejected {rejected_count} examples.")

        return ApprovalResponse(
            conversation=FeedMeConversation(**updated_conversation),
            action="rejected",
            timestamp=datetime.fromisoformat(rejection_time.replace('Z', '+00:00'))
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
        raise HTTPException(status_code=503, detail="FeedMe service is currently disabled")

    try:
        client = get_feedme_supabase_client()
        if not client:
            raise HTTPException(
                status_code=503,
                detail="FeedMe service unavailable."
            )

        stats_data = await client.get_approval_workflow_stats()

        conversation_approval = stats_data.get('conversation_approval', {})
        status_breakdown = conversation_approval.get('status_breakdown', {})

        return ApprovalWorkflowStats(
            total_conversations=conversation_approval.get('total', 0),
            pending_approval=status_breakdown.get('pending', 0),
            awaiting_review=status_breakdown.get('awaiting_review', 0),
            approved=status_breakdown.get('approved', 0),
            rejected=status_breakdown.get('rejected', 0),
            published=status_breakdown.get('published', 0),
            currently_processing=status_breakdown.get('processing', 0),
            processing_failed=status_breakdown.get('failed', 0),
            avg_quality_score=None,
            avg_processing_time_ms=None
        )

    except Exception as e:
        logger.error(f"Error getting approval workflow stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to get approval workflow statistics")
