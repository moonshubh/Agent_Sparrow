"""
Text Approval API Endpoints for FeedMe System
Handles human approval workflow for extracted text from PDF OCR and manual entry
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends, Query, Body
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.settings import settings
from app.feedme.schemas import ProcessingMethod, ApprovalStatus
from app.feedme.approval_workflow import HumanApprovalWorkflow, ApprovalDecision, ApprovalAction

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/v1/feedme/approval", tags=["FeedMe Text Approval"])


# Request/Response Models

class ApprovalPreviewResponse(BaseModel):
    """Response model for approval preview"""
    conversations: List[Dict[str, Any]] = Field(..., description="Conversations pending approval")
    total_count: int = Field(..., description="Total number of conversations pending approval")
    page_info: Dict[str, Any] = Field(..., description="Pagination information")


class TextApprovalRequest(BaseModel):
    """Request model for text approval"""
    action: ApprovalAction = Field(..., description="Approval action to take")
    reviewer_id: str = Field(..., min_length=1, description="ID of the reviewer")
    notes: Optional[str] = Field(None, description="Optional reviewer notes")
    edited_text: Optional[str] = Field(None, description="Edited text (required for edit_and_approve)")
    feedback: Optional[str] = Field(None, description="Feedback for rejection or reprocess requests")
    
    def validate_action_requirements(self):
        """Validate that required fields are provided for each action"""
        if self.action == ApprovalAction.EDIT_AND_APPROVE and not self.edited_text:
            raise ValueError("edited_text is required for edit_and_approve action")
        
        if self.action in [ApprovalAction.REJECT, ApprovalAction.REQUEST_REPROCESS] and not self.feedback:
            raise ValueError(f"feedback is required for {self.action.value} action")


class TextApprovalResponse(BaseModel):
    """Response model for text approval"""
    action: str = Field(..., description="Action that was taken")
    conversation_id: int = Field(..., description="ID of the conversation")
    reviewer_id: str = Field(..., description="ID of the reviewer")
    timestamp: str = Field(..., description="Timestamp of the action")
    message: str = Field(..., description="Success message")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional action details")


class BulkApprovalRequest(BaseModel):
    """Request model for bulk approval operations"""
    conversation_ids: List[int] = Field(..., min_items=1, max_items=50, description="Conversation IDs to process")
    action: ApprovalAction = Field(..., description="Action to apply to all conversations")
    reviewer_id: str = Field(..., min_length=1, description="ID of the reviewer")
    notes: Optional[str] = Field(None, description="Notes to apply to all conversations")


class BulkApprovalResponse(BaseModel):
    """Response model for bulk approval operations"""
    total_requested: int = Field(..., description="Total conversations requested")
    successful: List[int] = Field(..., description="Successfully processed conversation IDs")
    failed: List[Dict[str, Any]] = Field(..., description="Failed operations with details")
    action: str = Field(..., description="Action that was attempted")


class ApprovalStatsResponse(BaseModel):
    """Response model for approval statistics"""
    total_conversations: int = Field(..., description="Total conversations in system")
    pending_approval: int = Field(..., description="Conversations pending approval")
    approved: int = Field(..., description="Approved conversations")
    rejected: int = Field(..., description="Rejected conversations")
    processing_method_breakdown: Dict[str, int] = Field(..., description="Breakdown by processing method")
    quality_indicators: Dict[str, int] = Field(..., description="Quality indicators")


# Dependency to get approval workflow instance
async def get_approval_workflow() -> HumanApprovalWorkflow:
    """Get approval workflow instance with Supabase client"""
    # In production, inject the actual Supabase client
    return HumanApprovalWorkflow(supabase_client=None)  # TODO: Inject actual client


# API Endpoints

@router.get("/pending", response_model=ApprovalPreviewResponse)
async def get_pending_approvals(
    limit: int = Query(default=20, ge=1, le=100, description="Number of conversations to return"),
    offset: int = Query(default=0, ge=0, description="Offset for pagination"),
    processing_method: Optional[ProcessingMethod] = Query(default=None, description="Filter by processing method"),
    workflow: HumanApprovalWorkflow = Depends(get_approval_workflow)
):
    """
    Get conversations pending approval
    
    Returns conversations that have been processed but are waiting for human approval.
    Includes processing metadata, confidence scores, and review priority indicators.
    """
    try:
        result = await workflow.get_pending_approvals(
            limit=limit,
            offset=offset,
            processing_method=processing_method
        )
        
        return ApprovalPreviewResponse(**result)
        
    except Exception as e:
        logger.error(f"Failed to get pending approvals: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve pending approvals")


@router.get("/conversation/{conversation_id}/preview")
async def get_conversation_approval_preview(
    conversation_id: int,
    workflow: HumanApprovalWorkflow = Depends(get_approval_workflow)
):
    """
    Get detailed preview of a conversation for approval
    
    Returns the extracted text along with processing metadata, confidence scores,
    and any warnings or issues that require human attention.
    """
    try:
        # Get the conversation with approval context
        if workflow.supabase_client:
            conversation = await workflow.supabase_client.get_conversation_by_id(conversation_id)
        else:
            raise HTTPException(status_code=503, detail="Database service unavailable")
        
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        # Check if conversation is in the right status for approval
        approval_status = conversation.get('approval_status', 'pending')
        if approval_status != ApprovalStatus.PENDING.value:
            raise HTTPException(
                status_code=400, 
                detail=f"Conversation is in '{approval_status}' status and not available for approval"
            )
        
        # Enhance with approval context
        enhanced = await workflow._enhance_conversation_for_approval(conversation)
        
        return {
            "conversation": enhanced,
            "approval_context": {
                "can_approve": True,
                "can_reject": True,
                "can_edit": True,
                "can_reprocess": True,
                "requires_attention": enhanced.get('review_priority') == 'high'
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get conversation preview: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve conversation preview")


@router.post("/conversation/{conversation_id}/decide", response_model=TextApprovalResponse)
async def make_approval_decision(
    conversation_id: int,
    request: TextApprovalRequest,
    workflow: HumanApprovalWorkflow = Depends(get_approval_workflow)
):
    """
    Make an approval decision for a conversation
    
    Allows human reviewers to approve, reject, edit, or request reprocessing
    of extracted text. The action taken depends on the request.action field.
    
    Actions:
    - approve: Approve text as-is
    - reject: Reject text and mark for revision
    - edit_and_approve: Edit text and approve the edited version
    - request_reprocess: Request reprocessing of the original document
    """
    try:
        # Validate action requirements
        request.validate_action_requirements()
        
        # Create approval decision
        decision = ApprovalDecision(
            conversation_id=conversation_id,
            action=request.action,
            reviewer_id=request.reviewer_id,
            notes=request.notes,
            edited_text=request.edited_text,
            feedback=request.feedback
        )
        
        # Process the decision
        result = await workflow.process_approval_decision(decision)
        
        return TextApprovalResponse(
            action=result['action'],
            conversation_id=conversation_id,
            reviewer_id=request.reviewer_id,
            timestamp=result.get('approved_at') or result.get('rejected_at') or result.get('requested_at'),
            message=result['message'],
            details=result
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to process approval decision: {e}")
        raise HTTPException(status_code=500, detail="Failed to process approval decision")


@router.post("/bulk", response_model=BulkApprovalResponse)
async def bulk_approval_operation(
    request: BulkApprovalRequest,
    workflow: HumanApprovalWorkflow = Depends(get_approval_workflow)
):
    """
    Perform bulk approval operations
    
    Allows reviewers to approve or reject multiple conversations at once.
    Useful for processing conversations with high confidence scores or
    handling bulk rejections.
    
    Note: Bulk edit operations are not supported for safety reasons.
    """
    try:
        if request.action in [ApprovalAction.EDIT_AND_APPROVE]:
            raise HTTPException(
                status_code=400, 
                detail="Bulk edit operations are not supported. Please edit conversations individually."
            )
        
        successful = []
        failed = []
        
        for conversation_id in request.conversation_ids:
            try:
                # Create decision for this conversation
                decision = ApprovalDecision(
                    conversation_id=conversation_id,
                    action=request.action,
                    reviewer_id=request.reviewer_id,
                    notes=request.notes,
                    feedback=request.notes  # Use notes as feedback for bulk operations
                )
                
                # Process the decision
                result = await workflow.process_approval_decision(decision)
                successful.append(conversation_id)
                
            except Exception as e:
                failed.append({
                    'conversation_id': conversation_id,
                    'error': str(e)
                })
                logger.error(f"Failed to process conversation {conversation_id} in bulk operation: {e}")
        
        return BulkApprovalResponse(
            total_requested=len(request.conversation_ids),
            successful=successful,
            failed=failed,
            action=request.action.value
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to perform bulk approval operation: {e}")
        raise HTTPException(status_code=500, detail="Failed to perform bulk approval operation")


@router.get("/stats", response_model=ApprovalStatsResponse)
async def get_approval_statistics(
    workflow: HumanApprovalWorkflow = Depends(get_approval_workflow)
):
    """
    Get approval workflow statistics
    
    Returns comprehensive statistics about the approval workflow including
    approval rates, processing method breakdown, and quality indicators.
    """
    try:
        stats = await workflow.get_approval_statistics()
        
        if 'error' in stats:
            raise HTTPException(status_code=503, detail=stats['error'])
        
        return ApprovalStatsResponse(**stats)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get approval statistics: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve approval statistics")


@router.get("/queue/summary")
async def get_approval_queue_summary(
    workflow: HumanApprovalWorkflow = Depends(get_approval_workflow)
):
    """
    Get a summary of the approval queue
    
    Returns high-level metrics about conversations waiting for approval,
    categorized by priority and processing method.
    """
    try:
        # Get pending approvals without limit to count priorities
        result = await workflow.get_pending_approvals(limit=1000, offset=0)
        conversations = result.get('conversations', [])
        
        # Analyze the queue
        summary = {
            'total_pending': len(conversations),
            'priority_breakdown': {
                'high': 0,
                'medium': 0,
                'low': 0
            },
            'processing_method_breakdown': {
                'pdf_ocr': 0,
                'manual_text': 0,
                'text_paste': 0
            },
            'confidence_breakdown': {
                'high_confidence': 0,  # > 0.85
                'medium_confidence': 0,  # 0.7 - 0.85
                'low_confidence': 0,  # < 0.7
                'no_confidence': 0  # No confidence score
            }
        }
        
        for conv in conversations:
            # Count priorities
            priority = conv.get('review_priority', 'medium')
            summary['priority_breakdown'][priority] += 1
            
            # Count processing methods
            method = conv.get('processing_method', 'unknown')
            if method in summary['processing_method_breakdown']:
                summary['processing_method_breakdown'][method] += 1
            
            # Count confidence levels
            confidence = conv.get('extraction_confidence', None)
            if confidence is None:
                summary['confidence_breakdown']['no_confidence'] += 1
            elif confidence > 0.85:
                summary['confidence_breakdown']['high_confidence'] += 1
            elif confidence >= 0.7:
                summary['confidence_breakdown']['medium_confidence'] += 1
            else:
                summary['confidence_breakdown']['low_confidence'] += 1
        
        return summary
        
    except Exception as e:
        logger.error(f"Failed to get approval queue summary: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve approval queue summary")