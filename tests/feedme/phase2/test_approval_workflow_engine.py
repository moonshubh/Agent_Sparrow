"""
TDD Tests for FeedMe v2.0 Approval Workflow Engine
Tests for state machine, workflow orchestration, and business logic
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from typing import List, Dict, Any
from datetime import datetime, timedelta

import asyncio

from app.feedme.approval.workflow_engine import (
    ApprovalWorkflowEngine,
    WorkflowTransition
)
from app.feedme.approval.state_machine import (
    ApprovalStateMachine,
    ApprovalState,
    ApprovalAction,
    StateTransitionError
)
from app.feedme.approval.schemas import (
    TempExampleCreate,
    TempExampleUpdate,
    ApprovalDecision,
    BulkApprovalRequest,
    WorkflowMetrics,
    WorkflowConfig
)


class TestApprovalWorkflowEngine:
    """Test suite for approval workflow engine"""

    @pytest.fixture
    def mock_repository(self):
        """Mock repository for testing"""
        repo = Mock()
        repo.create_temp_example = AsyncMock()
        repo.update_temp_example = AsyncMock()
        repo.get_temp_example = AsyncMock()
        repo.get_temp_examples_by_status = AsyncMock()
        repo.bulk_update_temp_examples = AsyncMock()
        repo.create_review_history = AsyncMock()
        return repo

    @pytest.fixture
    def mock_embedding_service(self):
        """Mock embedding service for testing"""
        service = Mock()
        service.generate_embeddings = AsyncMock()
        return service

    @pytest.fixture
    def workflow_config(self):
        """Create workflow configuration for testing"""
        return WorkflowConfig(
            auto_approval_threshold=0.9,
            high_confidence_threshold=0.8,
            require_review_threshold=0.6,
            batch_size=10,
            max_pending_per_reviewer=20,
            enable_auto_assignment=True
        )

    @pytest.fixture
    def workflow_engine(self, mock_repository, mock_embedding_service, workflow_config):
        """Create workflow engine for testing"""
        engine = ApprovalWorkflowEngine(
            repository=mock_repository,
            embedding_service=mock_embedding_service,
            config=workflow_config
        )
        return engine

    @pytest.fixture
    def sample_temp_example_data(self):
        """Sample temp example data"""
        return {
            'conversation_id': 1,
            'question_text': 'How do I configure IMAP settings?',
            'answer_text': 'Go to Settings > Email Accounts and add your server details...',
            'context_before': 'User is having trouble with email setup',
            'context_after': 'Problem was resolved successfully',
            'extraction_confidence': 0.95,
            'ai_model_used': 'gemini-2.5-pro'
        }

    def test_workflow_engine_initialization(self, workflow_engine, workflow_config):
        """Test workflow engine initialization"""
        assert workflow_engine.config == workflow_config
        assert isinstance(workflow_engine.state_machine, ApprovalStateMachine)
        assert workflow_engine.repository is not None
        assert workflow_engine.embedding_service is not None

    async def test_create_temp_example_high_confidence_auto_approval(
        self, workflow_engine, sample_temp_example_data
    ):
        """Test creation of temp example with high confidence for auto-approval"""
        # Setup
        sample_temp_example_data['extraction_confidence'] = 0.95
        workflow_engine.repository.create_temp_example.return_value = {'id': 1, **sample_temp_example_data}
        workflow_engine.embedding_service.generate_embeddings.return_value = {
            'question_embedding': [0.1] * 384,
            'answer_embedding': [0.2] * 384,
            'combined_embedding': [0.15] * 384
        }

        # Execute
        result = await workflow_engine.create_temp_example(
            TempExampleCreate(**sample_temp_example_data)
        )

        # Verify auto-approval logic
        assert result['auto_approved'] == True
        assert result['approval_status'] == ApprovalState.AUTO_APPROVED.value
        assert result['auto_approval_reason'] == 'High confidence extraction (0.95 >= 0.9)'

        # Verify embeddings were generated
        workflow_engine.embedding_service.generate_embeddings.assert_called_once()

        # Verify repository calls
        workflow_engine.repository.create_temp_example.assert_called_once()

    async def test_create_temp_example_medium_confidence_requires_review(
        self, workflow_engine, sample_temp_example_data
    ):
        """Test creation of temp example with medium confidence requiring review"""
        # Setup
        sample_temp_example_data['extraction_confidence'] = 0.75
        workflow_engine.repository.create_temp_example.return_value = {'id': 1, **sample_temp_example_data}
        workflow_engine.embedding_service.generate_embeddings.return_value = {
            'question_embedding': [0.1] * 384,
            'answer_embedding': [0.2] * 384,
            'combined_embedding': [0.15] * 384
        }

        # Execute
        result = await workflow_engine.create_temp_example(
            TempExampleCreate(**sample_temp_example_data)
        )

        # Verify requires review
        assert result['auto_approved'] == False
        assert result['approval_status'] == ApprovalState.PENDING.value
        assert result['priority'] == 'normal'  # Medium confidence gets normal priority

        # Verify embeddings were generated
        workflow_engine.embedding_service.generate_embeddings.assert_called_once()

    async def test_create_temp_example_low_confidence_high_priority_review(
        self, workflow_engine, sample_temp_example_data
    ):
        """Test creation of temp example with low confidence requiring high priority review"""
        # Setup
        sample_temp_example_data['extraction_confidence'] = 0.5
        workflow_engine.repository.create_temp_example.return_value = {'id': 1, **sample_temp_example_data}
        workflow_engine.embedding_service.generate_embeddings.return_value = {
            'question_embedding': [0.1] * 384,
            'answer_embedding': [0.2] * 384,
            'combined_embedding': [0.15] * 384
        }

        # Execute
        result = await workflow_engine.create_temp_example(
            TempExampleCreate(**sample_temp_example_data)
        )

        # Verify high priority review
        assert result['auto_approved'] == False
        assert result['approval_status'] == ApprovalState.PENDING.value
        assert result['priority'] == 'high'  # Low confidence gets high priority

    async def test_assign_reviewer_automatic_assignment(self, workflow_engine):
        """Test automatic reviewer assignment based on workload"""
        # Setup
        temp_example_id = 1
        available_reviewers = ['reviewer1@example.com', 'reviewer2@example.com']
        
        # Mock reviewer workload
        workflow_engine.repository.get_reviewer_workload = AsyncMock(return_value={
            'reviewer1@example.com': 5,
            'reviewer2@example.com': 3
        })
        workflow_engine.repository.update_temp_example = AsyncMock()

        # Execute
        assigned_reviewer = await workflow_engine.assign_reviewer(
            temp_example_id, available_reviewers
        )

        # Verify least loaded reviewer is assigned
        assert assigned_reviewer == 'reviewer2@example.com'  # Has lower workload (3 vs 5)
        
        # Verify database update
        workflow_engine.repository.update_temp_example.assert_called_once_with(
            temp_example_id, {'assigned_reviewer': 'reviewer2@example.com'}
        )

    async def test_assign_reviewer_manual_assignment(self, workflow_engine):
        """Test manual reviewer assignment"""
        # Setup
        temp_example_id = 1
        specific_reviewer = 'specific@example.com'
        workflow_engine.repository.update_temp_example = AsyncMock()

        # Execute
        assigned_reviewer = await workflow_engine.assign_reviewer(
            temp_example_id, specific_reviewer
        )

        # Verify specific reviewer is assigned
        assert assigned_reviewer == specific_reviewer
        
        # Verify database update
        workflow_engine.repository.update_temp_example.assert_called_once_with(
            temp_example_id, {'assigned_reviewer': specific_reviewer}
        )

    async def test_approve_temp_example_success(self, workflow_engine):
        """Test successful approval of temp example"""
        # Setup
        temp_example_data = {
            'id': 1,
            'approval_status': ApprovalState.PENDING.value,
            'question_text': 'Test question',
            'answer_text': 'Test answer',
            'conversation_id': 1
        }
        
        approval_decision = ApprovalDecision(
            temp_example_id=1,
            action=ApprovalAction.APPROVE,
            reviewer_id='reviewer@example.com',
            review_notes='Good quality Q&A pair',
            confidence_assessment=0.9
        )

        workflow_engine.repository.get_temp_example.return_value = temp_example_data
        workflow_engine.repository.update_temp_example = AsyncMock()
        workflow_engine.repository.create_review_history = AsyncMock()
        workflow_engine.repository.move_to_production = AsyncMock()

        # Execute
        result = await workflow_engine.process_approval_decision(approval_decision)

        # Verify state transition
        assert result['approval_status'] == ApprovalState.APPROVED.value
        assert result['reviewer_id'] == 'reviewer@example.com'

        # Verify review history creation
        workflow_engine.repository.create_review_history.assert_called_once()

        # Verify move to production
        workflow_engine.repository.move_to_production.assert_called_once_with(1)

    async def test_reject_temp_example_with_reason(self, workflow_engine):
        """Test rejection of temp example with reason"""
        # Setup
        temp_example_data = {
            'id': 1,
            'approval_status': ApprovalState.PENDING.value,
            'question_text': 'Unclear question',
            'answer_text': 'Vague answer'
        }
        
        approval_decision = ApprovalDecision(
            temp_example_id=1,
            action=ApprovalAction.REJECT,
            reviewer_id='reviewer@example.com',
            review_notes='Question is too vague and answer lacks detail',
            rejection_reason='poor_quality'
        )

        workflow_engine.repository.get_temp_example.return_value = temp_example_data
        workflow_engine.repository.update_temp_example = AsyncMock()
        workflow_engine.repository.create_review_history = AsyncMock()

        # Execute
        result = await workflow_engine.process_approval_decision(approval_decision)

        # Verify state transition
        assert result['approval_status'] == ApprovalState.REJECTED.value
        assert result['rejection_reason'] == 'poor_quality'

        # Verify review history creation
        workflow_engine.repository.create_review_history.assert_called_once()

    async def test_request_revision_with_instructions(self, workflow_engine):
        """Test revision request with instructions"""
        # Setup
        temp_example_data = {
            'id': 1,
            'approval_status': ApprovalState.PENDING.value,
            'question_text': 'How to setup email?',
            'answer_text': 'Check settings'
        }
        
        approval_decision = ApprovalDecision(
            temp_example_id=1,
            action=ApprovalAction.REQUEST_REVISION,
            reviewer_id='reviewer@example.com',
            review_notes='Answer needs more detail',
            revision_instructions='Please provide step-by-step instructions for email setup'
        )

        workflow_engine.repository.get_temp_example.return_value = temp_example_data
        workflow_engine.repository.update_temp_example = AsyncMock()
        workflow_engine.repository.create_review_history = AsyncMock()

        # Execute
        result = await workflow_engine.process_approval_decision(approval_decision)

        # Verify state transition
        assert result['approval_status'] == ApprovalState.REVISION_REQUESTED.value
        assert result['revision_instructions'] == 'Please provide step-by-step instructions for email setup'

        # Verify review history creation
        workflow_engine.repository.create_review_history.assert_called_once()

    async def test_bulk_approval_operation(self, workflow_engine):
        """Test bulk approval of multiple temp examples"""
        # Setup
        bulk_request = BulkApprovalRequest(
            temp_example_ids=[1, 2, 3],
            action=ApprovalAction.APPROVE,
            reviewer_id='reviewer@example.com',
            review_notes='Bulk approval - all examples meet quality standards'
        )

        # Mock temp examples
        temp_examples = [
            {'id': 1, 'approval_status': ApprovalState.PENDING.value},
            {'id': 2, 'approval_status': ApprovalState.PENDING.value},
            {'id': 3, 'approval_status': ApprovalState.PENDING.value}
        ]

        workflow_engine.repository.get_temp_examples_by_ids = AsyncMock(return_value=temp_examples)
        workflow_engine.repository.bulk_update_temp_examples = AsyncMock()
        workflow_engine.repository.bulk_create_review_history = AsyncMock()
        workflow_engine.repository.bulk_move_to_production = AsyncMock()

        # Execute
        result = await workflow_engine.process_bulk_approval(bulk_request)

        # Verify bulk operations
        assert result['processed_count'] == 3
        assert result['successful_count'] == 3
        assert result['failed_count'] == 0

        # Verify bulk database operations were called
        workflow_engine.repository.bulk_update_temp_examples.assert_called_once()
        workflow_engine.repository.bulk_create_review_history.assert_called_once()
        workflow_engine.repository.bulk_move_to_production.assert_called_once()

    async def test_bulk_approval_with_failures(self, workflow_engine):
        """Test bulk approval with some failures"""
        # Setup
        bulk_request = BulkApprovalRequest(
            temp_example_ids=[1, 2, 3],
            action=ApprovalAction.APPROVE,
            reviewer_id='reviewer@example.com'
        )

        # Mock temp examples with one invalid state
        temp_examples = [
            {'id': 1, 'approval_status': ApprovalState.PENDING.value},
            {'id': 2, 'approval_status': ApprovalState.APPROVED.value},  # Already approved
            {'id': 3, 'approval_status': ApprovalState.PENDING.value}
        ]

        workflow_engine.repository.get_temp_examples_by_ids = AsyncMock(return_value=temp_examples)
        workflow_engine.repository.bulk_update_temp_examples = AsyncMock()
        workflow_engine.repository.bulk_create_review_history = AsyncMock()
        workflow_engine.repository.bulk_move_to_production = AsyncMock()

        # Execute
        result = await workflow_engine.process_bulk_approval(bulk_request)

        # Verify partial success
        assert result['processed_count'] == 3
        assert result['successful_count'] == 2  # Only 2 were in valid state
        assert result['failed_count'] == 1
        assert len(result['failures']) == 1
        assert result['failures'][0]['temp_example_id'] == 2

    async def test_get_workflow_metrics(self, workflow_engine):
        """Test workflow metrics calculation"""
        # Setup
        mock_metrics_data = {
            'total_pending': 25,
            'total_approved': 150,
            'total_rejected': 10,
            'total_revision_requested': 5,
            'avg_review_time_hours': 2.5,
            'auto_approval_rate': 0.75
        }

        workflow_engine.repository.get_approval_metrics = AsyncMock(return_value=mock_metrics_data)

        # Execute
        metrics = await workflow_engine.get_workflow_metrics()

        # Verify metrics calculation
        assert isinstance(metrics, WorkflowMetrics)
        assert metrics.total_pending == 25
        assert metrics.total_approved == 150
        assert metrics.approval_rate == 150 / (150 + 10)  # approved / (approved + rejected)
        assert metrics.avg_review_time_hours == 2.5

    async def test_error_handling_invalid_state_transition(self, workflow_engine):
        """Test error handling for invalid state transitions"""
        # Setup
        temp_example_data = {
            'id': 1,
            'approval_status': ApprovalState.APPROVED.value  # Already approved
        }
        
        approval_decision = ApprovalDecision(
            temp_example_id=1,
            action=ApprovalAction.APPROVE,  # Trying to approve again
            reviewer_id='reviewer@example.com'
        )

        workflow_engine.repository.get_temp_example.return_value = temp_example_data

        # Execute and verify exception
        with pytest.raises(StateTransitionError, match="Cannot transition from approved to approved"):
            await workflow_engine.process_approval_decision(approval_decision)

    async def test_performance_with_large_batch(self, workflow_engine):
        """Test performance with large batch operations"""
        # Setup large batch
        large_batch_ids = list(range(1, 101))  # 100 items
        bulk_request = BulkApprovalRequest(
            temp_example_ids=large_batch_ids,
            action=ApprovalAction.APPROVE,
            reviewer_id='reviewer@example.com'
        )

        # Mock large dataset
        temp_examples = [
            {'id': i, 'approval_status': ApprovalState.PENDING.value} 
            for i in large_batch_ids
        ]

        workflow_engine.repository.get_temp_examples_by_ids = AsyncMock(return_value=temp_examples)
        workflow_engine.repository.bulk_update_temp_examples = AsyncMock()
        workflow_engine.repository.bulk_create_review_history = AsyncMock()
        workflow_engine.repository.bulk_move_to_production = AsyncMock()

        # Execute with timing
        import time
        start_time = time.time()
        result = await workflow_engine.process_bulk_approval(bulk_request)
        processing_time = time.time() - start_time

        # Verify performance
        assert result['processed_count'] == 100
        assert processing_time < 5.0  # Should complete within 5 seconds
        
        # Verify batch processing was used
        workflow_engine.repository.bulk_update_temp_examples.assert_called_once()


class TestApprovalStateMachine:
    """Test suite for approval state machine"""

    @pytest.fixture
    def state_machine(self):
        """Create state machine for testing"""
        return ApprovalStateMachine()

    def test_valid_state_transitions(self, state_machine):
        """Test valid state transitions"""
        # Test all valid transitions
        valid_transitions = [
            (ApprovalState.PENDING, ApprovalAction.APPROVE, ApprovalState.APPROVED),
            (ApprovalState.PENDING, ApprovalAction.REJECT, ApprovalState.REJECTED),
            (ApprovalState.PENDING, ApprovalAction.REQUEST_REVISION, ApprovalState.REVISION_REQUESTED),
            (ApprovalState.REVISION_REQUESTED, ApprovalAction.APPROVE, ApprovalState.APPROVED),
            (ApprovalState.REVISION_REQUESTED, ApprovalAction.REJECT, ApprovalState.REJECTED),
            (ApprovalState.REVISION_REQUESTED, ApprovalAction.REQUEST_REVISION, ApprovalState.REVISION_REQUESTED)
        ]

        for current_state, action, expected_state in valid_transitions:
            result_state = state_machine.transition(current_state, action)
            assert result_state == expected_state

    def test_invalid_state_transitions(self, state_machine):
        """Test invalid state transitions"""
        # Test invalid transitions that should raise exceptions
        invalid_transitions = [
            (ApprovalState.APPROVED, ApprovalAction.APPROVE),
            (ApprovalState.APPROVED, ApprovalAction.REJECT),
            (ApprovalState.REJECTED, ApprovalAction.APPROVE),
            (ApprovalState.REJECTED, ApprovalAction.REJECT),
            (ApprovalState.AUTO_APPROVED, ApprovalAction.APPROVE)
        ]

        for current_state, action in invalid_transitions:
            with pytest.raises(StateTransitionError):
                state_machine.transition(current_state, action)

    def test_state_machine_validation(self, state_machine):
        """Test state machine validation"""
        # Test state validation
        assert state_machine.is_valid_state(ApprovalState.PENDING)
        assert state_machine.is_valid_state(ApprovalState.APPROVED)
        assert not state_machine.is_valid_state("invalid_state")

        # Test action validation
        assert state_machine.is_valid_action(ApprovalAction.APPROVE)
        assert state_machine.is_valid_action(ApprovalAction.REJECT)
        assert not state_machine.is_valid_action("invalid_action")

    def test_get_allowed_actions(self, state_machine):
        """Test getting allowed actions for current state"""
        # Test allowed actions for pending state
        pending_actions = state_machine.get_allowed_actions(ApprovalState.PENDING)
        expected_pending = {ApprovalAction.APPROVE, ApprovalAction.REJECT, ApprovalAction.REQUEST_REVISION}
        assert set(pending_actions) == expected_pending

        # Test allowed actions for final states
        approved_actions = state_machine.get_allowed_actions(ApprovalState.APPROVED)
        assert len(approved_actions) == 0  # No actions allowed from final state

        rejected_actions = state_machine.get_allowed_actions(ApprovalState.REJECTED)
        assert len(rejected_actions) == 0  # No actions allowed from final state


if __name__ == "__main__":
    pytest.main([__file__, "-v"])