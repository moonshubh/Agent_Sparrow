"""
Agent Sparrow - Diagnostic Step Sequencing Engine

This module implements intelligent sequencing of diagnostic steps with progressive
complexity handling, adaptive branching, and customer-specific optimization.
"""

import logging
import uuid
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
import asyncio

from .troubleshooting_schemas import (
    TroubleshootingSession,
    DiagnosticStep,
    DiagnosticStepType,
    TroubleshootingPhase,
    TroubleshootingConfig
)
from app.agents_v2.primary_agent.prompts.emotion_templates import EmotionalState

logger = logging.getLogger(__name__)


class DiagnosticSequencer:
    """
    Intelligent diagnostic step sequencing engine
    
    Provides progressive troubleshooting through:
    - Phase-based diagnostic progression (Basic → Intermediate → Advanced)
    - Adaptive step selection based on customer characteristics
    - Dynamic branching based on step results
    - Progressive complexity with safety checks
    """
    
    # Scoring weights for step selection
    _SCORE_BASE_STEP_POSITION = 0.1  # Weight for step position bonus
    
    # Emotional state weights
    _SCORE_EMOTION_FRUSTRATED_DIFFICULTY = 0.3  # Weight for difficulty in frustrated state
    _SCORE_EMOTION_FRUSTRATED_TIME = 0.2       # Weight for time in frustrated state
    _SCORE_EMOTION_CONFUSED_DIFFICULTY = 0.4   # Weight for difficulty in confused state
    _SCORE_EMOTION_CONFUSED_TIPS = 0.1         # Weight for tips in confused state
    _SCORE_EMOTION_PROFESSIONAL = 0.2          # Weight for professional state
    _SCORE_EMOTION_URGENT = 0.4                # Weight for urgent state
    
    # Technical level adjustments
    _SCORE_TECH_LEVEL_APPROPRIATE = 0.3  # Bonus for appropriate difficulty
    _SCORE_TECH_LEVEL_TOO_HARD = -0.5    # Penalty for too difficult
    
    # Success rate weight
    _SCORE_SUCCESS_RATE = 0.2  # Weight for step success rate
    
    def __init__(self, config: TroubleshootingConfig):
        """
        Initialize diagnostic sequencer
        
        Args:
            config: Troubleshooting configuration
        """
        self.config = config
        
        # Progressive complexity levels
        self.complexity_levels = {
            1: "Basic user-friendly steps",
            2: "Intermediate technical steps", 
            3: "Advanced diagnostic procedures",
            4: "Expert-level troubleshooting",
            5: "Specialist intervention required"
        }
        
        # Initialize step lookup cache
        self._step_lookup: Dict[str, Dict[str, DiagnosticStep]] = {}
        
        logger.info("DiagnosticSequencer initialized with progressive complexity handling")
    
    async def get_next_step(
        self,
        session: TroubleshootingSession,
        previous_step_successful: Optional[bool] = None
    ) -> Optional[DiagnosticStep]:
        """
        Get the next optimal diagnostic step for the session
        
        Args:
            session: Current troubleshooting session
            previous_step_successful: Result of previous step execution
            
        Returns:
            Next diagnostic step, None if workflow complete, or None if error occurs
            
        Note:
            This method includes comprehensive error handling to ensure the troubleshooting
            flow continues even if individual step generation fails.
        """
        try:
            # Handle first step (session initialization)
            if not session.completed_steps and not session.failed_steps:
                try:
                    return await self._get_initial_diagnostic_step(session)
                except Exception as e:
                    logger.error(f"Error getting initial diagnostic step: {str(e)}", 
                               exc_info=True)
                    return None
            
            # Handle progression based on previous step result
            if previous_step_successful is not None:
                try:
                    return await self._get_next_step_based_on_result(
                        session, previous_step_successful
                    )
                except Exception as e:
                    logger.error(
                        f"Error getting next step based on result (success={previous_step_successful}): {str(e)}",
                        exc_info=True
                    )
                    # Fall through to sequential step on error
            
            # Fallback: get next sequential step
            try:
                return await self._get_next_sequential_step(session)
            except Exception as e:
                logger.error(f"Error getting next sequential step: {str(e)}", 
                           exc_info=True)
                return None
                
        except Exception as e:
            # Catch any unexpected errors at the top level
            logger.critical(f"Unexpected error in get_next_step: {str(e)}", 
                          exc_info=True)
            return None
    
    async def _get_initial_diagnostic_step(
        self,
        session: TroubleshootingSession
    ) -> Optional[DiagnosticStep]:
        """Get the first diagnostic step for the session"""
        
        workflow = session.workflow
        
        # Filter steps for initial phase
        initial_steps = [
            step for step in workflow.diagnostic_steps
            if step.difficulty_level <= self._get_max_difficulty_for_phase(
                TroubleshootingPhase.INITIAL_ASSESSMENT
            )
        ]
        
        if not initial_steps:
            logger.warning(f"No initial steps found for workflow {workflow.name}")
            return None
        
        # Select most appropriate initial step
        selected_step = await self._select_step_for_customer(
            initial_steps, session
        )
        
        # Adapt step for customer characteristics
        adapted_step = await self._adapt_step_for_customer(selected_step, session)
        
        logger.info(f"Selected initial step: {adapted_step.title}")
        return adapted_step
    
    async def _get_next_step_based_on_result(
        self,
        session: TroubleshootingSession,
        previous_step_successful: bool
    ) -> Optional[DiagnosticStep]:
        """Get next step based on previous step result"""
        
        current_step = session.current_step
        if not current_step:
            return await self._get_next_sequential_step(session)
        
        # Check for explicit next steps defined in current step
        if previous_step_successful and current_step.next_steps_on_success:
            next_step_id = current_step.next_steps_on_success[0]
            next_step = self._find_step_by_id(session.workflow, next_step_id)
            if next_step:
                return await self._adapt_step_for_customer(next_step, session)
        
        elif not previous_step_successful and current_step.next_steps_on_failure:
            next_step_id = current_step.next_steps_on_failure[0]
            next_step = self._find_step_by_id(session.workflow, next_step_id)
            if next_step:
                return await self._adapt_step_for_customer(next_step, session)
        
        # Use intelligent progression logic
        if previous_step_successful:
            return await self._progress_to_next_complexity_level(session)
        else:
            return await self._handle_step_failure(session)
    
    async def _get_next_sequential_step(
        self,
        session: TroubleshootingSession
    ) -> Optional[DiagnosticStep]:
        """Get next step in sequential order"""
        
        workflow = session.workflow
        completed_step_ids = {step.step_id for step in session.completed_steps}
        failed_step_ids = {step.step_id for step in session.failed_steps}
        excluded_ids = completed_step_ids.union(failed_step_ids)
        
        # Find next available step
        available_steps = [
            step for step in workflow.diagnostic_steps
            if step.step_id not in excluded_ids
        ]
        
        if not available_steps:
            logger.info("No more diagnostic steps available")
            return None
        
        # Filter by current phase and difficulty
        current_phase = session.current_phase
        max_difficulty = self._get_max_difficulty_for_customer(session)
        
        suitable_steps = [
            step for step in available_steps
            if step.difficulty_level <= max_difficulty
        ]
        
        if not suitable_steps:
            # No steps at current difficulty - may need escalation
            logger.warning(f"No suitable steps found for difficulty level {max_difficulty}")
            return None
        
        # Select best step for current situation
        selected_step = await self._select_step_for_customer(suitable_steps, session)
        return await self._adapt_step_for_customer(selected_step, session)
    
    async def _progress_to_next_complexity_level(
        self,
        session: TroubleshootingSession
    ) -> Optional[DiagnosticStep]:
        """Progress to next complexity level after successful step"""
        
        # Determine if we should increase complexity
        should_increase = await self._should_increase_complexity(session)
        
        if should_increase:
            # Move to next phase if appropriate
            next_phase = self._get_next_phase(session.current_phase)
            if next_phase:
                session.current_phase = next_phase
                logger.info(f"Progressed to phase: {next_phase.value}")
        
        # Get next step with potentially increased complexity
        return await self._get_next_sequential_step(session)
    
    async def _handle_step_failure(
        self,
        session: TroubleshootingSession
    ) -> Optional[DiagnosticStep]:
        """Handle failed diagnostic step with alternative approaches"""
        
        failed_step = session.current_step
        if not failed_step:
            return await self._get_next_sequential_step(session)
        
        # Try to find alternative approach for same problem
        alternative_step = await self._find_alternative_approach(
            session, failed_step
        )
        
        if alternative_step:
            logger.info(f"Found alternative approach: {alternative_step.title}")
            return alternative_step
        
        # If no alternative, try simpler approach
        simpler_step = await self._find_simpler_approach(session, failed_step)
        
        if simpler_step:
            logger.info(f"Found simpler approach: {simpler_step.title}")
            return simpler_step
        
        # Continue with next step in sequence
        return await self._get_next_sequential_step(session)
    
    async def _select_step_for_customer(
        self,
        available_steps: List[DiagnosticStep],
        session: TroubleshootingSession
    ) -> DiagnosticStep:
        """Select most appropriate step for customer characteristics"""
        
        if len(available_steps) == 1:
            return available_steps[0]
        
        # Score steps based on customer factors
        step_scores = []
        
        for step in available_steps:
            score = 0.0
            
            # Base score from step position (prefer earlier steps)
            score += (10 - step.step_number) * self._SCORE_BASE_STEP_POSITION
            
            # Adjust for customer emotional state
            emotion = session.customer_emotional_state
            
            if emotion == EmotionalState.FRUSTRATED:
                # Prefer quick, simple steps
                score += (5 - step.difficulty_level) * self._SCORE_EMOTION_FRUSTRATED_DIFFICULTY
                score += max(0, (10 - step.time_estimate_minutes)) * self._SCORE_EMOTION_FRUSTRATED_TIME
                
            elif emotion == EmotionalState.CONFUSED:
                # Prefer simple, well-documented steps
                score += (5 - step.difficulty_level) * self._SCORE_EMOTION_CONFUSED_DIFFICULTY
                score += len(step.troubleshooting_tips) * self._SCORE_EMOTION_CONFUSED_TIPS
                
            elif emotion == EmotionalState.PROFESSIONAL:
                # Allow more complex steps
                score += min(step.difficulty_level, session.customer_technical_level) * self._SCORE_EMOTION_PROFESSIONAL
                
            elif emotion == EmotionalState.URGENT:
                # Prefer fast steps
                score += max(0, (5 - step.time_estimate_minutes)) * self._SCORE_EMOTION_URGENT
            
            # Adjust for customer technical level
            tech_level = session.customer_technical_level
            if step.difficulty_level <= tech_level:
                score += self._SCORE_TECH_LEVEL_APPROPRIATE  # Bonus for appropriate difficulty
            elif step.difficulty_level > tech_level + 1:
                score += self._SCORE_TECH_LEVEL_TOO_HARD  # Penalty for too difficult
            
            # Prefer steps with higher success rates
            if hasattr(step, 'success_rate'):
                score += getattr(step, 'success_rate', 0.8) * self._SCORE_SUCCESS_RATE
            
            step_scores.append((step, score))
        
        # Sort by score and return best step
        step_scores.sort(key=lambda x: x[1], reverse=True)
        selected_step = step_scores[0][0]
        
        logger.debug(f"Selected step '{selected_step.title}' with score {step_scores[0][1]:.2f}")
        return selected_step
    
    async def _adapt_step_for_customer(
        self,
        step: DiagnosticStep,
        session: TroubleshootingSession
    ) -> DiagnosticStep:
        """Adapt diagnostic step for specific customer characteristics"""
        
        # Create adapted copy of step
        adapted_step = DiagnosticStep(
            step_id=step.step_id,
            step_number=step.step_number,
            step_type=step.step_type,
            title=step.title,
            description=step.description,
            instructions=step.instructions,
            expected_outcome=step.expected_outcome,
            time_estimate_minutes=step.time_estimate_minutes,
            difficulty_level=step.difficulty_level,
            prerequisites=step.prerequisites.copy(),
            success_criteria=step.success_criteria.copy(),
            failure_indicators=step.failure_indicators.copy(),
            next_steps_on_success=step.next_steps_on_success.copy(),
            next_steps_on_failure=step.next_steps_on_failure.copy(),
            verification_method=step.verification_method,
            troubleshooting_tips=step.troubleshooting_tips.copy(),
            common_issues=step.common_issues.copy()
        )
        
        # Adapt based on customer emotional state
        emotion = session.customer_emotional_state
        
        if emotion == EmotionalState.FRUSTRATED:
            adapted_step.instructions = f"🚀 Quick Fix: {adapted_step.instructions}"
            adapted_step.troubleshooting_tips.insert(0, "This should resolve the issue quickly")
            
        elif emotion == EmotionalState.CONFUSED:
            adapted_step.instructions = f"📋 Step-by-step: {adapted_step.instructions}"
            adapted_step.troubleshooting_tips.insert(0, "Take your time with each step")
            
        elif emotion == EmotionalState.ANXIOUS:
            adapted_step.instructions = f"✅ Safe approach: {adapted_step.instructions}"
            adapted_step.troubleshooting_tips.insert(0, "This is a safe step that won't cause any issues")
            
        elif emotion == EmotionalState.URGENT:
            adapted_step.instructions = f"⚡ Fast track: {adapted_step.instructions}"
            # Reduce time estimate for urgent customers
            adapted_step.time_estimate_minutes = max(1, adapted_step.time_estimate_minutes - 2)
        
        # Adapt based on technical level
        tech_level = session.customer_technical_level
        
        if tech_level <= 2:
            # Add more detailed instructions for beginners
            adapted_step.troubleshooting_tips.append("If you need help finding any settings, let me know")
            adapted_step.troubleshooting_tips.append("Take a screenshot if something looks different")
            
        elif tech_level >= 4:
            # Add advanced options for technical users
            adapted_step.troubleshooting_tips.append("Advanced users can also try the command line approach")
            adapted_step.troubleshooting_tips.append("Check system logs for additional diagnostic information")
        
        # Add session-specific context
        if session.session_notes:
            adapted_step.troubleshooting_tips.append("Note: This step has been customized for your situation")
        
        return adapted_step
    
    def _get_max_difficulty_for_phase(self, phase: TroubleshootingPhase) -> int:
        """Get maximum difficulty level for troubleshooting phase"""
        
        phase_difficulty_map = {
            TroubleshootingPhase.INITIAL_ASSESSMENT: 2,
            TroubleshootingPhase.BASIC_DIAGNOSTICS: 2,
            TroubleshootingPhase.INTERMEDIATE_DIAGNOSTICS: 3,
            TroubleshootingPhase.ADVANCED_DIAGNOSTICS: 4,
            TroubleshootingPhase.SPECIALIZED_TESTING: 5,
            TroubleshootingPhase.ESCALATION_PREPARATION: 3,
            TroubleshootingPhase.RESOLUTION_VERIFICATION: 2
        }
        
        return phase_difficulty_map.get(phase, 3)
    
    def _get_max_difficulty_for_customer(self, session: TroubleshootingSession) -> int:
        """Get maximum difficulty level appropriate for customer
        
        Returns:
            int: Difficulty level between 1 and 5 (inclusive)
        """
        base_max = session.customer_technical_level
        
        # Adjust based on emotional state
        emotion = session.customer_emotional_state
        
        if emotion in [EmotionalState.CONFUSED, EmotionalState.ANXIOUS]:
            base_max = max(1, base_max - 1)
        elif emotion == EmotionalState.FRUSTRATED:
            base_max = max(1, base_max - 1)  # Keep simple when frustrated
        elif emotion == EmotionalState.PROFESSIONAL:
            base_max = min(5, base_max + 1)
        
        # Adjust based on failure history
        if len(session.failed_steps) >= 2:
            base_max = max(1, base_max - 1)  # Reduce complexity after failures
        
        # Phase limitations
        phase_max = self._get_max_difficulty_for_phase(session.current_phase)
        
        # Ensure final difficulty is between 1 and 5 (inclusive)
        return max(1, min(base_max, phase_max))
    
    async def _should_increase_complexity(self, session: TroubleshootingSession) -> bool:
        """Determine if complexity should be increased"""
        
        # Don't increase if customer is struggling
        if len(session.failed_steps) >= 2:
            return False
        
        # Don't increase for confused or anxious customers
        if session.customer_emotional_state in [EmotionalState.CONFUSED, EmotionalState.ANXIOUS]:
            return False
        
        # Increase after multiple successful steps
        if len(session.completed_steps) >= 3:
            return True
        
        # Increase for technical customers
        if session.customer_technical_level >= 4 and len(session.completed_steps) >= 2:
            return True
        
        return False
    
    def _get_next_phase(self, current_phase: TroubleshootingPhase) -> Optional[TroubleshootingPhase]:
        """Get next phase in troubleshooting progression"""
        
        phase_progression = [
            TroubleshootingPhase.INITIAL_ASSESSMENT,
            TroubleshootingPhase.BASIC_DIAGNOSTICS,
            TroubleshootingPhase.INTERMEDIATE_DIAGNOSTICS,
            TroubleshootingPhase.ADVANCED_DIAGNOSTICS,
            TroubleshootingPhase.SPECIALIZED_TESTING,
            TroubleshootingPhase.ESCALATION_PREPARATION
        ]
        
        try:
            current_index = phase_progression.index(current_phase)
            if current_index < len(phase_progression) - 1:
                return phase_progression[current_index + 1]
        except ValueError:
            pass
        
        return None
    
    def _build_step_lookup(self, workflow) -> None:
        """Build or rebuild the step lookup dictionary for a workflow"""
        workflow_id = getattr(workflow, 'workflow_id', None)
        if not workflow_id:
            workflow_id = str(uuid.uuid4())
            setattr(workflow, 'workflow_id', workflow_id)
            
        self._step_lookup[workflow_id] = {}
        
        for step in workflow.diagnostic_steps:
            # Store by step_id
            self._step_lookup[workflow_id][step.step_id] = step
            
            # Also store by normalized title for backward compatibility
            normalized_title = step.title.lower().replace(' ', '_')
            if normalized_title not in self._step_lookup[workflow_id]:
                self._step_lookup[workflow_id][normalized_title] = step
    
    def _find_step_by_id(
        self,
        workflow,
        step_id: str
    ) -> Optional[DiagnosticStep]:
        """
        Find diagnostic step by ID or normalized title in workflow
        
        Uses a dictionary for O(1) lookup after the first access to a workflow.
        """
        workflow_id = getattr(workflow, 'workflow_id', None)
        if not workflow_id:
            workflow_id = str(uuid.uuid4())
            setattr(workflow, 'workflow_id', workflow_id)
        
        # Build lookup if this is the first time seeing this workflow
        if workflow_id not in self._step_lookup:
            self._build_step_lookup(workflow)
        
        # Try to get from lookup
        return self._step_lookup.get(workflow_id, {}).get(step_id)
    
    async def _find_alternative_approach(
        self,
        session: TroubleshootingSession,
        failed_step: DiagnosticStep
    ) -> Optional[DiagnosticStep]:
        """Find alternative approach for failed step"""
        
        workflow = session.workflow
        completed_ids = {step.step_id for step in session.completed_steps}
        failed_ids = {step.step_id for step in session.failed_steps}
        
        # Look for steps of same type that haven't been tried
        alternative_steps = [
            step for step in workflow.diagnostic_steps
            if (step.step_type == failed_step.step_type and
                step.step_id not in completed_ids and
                step.step_id not in failed_ids and
                step.step_id != failed_step.step_id)
        ]
        
        if alternative_steps:
            # Select most appropriate alternative
            return await self._select_step_for_customer(alternative_steps, session)
        
        return None
    
    async def _find_simpler_approach(
        self,
        session: TroubleshootingSession,
        failed_step: DiagnosticStep
    ) -> Optional[DiagnosticStep]:
        """Find simpler approach after step failure"""
        
        workflow = session.workflow
        completed_ids = {step.step_id for step in session.completed_steps}
        failed_ids = {step.step_id for step in session.failed_steps}
        
        # Look for simpler steps of same or related type
        simpler_steps = [
            step for step in workflow.diagnostic_steps
            if (step.difficulty_level < failed_step.difficulty_level and
                step.step_id not in completed_ids and
                step.step_id not in failed_ids)
        ]
        
        if simpler_steps:
            # Prefer steps that are 1-2 levels simpler
            target_difficulty = max(1, failed_step.difficulty_level - 2)
            best_steps = [
                step for step in simpler_steps
                if step.difficulty_level >= target_difficulty
            ]
            
            if best_steps:
                return await self._select_step_for_customer(best_steps, session)
            else:
                return await self._select_step_for_customer(simpler_steps, session)
        
        return None