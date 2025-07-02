"""
Basic tests for FeedMe v2.0 Approval Workflow System
Simplified tests to verify core functionality
"""

import pytest
from datetime import datetime

from app.feedme.approval.schemas import (
    ApprovalState,
    ApprovalAction,
    WorkflowConfig,
    TempExampleCreate,
    ApprovalDecision
)
from app.feedme.approval.state_machine import (
    ApprovalStateMachine,
    StateTransitionError
)


class TestApprovalStateMachineBasic:
    """Basic tests for approval state machine"""

    @pytest.fixture
    def state_machine(self):
        """Create state machine for testing"""
        return ApprovalStateMachine()

    def test_valid_transitions(self, state_machine):
        """Test valid state transitions"""
        # Test pending to approved
        result = state_machine.transition(ApprovalState.PENDING, ApprovalAction.APPROVE)
        assert result == ApprovalState.APPROVED

        # Test pending to rejected
        result = state_machine.transition(ApprovalState.PENDING, ApprovalAction.REJECT)
        assert result == ApprovalState.REJECTED

        # Test pending to revision requested
        result = state_machine.transition(ApprovalState.PENDING, ApprovalAction.REQUEST_REVISION)
        assert result == ApprovalState.REVISION_REQUESTED

    def test_invalid_transitions(self, state_machine):
        """Test invalid state transitions"""
        # Cannot approve already approved item
        with pytest.raises(StateTransitionError):
            state_machine.transition(ApprovalState.APPROVED, ApprovalAction.APPROVE)

        # Cannot reject already rejected item
        with pytest.raises(StateTransitionError):
            state_machine.transition(ApprovalState.REJECTED, ApprovalAction.REJECT)

    def test_get_allowed_actions(self, state_machine):
        """Test getting allowed actions for states"""
        # Pending state should allow all actions
        actions = state_machine.get_allowed_actions(ApprovalState.PENDING)
        expected = [ApprovalAction.APPROVE, ApprovalAction.REJECT, ApprovalAction.REQUEST_REVISION]
        assert set(actions) == set(expected)

        # Final states should allow no actions
        actions = state_machine.get_allowed_actions(ApprovalState.APPROVED)
        assert len(actions) == 0

    def test_final_states(self, state_machine):
        """Test final state detection"""
        assert state_machine.is_final_state(ApprovalState.APPROVED)
        assert state_machine.is_final_state(ApprovalState.REJECTED)
        assert state_machine.is_final_state(ApprovalState.AUTO_APPROVED)
        assert not state_machine.is_final_state(ApprovalState.PENDING)
        assert not state_machine.is_final_state(ApprovalState.REVISION_REQUESTED)


class TestApprovalSchemas:
    """Basic tests for approval schemas"""

    def test_temp_example_create_valid(self):
        """Test valid temp example creation"""
        temp_example = TempExampleCreate(
            conversation_id=1,
            question_text="How do I configure IMAP settings?",
            answer_text="Go to Settings > Email Accounts and configure your server details.",
            extraction_confidence=0.85,
            ai_model_used="gemini-2.5-pro"
        )
        
        assert temp_example.conversation_id == 1
        assert temp_example.extraction_confidence == 0.85
        assert temp_example.ai_model_used == "gemini-2.5-pro"

    def test_temp_example_create_validation(self):
        """Test validation in temp example creation"""
        # Test invalid confidence score
        with pytest.raises(ValueError):
            TempExampleCreate(
                conversation_id=1,
                question_text="Question",
                answer_text="Answer",
                extraction_confidence=1.5,  # Invalid: > 1.0
                ai_model_used="model"
            )

        # Test empty question text
        with pytest.raises(ValueError):
            TempExampleCreate(
                conversation_id=1,
                question_text="",  # Invalid: empty
                answer_text="Answer",
                extraction_confidence=0.8,
                ai_model_used="model"
            )

    def test_approval_decision_validation(self):
        """Test approval decision validation"""
        # Valid approval decision
        decision = ApprovalDecision(
            temp_example_id=1,
            action=ApprovalAction.APPROVE,
            reviewer_id="reviewer@example.com",
            review_notes="Good quality Q&A pair"
        )
        
        assert decision.temp_example_id == 1
        assert decision.action == ApprovalAction.APPROVE

        # Test rejection without reason should fail
        with pytest.raises(ValueError):
            ApprovalDecision(
                temp_example_id=1,
                action=ApprovalAction.REJECT,
                reviewer_id="reviewer@example.com"
                # Missing rejection_reason
            )

    def test_workflow_config_defaults(self):
        """Test workflow configuration defaults"""
        config = WorkflowConfig()
        
        assert config.auto_approval_threshold == 0.9
        assert config.high_confidence_threshold == 0.8
        assert config.require_review_threshold == 0.6
        assert config.batch_size == 10
        assert config.enable_auto_assignment is True

    def test_workflow_config_validation(self):
        """Test workflow configuration validation"""
        # Test invalid threshold order
        with pytest.raises(ValueError):
            WorkflowConfig(
                auto_approval_threshold=0.8,
                high_confidence_threshold=0.9  # Should be less than auto_approval_threshold
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])