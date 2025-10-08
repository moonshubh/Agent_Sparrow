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
from app.agents.primary.primary_agent.prompts.emotion_templates import EmotionalState

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
        Initialize session manager
        
        Args:
            config: Troubleshooting configuration
        """
        self.config = config
        
        # Session storage
        self.active_sessions: Dict[str, TroubleshootingSession] = {}
        self.completed_sessions: Dict[str, TroubleshootingSession] = {}
        self.session_history: List[str] = []  # Session IDs in chronological order
        
        # Session limits configuration
        self.max_completed_sessions: int = getattr(config, 'max_completed_sessions', 1000)
        self.session_retention_days: int = getattr(config, 'session_retention_days', 30)
        
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
        Create new troubleshooting session
        
        Args:
            workflow: Troubleshooting workflow to use
            customer_emotional_state: Customer's emotional state
            customer_technical_level: Customer's technical skill level
            session_id: Optional specific session ID
            context: Optional additional context
            
        Returns:
            New troubleshooting session
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
        """Get active or completed session by ID"""
        
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
        Update session progress after step completion
        
        Args:
            session_id: Session identifier
            completed_step: The completed diagnostic step
            step_successful: Whether the step was successful
            customer_feedback: Optional customer feedback
            
        Returns:
            Updated session
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
        Complete troubleshooting session
        
        Args:
        """
        if session_id not in self.active_sessions:
            raise ValueError(f"No active session found with ID: {session_id}")
            
        session = self.active_sessions.pop(session_id)
        session.end_time = datetime.now()
        session.outcome = outcome
        session.state = TroubleshootingState.COMPLETED
        
        # Move to completed sessions
        self.completed_sessions[session_id] = session
        self.session_history.append(session_id)
        
        # Clean up old sessions if we're over the limit
        if len(self.completed_sessions) > self.max_completed_sessions:
            await self._cleanup_old_sessions()
        
        # Update analytics
        await self._update_session_analytics(session)
        
        logger.info(f"Session {session_id} completed with outcome: {outcome}")
        return session
    
    async def pause_session(
        self,
        session_id: str,
        pause_reason: str = "User requested pause"
    ) -> TroubleshootingSession:
        """
        Pause active troubleshooting session
        
        Args:
            session_id: Session identifier
            pause_reason: Reason for pausing
            
        Returns:
            Paused session
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
        Resume paused troubleshooting session
        
        Args:
            session_id: Session identifier
            resume_context: Optional context for resumption
            
        Returns:
            Resumed session
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
        Get recommendations for improving session effectiveness
        
        Args:
            session_id: Session identifier
            
        Returns:
            Session recommendations
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
        """Get comprehensive session analytics"""
        
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
        """Analyze customer feedback for emotional state changes"""
        
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
        """Update customer emotional state and adapt session accordingly"""
        
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
        """Update session progress metrics"""
        
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
        """Check and apply session optimizations if needed"""
        
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
        
    
    async def _cleanup_old_sessions(self) -> None:
        """
        Clean up old sessions based on retention policy.
        Removes sessions that exceed max_completed_sessions or are older than session_retention_days.
        """
        if not self.completed_sessions:
            return
            
        now = datetime.now()
        sessions_to_remove = set()
        
        # Check for sessions older than retention period
        for session_id, session in list(self.completed_sessions.items()):
            if session.end_time and (now - session.end_time).days > self.session_retention_days:
                sessions_to_remove.add(session_id)
        
        # If we still have too many sessions, remove the oldest ones
        remaining_sessions = len(self.completed_sessions) - len(sessions_to_remove)
        if remaining_sessions > self.max_completed_sessions:
            # Get sessions not already marked for removal, sorted by end_time (oldest first)
            sessions_by_age = [
                (session_id, session) 
                for session_id, session in self.completed_sessions.items()
                if session_id not in sessions_to_remove and session.end_time is not None
            ]
            sessions_by_age.sort(key=lambda x: x[1].end_time)  # type: ignore
            
            # Add oldest sessions to removal set until we're under the limit
            excess_sessions = remaining_sessions - self.max_completed_sessions
            for session_id, _ in sessions_by_age[:excess_sessions]:
                sessions_to_remove.add(session_id)
        
        # Remove the sessions
        for session_id in sessions_to_remove:
            self.completed_sessions.pop(session_id, None)
            logger.debug(f"Removed old session {session_id} during cleanup")
        
        # Clean up session_history
        self.session_history = [sid for sid in self.session_history if sid not in sessions_to_remove]
        
        if sessions_to_remove:
            logger.info(f"Cleaned up {len(sessions_to_remove)} old sessions")
    
    async def _update_session_analytics(self, session: TroubleshootingSession) -> None:
        """Update session analytics with data from completed session"""
        self.session_analytics['total_sessions'] += 1
        
        if session.outcome == TroubleshootingOutcome.RESOLVED:
            self.session_analytics['successful_sessions'] += 1
        elif session.outcome == TroubleshootingOutcome.ESCALATED:
            self.session_analytics['escalated_sessions'] += 1
            
        # Update average duration
        if session.start_time and session.end_time:
            duration = (session.end_time - session.start_time).total_seconds()
            total_sessions = self.session_analytics['total_sessions']
            current_avg = self.session_analytics['average_duration']
            self.session_analytics['average_duration'] = (
                (current_avg * (total_sessions - 1) + duration) / total_sessions
            )     # Update workflow performance
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
        """Record session insights for system learning"""
        
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
        """Calculate escalation probability score for session"""
        
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
        """Get trends from recent sessions"""
        
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