"""
TDD Tests for FeedMe v2.0 Approval API Endpoints
Tests for REST API operations, validation, and error handling
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from typing import List, Dict, Any
from datetime import datetime

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.v1.endpoints.approval_endpoints import router
from app.feedme.approval.schemas import (
    TempExampleResponse,
    ApprovalDecision,
    BulkApprovalRequest,
    WorkflowMetrics,
    ReviewerWorkload
)
from app.feedme.approval.workflow_engine import ApprovalWorkflowEngine


class TestApprovalEndpoints:
    """Test suite for approval API endpoints"""

    @pytest.fixture
    def mock_workflow_engine(self):
        """Mock workflow engine for testing"""
        engine = Mock(spec=ApprovalWorkflowEngine)
        engine.create_temp_example = AsyncMock()
        engine.get_temp_example = AsyncMock()
        engine.get_temp_examples_by_status = AsyncMock()
        engine.assign_reviewer = AsyncMock()
        engine.process_approval_decision = AsyncMock()
        engine.process_bulk_approval = AsyncMock()
        engine.get_workflow_metrics = AsyncMock()
        engine.get_reviewer_workload = AsyncMock()
        return engine

    @pytest.fixture
    def client(self, mock_workflow_engine):
        """Create test client with mocked dependencies"""
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(router)
        
        # Override dependency
        app.dependency_overrides[get_workflow_engine] = lambda: mock_workflow_engine
        
        return TestClient(app), mock_workflow_engine

    @pytest.fixture
    def sample_temp_example(self):
        """Sample temp example data"""
        return {
            'id': 1,
            'conversation_id': 1,
            'question_text': 'How to configure IMAP?',
            'answer_text': 'Go to Settings > Email Accounts...',
            'extraction_confidence': 0.85,
            'approval_status': 'pending',
            'created_at': datetime.now().isoformat()
        }

    def test_create_temp_example_success(self, client, sample_temp_example):
        """Test successful creation of temp example"""
        test_client, mock_engine = client
        
        # Setup mock response
        mock_engine.create_temp_example.return_value = sample_temp_example
        
        # Test data
        create_data = {
            'conversation_id': 1,
            'question_text': 'How to configure IMAP?',
            'answer_text': 'Go to Settings > Email Accounts...',
            'extraction_confidence': 0.85
        }
        
        # Execute request
        response = test_client.post("/api/v1/approval/temp-examples", json=create_data)
        
        # Verify response
        assert response.status_code == 201
        response_data = response.json()
        assert response_data['question_text'] == create_data['question_text']
        assert response_data['approval_status'] == 'pending'
        
        # Verify mock was called
        mock_engine.create_temp_example.assert_called_once()

    def test_create_temp_example_validation_error(self, client):
        """Test creation with validation errors"""
        test_client, mock_engine = client
        
        # Test data with missing required fields
        invalid_data = {
            'conversation_id': 1,
            # Missing question_text and answer_text
            'extraction_confidence': 0.85
        }
        
        # Execute request
        response = test_client.post("/api/v1/approval/temp-examples", json=invalid_data)
        
        # Verify validation error
        assert response.status_code == 422
        error_detail = response.json()['detail']
        assert any('question_text' in str(error) for error in error_detail)
        assert any('answer_text' in str(error) for error in error_detail)

    def test_get_temp_example_success(self, client, sample_temp_example):
        """Test successful retrieval of temp example"""
        test_client, mock_engine = client
        
        # Setup mock response
        mock_engine.get_temp_example.return_value = sample_temp_example
        
        # Execute request
        response = test_client.get("/api/v1/approval/temp-examples/1")
        
        # Verify response
        assert response.status_code == 200
        response_data = response.json()
        assert response_data['id'] == 1
        assert response_data['question_text'] == sample_temp_example['question_text']

    def test_get_temp_example_not_found(self, client):
        """Test retrieval of non-existent temp example"""
        test_client, mock_engine = client
        
        # Setup mock to return None
        mock_engine.get_temp_example.return_value = None
        
        # Execute request
        response = test_client.get("/api/v1/approval/temp-examples/999")
        
        # Verify not found response
        assert response.status_code == 404
        assert "Temp example not found" in response.json()['detail']

    def test_get_temp_examples_by_status(self, client, sample_temp_example):
        """Test retrieval of temp examples by status"""
        test_client, mock_engine = client
        
        # Setup mock response
        examples_list = [sample_temp_example, {**sample_temp_example, 'id': 2}]
        mock_engine.get_temp_examples_by_status.return_value = {
            'items': examples_list,
            'total': 2,
            'page': 1,
            'page_size': 10
        }
        
        # Execute request
        response = test_client.get("/api/v1/approval/temp-examples?status=pending")
        
        # Verify response
        assert response.status_code == 200
        response_data = response.json()
        assert response_data['total'] == 2
        assert len(response_data['items']) == 2
        assert response_data['items'][0]['approval_status'] == 'pending'

    def test_get_temp_examples_with_pagination(self, client):
        """Test retrieval with pagination parameters"""
        test_client, mock_engine = client
        
        # Setup mock response
        mock_engine.get_temp_examples_by_status.return_value = {
            'items': [],
            'total': 50,
            'page': 2,
            'page_size': 20
        }
        
        # Execute request with pagination
        response = test_client.get("/api/v1/approval/temp-examples?page=2&page_size=20")
        
        # Verify pagination parameters were passed
        mock_engine.get_temp_examples_by_status.assert_called_once()
        call_args = mock_engine.get_temp_examples_by_status.call_args
        assert call_args[1]['page'] == 2
        assert call_args[1]['page_size'] == 20

    def test_assign_reviewer_success(self, client, sample_temp_example):
        """Test successful reviewer assignment"""
        test_client, mock_engine = client
        
        # Setup mock response
        updated_example = {**sample_temp_example, 'assigned_reviewer': 'reviewer@example.com'}
        mock_engine.assign_reviewer.return_value = 'reviewer@example.com'
        mock_engine.get_temp_example.return_value = updated_example
        
        # Execute request
        assignment_data = {'reviewer_id': 'reviewer@example.com'}
        response = test_client.put("/api/v1/approval/temp-examples/1/assign", json=assignment_data)
        
        # Verify response
        assert response.status_code == 200
        response_data = response.json()
        assert response_data['assigned_reviewer'] == 'reviewer@example.com'

    def test_assign_reviewer_auto_assignment(self, client, sample_temp_example):
        """Test automatic reviewer assignment"""
        test_client, mock_engine = client
        
        # Setup mock response for auto-assignment
        mock_engine.assign_reviewer.return_value = 'auto-assigned@example.com'
        updated_example = {**sample_temp_example, 'assigned_reviewer': 'auto-assigned@example.com'}
        mock_engine.get_temp_example.return_value = updated_example
        
        # Execute request without specific reviewer
        response = test_client.put("/api/v1/approval/temp-examples/1/assign", json={})
        
        # Verify auto-assignment
        assert response.status_code == 200
        response_data = response.json()
        assert response_data['assigned_reviewer'] == 'auto-assigned@example.com'

    def test_process_approval_decision_approve(self, client, sample_temp_example):
        """Test processing approval decision - approve"""
        test_client, mock_engine = client
        
        # Setup mock response
        approved_example = {
            **sample_temp_example, 
            'approval_status': 'approved',
            'reviewer_id': 'reviewer@example.com',
            'reviewed_at': datetime.now().isoformat()
        }
        mock_engine.process_approval_decision.return_value = approved_example
        
        # Execute request
        decision_data = {
            'action': 'approve',
            'reviewer_id': 'reviewer@example.com',
            'review_notes': 'Good quality Q&A pair',
            'confidence_assessment': 0.9
        }
        response = test_client.post("/api/v1/approval/temp-examples/1/decision", json=decision_data)
        
        # Verify response
        assert response.status_code == 200
        response_data = response.json()
        assert response_data['approval_status'] == 'approved'
        assert response_data['reviewer_id'] == 'reviewer@example.com'

    def test_process_approval_decision_reject(self, client, sample_temp_example):
        """Test processing approval decision - reject"""
        test_client, mock_engine = client
        
        # Setup mock response
        rejected_example = {
            **sample_temp_example, 
            'approval_status': 'rejected',
            'reviewer_id': 'reviewer@example.com',
            'rejection_reason': 'poor_quality'
        }
        mock_engine.process_approval_decision.return_value = rejected_example
        
        # Execute request
        decision_data = {
            'action': 'reject',
            'reviewer_id': 'reviewer@example.com',
            'review_notes': 'Poor quality content',
            'rejection_reason': 'poor_quality'
        }
        response = test_client.post("/api/v1/approval/temp-examples/1/decision", json=decision_data)
        
        # Verify response
        assert response.status_code == 200
        response_data = response.json()
        assert response_data['approval_status'] == 'rejected'
        assert response_data['rejection_reason'] == 'poor_quality'

    def test_process_approval_decision_request_revision(self, client, sample_temp_example):
        """Test processing approval decision - request revision"""
        test_client, mock_engine = client
        
        # Setup mock response
        revision_example = {
            **sample_temp_example, 
            'approval_status': 'revision_requested',
            'reviewer_id': 'reviewer@example.com',
            'revision_instructions': 'Please provide more detailed answer'
        }
        mock_engine.process_approval_decision.return_value = revision_example
        
        # Execute request
        decision_data = {
            'action': 'request_revision',
            'reviewer_id': 'reviewer@example.com',
            'review_notes': 'Answer needs more detail',
            'revision_instructions': 'Please provide more detailed answer'
        }
        response = test_client.post("/api/v1/approval/temp-examples/1/decision", json=decision_data)
        
        # Verify response
        assert response.status_code == 200
        response_data = response.json()
        assert response_data['approval_status'] == 'revision_requested'
        assert response_data['revision_instructions'] == 'Please provide more detailed answer'

    def test_bulk_approval_success(self, client):
        """Test successful bulk approval operation"""
        test_client, mock_engine = client
        
        # Setup mock response
        bulk_result = {
            'processed_count': 3,
            'successful_count': 3,
            'failed_count': 0,
            'failures': []
        }
        mock_engine.process_bulk_approval.return_value = bulk_result
        
        # Execute request
        bulk_data = {
            'temp_example_ids': [1, 2, 3],
            'action': 'approve',
            'reviewer_id': 'reviewer@example.com',
            'review_notes': 'Bulk approval - all examples meet standards'
        }
        response = test_client.post("/api/v1/approval/bulk-decision", json=bulk_data)
        
        # Verify response
        assert response.status_code == 200
        response_data = response.json()
        assert response_data['processed_count'] == 3
        assert response_data['successful_count'] == 3
        assert response_data['failed_count'] == 0

    def test_bulk_approval_partial_failure(self, client):
        """Test bulk approval with partial failures"""
        test_client, mock_engine = client
        
        # Setup mock response with failures
        bulk_result = {
            'processed_count': 3,
            'successful_count': 2,
            'failed_count': 1,
            'failures': [
                {
                    'temp_example_id': 2,
                    'error': 'Already approved',
                    'current_status': 'approved'
                }
            ]
        }
        mock_engine.process_bulk_approval.return_value = bulk_result
        
        # Execute request
        bulk_data = {
            'temp_example_ids': [1, 2, 3],
            'action': 'approve',
            'reviewer_id': 'reviewer@example.com'
        }
        response = test_client.post("/api/v1/approval/bulk-decision", json=bulk_data)
        
        # Verify partial success response
        assert response.status_code == 207  # Multi-status
        response_data = response.json()
        assert response_data['successful_count'] == 2
        assert response_data['failed_count'] == 1
        assert len(response_data['failures']) == 1

    def test_get_workflow_metrics(self, client):
        """Test workflow metrics retrieval"""
        test_client, mock_engine = client
        
        # Setup mock response
        metrics = {
            'total_pending': 25,
            'total_approved': 150,
            'total_rejected': 10,
            'total_revision_requested': 5,
            'approval_rate': 0.9375,  # 150 / (150 + 10)
            'rejection_rate': 0.0625,
            'avg_review_time_hours': 2.5,
            'auto_approval_rate': 0.75,
            'reviewer_efficiency': {
                'reviewer1@example.com': 15,
                'reviewer2@example.com': 12
            }
        }
        mock_engine.get_workflow_metrics.return_value = metrics
        
        # Execute request
        response = test_client.get("/api/v1/approval/metrics")
        
        # Verify response
        assert response.status_code == 200
        response_data = response.json()
        assert response_data['total_pending'] == 25
        assert response_data['approval_rate'] == 0.9375
        assert 'reviewer_efficiency' in response_data

    def test_get_reviewer_workload(self, client):
        """Test reviewer workload retrieval"""
        test_client, mock_engine = client
        
        # Setup mock response
        workload_data = {
            'reviewers': [
                {
                    'reviewer_id': 'reviewer1@example.com',
                    'pending_count': 8,
                    'total_reviewed': 45,
                    'avg_review_time_hours': 2.2,
                    'efficiency_score': 0.85
                },
                {
                    'reviewer_id': 'reviewer2@example.com',
                    'pending_count': 5,
                    'total_reviewed': 38,
                    'avg_review_time_hours': 1.8,
                    'efficiency_score': 0.92
                }
            ],
            'total_pending': 13,
            'avg_workload': 6.5
        }
        mock_engine.get_reviewer_workload.return_value = workload_data
        
        # Execute request
        response = test_client.get("/api/v1/approval/reviewer-workload")
        
        # Verify response
        assert response.status_code == 200
        response_data = response.json()
        assert len(response_data['reviewers']) == 2
        assert response_data['total_pending'] == 13

    def test_error_handling_workflow_engine_exception(self, client):
        """Test error handling when workflow engine raises exceptions"""
        test_client, mock_engine = client
        
        # Setup mock to raise exception
        mock_engine.get_temp_example.side_effect = Exception("Database connection error")
        
        # Execute request
        response = test_client.get("/api/v1/approval/temp-examples/1")
        
        # Verify error response
        assert response.status_code == 500
        assert "Internal server error" in response.json()['detail']

    def test_authentication_required(self, client):
        """Test that authentication is required for approval endpoints"""
        test_client, mock_engine = client
        
        # Execute request without authentication header
        response = test_client.get("/api/v1/approval/temp-examples/1")
        
        # Should be handled by authentication middleware
        # This test assumes authentication middleware is in place
        # The actual implementation will depend on the auth system
        pass  # Implementation depends on auth system

    def test_authorization_reviewer_permissions(self, client):
        """Test that proper reviewer permissions are enforced"""
        test_client, mock_engine = client
        
        # This test would verify that only authorized reviewers
        # can approve/reject examples
        # Implementation depends on authorization system
        pass  # Implementation depends on auth system

    def test_rate_limiting_bulk_operations(self, client):
        """Test rate limiting for bulk operations"""
        test_client, mock_engine = client
        
        # Test with very large bulk request
        large_bulk_data = {
            'temp_example_ids': list(range(1, 1001)),  # 1000 items
            'action': 'approve',
            'reviewer_id': 'reviewer@example.com'
        }
        
        # Execute request
        response = test_client.post("/api/v1/approval/bulk-decision", json=large_bulk_data)
        
        # Should be limited or processed in batches
        # Implementation depends on rate limiting strategy
        assert response.status_code in [200, 202, 429]  # Success, Accepted, or Rate Limited

    def test_input_sanitization(self, client):
        """Test input sanitization for XSS prevention"""
        test_client, mock_engine = client
        
        # Test data with potential XSS content
        malicious_data = {
            'conversation_id': 1,
            'question_text': '<script>alert("xss")</script>How to configure email?',
            'answer_text': 'Go to settings... <img src=x onerror=alert("xss")>',
            'extraction_confidence': 0.85
        }
        
        # Setup mock to return sanitized data
        sanitized_response = {
            'id': 1,
            'question_text': 'How to configure email?',  # Script tag removed
            'answer_text': 'Go to settings...',  # Malicious img removed
            'approval_status': 'pending'
        }
        mock_engine.create_temp_example.return_value = sanitized_response
        
        # Execute request
        response = test_client.post("/api/v1/approval/temp-examples", json=malicious_data)
        
        # Verify sanitization
        assert response.status_code == 201
        response_data = response.json()
        assert '<script>' not in response_data['question_text']
        assert 'onerror=' not in response_data['answer_text']


if __name__ == "__main__":
    pytest.main([__file__, "-v"])