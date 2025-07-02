"""
FeedMe v2.0 Approval State Machine

State machine implementation for managing approval workflow transitions
with validation and business rule enforcement.
"""

from typing import Dict, Set, Optional, List
from enum import Enum
import logging

from .schemas import ApprovalState, ApprovalAction

logger = logging.getLogger(__name__)


class StateTransitionError(Exception):
    """Exception raised for invalid state transitions"""
    pass


class ApprovalStateMachine:
    """
    State machine for managing approval workflow transitions.
    
    Implements a finite state machine with validation for state transitions
    and business rule enforcement for the approval workflow.
    """
    
    def __init__(self):
        """Initialize the state machine with valid transitions"""
        self._transitions: Dict[ApprovalState, Dict[ApprovalAction, ApprovalState]] = {
            ApprovalState.PENDING: {
                ApprovalAction.APPROVE: ApprovalState.APPROVED,
                ApprovalAction.REJECT: ApprovalState.REJECTED,
                ApprovalAction.REQUEST_REVISION: ApprovalState.REVISION_REQUESTED
            },
            ApprovalState.REVISION_REQUESTED: {
                ApprovalAction.APPROVE: ApprovalState.APPROVED,
                ApprovalAction.REJECT: ApprovalState.REJECTED,
                ApprovalAction.REQUEST_REVISION: ApprovalState.REVISION_REQUESTED  # Allow re-revision
            },
            # Final states - no transitions allowed
            ApprovalState.APPROVED: {},
            ApprovalState.REJECTED: {},
            ApprovalState.AUTO_APPROVED: {}
        }
        
        # Valid states and actions for validation
        self._valid_states = set(ApprovalState)
        self._valid_actions = set(ApprovalAction)
        
        # State metadata
        self._state_metadata = {
            ApprovalState.PENDING: {
                'description': 'Awaiting review',
                'is_final': False,
                'requires_reviewer': True,
                'allows_editing': True
            },
            ApprovalState.REVISION_REQUESTED: {
                'description': 'Revision requested',
                'is_final': False,
                'requires_reviewer': True,
                'allows_editing': True
            },
            ApprovalState.APPROVED: {
                'description': 'Approved and published',
                'is_final': True,
                'requires_reviewer': False,
                'allows_editing': False
            },
            ApprovalState.REJECTED: {
                'description': 'Rejected and archived',
                'is_final': True,
                'requires_reviewer': False,
                'allows_editing': False
            },
            ApprovalState.AUTO_APPROVED: {
                'description': 'Automatically approved',
                'is_final': True,
                'requires_reviewer': False,
                'allows_editing': False
            }
        }

    def transition(self, current_state: ApprovalState, action: ApprovalAction) -> ApprovalState:
        """
        Execute a state transition.
        
        Args:
            current_state: Current approval state
            action: Action to execute
            
        Returns:
            New state after transition
            
        Raises:
            StateTransitionError: If transition is invalid
        """
        if not self.is_valid_state(current_state):
            raise StateTransitionError(f"Invalid current state: {current_state}")
        
        if not self.is_valid_action(action):
            raise StateTransitionError(f"Invalid action: {action}")
        
        # Check if transition is allowed
        if current_state not in self._transitions:
            raise StateTransitionError(f"No transitions defined for state: {current_state}")
        
        allowed_actions = self._transitions[current_state]
        if action not in allowed_actions:
            allowed = list(allowed_actions.keys())
            raise StateTransitionError(
                f"Cannot transition from {current_state} with action {action}. "
                f"Allowed actions: {allowed}"
            )
        
        new_state = allowed_actions[action]
        
        logger.info(
            f"State transition: {current_state} --({action})--> {new_state}"
        )
        
        return new_state

    def can_transition(self, current_state: ApprovalState, action: ApprovalAction) -> bool:
        """
        Check if a state transition is valid without executing it.
        
        Args:
            current_state: Current approval state
            action: Action to check
            
        Returns:
            True if transition is valid, False otherwise
        """
        try:
            self.transition(current_state, action)
            return True
        except StateTransitionError:
            return False

    def get_allowed_actions(self, current_state: ApprovalState) -> List[ApprovalAction]:
        """
        Get list of allowed actions for current state.
        
        Args:
            current_state: Current approval state
            
        Returns:
            List of allowed actions
        """
        if current_state not in self._transitions:
            return []
        
        return list(self._transitions[current_state].keys())

    def is_final_state(self, state: ApprovalState) -> bool:
        """
        Check if a state is final (no further transitions allowed).
        
        Args:
            state: State to check
            
        Returns:
            True if state is final, False otherwise
        """
        metadata = self._state_metadata.get(state, {})
        return metadata.get('is_final', False)

    def requires_reviewer(self, state: ApprovalState) -> bool:
        """
        Check if a state requires reviewer assignment.
        
        Args:
            state: State to check
            
        Returns:
            True if reviewer is required, False otherwise
        """
        metadata = self._state_metadata.get(state, {})
        return metadata.get('requires_reviewer', False)

    def allows_editing(self, state: ApprovalState) -> bool:
        """
        Check if a state allows content editing.
        
        Args:
            state: State to check
            
        Returns:
            True if editing is allowed, False otherwise
        """
        metadata = self._state_metadata.get(state, {})
        return metadata.get('allows_editing', False)

    def get_state_description(self, state: ApprovalState) -> str:
        """
        Get human-readable description of a state.
        
        Args:
            state: State to describe
            
        Returns:
            Description string
        """
        metadata = self._state_metadata.get(state, {})
        return metadata.get('description', str(state))

    def is_valid_state(self, state: any) -> bool:
        """
        Validate if a value is a valid approval state.
        
        Args:
            state: Value to validate
            
        Returns:
            True if valid state, False otherwise
        """
        return state in self._valid_states

    def is_valid_action(self, action: any) -> bool:
        """
        Validate if a value is a valid approval action.
        
        Args:
            action: Value to validate
            
        Returns:
            True if valid action, False otherwise
        """
        return action in self._valid_actions

    def get_workflow_path(self, start_state: ApprovalState, end_state: ApprovalState) -> Optional[List[ApprovalAction]]:
        """
        Find a path from start state to end state.
        
        Args:
            start_state: Starting state
            end_state: Target state
            
        Returns:
            List of actions to reach target state, or None if no path exists
        """
        if start_state == end_state:
            return []
        
        # Simple BFS to find shortest path
        from collections import deque
        
        queue = deque([(start_state, [])])
        visited = {start_state}
        
        while queue:
            current_state, path = queue.popleft()
            
            # Get possible next states
            for action, next_state in self._transitions.get(current_state, {}).items():
                if next_state == end_state:
                    return path + [action]
                
                if next_state not in visited:
                    visited.add(next_state)
                    queue.append((next_state, path + [action]))
        
        return None  # No path found

    def validate_workflow(self, states_and_actions: List[tuple]) -> bool:
        """
        Validate a complete workflow sequence.
        
        Args:
            states_and_actions: List of (state, action) tuples
            
        Returns:
            True if workflow is valid, False otherwise
        """
        if not states_and_actions:
            return True
        
        current_state = states_and_actions[0][0]
        
        for i, (expected_state, action) in enumerate(states_and_actions):
            # Check if current state matches expected
            if current_state != expected_state:
                logger.error(
                    f"Workflow validation failed at step {i}: "
                    f"expected state {expected_state}, got {current_state}"
                )
                return False
            
            # If there's a next step, validate the transition
            if i < len(states_and_actions) - 1:
                try:
                    current_state = self.transition(current_state, action)
                except StateTransitionError as e:
                    logger.error(f"Workflow validation failed at step {i}: {e}")
                    return False
        
        return True

    def get_state_statistics(self) -> Dict[str, any]:
        """
        Get statistics about the state machine configuration.
        
        Returns:
            Dictionary with state machine statistics
        """
        total_states = len(self._valid_states)
        final_states = sum(1 for state in self._valid_states if self.is_final_state(state))
        total_transitions = sum(len(actions) for actions in self._transitions.values())
        
        return {
            'total_states': total_states,
            'final_states': final_states,
            'intermediate_states': total_states - final_states,
            'total_transitions': total_transitions,
            'avg_transitions_per_state': total_transitions / total_states if total_states > 0 else 0,
            'states_requiring_reviewer': sum(
                1 for state in self._valid_states if self.requires_reviewer(state)
            ),
            'states_allowing_editing': sum(
                1 for state in self._valid_states if self.allows_editing(state)
            )
        }


# Factory function for creating state machine instances
def create_approval_state_machine() -> ApprovalStateMachine:
    """
    Factory function to create a configured approval state machine.
    
    Returns:
        Configured ApprovalStateMachine instance
    """
    return ApprovalStateMachine()


# Utility functions for common state machine operations
def is_actionable_state(state: ApprovalState) -> bool:
    """
    Check if a state allows actions to be taken.
    
    Args:
        state: State to check
        
    Returns:
        True if state is actionable, False otherwise
    """
    machine = create_approval_state_machine()
    return not machine.is_final_state(state)


def get_next_possible_states(current_state: ApprovalState) -> List[ApprovalState]:
    """
    Get all possible next states from current state.
    
    Args:
        current_state: Current state
        
    Returns:
        List of possible next states
    """
    machine = create_approval_state_machine()
    next_states = []
    
    for action in machine.get_allowed_actions(current_state):
        try:
            next_state = machine.transition(current_state, action)
            if next_state not in next_states:
                next_states.append(next_state)
        except StateTransitionError:
            continue
    
    return next_states