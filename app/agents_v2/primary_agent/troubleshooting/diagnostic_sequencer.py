"""
Agent Sparrow - Diagnostic Step Sequencing Engine

This module implements intelligent sequencing of diagnostic steps with progressive
complexity handling, adaptive branching, and customer-specific optimization.
"""

import logging
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
    
    def __init__(self, config: TroubleshootingConfig):
        """
        Initializes the DiagnosticSequencer with the provided troubleshooting configuration and defines progressive complexity levels for diagnostic steps.
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
        
        logger.info("DiagnosticSequencer initialized with progressive complexity handling")
    
    async def get_next_step(
        self,
        session: TroubleshootingSession,
        previous_step_successful: Optional[bool] = None
    ) -> Optional[DiagnosticStep]:
        """
        Determines and returns the next diagnostic step for a troubleshooting session.
        
        Selects the next step based on session progress and the outcome of the previous step, adapting to customer context and workflow state. Returns `None` if no further steps are available, indicating workflow completion or escalation.
         
        Returns:
            The next `DiagnosticStep` to perform, or `None` if the workflow is complete.
        """
        
        # Handle first step (session initialization)
        if not session.completed_steps and not session.failed_steps:
            return await self._get_initial_diagnostic_step(session)
        
        # Handle progression based on previous step result
        if previous_step_successful is not None:
            return await self._get_next_step_based_on_result(
                session, previous_step_successful
            )
        
        # Fallback: get next sequential step
        return await self._get_next_sequential_step(session)
    
    async def _get_initial_diagnostic_step(
        self,
        session: TroubleshootingSession
    ) -> Optional[DiagnosticStep]:
        """
        Selects and returns the most suitable initial diagnostic step for a troubleshooting session, adapting it to the customer's characteristics.
        
        Returns:
            The adapted initial diagnostic step, or None if no suitable step is available.
        """
        
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
        """
        Determines and returns the next diagnostic step based on the outcome of the previous step.
        
        If the current step defines explicit next steps for success or failure, selects and adapts the corresponding step for the customer. Otherwise, advances to a higher complexity level on success or handles failure by seeking alternative or simpler approaches.
        
        Returns:
            The next DiagnosticStep to perform, or None if no suitable step is found.
        """
        
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
        """
        Returns the next appropriate diagnostic step in the workflow that has not yet been completed or failed, filtered by the customer's current phase and maximum allowed difficulty.
        
        If no suitable steps remain, returns None to indicate workflow completion or escalation.
        """
        
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
        """
        Advances the troubleshooting session to a higher complexity level if appropriate and returns the next diagnostic step.
        
        If criteria for increasing complexity are met, updates the session to the next troubleshooting phase before selecting the next suitable step.
        Returns:
            The next diagnostic step for the session, or None if no further steps are available.
        """
        
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
        """
        Attempts to recover from a failed diagnostic step by selecting an alternative or simpler approach, or proceeds to the next sequential step if none are available.
        
        Returns:
            The next DiagnosticStep to attempt, or None if no suitable step is found.
        """
        
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
        """
        Selects the most suitable diagnostic step from a list based on customer characteristics and session context.
        
        Scores each available step using factors such as step order, customer emotional state, technical level, estimated time, troubleshooting tips, and historical success rate. Returns the step with the highest score as the optimal choice for the current customer and troubleshooting session.
        """
        
        if len(available_steps) == 1:
            return available_steps[0]
        
        # Score steps based on customer factors
        step_scores = []
        
        for step in available_steps:
            score = 0.0
            
            # Base score from step position (prefer earlier steps)
            score += (10 - step.step_number) * 0.1
            
            # Adjust for customer emotional state
            emotion = session.customer_emotional_state
            
            if emotion == EmotionalState.FRUSTRATED:
                # Prefer quick, simple steps
                score += (5 - step.difficulty_level) * 0.3
                score += max(0, (10 - step.time_estimate_minutes)) * 0.2
                
            elif emotion == EmotionalState.CONFUSED:
                # Prefer simple, well-documented steps
                score += (5 - step.difficulty_level) * 0.4
                score += len(step.troubleshooting_tips) * 0.1
                
            elif emotion == EmotionalState.PROFESSIONAL:
                # Allow more complex steps
                score += min(step.difficulty_level, session.customer_technical_level) * 0.2
                
            elif emotion == EmotionalState.URGENT:
                # Prefer fast steps
                score += max(0, (5 - step.time_estimate_minutes)) * 0.4
            
            # Adjust for customer technical level
            tech_level = session.customer_technical_level
            if step.difficulty_level <= tech_level:
                score += 0.3  # Bonus for appropriate difficulty
            elif step.difficulty_level > tech_level + 1:
                score -= 0.5  # Penalty for too difficult
            
            # Prefer steps with higher success rates
            if hasattr(step, 'success_rate'):
                score += getattr(step, 'success_rate', 0.8) * 0.2
            
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
        """
        Create a customized version of a diagnostic step by adapting its instructions and troubleshooting tips to the customer's emotional state, technical level, and session context.
        
        Parameters:
        	step (DiagnosticStep): The diagnostic step to be adapted.
        	session (TroubleshootingSession): The current troubleshooting session containing customer characteristics.
        
        Returns:
        	DiagnosticStep: A new diagnostic step instance with instructions and tips tailored to the customer's needs and session context.
        """
        
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
        """
        Returns the maximum allowed diagnostic step difficulty for a given troubleshooting phase.
        
        Parameters:
        	phase (TroubleshootingPhase): The current phase of the troubleshooting workflow.
        
        Returns:
        	int: The highest difficulty level permitted for the specified phase.
        """
        
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
        """
        Determine the maximum diagnostic step difficulty suitable for the customer, factoring in their technical level, emotional state, failure history, and current troubleshooting phase.
        
        Returns:
            int: The highest allowed difficulty level for the next diagnostic step.
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
        
        return min(base_max, phase_max)
    
    async def _should_increase_complexity(self, session: TroubleshootingSession) -> bool:
        """
        Determines whether the troubleshooting session should progress to a higher complexity level.
        
        Returns:
            bool: True if conditions indicate readiness to increase complexity, otherwise False.
        """
        
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
        """
        Returns the next troubleshooting phase following the given current phase.
        
        If the current phase is the last in the progression or unrecognized, returns None.
        """
        
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
    
    def _find_step_by_id(
        self,
        workflow,
        step_id: str
    ) -> Optional[DiagnosticStep]:
        """
        Locate a diagnostic step within the workflow by its step ID or normalized title.
        
        Returns:
            The matching DiagnosticStep if found; otherwise, None.
        """
        
        for step in workflow.diagnostic_steps:
            if step.step_id == step_id or step.title.lower().replace(' ', '_') == step_id:
                return step
        
        return None
    
    async def _find_alternative_approach(
        self,
        session: TroubleshootingSession,
        failed_step: DiagnosticStep
    ) -> Optional[DiagnosticStep]:
        """
        Searches for an alternative diagnostic step of the same type as a failed step that has not yet been attempted in the current session.
        
        Returns:
            A suitable alternative DiagnosticStep if available; otherwise, None.
        """
        
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
        """
        Searches for a simpler diagnostic step to attempt after a failure, prioritizing steps 1–2 difficulty levels lower than the failed step and not previously attempted.
        
        Returns:
            A suitable simpler DiagnosticStep if available; otherwise, None.
        """
        
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