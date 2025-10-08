"""
Agent Sparrow - Core Troubleshooting Engine

This module implements the main orchestration engine for structured troubleshooting
workflows with diagnostic step sequencing, verification checkpoints, and progressive
complexity handling.
"""

import logging
import asyncio
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
import uuid
import time

from opentelemetry import trace

from .troubleshooting_schemas import (
    TroubleshootingState,
    TroubleshootingSession,
    TroubleshootingWorkflow,
    DiagnosticStep,
    VerificationCheckpoint,
    TroubleshootingPhase,
    TroubleshootingOutcome,
    VerificationStatus,
    EscalationTrigger,
    TroubleshootingConfig
)
from .diagnostic_sequencer import DiagnosticSequencer
from .verification_system import VerificationSystem
from .escalation_manager import EscalationManager
from .workflow_library import WorkflowLibrary

from app.agents.primary.primary_agent.reasoning.schemas import (
    ReasoningState, 
    ProblemCategory,
    SolutionCandidate
)
from app.agents.primary.primary_agent.prompts.emotion_templates import EmotionalState

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class TroubleshootingEngine:
    """
    Core orchestration engine for structured troubleshooting workflows
    
    Provides systematic problem resolution through:
    - Diagnostic step sequencing with progressive complexity
    - Verification checkpoints for progress validation
    - Adaptive workflow selection based on problem analysis
    - Integration with Agent Sparrow reasoning framework
    - Automatic escalation criteria and pathways
    """
    
    def __init__(self, config: Optional[TroubleshootingConfig] = None):
        """
        Initializes the TroubleshootingEngine with optional configuration and sets up all core subsystems for managing troubleshooting workflows.
        """
        self.config = config or TroubleshootingConfig()
        
        # Initialize subsystems
        self.diagnostic_sequencer = DiagnosticSequencer(self.config)
        self.verification_system = VerificationSystem(self.config)
        self.escalation_manager = EscalationManager(self.config)
        self.workflow_library = WorkflowLibrary()
        
        # Active sessions tracking
        self.active_sessions: Dict[str, TroubleshootingSession] = {}
        self._last_cleanup_time = time.time()
        
        # Configure cleanup parameters from config with defaults
        self._cleanup_interval = getattr(self.config, 'session_cleanup_interval_seconds', 300)  # 5 minutes
        self._session_timeout = getattr(self.config, 'session_timeout_seconds', 3600)  # 1 hour
        
        logger.info("TroubleshootingEngine initialized with structured workflow capabilities")
    
    async def initiate_troubleshooting(
        self,
        query_text: str,
        problem_category: ProblemCategory,
        customer_emotion: EmotionalState,
        reasoning_state: Optional[ReasoningState] = None,
        session_id: Optional[str] = None
    ) -> TroubleshootingState:
        """
        Initiates a structured troubleshooting workflow based on the customer's query, problem category, emotional state, and optional reasoning insights.
        
        Analyzes the provided information to create a troubleshooting state, integrates reasoning insights if available, retrieves relevant workflows, and selects a recommended workflow tailored to the situation.
        
        Returns:
            TroubleshootingState: The populated troubleshooting state with available workflows and a recommended workflow.
        """
        with tracer.start_as_current_span("troubleshooting_engine.initiate") as span:
            span.set_attribute("problem_category", problem_category.value)
            span.set_attribute("customer_emotion", customer_emotion.value)
            
            # Create troubleshooting state
            troubleshooting_state = TroubleshootingState(
                query_text=query_text,
                problem_category=problem_category,
                customer_emotion=customer_emotion
            )
            
            # Integrate reasoning insights if available
            if reasoning_state:
                troubleshooting_state.reasoning_insights = self._extract_reasoning_insights(reasoning_state)
                troubleshooting_state.solution_candidates = reasoning_state.solution_candidates
                span.set_attribute("reasoning_insights", len(troubleshooting_state.reasoning_insights))
            
            # Get available workflows for problem category
            available_workflows = await self.workflow_library.get_workflows_for_category(
                problem_category, customer_emotion
            )
            troubleshooting_state.available_workflows = available_workflows
            
            # Select optimal workflow
            recommended_workflow = await self._select_optimal_workflow(
                troubleshooting_state, available_workflows
            )
            troubleshooting_state.recommended_workflow = recommended_workflow
            
            span.set_attribute("available_workflows", len(available_workflows))
            span.set_attribute("recommended_workflow", recommended_workflow.name if recommended_workflow else "none")
            
            logger.info(f"Initiated troubleshooting for {problem_category.value} with {len(available_workflows)} workflows")
            
            return troubleshooting_state
    
    async def start_troubleshooting_session(
        self,
        troubleshooting_state: TroubleshootingState,
        workflow: Optional[TroubleshootingWorkflow] = None,
        session_id: Optional[str] = None
    ) -> TroubleshootingSession:
        """
        Begins an active troubleshooting session using the provided troubleshooting state and workflow.
        
        If no workflow is specified, uses the recommended workflow from the troubleshooting state. Adapts the workflow based on customer emotion and technical level if enabled in the configuration, initializes the first diagnostic step, and tracks the session as active.
        
        Returns:
            TroubleshootingSession: The initialized and active troubleshooting session.
        """
        with tracer.start_as_current_span("troubleshooting_engine.start_session") as span:
            
            # Use recommended workflow if none specified
            selected_workflow = workflow or troubleshooting_state.recommended_workflow
            if not selected_workflow:
                raise ValueError("No workflow available for troubleshooting session")
            
            # Create troubleshooting session
            session = TroubleshootingSession(
                session_id=session_id or str(uuid.uuid4()),
                workflow=selected_workflow,
                customer_emotional_state=troubleshooting_state.customer_emotion,
                customer_technical_level=self._assess_customer_technical_level(troubleshooting_state)
            )
            
            # Adapt workflow based on customer characteristics
            if self.config.emotional_adaptation_enabled:
                await self._adapt_workflow_for_emotion(session)
            
            if self.config.technical_level_adaptation:
                await self._adapt_workflow_for_technical_level(session)
            
            # Initialize first diagnostic step
            first_step = await self.diagnostic_sequencer.get_next_step(session)
            if first_step:
                session.current_step = first_step
                logger.info(f"Starting with diagnostic step: {first_step.title}")
            
            # Track active session and update last activity time
            session.last_activity_time = datetime.utcnow()
            self.active_sessions[session.session_id] = session
            troubleshooting_state.active_session = session
            
            # Clean up stale sessions if needed
            await self._cleanup_stale_sessions()
            
            span.set_attribute("session_id", session.session_id)
            span.set_attribute("workflow_name", selected_workflow.name)
            span.set_attribute("customer_technical_level", session.customer_technical_level)
            
            logger.info(f"Started troubleshooting session {session.session_id} with workflow: {selected_workflow.name}")
            
            return session
    
    async def execute_diagnostic_step(
        self,
        session: TroubleshootingSession,
        step_result: Dict[str, Any],
        customer_feedback: Optional[str] = None
    ) -> Tuple[bool, Optional[DiagnosticStep]]:
        """
        Executes the current diagnostic step in a troubleshooting session, evaluates its outcome, and determines the next step.
        
        Parameters:
            session (TroubleshootingSession): The active troubleshooting session containing the current diagnostic step.
            step_result (Dict[str, Any]): The results produced from executing the diagnostic step.
            customer_feedback (Optional[str]): Optional feedback provided by the customer for this step.
        
        Returns:
            Tuple[bool, Optional[DiagnosticStep]]: A tuple where the first element indicates if the step was successful, and the second is the next diagnostic step to execute, or None if escalation is triggered or no further steps remain.
        
        Raises:
            ValueError: If there is no current diagnostic step to execute.
        """
        with tracer.start_as_current_span("troubleshooting_engine.execute_step") as span:
            
            if not session.current_step:
                raise ValueError("No current diagnostic step to execute")
            
            current_step = session.current_step
            span.set_attribute("step_type", current_step.step_type.value)
            span.set_attribute("step_title", current_step.title)
            
            # Update step execution status
            current_step.execution_end_time = datetime.now()
            current_step.result_data = step_result
            if customer_feedback:
                current_step.customer_feedback = customer_feedback
            
            # Evaluate step success
            step_successful = await self._evaluate_step_success(current_step, step_result)
            current_step.execution_status = "completed" if step_successful else "failed"
            
            # Update session tracking
            if step_successful:
                session.completed_steps.append(current_step)
                logger.info(f"Diagnostic step '{current_step.title}' completed successfully")
            else:
                session.failed_steps.append(current_step)
                logger.warning(f"Diagnostic step '{current_step.title}' failed")
            
            # Check for verification checkpoint
            if self.config.enable_verification_checkpoints:
                verification_needed = await self._check_verification_needed(session)
                if verification_needed:
                    verification_result = await self.verification_system.run_verification_checkpoint(session)
                    session.verification_results.append(verification_result)
            
            # Check escalation criteria
            escalation_needed = await self.escalation_manager.check_escalation_criteria(session)
            if escalation_needed:
                logger.info(f"Escalation criteria met for session {session.session_id}")
                session.outcome = TroubleshootingOutcome.ESCALATED
                session.escalation_reason = await self.escalation_manager.get_escalation_reason(session)
                return step_successful, None
            
            # Get next diagnostic step
            next_step = await self.diagnostic_sequencer.get_next_step(session, step_successful)
            session.current_step = next_step
            
            # Update progress, handling case where there are no diagnostic steps
            if hasattr(session.workflow, 'diagnostic_steps') and session.workflow.diagnostic_steps:
                session.overall_progress = len(session.completed_steps) / len(session.workflow.diagnostic_steps)
            else:
                session.overall_progress = 0.0  # Default to 0 if no steps are defined
            
            span.set_attribute("step_successful", step_successful)
            span.set_attribute("next_step_available", next_step is not None)
            span.set_attribute("session_progress", session.overall_progress)
            
            return step_successful, next_step
    
    async def complete_troubleshooting_session(
        self,
        session: TroubleshootingSession,
        resolution_achieved: bool,
        resolution_summary: str = ""
    ) -> TroubleshootingOutcome:
        """
        Finalize a troubleshooting session and determine its outcome based on resolution status, escalation, and completed steps.
        
        If verification checkpoints are enabled and the session is marked as resolved, a final verification is performed, which may update the outcome to require follow-up if verification does not pass. Generates follow-up actions, removes the session from active tracking, and records session data for workflow learning if enabled.
        
        Returns:
            TroubleshootingOutcome: The final outcome of the troubleshooting session.
        """
        with tracer.start_as_current_span("troubleshooting_engine.complete_session") as span:
            
            session.end_time = datetime.now()
            session.resolution_summary = resolution_summary
            
            # Determine final outcome
            if resolution_achieved:
                session.outcome = TroubleshootingOutcome.RESOLVED
            elif session.escalation_reason:
                session.outcome = TroubleshootingOutcome.ESCALATED
            elif len(session.completed_steps) > 0:
                session.outcome = TroubleshootingOutcome.PARTIALLY_RESOLVED
            else:
                session.outcome = TroubleshootingOutcome.DEFERRED
            
            # Run final verification if resolved
            if resolution_achieved and self.config.enable_verification_checkpoints:
                final_verification = await self.verification_system.run_final_verification(session)
                session.verification_results.append(final_verification)
                
                if final_verification.status != VerificationStatus.PASSED:
                    session.outcome = TroubleshootingOutcome.REQUIRES_FOLLOW_UP
                    session.follow_up_actions.append("Verify resolution persistence")
            
            # Generate follow-up actions
            session.follow_up_actions.extend(
                await self._generate_follow_up_actions(session)
            )
            
            # Remove from active sessions
            if session.session_id in self.active_sessions:
                del self.active_sessions[session.session_id]
            
            # Clean up stale sessions if we have many active sessions
            if len(self.active_sessions) > getattr(self.config, 'session_cleanup_threshold', 10):
                await self._cleanup_stale_sessions()
            
            # Record session for learning
            if self.config.enable_workflow_learning:
                await self._record_session_learning(session)
            
            span.set_attribute("final_outcome", session.outcome.value)
            span.set_attribute("resolution_achieved", resolution_achieved)
            span.set_attribute("steps_completed", len(session.completed_steps))
            span.set_attribute("session_duration", (session.end_time - session.start_time).total_seconds())
            
            logger.info(f"Completed troubleshooting session {session.session_id} with outcome: {session.outcome.value}")
            
            return session.outcome
    
    # Helper methods
    
    def _extract_reasoning_insights(self, reasoning_state: ReasoningState) -> Dict[str, Any]:
        """
        Extracts key diagnostic and contextual insights from a ReasoningState object.
        
        Returns:
            insights (dict): Dictionary containing complexity score, urgency level, key entities, inferred intent, tool decision, knowledge gaps, solution confidence, estimated time, and overall confidence, if available.
        """
        insights = {}
        
        if reasoning_state.query_analysis:
            insights['complexity_score'] = reasoning_state.query_analysis.complexity_score
            insights['urgency_level'] = reasoning_state.query_analysis.urgency_level
            insights['key_entities'] = reasoning_state.query_analysis.key_entities
            insights['inferred_intent'] = reasoning_state.query_analysis.inferred_intent
        
        if reasoning_state.tool_reasoning:
            insights['tool_decision'] = reasoning_state.tool_reasoning.decision_type.value
            insights['knowledge_gaps'] = reasoning_state.tool_reasoning.knowledge_gaps
        
        if reasoning_state.selected_solution:
            insights['solution_confidence'] = reasoning_state.selected_solution.confidence_score
            insights['estimated_time'] = reasoning_state.selected_solution.estimated_time_minutes
        
        insights['overall_confidence'] = reasoning_state.overall_confidence
        
        return insights
    
    async def _select_optimal_workflow(
        self,
        troubleshooting_state: TroubleshootingState,
        available_workflows: List[TroubleshootingWorkflow]
    ) -> Optional[TroubleshootingWorkflow]:
        """
        Selects the most suitable troubleshooting workflow from a list based on customer emotional state, workflow success rate, and reasoning insights.
        
        Considers factors such as workflow success rate, estimated time, difficulty level, customer urgency or confusion, and problem complexity to compute a score for each workflow. Returns the workflow with the highest score, or None if no workflows are available.
        
        Parameters:
            troubleshooting_state (TroubleshootingState): The current troubleshooting context, including customer emotion and reasoning insights.
            available_workflows (List[TroubleshootingWorkflow]): Candidate workflows to evaluate.
        
        Returns:
            Optional[TroubleshootingWorkflow]: The workflow with the highest suitability score, or None if no workflows are provided.
        """
        
        if not available_workflows:
            return None
        
        # Score workflows based on various factors
        workflow_scores = []
        
        for workflow in available_workflows:
            score = 0.0
            
            # Base score from workflow success rate
            score += workflow.success_rate * 0.4
            
            # Adjust for customer emotional state
            if troubleshooting_state.customer_emotion == EmotionalState.URGENT:
                # Prefer faster workflows for urgent customers
                time_factor = max(0.1, 1.0 - (workflow.estimated_time_minutes / 60))
                score += time_factor * 0.3
            elif troubleshooting_state.customer_emotion == EmotionalState.CONFUSED:
                # Prefer simpler workflows for confused customers
                simplicity_factor = max(0.1, 1.0 - (workflow.difficulty_level / 5))
                score += simplicity_factor * 0.3
            
            # Adjust for reasoning insights if available
            if troubleshooting_state.reasoning_insights:
                complexity = troubleshooting_state.reasoning_insights.get('complexity_score', 0.5)
                urgency = troubleshooting_state.reasoning_insights.get('urgency_level', 2)
                
                # Match workflow complexity to problem complexity
                complexity_match = 1.0 - abs(complexity - (workflow.difficulty_level / 5))
                score += complexity_match * 0.2
                
                # Adjust for urgency
                if urgency >= 4:
                    time_factor = max(0.1, 1.0 - (workflow.estimated_time_minutes / 30))
                    score += time_factor * 0.1
            
            workflow_scores.append((workflow, score))
        
        # Sort by score and return best workflow
        workflow_scores.sort(key=lambda x: x[1], reverse=True)
        selected_workflow = workflow_scores[0][0]
        
        logger.info(f"Selected workflow '{selected_workflow.name}' with score {workflow_scores[0][1]:.2f}")
        
        return selected_workflow
    
    def _assess_customer_technical_level(self, troubleshooting_state: TroubleshootingState) -> int:
        """
        Estimate the customer's technical proficiency level on a scale from 1 to 5 based on their query content and emotional state.
        
        The assessment considers the presence of technical terms, query length, and emotional indicators to infer the customer's familiarity with technical concepts.
        
        Returns:
            int: An integer from 1 (least technical) to 5 (most technical) representing the estimated technical level.
        """
        
        base_level = 2  # Default assumption
        
        # Analyze query text for technical indicators
        query_lower = troubleshooting_state.query_text.lower()
        
        # Technical terms indicate higher level
        technical_terms = [
            'imap', 'smtp', 'ssl', 'tls', 'oauth', 'api', 'server', 'port',
            'configuration', 'protocol', 'authentication', 'encryption'
        ]
        tech_term_count = sum(1 for term in technical_terms if term in query_lower)
        if tech_term_count >= 3:
            base_level += 2
        elif tech_term_count >= 1:
            base_level += 1
        
        # Detailed problem descriptions indicate higher level
        if len(troubleshooting_state.query_text) > 200:
            base_level += 1
        
        # Confusion emotion indicates lower level
        if troubleshooting_state.customer_emotion == EmotionalState.CONFUSED:
            base_level -= 1
        
        # Professional tone indicates higher level
        if troubleshooting_state.customer_emotion == EmotionalState.PROFESSIONAL:
            base_level += 1
        
        return max(1, min(5, base_level))
    
    async def _adapt_workflow_for_emotion(self, session: TroubleshootingSession) -> None:
        """
        Adapts the troubleshooting workflow in the session to address the customer's emotional state.
        
        Modifies session notes to reflect workflow adjustments such as prioritizing quick resolutions, adding verification checkpoints, simplifying steps, or optimizing for speed based on the customer's emotion.
        """
        
        emotion = session.customer_emotional_state
        
        if emotion == EmotionalState.FRUSTRATED:
            # Prioritize quick wins and add reassurance
            session.session_notes.append("Adapted for frustrated customer: prioritizing quick resolution steps")
            
        elif emotion == EmotionalState.ANXIOUS:
            # Add extra verification and reassurance
            session.session_notes.append("Adapted for anxious customer: adding extra verification checkpoints")
            
        elif emotion == EmotionalState.CONFUSED:
            # Simplify steps and add more detailed instructions
            session.session_notes.append("Adapted for confused customer: simplifying diagnostic steps")
            
        elif emotion == EmotionalState.URGENT:
            # Focus on fastest resolution path
            session.session_notes.append("Adapted for urgent customer: optimizing for speed")
    
    async def _adapt_workflow_for_technical_level(self, session: TroubleshootingSession) -> None:
        """
        Adapts the troubleshooting workflow in the session based on the customer's technical level.
        
        For beginner customers (technical level 2 or below), adds notes to provide more detailed instructions and safety checks. For advanced customers (technical level 4 or above), adds notes to enable more complex diagnostics and skip basic checks.
        """
        
        tech_level = session.customer_technical_level
        
        if tech_level <= 2:
            # Beginner: Add more detailed instructions and safety checks
            session.session_notes.append(f"Adapted for beginner level {tech_level}: adding detailed instructions")
            
        elif tech_level >= 4:
            # Advanced: Allow more complex steps and skip basic checks
            session.session_notes.append(f"Adapted for advanced level {tech_level}: enabling complex diagnostics")
    
    async def _evaluate_step_success(
        self,
        step: DiagnosticStep,
        step_result: Dict[str, Any]
    ) -> bool:
        """
        Determines if a diagnostic step was successful based on explicit success flags, matching success criteria, failure indicators, or the presence of result data.
        
        Parameters:
            step (DiagnosticStep): The diagnostic step being evaluated.
            step_result (Dict[str, Any]): The result data from executing the step.
        
        Returns:
            bool: True if the step is considered successful, otherwise False.
        """
        
        # Check explicit success/failure indicators
        if 'success' in step_result:
            return bool(step_result['success'])
        
        # Check against success criteria
        for criteria in step.success_criteria:
            if criteria.lower() in str(step_result).lower():
                return True
        
        # Check against failure indicators
        for indicator in step.failure_indicators:
            if indicator.lower() in str(step_result).lower():
                return False
        
        # Default evaluation based on result presence
        return bool(step_result and step_result.get('data'))
    
    async def _check_verification_needed(self, session: TroubleshootingSession) -> bool:
        """
        Determine whether a verification checkpoint is required based on the number of completed steps since the last verification.
        
        Returns:
            bool: True if the number of steps since the last verification meets or exceeds the configured verification interval; otherwise, False.
        """
        
        steps_since_verification = len(session.completed_steps) - len(session.verification_results)
        return steps_since_verification >= self.config.verification_interval_steps
    
    async def _generate_follow_up_actions(self, session: TroubleshootingSession) -> List[str]:
        """
        Generate a list of recommended follow-up actions based on the outcome of a troubleshooting session.
        
        Returns:
            actions (List[str]): A list of follow-up actions tailored to the session's final outcome.
        """
        
        actions = []
        
        if session.outcome == TroubleshootingOutcome.RESOLVED:
            actions.append("Monitor for issue recurrence")
            actions.append("Document successful resolution approach")
            
        elif session.outcome == TroubleshootingOutcome.PARTIALLY_RESOLVED:
            actions.append("Continue with remaining troubleshooting steps")
            actions.append("Schedule follow-up contact")
            
        elif session.outcome == TroubleshootingOutcome.ESCALATED:
            actions.append("Prepare escalation documentation")
            actions.append("Brief specialist on attempted solutions")
            
        elif session.outcome == TroubleshootingOutcome.REQUIRES_FOLLOW_UP:
            actions.append("Schedule verification call")
            actions.append("Provide additional resources")
        
        return actions
    
    async def _record_session_learning(self, session: TroubleshootingSession) -> None:
        """
        Records the outcomes and step patterns of a troubleshooting session to support workflow improvement and learning.
        
        This method logs information about successful and failed diagnostic steps, which can be used to refine troubleshooting workflows over time.
        """
        
        # This would integrate with a learning system to improve workflows
        logger.info(f"Recording learning insights from session {session.session_id}")
        
        # Track success patterns
        if session.outcome == TroubleshootingOutcome.RESOLVED:
            successful_steps = [step.step_type.value for step in session.completed_steps]
            logger.debug(f"Successful step sequence: {' -> '.join(successful_steps)}")
        
        # Track failure patterns
        if session.failed_steps:
            failed_step_types = [step.step_type.value for step in session.failed_steps]
            logger.debug(f"Failed steps for learning: {failed_step_types}")
    
    async def _cleanup_stale_sessions(self) -> int:
        """
        Clean up stale sessions that have exceeded the inactivity timeout.
        
        Returns:
            int: Number of sessions that were cleaned up
        """
        current_time = time.time()
        
        # Only run cleanup if enough time has passed since the last cleanup
        if current_time - self._last_cleanup_time < self._cleanup_interval:
            return 0
            
        logger.debug(f"Starting cleanup of stale sessions (timeout: {self._session_timeout}s)")
        
        # Make a copy of session IDs to avoid modifying dict during iteration
        session_ids = list(self.active_sessions.keys())
        removed_count = 0
        
        for session_id in session_ids:
            try:
                session = self.active_sessions.get(session_id)
                if not session:
                    continue
                    
                # Calculate session age in seconds
                session_age = current_time - session.last_activity_time.timestamp()
                
                if session_age > self._session_timeout:
                    # Log session termination
                    logger.info(f"Removing stale session {session_id} (inactive for {session_age:.1f}s)")
                    
                    # Add session to history before removing
                    if hasattr(session, 'troubleshooting_history'):
                        session.troubleshooting_history.append({
                            'timestamp': datetime.utcnow(),
                            'event': 'session_terminated',
                            'reason': 'inactivity_timeout',
                            'inactive_seconds': session_age
                        })
                    
                    # Remove the session
                    self.active_sessions.pop(session_id, None)
                    removed_count += 1
                    
            except Exception as e:
                logger.error(f"Error cleaning up session {session_id}: {str(e)}", exc_info=True)
        
        # Update last cleanup time
        self._last_cleanup_time = current_time
        
        if removed_count > 0:
            logger.info(f"Cleaned up {removed_count} stale sessions")
        
        return removed_count