"""
FeedMe v2.0 Approval Workflow Engine

Core workflow orchestration engine that manages the approval process for AI-extracted
content, including state transitions, reviewer assignment, and business logic.
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any, Union
import time

from .schemas import (
    TempExampleCreate,
    TempExampleUpdate,
    TempExampleResponse,
    ApprovalDecision,
    BulkApprovalRequest,
    BulkApprovalResponse,
    WorkflowMetrics,
    ReviewerWorkload,
    ReviewerWorkloadSummary,
    WorkflowConfig,
    ApprovalState,
    ApprovalAction,
    Priority
)
from .state_machine import ApprovalStateMachine, StateTransitionError
from ..repositories.optimized_repository import OptimizedFeedMeRepository
from ..embeddings.embedding_pipeline import FeedMeEmbeddingPipeline

logger = logging.getLogger(__name__)


class WorkflowTransition:
    """Represents a workflow state transition with metadata"""
    
    def __init__(self, from_state: ApprovalState, to_state: ApprovalState, 
                 action: ApprovalAction, timestamp: datetime, reviewer_id: str):
        self.from_state = from_state
        self.to_state = to_state
        self.action = action
        self.timestamp = timestamp
        self.reviewer_id = reviewer_id


class ApprovalWorkflowEngine:
    """
    Core workflow engine for managing approval processes.
    
    This engine orchestrates the entire approval workflow including:
    - Creating and processing temp examples
    - Managing state transitions
    - Assigning reviewers
    - Processing approval decisions
    - Bulk operations
    - Analytics and metrics
    """
    
    def __init__(
        self,
        repository: OptimizedFeedMeRepository,
        embedding_service: FeedMeEmbeddingPipeline,
        config: WorkflowConfig
    ):
        """
        Initialize the workflow engine.
        
        Args:
            repository: Database repository for data operations
            embedding_service: Service for generating embeddings
            config: Workflow configuration
        """
        self.repository = repository
        self.embedding_service = embedding_service
        self.config = config
        self.state_machine = ApprovalStateMachine()
        
        # Performance tracking
        self._metrics_cache = {}
        self._cache_timestamp = None
        self._cache_ttl = timedelta(minutes=5)

    async def create_temp_example(self, temp_example: TempExampleCreate) -> Dict[str, Any]:
        """
        Create a new temp example with automatic approval logic.
        
        Args:
            temp_example: Temp example data
            
        Returns:
            Created temp example with approval status
        """
        start_time = time.time()
        
        try:
            # Generate embeddings for the Q&A content
            embeddings = await self._generate_embeddings(temp_example)
            
            # Determine approval status based on confidence
            approval_status, auto_approved, auto_approval_reason, priority = (
                self._determine_approval_status(temp_example.extraction_confidence)
            )
            
            # Prepare data for database insertion
            temp_example_data = {
                **temp_example.model_dump(),
                **embeddings,
                'approval_status': approval_status.value,
                'auto_approved': auto_approved,
                'auto_approval_reason': auto_approval_reason,
                'priority': priority.value,
                'extraction_timestamp': datetime.now()
            }
            
            # Create in database
            created_example = await self.repository.create_temp_example(temp_example_data)
            
            # Log workflow event
            processing_time = (time.time() - start_time) * 1000
            logger.info(
                f"Created temp example {created_example['id']} with status {approval_status} "
                f"(confidence: {temp_example.extraction_confidence:.3f}, "
                f"processing_time: {processing_time:.1f}ms)"
            )
            
            # If auto-approved, immediately move to production
            if auto_approved:
                await self._move_to_production(created_example['id'])
            
            return created_example
            
        except Exception as e:
            logger.error(f"Failed to create temp example: {e}")
            raise

    async def assign_reviewer(
        self, 
        temp_example_id: int, 
        reviewer_id: Optional[Union[str, List[str]]] = None
    ) -> str:
        """
        Assign a reviewer to a temp example.
        
        Args:
            temp_example_id: ID of temp example to assign
            reviewer_id: Specific reviewer ID or list for auto-assignment
            
        Returns:
            Assigned reviewer ID
        """
        try:
            if isinstance(reviewer_id, str):
                # Manual assignment to specific reviewer
                assigned_reviewer = reviewer_id
            else:
                # Auto-assignment based on workload
                available_reviewers = reviewer_id or await self._get_available_reviewers()
                assigned_reviewer = await self._auto_assign_reviewer(available_reviewers)
            
            # Update database
            await self.repository.update_temp_example(
                temp_example_id, 
                {'assigned_reviewer': assigned_reviewer}
            )
            
            logger.info(f"Assigned reviewer {assigned_reviewer} to temp example {temp_example_id}")
            return assigned_reviewer
            
        except Exception as e:
            logger.error(f"Failed to assign reviewer to temp example {temp_example_id}: {e}")
            raise

    async def process_approval_decision(self, decision: ApprovalDecision) -> Dict[str, Any]:
        """
        Process an approval decision and update temp example state.
        
        Args:
            decision: Approval decision details
            
        Returns:
            Updated temp example data
        """
        start_time = time.time()
        
        try:
            # Get current temp example
            temp_example = await self.repository.get_temp_example(decision.temp_example_id)
            if not temp_example:
                raise ValueError(f"Temp example {decision.temp_example_id} not found")
            
            current_state = ApprovalState(temp_example['approval_status'])
            
            # Validate state transition
            new_state = self.state_machine.transition(current_state, decision.action)
            
            # Prepare update data
            update_data = {
                'approval_status': new_state.value,
                'reviewer_id': decision.reviewer_id,
                'reviewed_at': datetime.now(),
                'review_notes': decision.review_notes,
                'reviewer_confidence_score': decision.reviewer_confidence_score,
                'reviewer_usefulness_score': decision.reviewer_usefulness_score
            }
            
            # Add action-specific data
            if decision.action == ApprovalAction.REJECT:
                update_data['rejection_reason'] = decision.rejection_reason.value
            elif decision.action == ApprovalAction.REQUEST_REVISION:
                update_data['revision_instructions'] = decision.revision_instructions
            
            # Update temp example
            updated_example = await self.repository.update_temp_example(
                decision.temp_example_id, update_data
            )
            
            # Create review history record
            await self._create_review_history(decision, current_state, new_state)
            
            # Handle post-decision actions
            if decision.action == ApprovalAction.APPROVE:
                await self._move_to_production(decision.temp_example_id)
            elif decision.action == ApprovalAction.REQUEST_REVISION:
                await self._notify_revision_requested(decision.temp_example_id)
            
            processing_time = (time.time() - start_time) * 1000
            logger.info(
                f"Processed {decision.action} decision for temp example {decision.temp_example_id} "
                f"by {decision.reviewer_id} (processing_time: {processing_time:.1f}ms)"
            )
            
            return updated_example
            
        except StateTransitionError as e:
            logger.error(f"Invalid state transition for temp example {decision.temp_example_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to process approval decision: {e}")
            raise

    async def process_bulk_approval(self, bulk_request: BulkApprovalRequest) -> BulkApprovalResponse:
        """
        Process bulk approval operations for multiple temp examples.
        
        Args:
            bulk_request: Bulk approval request details
            
        Returns:
            Bulk operation results
        """
        start_time = time.time()
        
        try:
            # Get all temp examples
            temp_examples = await self.repository.get_temp_examples_by_ids(
                bulk_request.temp_example_ids
            )
            
            # Process in batches for performance
            batch_size = self.config.batch_size
            successful_count = 0
            failed_count = 0
            failures = []
            
            for i in range(0, len(temp_examples), batch_size):
                batch = temp_examples[i:i + batch_size]
                batch_results = await self._process_bulk_batch(batch, bulk_request)
                
                successful_count += batch_results['successful_count']
                failed_count += batch_results['failed_count']
                failures.extend(batch_results['failures'])
            
            processing_time = (time.time() - start_time) * 1000
            
            result = BulkApprovalResponse(
                processed_count=len(temp_examples),
                successful_count=successful_count,
                failed_count=failed_count,
                failures=failures,
                processing_time_ms=processing_time
            )
            
            logger.info(
                f"Processed bulk {bulk_request.action} for {len(bulk_request.temp_example_ids)} items: "
                f"{successful_count} successful, {failed_count} failed "
                f"(processing_time: {processing_time:.1f}ms)"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to process bulk approval: {e}")
            raise

    async def get_workflow_metrics(
        self, 
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> WorkflowMetrics:
        """
        Get workflow metrics and analytics.
        
        Args:
            start_date: Start date for metrics (default: 30 days ago)
            end_date: End date for metrics (default: now)
            
        Returns:
            Workflow metrics
        """
        # Use cache if recent
        if self._is_metrics_cache_valid():
            return self._metrics_cache
        
        try:
            # Set default date range
            end_date = end_date or datetime.now()
            start_date = start_date or (end_date - timedelta(days=30))
            
            # Get raw metrics from repository
            raw_metrics = await self.repository.get_approval_metrics(start_date, end_date)
            
            # Calculate derived metrics
            total_decisions = (
                raw_metrics['total_approved'] + 
                raw_metrics['total_rejected']
            )
            
            approval_rate = (
                raw_metrics['total_approved'] / total_decisions 
                if total_decisions > 0 else 0.0
            )
            
            rejection_rate = (
                raw_metrics['total_rejected'] / total_decisions 
                if total_decisions > 0 else 0.0
            )
            
            total_processed = (
                raw_metrics['total_approved'] + 
                raw_metrics['total_rejected'] + 
                raw_metrics['total_auto_approved']
            )
            
            auto_approval_rate = (
                raw_metrics['total_auto_approved'] / total_processed 
                if total_processed > 0 else 0.0
            )
            
            # Create metrics object
            metrics = WorkflowMetrics(
                total_pending=raw_metrics['total_pending'],
                total_approved=raw_metrics['total_approved'],
                total_rejected=raw_metrics['total_rejected'],
                total_revision_requested=raw_metrics['total_revision_requested'],
                total_auto_approved=raw_metrics['total_auto_approved'],
                approval_rate=approval_rate,
                rejection_rate=rejection_rate,
                auto_approval_rate=auto_approval_rate,
                avg_review_time_hours=raw_metrics.get('avg_review_time_hours'),
                median_review_time_hours=raw_metrics.get('median_review_time_hours'),
                avg_extraction_confidence=raw_metrics.get('avg_extraction_confidence'),
                avg_reviewer_confidence=raw_metrics.get('avg_reviewer_confidence'),
                reviewer_efficiency=raw_metrics.get('reviewer_efficiency', {}),
                period_start=start_date,
                period_end=end_date
            )
            
            # Cache the result
            self._metrics_cache = metrics
            self._cache_timestamp = datetime.now()
            
            return metrics
            
        except Exception as e:
            logger.error(f"Failed to get workflow metrics: {e}")
            raise

    async def get_reviewer_workload(self) -> ReviewerWorkloadSummary:
        """
        Get reviewer workload information and recommendations.
        
        Returns:
            Reviewer workload summary
        """
        try:
            # Get workload data from repository
            workload_data = await self.repository.get_reviewer_workload()
            
            # Create reviewer workload objects
            reviewers = []
            for reviewer_data in workload_data['reviewers']:
                reviewer = ReviewerWorkload(**reviewer_data)
                reviewers.append(reviewer)
            
            # Calculate summary statistics
            total_pending = sum(r.pending_count for r in reviewers)
            avg_workload = total_pending / len(reviewers) if reviewers else 0
            max_workload = max(r.pending_count for r in reviewers) if reviewers else 0
            min_workload = min(r.pending_count for r in reviewers) if reviewers else 0
            
            # Generate recommendations
            recommendations = self._generate_workload_recommendations(
                reviewers, avg_workload, max_workload
            )
            
            return ReviewerWorkloadSummary(
                reviewers=reviewers,
                total_pending=total_pending,
                avg_workload=avg_workload,
                max_workload=max_workload,
                min_workload=min_workload,
                recommendations=recommendations
            )
            
        except Exception as e:
            logger.error(f"Failed to get reviewer workload: {e}")
            raise

    # ===========================
    # Private Helper Methods
    # ===========================

    async def _generate_embeddings(self, temp_example: TempExampleCreate) -> Dict[str, List[float]]:
        """Generate embeddings for Q&A content"""
        try:
            qa_pair = {
                'question_text': temp_example.question_text,
                'answer_text': temp_example.answer_text,
                'context_before': temp_example.context_before or '',
                'context_after': temp_example.context_after or ''
            }
            
            embeddings = await self.embedding_service.generate_embeddings([qa_pair])
            return embeddings[0] if embeddings else {}
            
        except Exception as e:
            logger.error(f"Failed to generate embeddings: {e}")
            # Return empty embeddings on failure
            return {
                'question_embedding': [],
                'answer_embedding': [],
                'combined_embedding': []
            }

    def _determine_approval_status(
        self, 
        extraction_confidence: float
    ) -> tuple[ApprovalState, bool, Optional[str], Priority]:
        """Determine approval status based on extraction confidence"""
        
        if extraction_confidence >= self.config.auto_approval_threshold:
            return (
                ApprovalState.AUTO_APPROVED, 
                True, 
                f"High confidence extraction ({extraction_confidence:.2f} >= {self.config.auto_approval_threshold})",
                Priority.LOW
            )
        elif extraction_confidence >= self.config.high_confidence_threshold:
            return (
                ApprovalState.PENDING,
                False,
                None,
                Priority.NORMAL
            )
        elif extraction_confidence >= self.config.require_review_threshold:
            return (
                ApprovalState.PENDING,
                False,
                None,
                Priority.HIGH
            )
        else:
            return (
                ApprovalState.PENDING,
                False,
                None,
                Priority.URGENT
            )

    async def _auto_assign_reviewer(self, available_reviewers: List[str]) -> str:
        """Auto-assign reviewer based on workload"""
        if not available_reviewers:
            raise ValueError("No available reviewers for assignment")
        
        # Get current workload for all reviewers
        workload_data = await self.repository.get_reviewer_workload()
        reviewer_workloads = {
            r['reviewer_id']: r['pending_count'] 
            for r in workload_data['reviewers']
        }
        
        # Find reviewer with minimum workload
        min_workload = float('inf')
        selected_reviewer = available_reviewers[0]
        
        for reviewer in available_reviewers:
            workload = reviewer_workloads.get(reviewer, 0)
            if workload < min_workload:
                min_workload = workload
                selected_reviewer = reviewer
        
        return selected_reviewer

    async def _get_available_reviewers(self) -> List[str]:
        """Get list of available reviewers"""
        # This would typically query a user management system
        # For now, return a static list or query from configuration
        return [
            'reviewer1@mailbird.com',
            'reviewer2@mailbird.com',
            'reviewer3@mailbird.com'
        ]

    async def _create_review_history(
        self, 
        decision: ApprovalDecision,
        from_state: ApprovalState,
        to_state: ApprovalState
    ):
        """Create review history record"""
        history_data = {
            'temp_example_id': decision.temp_example_id,
            'reviewer_id': decision.reviewer_id,
            'action': decision.action.value,
            'review_notes': decision.review_notes,
            'confidence_assessment': decision.confidence_assessment,
            'time_spent_minutes': decision.time_spent_minutes,
            'previous_status': from_state.value,
            'new_status': to_state.value,
            'changes_made': {
                'action': decision.action.value,
                'reviewer_confidence_score': decision.reviewer_confidence_score,
                'reviewer_usefulness_score': decision.reviewer_usefulness_score,
                'rejection_reason': decision.rejection_reason.value if decision.rejection_reason else None,
                'revision_instructions': decision.revision_instructions
            }
        }
        
        await self.repository.create_review_history(history_data)

    async def _move_to_production(self, temp_example_id: int):
        """Move approved temp example to production examples table"""
        try:
            await self.repository.move_to_production(temp_example_id)
            logger.info(f"Moved temp example {temp_example_id} to production")
        except Exception as e:
            logger.error(f"Failed to move temp example {temp_example_id} to production: {e}")

    async def _notify_revision_requested(self, temp_example_id: int):
        """Send notification for revision request"""
        # This would integrate with a notification system
        logger.info(f"Revision requested for temp example {temp_example_id}")

    async def _process_bulk_batch(
        self, 
        batch: List[Dict], 
        bulk_request: BulkApprovalRequest
    ) -> Dict[str, Any]:
        """Process a batch of temp examples for bulk operations"""
        successful_count = 0
        failed_count = 0
        failures = []
        
        # Process each item in parallel
        tasks = []
        for temp_example in batch:
            decision = ApprovalDecision(
                temp_example_id=temp_example['id'],
                action=bulk_request.action,
                reviewer_id=bulk_request.reviewer_id,
                review_notes=bulk_request.review_notes,
                rejection_reason=bulk_request.rejection_reason,
                revision_instructions=bulk_request.revision_instructions
            )
            tasks.append(self._process_single_bulk_item(decision))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                failed_count += 1
                failures.append({
                    'temp_example_id': batch[i]['id'],
                    'error': str(result),
                    'current_status': batch[i]['approval_status']
                })
            else:
                successful_count += 1
        
        return {
            'successful_count': successful_count,
            'failed_count': failed_count,
            'failures': failures
        }

    async def _process_single_bulk_item(self, decision: ApprovalDecision) -> Dict[str, Any]:
        """Process a single item in bulk operation"""
        try:
            return await self.process_approval_decision(decision)
        except Exception as e:
            logger.error(f"Failed to process bulk item {decision.temp_example_id}: {e}")
            raise

    def _is_metrics_cache_valid(self) -> bool:
        """Check if metrics cache is still valid"""
        if not self._cache_timestamp or not self._metrics_cache:
            return False
        
        return datetime.now() - self._cache_timestamp < self._cache_ttl

    def _generate_workload_recommendations(
        self, 
        reviewers: List[ReviewerWorkload],
        avg_workload: float,
        max_workload: int
    ) -> List[str]:
        """Generate workload balancing recommendations"""
        recommendations = []
        
        if max_workload > self.config.max_pending_per_reviewer:
            recommendations.append(
                f"High workload detected: {max_workload} pending items for top reviewer. "
                f"Consider redistributing or adding more reviewers."
            )
        
        # Find overloaded reviewers
        overloaded = [r for r in reviewers if r.pending_count > avg_workload * 1.5]
        if overloaded:
            reviewer_ids = [r.reviewer_id for r in overloaded]
            recommendations.append(
                f"Reviewers with high workload: {', '.join(reviewer_ids)}. "
                f"Consider reassigning some pending items."
            )
        
        # Find underutilized reviewers
        underutilized = [r for r in reviewers if r.pending_count < avg_workload * 0.5]
        if underutilized and avg_workload > 1:
            reviewer_ids = [r.reviewer_id for r in underutilized]
            recommendations.append(
                f"Reviewers with low workload: {', '.join(reviewer_ids)}. "
                f"Consider assigning more items to these reviewers."
            )
        
        return recommendations