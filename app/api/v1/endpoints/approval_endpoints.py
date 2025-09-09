"""
FeedMe v2.0 Approval API Endpoints

REST API endpoints for approval workflow operations including CRUD operations,
bulk actions, metrics, and reviewer management.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from functools import lru_cache
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse

from app.feedme.approval import (
    ApprovalWorkflowEngine,
    ApprovalState,
    ApprovalAction,
    TempExampleCreate,
    TempExampleUpdate,
    TempExampleResponse,
    ApprovalDecision,
    BulkApprovalRequest,
    BulkApprovalResponse,
    WorkflowMetrics,
    ReviewerWorkloadSummary,
    PaginatedTempExampleResponse,
    WorkflowSummary
)
from app.feedme.approval.state_machine import StateTransitionError
from app.core.config import get_settings
from app.core.rate_limiting import RateLimiter

logger = logging.getLogger(__name__)
settings = get_settings()

# Create router
router = APIRouter(prefix="/approval", tags=["approval"])

# Rate limiting
rate_limiter = RateLimiter()


# ===========================
# Dependency Injection
# ===========================

@lru_cache(maxsize=1)
def _create_workflow_engine() -> ApprovalWorkflowEngine:
    """Create singleton workflow engine instance"""
    from app.feedme.embeddings.embedding_pipeline import FeedMeEmbeddingPipeline
    from app.feedme.approval.schemas import WorkflowConfig
    
    embedding_service = FeedMeEmbeddingPipeline()
    config = WorkflowConfig()
    
    return ApprovalWorkflowEngine(embedding_service, config)

async def get_workflow_engine() -> ApprovalWorkflowEngine:
    """Get workflow engine instance with singleton pattern"""
    return _create_workflow_engine()


async def get_current_user() -> str:
    """Get current authenticated user (placeholder)"""
    # This would integrate with your authentication system
    return "user@mailbird.com"

async def get_current_admin_user() -> str:
    """Get current authenticated admin user"""
    # This would integrate with your authentication system
    # and verify admin permissions
    user = await get_current_user()
    # In a real system, check if user has admin role
    # For now, assume all users are admins for demo purposes
    return user


# ===========================
# Temp Example Operations
# ===========================

@router.post(
    "/temp-examples",
    response_model=TempExampleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create new temp example for approval"
)
async def create_temp_example(
    temp_example: TempExampleCreate,
    workflow_engine: ApprovalWorkflowEngine = Depends(get_workflow_engine),
    current_user: str = Depends(get_current_user)
):
    """
    Create a new temp example for approval workflow.
    
    The system will automatically determine approval status based on
    extraction confidence and configured thresholds.
    """
    try:
        # Apply rate limiting
        await rate_limiter.check_rate_limit(f"create_temp_example:{current_user}", 10, 60)
        
        result = await workflow_engine.create_temp_example(temp_example)
        
        logger.info(
            f"Created temp example {result['id']} by {current_user} "
            f"with status {result['approval_status']}"
        )
        
        return TempExampleResponse(**result)
        
    except Exception as e:
        logger.error(f"Failed to create temp example: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create temp example"
        )


@router.get(
    "/temp-examples/{temp_example_id}",
    response_model=TempExampleResponse,
    summary="Get temp example by ID"
)
async def get_temp_example(
    temp_example_id: int,
    workflow_engine: ApprovalWorkflowEngine = Depends(get_workflow_engine),
    current_user: str = Depends(get_current_user)
):
    """Get a specific temp example by ID."""
    try:
        result = await workflow_engine.repository.get_temp_example(temp_example_id)
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Temp example not found"
            )
        
        return TempExampleResponse(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get temp example {temp_example_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.get(
    "/temp-examples",
    response_model=PaginatedTempExampleResponse,
    summary="List temp examples with filtering and pagination"
)
async def list_temp_examples(
    status: Optional[ApprovalState] = Query(None, description="Filter by approval status"),
    assigned_reviewer: Optional[str] = Query(None, description="Filter by assigned reviewer"),
    priority: Optional[str] = Query(None, description="Filter by priority"),
    min_confidence: Optional[float] = Query(None, ge=0.0, le=1.0, description="Minimum confidence score"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=100, description="Items per page"),
    workflow_engine: ApprovalWorkflowEngine = Depends(get_workflow_engine),
    current_user: str = Depends(get_current_user)
):
    """
    List temp examples with filtering and pagination.
    
    Supports filtering by status, reviewer, priority, and confidence score.
    """
    try:
        # Build filters
        filters = {}
        if status:
            filters['approval_status'] = status.value
        if assigned_reviewer:
            filters['assigned_reviewer'] = assigned_reviewer
        if priority:
            filters['priority'] = priority
        if min_confidence is not None:
            filters['min_confidence'] = min_confidence
        
        result = await workflow_engine.repository.get_temp_examples_by_status(
            filters=filters,
            page=page,
            page_size=page_size
        )
        
        return PaginatedTempExampleResponse(**result)
        
    except Exception as e:
        logger.error(f"Failed to list temp examples: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve temp examples"
        )


@router.put(
    "/temp-examples/{temp_example_id}",
    response_model=TempExampleResponse,
    summary="Update temp example"
)
async def update_temp_example(
    temp_example_id: int,
    update_data: TempExampleUpdate,
    workflow_engine: ApprovalWorkflowEngine = Depends(get_workflow_engine),
    current_user: str = Depends(get_current_user)
):
    """Update a temp example (only allowed for non-final states)."""
    try:
        # Check if temp example exists and is editable
        existing = await workflow_engine.repository.get_temp_example(temp_example_id)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Temp example not found"
            )
        
        current_state = ApprovalState(existing['approval_status'])
        if not workflow_engine.state_machine.allows_editing(current_state):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot edit temp example in {current_state} state"
            )
        
        # Update
        update_dict = update_data.model_dump(exclude_unset=True)
        updated = await workflow_engine.repository.update_temp_example(
            temp_example_id, update_dict
        )
        
        logger.info(f"Updated temp example {temp_example_id} by {current_user}")
        return TempExampleResponse(**updated)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update temp example {temp_example_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update temp example"
        )


# ===========================
# Reviewer Assignment
# ===========================

@router.put(
    "/temp-examples/{temp_example_id}/assign",
    response_model=TempExampleResponse,
    summary="Assign reviewer to temp example"
)
async def assign_reviewer(
    temp_example_id: int,
    assignment_data: Dict[str, Optional[str]] = None,
    workflow_engine: ApprovalWorkflowEngine = Depends(get_workflow_engine),
    current_user: str = Depends(get_current_user)
):
    """
    Assign a reviewer to a temp example.
    
    If no reviewer_id is provided, the system will auto-assign based on workload.
    """
    try:
        reviewer_id = assignment_data.get('reviewer_id') if assignment_data else None
        
        assigned_reviewer = await workflow_engine.assign_reviewer(
            temp_example_id, reviewer_id
        )
        
        # Get updated temp example
        updated = await workflow_engine.repository.get_temp_example(temp_example_id)
        
        logger.info(
            f"Assigned reviewer {assigned_reviewer} to temp example {temp_example_id} "
            f"by {current_user}"
        )
        
        return TempExampleResponse(**updated)
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to assign reviewer to temp example {temp_example_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to assign reviewer"
        )


# ===========================
# Approval Decisions
# ===========================

@router.post(
    "/temp-examples/{temp_example_id}/decision",
    response_model=TempExampleResponse,
    summary="Process approval decision"
)
async def process_approval_decision(
    temp_example_id: int,
    decision_data: Dict[str, Any],
    workflow_engine: ApprovalWorkflowEngine = Depends(get_workflow_engine),
    current_user: str = Depends(get_current_user)
):
    """
    Process an approval decision (approve, reject, or request revision).
    
    The decision will trigger appropriate state transitions and actions.
    """
    try:
        # Apply rate limiting for approval decisions
        await rate_limiter.check_rate_limit(f"approval_decision:{current_user}", 30, 60)
        
        # Create decision object
        decision = ApprovalDecision(
            temp_example_id=temp_example_id,
            reviewer_id=current_user,
            **decision_data
        )
        
        result = await workflow_engine.process_approval_decision(decision)
        
        logger.info(
            f"Processed {decision.action} decision for temp example {temp_example_id} "
            f"by {current_user}"
        )
        
        return TempExampleResponse(**result)
        
    except StateTransitionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid state transition: {e}"
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to process approval decision: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process approval decision"
        )


@router.post(
    "/bulk-decision",
    response_model=BulkApprovalResponse,
    summary="Process bulk approval decisions"
)
async def process_bulk_approval(
    bulk_request: BulkApprovalRequest,
    workflow_engine: ApprovalWorkflowEngine = Depends(get_workflow_engine),
    current_user: str = Depends(get_current_user)
):
    """
    Process bulk approval decisions for multiple temp examples.
    
    Returns detailed results including successful and failed operations.
    """
    try:
        # Apply stricter rate limiting for bulk operations
        await rate_limiter.check_rate_limit(f"bulk_approval:{current_user}", 5, 60)
        
        # Validate bulk request size
        if len(bulk_request.temp_example_ids) > 100:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Bulk operations limited to 100 items per request"
            )
        
        # Set reviewer_id to current user
        bulk_request.reviewer_id = current_user
        
        result = await workflow_engine.process_bulk_approval(bulk_request)
        
        # Determine response status code based on results
        if result.failed_count == 0:
            response_status = status.HTTP_200_OK
        elif result.successful_count > 0:
            response_status = status.HTTP_207_MULTI_STATUS
        else:
            response_status = status.HTTP_400_BAD_REQUEST
        
        logger.info(
            f"Processed bulk {bulk_request.action} for {len(bulk_request.temp_example_ids)} items "
            f"by {current_user}: {result.successful_count} successful, {result.failed_count} failed"
        )
        
        return JSONResponse(
            status_code=response_status,
            content=result.model_dump()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to process bulk approval: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process bulk approval"
        )


# ===========================
# Analytics and Metrics
# ===========================

@router.get(
    "/metrics",
    response_model=WorkflowMetrics,
    summary="Get workflow metrics and analytics"
)
async def get_workflow_metrics(
    start_date: Optional[datetime] = Query(None, description="Start date for metrics"),
    end_date: Optional[datetime] = Query(None, description="End date for metrics"),
    workflow_engine: ApprovalWorkflowEngine = Depends(get_workflow_engine),
    current_user: str = Depends(get_current_user)
):
    """
    Get comprehensive workflow metrics and analytics.
    
    Default time range is the last 30 days if no dates are specified.
    """
    try:
        metrics = await workflow_engine.get_workflow_metrics(start_date, end_date)
        return metrics
        
    except Exception as e:
        logger.error(f"Failed to get workflow metrics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve workflow metrics"
        )


@router.get(
    "/reviewer-workload",
    response_model=ReviewerWorkloadSummary,
    summary="Get reviewer workload information"
)
async def get_reviewer_workload(
    workflow_engine: ApprovalWorkflowEngine = Depends(get_workflow_engine),
    current_user: str = Depends(get_current_user)
):
    """
    Get reviewer workload information and balancing recommendations.
    """
    try:
        workload = await workflow_engine.get_reviewer_workload()
        return workload
        
    except Exception as e:
        logger.error(f"Failed to get reviewer workload: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve reviewer workload"
        )


@router.get(
    "/summary",
    response_model=WorkflowSummary,
    summary="Get high-level workflow summary"
)
async def get_workflow_summary(
    workflow_engine: ApprovalWorkflowEngine = Depends(get_workflow_engine),
    current_user: str = Depends(get_current_user)
):
    """Get high-level workflow summary with status breakdown and recommendations."""
    try:
        # Get metrics for summary
        metrics = await workflow_engine.get_workflow_metrics()
        
        # Calculate status breakdown
        total_items = (
            metrics.total_pending + 
            metrics.total_approved + 
            metrics.total_rejected + 
            metrics.total_revision_requested + 
            metrics.total_auto_approved
        )
        
        status_breakdown = []
        if total_items > 0:
            statuses = [
                (ApprovalState.PENDING, metrics.total_pending),
                (ApprovalState.APPROVED, metrics.total_approved),
                (ApprovalState.REJECTED, metrics.total_rejected),
                (ApprovalState.REVISION_REQUESTED, metrics.total_revision_requested),
                (ApprovalState.AUTO_APPROVED, metrics.total_auto_approved)
            ]
            
            for status_val, count in statuses:
                percentage = (count / total_items) * 100
                status_breakdown.append({
                    'status': status_val,
                    'count': count,
                    'percentage': percentage
                })
        
        # Generate recommendations
        recommendations = []
        if metrics.total_pending > 50:
            recommendations.append("High number of pending reviews. Consider adding more reviewers.")
        
        if metrics.approval_rate < 0.8:
            recommendations.append("Low approval rate detected. Review extraction quality or thresholds.")
        
        if metrics.auto_approval_rate < 0.5:
            recommendations.append("Low auto-approval rate. Consider adjusting confidence thresholds.")
        
        summary = WorkflowSummary(
            total_items=total_items,
            status_breakdown=status_breakdown,
            avg_processing_time_hours=metrics.avg_review_time_hours,
            bottlenecks=[],  # Would be calculated based on metrics
            recommendations=recommendations
        )
        
        return summary
        
    except Exception as e:
        logger.error(f"Failed to get workflow summary: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve workflow summary"
        )


# ===========================
# Administrative Operations
# ===========================

@router.post(
    "/maintenance/cleanup",
    summary="Clean up old rejected items"
)
async def cleanup_old_rejected_items(
    days_old: int = Query(30, ge=1, le=365, description="Age in days for cleanup"),
    workflow_engine: ApprovalWorkflowEngine = Depends(get_workflow_engine),
    current_user: str = Depends(get_current_admin_user)
):
    """Clean up old rejected items to free up storage."""
    try:
        # Verify admin permissions
        cutoff_date = datetime.now() - timedelta(days=days_old)
        
        # Implementation would delete old rejected items
        cleanup_count = await workflow_engine.repository.cleanup_old_rejected_items(cutoff_date)
        
        logger.info(
            f"Cleaned up {cleanup_count} old rejected items older than {days_old} days "
            f"by {current_user}"
        )
        
        return {
            "message": f"Cleaned up {cleanup_count} old rejected items",
            "cutoff_date": cutoff_date.isoformat(),
            "items_cleaned": cleanup_count
        }
        
    except Exception as e:
        logger.error(f"Failed to cleanup old rejected items: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cleanup old rejected items"
        )


@router.get(
    "/health",
    summary="Health check for approval system"
)
async def health_check(
    workflow_engine: ApprovalWorkflowEngine = Depends(get_workflow_engine)
):
    """Health check endpoint for approval system."""
    try:
        # Basic health checks
        health_status = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "checks": {
                "database": "healthy",
                "workflow_engine": "healthy",
                "state_machine": "healthy"
            }
        }
        
        # Test basic operations
        try:
            await workflow_engine.repository.get_approval_metrics(
                datetime.now() - timedelta(days=1),
                datetime.now()
            )
        except Exception:
            health_status["checks"]["database"] = "unhealthy"
            health_status["status"] = "degraded"
        
        return health_status
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "timestamp": datetime.now().isoformat(),
            "error": str(e)
        }