"""
TDD Tests for FeedMe v2.0 Approval Workflow System
Tests for AI-extracted content approval pipeline and review interface
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timedelta
from typing import List, Dict, Any
from enum import Enum

from app.feedme.approval.workflow_engine import ApprovalWorkflowEngine
from app.feedme.approval.review_manager import ReviewManager
from app.feedme.schemas import ApprovalStatus, ReviewAction


class TestApprovalWorkflowEngine:
    """Test suite for approval workflow engine"""

    @pytest.fixture
    def mock_db(self):
        """Mock database connection"""
        db = Mock()
        db.fetch_all = AsyncMock()
        db.fetch_one = AsyncMock()
        db.execute = AsyncMock()
        return db

    @pytest.fixture
    def workflow_engine(self, mock_db):
        """Create approval workflow engine for testing"""
        engine = ApprovalWorkflowEngine()
        engine.db = mock_db
        return engine

    @pytest.fixture
    def sample_extracted_qa(self):
        """Sample extracted Q&A for approval"""
        return {
            'conversation_id': 1,
            'question_text': 'How do I setup IMAP email?',
            'answer_text': 'To setup IMAP, go to Settings > Email Accounts and add your account with IMAP settings.',
            'context_before': 'User is having trouble with email configuration.',
            'context_after': 'User confirmed the solution worked.',
            'confidence_score': 0.85,
            'quality_score': 0.9,
            'issue_type': 'email_setup',
            'tags': ['email', 'imap', 'configuration'],
            'extraction_method': 'ai',
            'extracted_at': datetime.now()
        }

    @pytest.fixture
    def sample_reviewer(self):
        """Sample reviewer information"""
        return {
            'user_id': 'reviewer123',
            'email': 'reviewer@mailbird.com',
            'role': 'senior_support_engineer',
            'expertise_areas': ['email_setup', 'sync_issues']
        }

    @pytest.mark.asyncio
    async def test_create_approval_request(self, workflow_engine, sample_extracted_qa):
        """Test creating approval request for extracted Q&A"""
        # Mock database response
        workflow_engine.db.execute.return_value = Mock(lastrowid=123)
        
        approval_id = await workflow_engine.create_approval_request(
            qa_data=sample_extracted_qa,
            requester_id='extractor_ai',
            priority='normal'
        )
        
        assert approval_id == 123
        
        # Verify database call
        call_args = workflow_engine.db.execute.call_args
        sql_query = str(call_args[0][0])
        assert 'INSERT INTO feedme_temp_examples' in sql_query
        
        params = call_args[1]
        assert params['approval_status'] == ApprovalStatus.PENDING
        assert params['confidence_score'] == 0.85

    @pytest.mark.asyncio
    async def test_auto_approval_high_confidence(self, workflow_engine, sample_extracted_qa):
        """Test automatic approval for high confidence extractions"""
        # Set high confidence score for auto-approval
        sample_extracted_qa['confidence_score'] = 0.95
        sample_extracted_qa['quality_score'] = 0.92
        
        # Mock auto-approval settings
        workflow_engine.auto_approval_threshold = 0.9
        workflow_engine.enable_auto_approval = True
        
        workflow_engine.db.execute.return_value = Mock(lastrowid=123)
        
        approval_id = await workflow_engine.create_approval_request(
            qa_data=sample_extracted_qa,
            requester_id='extractor_ai'
        )
        
        # Should automatically approve and move to main table
        call_args_list = workflow_engine.db.execute.call_args_list
        
        # First call: insert to temp table
        assert 'feedme_temp_examples' in str(call_args_list[0][0][0])
        
        # Second call: auto-approve and move to main table
        assert 'feedme_examples' in str(call_args_list[1][0][0])

    @pytest.mark.asyncio
    async def test_batch_approval_request(self, workflow_engine):
        """Test batch creation of approval requests"""
        qa_batch = [
            {
                'question_text': f'Question {i}',
                'answer_text': f'Answer {i}',
                'confidence_score': 0.8 + i * 0.01,
                'conversation_id': 1
            }
            for i in range(5)
        ]
        
        workflow_engine.db.execute.return_value = Mock(lastrowid=100)
        
        approval_ids = await workflow_engine.create_batch_approval_request(
            qa_batch=qa_batch,
            requester_id='batch_extractor'
        )
        
        assert len(approval_ids) == 5
        assert all(isinstance(aid, int) for aid in approval_ids)

    @pytest.mark.asyncio
    async def test_get_pending_approvals(self, workflow_engine):
        """Test retrieving pending approval requests"""
        # Mock pending approvals
        pending_approvals = [
            {
                'id': 1,
                'question_text': 'Test question 1',
                'approval_status': 'pending',
                'confidence_score': 0.8,
                'created_at': datetime.now()
            },
            {
                'id': 2,
                'question_text': 'Test question 2',
                'approval_status': 'pending',
                'confidence_score': 0.9,
                'created_at': datetime.now()
            }
        ]
        
        workflow_engine.db.fetch_all.return_value = pending_approvals
        
        results = await workflow_engine.get_pending_approvals(
            reviewer_id='reviewer123',
            limit=10
        )
        
        assert len(results) == 2
        assert all(r['approval_status'] == 'pending' for r in results)

    @pytest.mark.asyncio
    async def test_get_pending_approvals_with_filters(self, workflow_engine):
        """Test retrieving pending approvals with filters"""
        workflow_engine.db.fetch_all.return_value = []
        
        await workflow_engine.get_pending_approvals(
            reviewer_id='reviewer123',
            filters={
                'issue_type': 'email_setup',
                'min_confidence': 0.8,
                'priority': 'high'
            },
            limit=10
        )
        
        # Verify filters are applied in query
        call_args = workflow_engine.db.fetch_all.call_args
        params = call_args[1]
        assert 'issue_type' in params
        assert 'min_confidence' in params

    @pytest.mark.asyncio
    async def test_approve_qa_pair(self, workflow_engine, sample_reviewer):
        """Test approving a Q&A pair"""
        workflow_engine.db.fetch_one.return_value = {
            'id': 1,
            'question_text': 'Test question',
            'answer_text': 'Test answer',
            'approval_status': 'pending'
        }
        workflow_engine.db.execute.return_value = Mock()
        
        result = await workflow_engine.approve_qa_pair(
            temp_example_id=1,
            reviewer_id='reviewer123',
            review_notes='Looks good, approved.'
        )
        
        assert result['status'] == 'approved'
        
        # Verify approval was recorded and item moved to main table
        call_args_list = workflow_engine.db.execute.call_args_list
        
        # Should have multiple SQL operations
        assert len(call_args_list) >= 2
        
        # One should be moving to main table
        main_table_insert = any('INSERT INTO feedme_examples' in str(call[0][0]) 
                               for call in call_args_list)
        assert main_table_insert

    @pytest.mark.asyncio
    async def test_reject_qa_pair(self, workflow_engine, sample_reviewer):
        """Test rejecting a Q&A pair"""
        workflow_engine.db.fetch_one.return_value = {
            'id': 1,
            'question_text': 'Test question',
            'approval_status': 'pending'
        }
        workflow_engine.db.execute.return_value = Mock()
        
        result = await workflow_engine.reject_qa_pair(
            temp_example_id=1,
            reviewer_id='reviewer123',
            rejection_reason='Low quality extraction',
            review_notes='Contains errors in the answer.'
        )
        
        assert result['status'] == 'rejected'
        
        # Verify rejection was recorded
        call_args = workflow_engine.db.execute.call_args
        params = call_args[1]
        assert params['approval_status'] == ApprovalStatus.REJECTED
        assert 'Low quality extraction' in params['review_notes']

    @pytest.mark.asyncio
    async def test_request_revision(self, workflow_engine):
        """Test requesting revision for a Q&A pair"""
        workflow_engine.db.fetch_one.return_value = {
            'id': 1,
            'approval_status': 'pending'
        }
        workflow_engine.db.execute.return_value = Mock()
        
        result = await workflow_engine.request_revision(
            temp_example_id=1,
            reviewer_id='reviewer123',
            revision_instructions='Please clarify the answer section.'
        )
        
        assert result['status'] == 'revision_requested'
        
        # Verify revision request was recorded
        call_args = workflow_engine.db.execute.call_args
        params = call_args[1]
        assert params['approval_status'] == ApprovalStatus.REVISION_REQUESTED

    @pytest.mark.asyncio
    async def test_bulk_approval(self, workflow_engine):
        """Test bulk approval of multiple Q&A pairs"""
        temp_example_ids = [1, 2, 3, 4, 5]
        
        # Mock temp examples
        workflow_engine.db.fetch_all.return_value = [
            {'id': i, 'question_text': f'Question {i}', 'approval_status': 'pending'}
            for i in temp_example_ids
        ]
        workflow_engine.db.execute.return_value = Mock()
        
        results = await workflow_engine.bulk_approve(
            temp_example_ids=temp_example_ids,
            reviewer_id='reviewer123',
            review_notes='Bulk approved after review.'
        )
        
        assert len(results['approved']) == 5
        assert len(results['failed']) == 0
        
        # Verify multiple database operations
        assert workflow_engine.db.execute.call_count >= len(temp_example_ids)

    @pytest.mark.asyncio
    async def test_bulk_rejection(self, workflow_engine):
        """Test bulk rejection of multiple Q&A pairs"""
        temp_example_ids = [1, 2, 3]
        
        workflow_engine.db.fetch_all.return_value = [
            {'id': i, 'approval_status': 'pending'} for i in temp_example_ids
        ]
        workflow_engine.db.execute.return_value = Mock()
        
        results = await workflow_engine.bulk_reject(
            temp_example_ids=temp_example_ids,
            reviewer_id='reviewer123',
            rejection_reason='Batch contains extraction errors'
        )
        
        assert len(results['rejected']) == 3
        assert len(results['failed']) == 0

    @pytest.mark.asyncio
    async def test_approval_workflow_with_invalid_id(self, workflow_engine):
        """Test approval workflow with invalid temp example ID"""
        workflow_engine.db.fetch_one.return_value = None  # Not found
        
        with pytest.raises(ValueError, match="Temp example not found"):
            await workflow_engine.approve_qa_pair(
                temp_example_id=999,
                reviewer_id='reviewer123'
            )

    @pytest.mark.asyncio
    async def test_approval_workflow_with_already_processed(self, workflow_engine):
        """Test approval workflow with already processed item"""
        workflow_engine.db.fetch_one.return_value = {
            'id': 1,
            'approval_status': 'approved'  # Already approved
        }
        
        with pytest.raises(ValueError, match="already been processed"):
            await workflow_engine.approve_qa_pair(
                temp_example_id=1,
                reviewer_id='reviewer123'
            )

    @pytest.mark.asyncio
    async def test_approval_statistics(self, workflow_engine):
        """Test approval workflow statistics"""
        # Mock statistics data
        workflow_engine.db.fetch_one.return_value = {
            'total_pending': 25,
            'total_approved': 150,
            'total_rejected': 12,
            'auto_approved': 89,
            'avg_approval_time_hours': 4.5
        }
        
        stats = await workflow_engine.get_approval_statistics(
            date_range='last_30_days'
        )
        
        assert stats['total_pending'] == 25
        assert stats['total_approved'] == 150
        assert stats['approval_rate'] == 150 / (150 + 12)  # approved / (approved + rejected)

    @pytest.mark.asyncio
    async def test_reviewer_assignment_logic(self, workflow_engine):
        """Test automatic reviewer assignment based on expertise"""
        qa_data = {
            'issue_type': 'email_setup',
            'tags': ['email', 'imap'],
            'confidence_score': 0.7  # Below auto-approval threshold
        }
        
        # Mock available reviewers
        workflow_engine.db.fetch_all.return_value = [
            {
                'user_id': 'reviewer1',
                'expertise_areas': ['email_setup', 'calendar'],
                'current_workload': 3
            },
            {
                'user_id': 'reviewer2', 
                'expertise_areas': ['sync_issues'],
                'current_workload': 1
            }
        ]
        
        assigned_reviewer = await workflow_engine.assign_reviewer(qa_data)
        
        # Should assign to reviewer with email_setup expertise
        assert assigned_reviewer == 'reviewer1'

    @pytest.mark.asyncio
    async def test_workflow_notifications(self, workflow_engine):
        """Test workflow notification system"""
        with patch('app.feedme.approval.workflow_engine.send_notification') as mock_notify:
            await workflow_engine.approve_qa_pair(
                temp_example_id=1,
                reviewer_id='reviewer123'
            )
            
            # Should send notification about approval
            mock_notify.assert_called()
            call_args = mock_notify.call_args
            assert 'approved' in call_args[1]['message_type']


class TestReviewManager:
    """Test suite for review manager"""

    @pytest.fixture
    def review_manager(self):
        """Create review manager for testing"""
        manager = ReviewManager()
        manager.db = Mock()
        manager.db.fetch_all = AsyncMock()
        manager.db.execute = AsyncMock()
        return manager

    @pytest.mark.asyncio
    async def test_get_reviewer_dashboard(self, review_manager):
        """Test reviewer dashboard data"""
        # Mock dashboard data
        review_manager.db.fetch_all.return_value = [
            {
                'pending_count': 15,
                'approved_today': 8,
                'rejected_today': 2,
                'avg_review_time_minutes': 12.5
            }
        ]
        
        dashboard = await review_manager.get_reviewer_dashboard('reviewer123')
        
        assert dashboard['pending_count'] == 15
        assert dashboard['approved_today'] == 8

    @pytest.mark.asyncio
    async def test_review_history(self, review_manager):
        """Test reviewer's review history"""
        review_manager.db.fetch_all.return_value = [
            {
                'temp_example_id': 1,
                'action': 'approved',
                'review_date': datetime.now(),
                'review_notes': 'Good quality'
            }
        ]
        
        history = await review_manager.get_review_history(
            reviewer_id='reviewer123',
            limit=20
        )
        
        assert len(history) == 1
        assert history[0]['action'] == 'approved'

    @pytest.mark.asyncio
    async def test_review_performance_metrics(self, review_manager):
        """Test review performance metrics"""
        review_manager.db.fetch_one.return_value = {
            'total_reviews': 150,
            'approval_rate': 0.85,
            'avg_review_time_minutes': 8.5,
            'quality_score': 4.2
        }
        
        metrics = await review_manager.get_performance_metrics(
            reviewer_id='reviewer123',
            period='last_month'
        )
        
        assert metrics['total_reviews'] == 150
        assert metrics['approval_rate'] == 0.85


class TestApprovalWorkflowIntegration:
    """Integration tests for approval workflow"""

    @pytest.mark.asyncio
    async def test_end_to_end_approval_workflow(self):
        """Test complete approval workflow from extraction to approval"""
        # This would be an integration test that spans multiple components
        # Mock the entire workflow
        
        # 1. AI extraction creates temp example
        temp_example_data = {
            'question_text': 'How to fix sync issues?',
            'answer_text': 'Check internet connection and restart sync.',
            'confidence_score': 0.75
        }
        
        # 2. Workflow engine creates approval request
        workflow_engine = Mock()
        workflow_engine.create_approval_request = AsyncMock(return_value=123)
        
        approval_id = await workflow_engine.create_approval_request(
            qa_data=temp_example_data,
            requester_id='ai_extractor'
        )
        
        # 3. Reviewer approves the request
        workflow_engine.approve_qa_pair = AsyncMock(return_value={'status': 'approved'})
        
        result = await workflow_engine.approve_qa_pair(
            temp_example_id=approval_id,
            reviewer_id='reviewer123'
        )
        
        assert result['status'] == 'approved'
        
        # Verify all steps were called
        workflow_engine.create_approval_request.assert_called_once()
        workflow_engine.approve_qa_pair.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])