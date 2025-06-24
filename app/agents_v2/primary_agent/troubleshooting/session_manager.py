"""
Agent Sparrow - Troubleshooting Session State Management

This module implements comprehensive session state management for troubleshooting
workflows with persistence, recovery, and adaptive session handling.
"""

import logging
import asyncio
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
import json
import uuid

from .troubleshooting_schemas import (
    TroubleshootingSession,
    TroubleshootingState,
    TroubleshootingWorkflow,
    DiagnosticStep,
    TroubleshootingOutcome,
    TroubleshootingConfig,
    TroubleshootingPhase
)
from app.agents_v2.primary_agent.prompts.emotion_templates import EmotionalState

logger = logging.getLogger(__name__)


class TroubleshootingSessionManager:
    """
    Comprehensive troubleshooting session state management
    
    Provides systematic session management through:
    - Session persistence and recovery
    - Multi-session coordination
    - Session analytics and learning
    - Adaptive session optimization
    - Session lifecycle management
    """
    
    def __init__(self, config: TroubleshootingConfig):
        """
        Initializes the TroubleshootingSessionManager with the provided configuration, setting up session storage and analytics tracking.
        """
        self.config = config
        
        # Session storage
        self.active_sessions: Dict[str, TroubleshootingSession] = {}
        self.completed_sessions: Dict[str, TroubleshootingSession] = {}
        self.session_history: List[str] = []  # Session IDs in chronological order
        
        # Session analytics
        self.session_analytics: Dict[str, Any] = {
            'total_sessions': 0,
            'successful_sessions': 0,
            'escalated_sessions': 0,
            'average_duration': 0.0,
            'common_patterns': {},
            'workflow_performance': {}
        }
        
        logger.info("TroubleshootingSessionManager initialized with state persistence")
    
    async def create_session(
        self,
        workflow: TroubleshootingWorkflow,
        customer_emotional_state: EmotionalState,
        customer_technical_level: int,
        session_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> TroubleshootingSession:
        """
        Asynchronously creates and initializes a new troubleshooting session with the specified workflow, customer emotional state, technical level, and optional context.
        
        If no session ID is provided, a unique one is generated. The session is initialized with the given workflow and customer attributes, optional context (system context, environmental factors, customer preferences), and set to the initial assessment phase with zero progress. The session is stored as active, added to the session history, and analytics are updated.
        
        Returns:
            TroubleshootingSession: The newly created troubleshooting session.
        """
        
        # Generate session ID if not provided
        if not session_id:
            session_id = str(uuid.uuid4())
        
        # Create session
        session = TroubleshootingSession(
            session_id=session_id,
            workflow=workflow,
            customer_emotional_state=customer_emotional_state,
            customer_technical_level=customer_technical_level,
            start_time=datetime.now()
        )
        
        # Apply context if provided
        if context:
            session.system_context = context.get('system_context', {})
            session.environmental_factors = context.get('environmental_factors', {})
            session.customer_preferences = context.get('customer_preferences', {})
        
        # Initialize session state
        session.current_phase = TroubleshootingPhase.INITIAL_ASSESSMENT
        session.overall_progress = 0.0
        
        # Store session
        self.active_sessions[session_id] = session
        self.session_history.append(session_id)
        
        # Update analytics
        self.session_analytics['total_sessions'] += 1
        
        logger.info(f"Created troubleshooting session {session_id} with workflow: {workflow.name}")
        
        return session
    
    async def get_session(self, session_id: str) -> Optional[TroubleshootingSession]:
        """
        Retrieve a troubleshooting session by its ID from active or completed sessions.
        
        Returns:
            TroubleshootingSession or None: The session if found; otherwise, None.
        """
        
        # Check active sessions first
        if session_id in self.active_sessions:
            return self.active_sessions[session_id]
        
        # Check completed sessions
        if session_id in self.completed_sessions:
            return self.completed_sessions[session_id]
        
        return None
    
    async def update_session_progress(
        self,
        session_id: str,
        completed_step: DiagnosticStep,
        step_successful: bool,
        customer_feedback: Optional[str] = None
    ) -> TroubleshootingSession:
        """
        Updates the progress of an active troubleshooting session after a diagnostic step is completed.
        
        If customer feedback is provided, analyzes it for emotional state changes and updates the session accordingly. Progress metrics are recalculated, and session optimization is triggered if enabled. Raises a ValueError if the session is not found.
        
        Returns:
            TroubleshootingSession: The updated session object.
        """
        
        session = self.active_sessions.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        # Update step tracking
        if step_successful:
            session.completed_steps.append(completed_step)
        else:
            session.failed_steps.append(completed_step)
        
        # Update customer feedback if provided
        if customer_feedback:
            completed_step.customer_feedback = customer_feedback
            
            # Analyze feedback for emotional state changes
            new_emotion = await self._analyze_feedback_emotion(customer_feedback)
            if new_emotion and new_emotion != session.customer_emotional_state:
                await self._update_customer_emotional_state(session, new_emotion)
        
        # Update progress metrics
        await self._update_progress_metrics(session)
        
        # Check for session optimization opportunities
        if self.config.enable_session_optimization:
            await self._optimize_session_if_needed(session)
        
        logger.debug(f"Updated session {session_id} progress: {session.overall_progress:.2f}")
        
        return session
    
    async def complete_session(
        self,
        session_id: str,
        outcome: TroubleshootingOutcome,
        resolution_summary: str = "",
        follow_up_actions: Optional[List[str]] = None
    ) -> TroubleshootingSession:
        """
        Marks an active troubleshooting session as completed, finalizes its outcome, and updates analytics and learning records.
        
        Parameters:
            session_id (str): Unique identifier of the session to complete.
            outcome (TroubleshootingOutcome): The final outcome of the session.
            resolution_summary (str, optional): Summary describing the session's resolution.
            follow_up_actions (List[str], optional): Additional actions to be taken after session completion.
        
        Returns:
            TroubleshootingSession: The completed session object with updated metrics and outcome.
        
        Raises:
            ValueError: If the specified session is not found among active sessions.
        """
        
        session = self.active_sessions.get(session_id)
        if not session:
            raise ValueError(f"Active session {session_id} not found")
        
        # Update session completion
        session.end_time = datetime.now()
        session.outcome = outcome
        session.resolution_summary = resolution_summary
        
        if follow_up_actions:
            session.follow_up_actions.extend(follow_up_actions)
        
        # Calculate final metrics
        await self._calculate_final_session_metrics(session)
        
        # Move to completed sessions
        del self.active_sessions[session_id]
        self.completed_sessions[session_id] = session
        
        # Update analytics
        await self._update_session_analytics(session)
        
        # Record session learning
        if self.config.enable_session_learning:
            await self._record_session_learning(session)
        
        logger.info(f"Completed session {session_id} with outcome: {outcome.value}")
        
        return session
    
    async def pause_session(
        self,
        session_id: str,
        pause_reason: str = "User requested pause"
    ) -> TroubleshootingSession:
        """
        Pauses an active troubleshooting session and records the reason for the pause.
        
        Raises:
            ValueError: If the session with the specified ID is not found.
        
        Returns:
            TroubleshootingSession: The paused session with updated notes.
        """
        
        session = self.active_sessions.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        # Add pause note
        session.session_notes.append(f"Session paused: {pause_reason}")
        
        # Update current step if active
        if session.current_step and session.current_step.execution_start_time:
            session.current_step.execution_notes = f"Paused: {pause_reason}"
        
        logger.info(f"Paused session {session_id}: {pause_reason}")
        
        return session
    
    async def resume_session(
        self,
        session_id: str,
        resume_context: Optional[Dict[str, Any]] = None
    ) -> TroubleshootingSession:
        """
        Resumes a paused troubleshooting session, optionally updating system context and environmental factors.
        
        Parameters:
            session_id (str): The unique identifier of the session to resume.
            resume_context (Optional[Dict[str, Any]]): Optional context updates for system or environmental factors.
        
        Returns:
            TroubleshootingSession: The resumed session object.
        
        Raises:
            ValueError: If the session with the given ID is not found.
        """
        
        session = self.active_sessions.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        # Add resume note
        session.session_notes.append("Session resumed")
        
        # Update context if provided
        if resume_context:
            session.system_context.update(resume_context.get('system_context', {}))
            session.environmental_factors.update(resume_context.get('environmental_factors', {}))
        
        # Reset current step execution time if needed
        if session.current_step:
            session.current_step.execution_start_time = datetime.now()
        
        logger.info(f"Resumed session {session_id}")
        
        return session
    
    async def get_session_recommendations(
        self,
        session_id: str
    ) -> Dict[str, Any]:
        """
        Generate recommendations to improve the effectiveness of a troubleshooting session based on its performance metrics.
        
        Analyzes session failure rate, workflow complexity relative to customer technical level, session duration, customer emotional state, and escalation likelihood to provide actionable suggestions for workflow adjustments, complexity changes, timing optimizations, customer adaptations, and escalation considerations.
        
        Parameters:
            session_id (str): The unique identifier of the troubleshooting session.
        
        Returns:
            Dict[str, Any]: A dictionary containing categorized recommendations for the session.
        
        Raises:
            ValueError: If the session with the specified ID is not found.
        """
        
        session = await self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        recommendations = {
            'workflow_adjustments': [],
            'complexity_changes': [],
            'timing_optimizations': [],
            'customer_adaptations': [],
            'escalation_considerations': []
        }
        
        # Analyze session performance
        session_duration = datetime.now() - session.start_time
        failure_rate = len(session.failed_steps) / max(1, len(session.completed_steps) + len(session.failed_steps))
        
        # Workflow adjustment recommendations
        if failure_rate >= 0.4:
            recommendations['workflow_adjustments'].append(
                "Consider switching to simpler workflow due to high failure rate"
            )
        
        # Complexity recommendations
        if session.customer_technical_level <= 2 and session.workflow.difficulty_level >= 4:
            recommendations['complexity_changes'].append(
                "Reduce workflow complexity for customer technical level"
            )
        
        # Timing recommendations
        if session_duration > timedelta(minutes=session.workflow.estimated_time_minutes * 1.5):
            recommendations['timing_optimizations'].append(
                "Session duration exceeds estimates - consider faster approaches"
            )
        
        # Customer adaptation recommendations
        if session.customer_emotional_state == EmotionalState.FRUSTRATED:
            recommendations['customer_adaptations'].append(
                "Customer showing frustration - prioritize quick wins and reassurance"
            )
        
        # Escalation recommendations
        escalation_score = await self._calculate_escalation_score(session)
        if escalation_score >= 0.7:
            recommendations['escalation_considerations'].append(
                f"High escalation score ({escalation_score:.2f}) - consider specialist assistance"
            )
        
        return recommendations
    
    async def get_session_analytics(self) -> Dict[str, Any]:
        """
        Return a comprehensive summary of troubleshooting session analytics.
        
        The analytics include overall session counts, calculated success and escalation rates, counts of active and completed sessions, and recent session trends such as average duration, success rate, and common workflows.
         
        Returns:
            Dict[str, Any]: A dictionary containing aggregate session analytics and recent trends.
        """
        
        analytics = self.session_analytics.copy()
        
        # Calculate current metrics
        if analytics['total_sessions'] > 0:
            analytics['success_rate'] = analytics['successful_sessions'] / analytics['total_sessions']
            analytics['escalation_rate'] = analytics['escalated_sessions'] / analytics['total_sessions']
        
        # Add active session statistics
        analytics['active_sessions_count'] = len(self.active_sessions)
        analytics['completed_sessions_count'] = len(self.completed_sessions)
        
        # Recent session trends
        recent_sessions = await self._get_recent_session_trends()
        analytics['recent_trends'] = recent_sessions
        
        return analytics
    
    # Private helper methods
    
    async def _analyze_feedback_emotion(self, feedback: str) -> Optional[EmotionalState]:
        """
        Analyzes customer feedback text to infer the customer's emotional state.
        
        Returns:
            EmotionalState or None: The detected emotional state based on feedback content, or None if no clear emotion is identified.
        """
        
        feedback_lower = feedback.lower()
        
        # Positive emotion indicators
        if any(word in feedback_lower for word in ['great', 'good', 'thanks', 'working', 'helpful']):
            return EmotionalState.SATISFIED
        
        # Frustration indicators
        elif any(word in feedback_lower for word in ['frustrated', 'annoyed', 'waste', 'ridiculous']):
            return EmotionalState.FRUSTRATED
        
        # Confusion indicators
        elif any(word in feedback_lower for word in ['confused', 'don\'t understand', 'unclear', 'lost']):
            return EmotionalState.CONFUSED
        
        # Urgency indicators
        elif any(word in feedback_lower for word in ['urgent', 'asap', 'quickly', 'emergency']):
            return EmotionalState.URGENT
        
        return None
    
    async def _update_customer_emotional_state(
        self,
        session: TroubleshootingSession,
        new_emotion: EmotionalState
    ) -> None:
        """
        Update the customer's emotional state in the session and apply adaptive changes based on the new emotion.
        
        If the emotional state changes to 'frustrated', the session complexity is reduced. If it improves to 'satisfied' from a negative state, a note is added to maintain the current approach.
        """
        
        old_emotion = session.customer_emotional_state
        session.customer_emotional_state = new_emotion
        
        session.session_notes.append(
            f"Customer emotional state changed: {old_emotion.value} → {new_emotion.value}"
        )
        
        # Apply adaptive changes based on new emotion
        if new_emotion == EmotionalState.FRUSTRATED and old_emotion != EmotionalState.FRUSTRATED:
            session.difficulty_adjustments.append("Reduced complexity due to customer frustration")
        
        elif new_emotion == EmotionalState.SATISFIED and old_emotion in [EmotionalState.FRUSTRATED, EmotionalState.CONFUSED]:
            session.session_notes.append("Customer satisfaction improved - maintain current approach")
        
        logger.info(f"Session {session.session_id} emotion changed: {old_emotion.value} → {new_emotion.value}")
    
    async def _update_progress_metrics(self, session: TroubleshootingSession) -> None:
        """
        Updates the overall and per-phase progress metrics for a troubleshooting session.
        
        Calculates the ratio of completed diagnostic steps to total steps for overall progress, and updates progress for each workflow phase based on completed steps within that phase.
        """
        
        total_steps = len(session.workflow.diagnostic_steps)
        completed_steps = len(session.completed_steps)
        
        if total_steps > 0:
            session.overall_progress = completed_steps / total_steps
        
        # Update phase progress
        for phase in session.workflow.phases:
            phase_steps = [
                step for step in session.workflow.diagnostic_steps
                if hasattr(step, 'phase') and step.phase == phase
            ]
            if phase_steps:
                phase_completed = len([
                    step for step in session.completed_steps
                    if step in phase_steps
                ])
                session.phase_progress[phase] = phase_completed / len(phase_steps)
    
    async def _optimize_session_if_needed(self, session: TroubleshootingSession) -> None:
        """
        Evaluates the session for high failure rate, extended duration, or customer frustration, and applies appropriate optimizations if any triggers are met.
        
        If optimization is needed, updates the session's difficulty adjustments and notes to reflect the changes.
        """
        
        # Check for optimization triggers
        optimization_needed = False
        optimizations = []
        
        # High failure rate optimization
        failure_rate = len(session.failed_steps) / max(1, len(session.completed_steps) + len(session.failed_steps))
        if failure_rate >= 0.5:
            optimization_needed = True
            optimizations.append("Reduce step complexity due to high failure rate")
        
        # Long duration optimization
        session_duration = datetime.now() - session.start_time
        expected_duration = timedelta(minutes=session.workflow.estimated_time_minutes)
        if session_duration > expected_duration * 1.5:
            optimization_needed = True
            optimizations.append("Accelerate remaining steps due to extended duration")
        
        # Customer frustration optimization
        if session.customer_emotional_state == EmotionalState.FRUSTRATED:
            optimization_needed = True
            optimizations.append("Prioritize quick resolution due to customer frustration")
        
        if optimization_needed:
            session.difficulty_adjustments.extend(optimizations)
            session.session_notes.append(f"Applied optimizations: {', '.join(optimizations)}")
            logger.info(f"Applied session optimizations for {session.session_id}")
    
    async def _calculate_final_session_metrics(self, session: TroubleshootingSession) -> None:
        """
        Calculates and assigns final metrics for a completed troubleshooting session, including total duration, success score based on outcome, and efficiency score relative to expected and actual steps.
        """
        
        if session.end_time and session.start_time:
            duration = session.end_time - session.start_time
            session.total_duration_minutes = duration.total_seconds() / 60
        
        # Calculate success metrics
        if session.outcome == TroubleshootingOutcome.RESOLVED:
            session.success_score = 1.0
        elif session.outcome == TroubleshootingOutcome.PARTIALLY_RESOLVED:
            session.success_score = 0.7
        elif session.outcome == TroubleshootingOutcome.ESCALATED:
            session.success_score = 0.4
        else:
            session.success_score = 0.2
        
        # Calculate efficiency score
        expected_steps = len(session.workflow.diagnostic_steps)
        actual_steps = len(session.completed_steps) + len(session.failed_steps)
        
        if expected_steps > 0:
            session.efficiency_score = min(1.0, expected_steps / max(1, actual_steps))
        else:
            session.efficiency_score = 0.5
    
    async def _update_session_analytics(self, session: TroubleshootingSession) -> None:
        """
        Updates aggregate session analytics with the latest session outcome, duration, and workflow-specific performance metrics.
        
        This includes incrementing counts for successful and escalated sessions, recalculating average session duration, and updating workflow usage statistics such as total uses, successful resolutions, average duration, and success rate.
        """
        
        # Update outcome counts
        if session.outcome == TroubleshootingOutcome.RESOLVED:
            self.session_analytics['successful_sessions'] += 1
        elif session.outcome == TroubleshootingOutcome.ESCALATED:
            self.session_analytics['escalated_sessions'] += 1
        
        # Update average duration
        if hasattr(session, 'total_duration_minutes'):
            total_duration = self.session_analytics['average_duration'] * (self.session_analytics['total_sessions'] - 1)
            total_duration += session.total_duration_minutes
            self.session_analytics['average_duration'] = total_duration / self.session_analytics['total_sessions']
        
        # Update workflow performance
        workflow_name = session.workflow.name
        if workflow_name not in self.session_analytics['workflow_performance']:
            self.session_analytics['workflow_performance'][workflow_name] = {
                'total_uses': 0,
                'successful_resolutions': 0,
                'average_duration': 0.0,
                'success_rate': 0.0
            }
        
        workflow_stats = self.session_analytics['workflow_performance'][workflow_name]
        workflow_stats['total_uses'] += 1
        
        if session.outcome == TroubleshootingOutcome.RESOLVED:
            workflow_stats['successful_resolutions'] += 1
        
        workflow_stats['success_rate'] = workflow_stats['successful_resolutions'] / workflow_stats['total_uses']
        
        if hasattr(session, 'total_duration_minutes'):
            total_workflow_duration = workflow_stats['average_duration'] * (workflow_stats['total_uses'] - 1)
            total_workflow_duration += session.total_duration_minutes
            workflow_stats['average_duration'] = total_workflow_duration / workflow_stats['total_uses']
    
    async def _record_session_learning(self, session: TroubleshootingSession) -> None:
        """
        Records learning insights from a troubleshooting session, including successful and failed step patterns, effective difficulty adaptations, customer emotional state, and technical level. Updates the session's learning insights for future system improvement.
        """
        
        learning_insights = []
        
        # Successful patterns
        if session.outcome == TroubleshootingOutcome.RESOLVED:
            successful_steps = [step.step_type.value for step in session.completed_steps]
            learning_insights.append(f"Successful pattern: {' → '.join(successful_steps)}")
        
        # Failure patterns
        if session.failed_steps:
            failed_step_types = [step.step_type.value for step in session.failed_steps]
            learning_insights.append(f"Failed steps: {', '.join(set(failed_step_types))}")
        
        # Customer adaptation insights
        if session.difficulty_adjustments:
            learning_insights.append(f"Effective adaptations: {', '.join(session.difficulty_adjustments)}")
        
        # Emotional state insights
        learning_insights.append(f"Customer emotion: {session.customer_emotional_state.value}")
        learning_insights.append(f"Technical level: {session.customer_technical_level}")
        
        session.learning_insights = learning_insights
        
        logger.debug(f"Recorded learning insights for session {session.session_id}")
    
    async def _calculate_escalation_score(self, session: TroubleshootingSession) -> float:
        """
        Compute a probability score estimating the likelihood of session escalation.
        
        The score is based on weighted factors including failure rate, session duration relative to workflow estimates, customer emotional state, and the gap between workflow difficulty and customer technical level. The result is capped between 0 and 1.
        
        Returns:
            float: Escalation probability score between 0 (unlikely) and 1 (highly likely).
        """
        
        score = 0.0
        
        # Failure rate component
        total_attempts = len(session.completed_steps) + len(session.failed_steps)
        if total_attempts > 0:
            failure_rate = len(session.failed_steps) / total_attempts
            score += failure_rate * 0.3
        
        # Duration component
        session_duration = datetime.now() - session.start_time
        expected_duration = timedelta(minutes=session.workflow.estimated_time_minutes)
        if session_duration > expected_duration:
            duration_factor = min(1.0, session_duration.total_seconds() / (expected_duration.total_seconds() * 2))
            score += duration_factor * 0.2
        
        # Emotional state component
        emotion_scores = {
            EmotionalState.FRUSTRATED: 0.8,
            EmotionalState.URGENT: 0.9,
            EmotionalState.ANXIOUS: 0.6,
            EmotionalState.CONFUSED: 0.4,
            EmotionalState.NEUTRAL: 0.1,
            EmotionalState.PROFESSIONAL: 0.1,
            EmotionalState.SATISFIED: 0.0
        }
        score += emotion_scores.get(session.customer_emotional_state, 0.5) * 0.3
        
        # Complexity mismatch component
        complexity_gap = session.workflow.difficulty_level - session.customer_technical_level
        if complexity_gap > 1:
            score += min(0.2, complexity_gap * 0.05)
        
        return min(1.0, score)
    
    async def _get_recent_session_trends(self) -> Dict[str, Any]:
        """
        Analyze the last 10 sessions to extract recent trends such as average duration, success rate, and most commonly used workflows.
        
        Returns:
            trends (Dict[str, Any]): A dictionary containing recent session trends, including success rate, common workflow usage, and placeholders for average duration and improvement areas.
        """
        
        # Get last 10 sessions
        recent_session_ids = self.session_history[-10:] if len(self.session_history) >= 10 else self.session_history
        recent_sessions = []
        
        for session_id in recent_session_ids:
            session = await self.get_session(session_id)
            if session:
                recent_sessions.append(session)
        
        if not recent_sessions:
            return {}
        
        # Calculate trends
        trends = {
            'average_duration_trend': 0.0,
            'success_rate_trend': 0.0,
            'common_issues': [],
            'improvement_areas': []
        }
        
        # Success rate trend
        successful_count = sum(1 for s in recent_sessions if hasattr(s, 'outcome') and s.outcome == TroubleshootingOutcome.RESOLVED)
        trends['success_rate_trend'] = successful_count / len(recent_sessions)
        
        # Common workflow usage
        workflow_usage = {}
        for session in recent_sessions:
            workflow_name = session.workflow.name
            workflow_usage[workflow_name] = workflow_usage.get(workflow_name, 0) + 1
        
        if workflow_usage:
            most_common_workflow = max(workflow_usage.items(), key=lambda x: x[1])
            trends['common_issues'].append(f"Most common workflow: {most_common_workflow[0]} ({most_common_workflow[1]} uses)")
        
        return trends