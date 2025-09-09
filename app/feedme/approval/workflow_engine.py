"""
FeedMe v3.0 Approval Workflow Engine - Supabase Only

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
from ..embeddings.embedding_pipeline import FeedMeEmbeddingPipeline
from app.db.supabase_client import get_supabase_client

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
        embedding_service: FeedMeEmbeddingPipeline,
        config: WorkflowConfig
    ):
        """
        Initialize the workflow engine.
        
        Args:
            embedding_service: Service for generating embeddings
            config: Workflow configuration
        """
        self._supabase_client = None
        self.embedding_service = embedding_service
        self.config = config
        self.state_machine = ApprovalStateMachine()
        
        # Performance tracking
        self._metrics_cache = {}
        self._cache_timestamp = None
        self._cache_ttl = timedelta(minutes=5)
    
    @property
    def supabase_client(self):
        """Lazy load Supabase client"""
        if self._supabase_client is None:
            self._supabase_client = get_supabase_client()
        return self._supabase_client

    async def create_temp_example(self, temp_example: TempExampleCreate) -> Dict[str, Any]:
        """
        Create a new temp example with automatic approval logic.
        
        Note: Temp examples not implemented in Supabase yet
        All examples go directly to production table
        """
        logger.warning("Temp examples not implemented in Supabase - creating directly in production")
        
        try:
            # Generate embeddings for the Q&A content
            embeddings = await self._generate_embeddings(temp_example)
            
            # Create example directly in Supabase
            example_data = {
                'conversation_id': temp_example.conversation_id,
                'question_text': temp_example.question_text,
                'answer_text': temp_example.answer_text,
                'context_before': temp_example.context_before,
                'context_after': temp_example.context_after,
                'question_embedding': embeddings['question_embedding'],
                'answer_embedding': embeddings['answer_embedding'],
                'combined_embedding': embeddings['combined_embedding'],
                'confidence_score': temp_example.confidence_score,
                'tags': temp_example.tags or [],
                'issue_type': temp_example.issue_type,
                'resolution_type': temp_example.resolution_type
            }
            
            # Insert into Supabase
            result = await self.supabase_client.insert_examples(
                conversation_id=temp_example.conversation_id,
                examples=[example_data]
            )
            
            return result[0] if result else {}
            
        except Exception as e:
            logger.error(f"Failed to create example: {e}")
            raise

    async def _generate_embeddings(self, temp_example: Union[TempExampleCreate, Dict[str, Any]]) -> Dict[str, Any]:
        """Generate embeddings for Q&A content"""
        if isinstance(temp_example, dict):
            question = temp_example.get('question_text', '')
            answer = temp_example.get('answer_text', '')
        else:
            question = temp_example.question_text
            answer = temp_example.answer_text
        
        # Use embedding service to generate embeddings
        embeddings = await self.embedding_service.generate_embeddings({
            'question': question,
            'answer': answer
        })
        
        return embeddings

    async def process_approval_decision(
        self,
        temp_example_id: int,
        decision: ApprovalDecision
    ) -> Dict[str, Any]:
        """
        Process approval decision for a temp example.
        
        Note: Direct approval in Supabase - no temp table
        """
        logger.warning("Approval workflow not fully implemented in Supabase")
        
        # For now, just update the example status
        if decision.action == ApprovalAction.APPROVE:
            # Example already in production table
            return {"status": "approved", "example_id": temp_example_id}
        else:
            # Delete rejected examples
            # TODO: Implement delete in Supabase client
            return {"status": "rejected", "example_id": temp_example_id}

    async def bulk_approve_examples(
        self,
        request: BulkApprovalRequest
    ) -> BulkApprovalResponse:
        """
        Process bulk approval of multiple examples.
        
        Note: Not fully implemented for Supabase
        """
        logger.warning("Bulk approval not fully implemented in Supabase")
        
        return BulkApprovalResponse(
            total_processed=0,
            approved=0,
            rejected=0,
            failed=0,
            processing_time_ms=0,
            errors=["Bulk approval not implemented in Supabase"]
        )

    async def get_workflow_metrics(self) -> WorkflowMetrics:
        """
        Get workflow performance metrics.
        
        Note: Limited metrics available without temp table
        """
        try:
            # Get basic stats from Supabase
            health_info = await self.supabase_client.health_check()
            
            return WorkflowMetrics(
                total_examples=health_info.get('stats', {}).get('total_examples', 0),
                pending_approval=0,  # No temp table
                approved_today=0,    # Would need date filtering
                rejected_today=0,    # Would need date filtering
                auto_approved=0,     # Not tracked
                avg_approval_time_hours=0.0,
                approval_rate=1.0,   # All auto-approved for now
                reviewer_workload=[]
            )
        except Exception as e:
            logger.error(f"Failed to get workflow metrics: {e}")
            return WorkflowMetrics(
                total_examples=0,
                pending_approval=0,
                approved_today=0,
                rejected_today=0,
                auto_approved=0,
                avg_approval_time_hours=0.0,
                approval_rate=0.0,
                reviewer_workload=[]
            )

    async def assign_reviewer(self, temp_example_id: int, reviewer_id: str) -> bool:
        """
        Assign a reviewer to a temp example.
        
        Note: Not implemented for Supabase
        """
        logger.warning("Reviewer assignment not implemented in Supabase")
        return False

    async def get_reviewer_workload(self, reviewer_id: str) -> ReviewerWorkloadSummary:
        """
        Get workload summary for a specific reviewer.
        
        Note: Not implemented for Supabase
        """
        logger.warning("Reviewer workload not implemented in Supabase")
        
        return ReviewerWorkloadSummary(
            reviewer_id=reviewer_id,
            pending_count=0,
            approved_today=0,
            rejected_today=0,
            avg_review_time_minutes=0.0,
            oldest_pending_hours=0.0
        )