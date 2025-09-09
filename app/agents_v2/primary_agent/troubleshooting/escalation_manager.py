"""
Agent Sparrow - Escalation Management System

This module implements intelligent escalation criteria and pathways for complex
troubleshooting scenarios that require human intervention or specialized expertise.
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
import asyncio

from .troubleshooting_schemas import (
    TroubleshootingSession,
    EscalationCriteria,
    EscalationTrigger,
    TroubleshootingConfig,
    TroubleshootingPhase,
    DiagnosticStep
)
from app.agents_v2.primary_agent.prompts.emotion_templates import EmotionalState

logger = logging.getLogger(__name__)


class EscalationManager:
    """
    Intelligent escalation management system
    
    Provides systematic escalation through:
    - Multi-factor escalation criteria evaluation
    - Customer satisfaction monitoring
    - Technical complexity assessment
    - Time and resource constraints
    - Specialized expertise routing
    """
    
    def __init__(self, config: TroubleshootingConfig):
        """
        Initializes the EscalationManager with escalation pathways and configuration.
        
        The manager defines multiple escalation pathways, each with specific criteria, estimated resolution times, and success rates, to support intelligent escalation decisions during troubleshooting sessions.
        """
        self.config = config
        
        # Escalation pathway definitions
        self.escalation_pathways = {
            'technical_specialist': {
                'description': 'Route to technical specialist for complex issues',
                'criteria': ['high_complexity', 'multiple_failures', 'expert_knowledge_required'],
                'estimated_resolution_time': 60,
                'success_rate': 0.85
            },
            'account_specialist': {
                'description': 'Route to account specialist for account-related issues',
                'criteria': ['account_setup', 'billing_inquiry', 'permission_issues'],
                'estimated_resolution_time': 30,
                'success_rate': 0.90
            },
            'senior_support': {
                'description': 'Route to senior support for customer satisfaction issues',
                'criteria': ['customer_frustration', 'time_exceeded', 'multiple_escalations'],
                'estimated_resolution_time': 45,
                'success_rate': 0.95
            },
            'development_team': {
                'description': 'Route to development team for potential bugs',
                'criteria': ['suspected_bug', 'system_level_issue', 'reproducible_error'],
                'estimated_resolution_time': 120,
                'success_rate': 0.75
            },
            'emergency_response': {
                'description': 'Emergency escalation for critical issues',
                'criteria': ['critical_issue', 'business_impact', 'urgent_customer'],
                'estimated_resolution_time': 15,
                'success_rate': 0.98
            }
        }
        
        logger.info("EscalationManager initialized with intelligent criteria and pathways")
    
    async def check_escalation_criteria(
        self,
        session: TroubleshootingSession
    ) -> bool:
        """
        Evaluates whether a troubleshooting session meets any escalation criteria.
        
        Aggregates triggers from time, complexity, failure, customer satisfaction, and resource/expertise checks to determine if escalation is required. Returns True if any escalation triggers are present and records the triggers in the session notes.
        
        Returns:
            bool: True if escalation is needed, otherwise False.
        """
        
        escalation_triggers = []
        
        # Check time-based criteria
        time_triggers = await self._check_time_based_triggers(session)
        escalation_triggers.extend(time_triggers)
        
        # Check complexity-based criteria
        complexity_triggers = await self._check_complexity_triggers(session)
        escalation_triggers.extend(complexity_triggers)
        
        # Check failure-based criteria
        failure_triggers = await self._check_failure_triggers(session)
        escalation_triggers.extend(failure_triggers)
        
        # Check customer satisfaction criteria
        satisfaction_triggers = await self._check_customer_satisfaction_triggers(session)
        escalation_triggers.extend(satisfaction_triggers)
        
        # Check resource and expertise criteria
        resource_triggers = await self._check_resource_triggers(session)
        escalation_triggers.extend(resource_triggers)
        
        # Evaluate overall escalation need
        escalation_needed = len(escalation_triggers) > 0
        
        if escalation_needed:
            # Store triggers for escalation reasoning
            session.session_notes.append(f"Escalation triggers: {', '.join([t.value for t in escalation_triggers])}")
            logger.info(f"Escalation criteria met for session {session.session_id}: {escalation_triggers}")
        
        return escalation_needed
    
    async def get_escalation_reason(
        self,
        session: TroubleshootingSession
    ) -> str:
        """
        Generate a detailed textual explanation for why a troubleshooting session should be escalated.
        
        Analyzes session duration, workflow complexity, failure count, progress, customer emotional state, and technical expertise mismatch to construct a comprehensive escalation reason. Returns a summary string describing the primary escalation triggers, or a generic reason if no specific triggers are found.
        
        Returns:
            str: Detailed escalation reason for the session.
        """
        
        reasons = []
        
        # Analyze session state
        session_duration = datetime.now() - session.start_time
        completed_steps = len(session.completed_steps)
        failed_steps = len(session.failed_steps)
        
        # Time-based reasons
        if session_duration > timedelta(minutes=self.config.max_session_duration_minutes):
            reasons.append(f"Session duration exceeded limit ({session_duration.total_seconds()/60:.1f} min)")
        
        # Complexity reasons
        workflow_difficulty = session.workflow.difficulty_level
        if workflow_difficulty >= 4:
            reasons.append(f"High complexity workflow (level {workflow_difficulty}/5)")
        
        # Failure reasons
        if failed_steps >= 3:
            reasons.append(f"Multiple diagnostic failures ({failed_steps} failed steps)")
        
        # Progress reasons
        if completed_steps >= 8 and session.overall_progress < 0.6:
            reasons.append(f"Limited progress despite {completed_steps} completed steps")
        
        # Customer emotion reasons
        emotion = session.customer_emotional_state
        if emotion in [EmotionalState.FRUSTRATED, EmotionalState.URGENT]:
            reasons.append(f"Customer emotional state requires specialized attention ({emotion.value})")
        
        # Technical expertise reasons
        if session.customer_technical_level <= 2 and workflow_difficulty >= 4:
            reasons.append("Workflow complexity exceeds customer technical level")
        
        # Default reason if no specific triggers
        if not reasons:
            reasons.append("Automated escalation criteria met - requires human review")
        
        escalation_reason = " | ".join(reasons)
        logger.info(f"Escalation reason for session {session.session_id}: {escalation_reason}")
        
        return escalation_reason
    
    async def recommend_escalation_pathway(
        self,
        session: TroubleshootingSession
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Selects and returns the most suitable escalation pathway for a troubleshooting session based on session characteristics and pathway criteria.
        
        The method evaluates all available escalation pathways, scores them according to their fit with the session's context, and returns the pathway with the highest score along with detailed pathway information, including recommendation score, session context, and escalation priority.
        
        Returns:
            tuple: A pair containing the recommended pathway name and a dictionary with pathway details and session-specific context.
        """
        
        # Score each pathway based on session characteristics
        pathway_scores = {}
        
        for pathway_name, pathway_info in self.escalation_pathways.items():
            score = await self._score_escalation_pathway(session, pathway_name, pathway_info)
            pathway_scores[pathway_name] = score
        
        # Select highest scoring pathway
        best_pathway = max(pathway_scores.items(), key=lambda x: x[1])
        pathway_name = best_pathway[0]
        pathway_info = self.escalation_pathways[pathway_name].copy()
        
        # Add session-specific context
        pathway_info['recommendation_score'] = best_pathway[1]
        pathway_info['session_context'] = await self._generate_session_context(session)
        pathway_info['escalation_priority'] = await self._determine_escalation_priority(session)
        
        logger.info(f"Recommended escalation pathway: {pathway_name} (score: {best_pathway[1]:.2f})")
        
        return pathway_name, pathway_info
    
    async def prepare_escalation_documentation(
        self,
        session: TroubleshootingSession,
        pathway_name: str
    ) -> Dict[str, Any]:
        """
        Compile a comprehensive escalation documentation package for a troubleshooting session and selected escalation pathway.
        
        The documentation includes a session summary, problem analysis, attempted solutions, customer profile, technical context, escalation reasoning, recommended actions, priority level, specialist requirements, and handoff instructions.
        
        Parameters:
            session (TroubleshootingSession): The current troubleshooting session to be escalated.
            pathway_name (str): The name of the selected escalation pathway.
        
        Returns:
            Dict[str, Any]: A dictionary containing all relevant escalation documentation fields for handoff and further action.
        """
        
        escalation_doc = {
            'session_summary': await self._generate_session_summary(session),
            'problem_analysis': await self._generate_problem_analysis(session),
            'attempted_solutions': await self._document_attempted_solutions(session),
            'customer_profile': await self._generate_customer_profile(session),
            'technical_context': await self._gather_technical_context(session),
            'escalation_reasoning': await self.get_escalation_reason(session),
            'recommended_actions': await self._generate_recommended_actions(session, pathway_name),
            'priority_level': await self._determine_escalation_priority(session),
            'specialist_requirements': await self._identify_specialist_requirements(session),
            'handoff_instructions': await self._generate_handoff_instructions(session, pathway_name)
        }
        
        logger.info(f"Prepared escalation documentation for session {session.session_id}")
        
        return escalation_doc
    
    # Trigger checking methods
    
    async def _check_time_based_triggers(self, session: TroubleshootingSession) -> List[EscalationTrigger]:
        """
        Checks for time-based escalation triggers in a troubleshooting session.
        
        Evaluates whether the overall session duration or the current step duration has exceeded configured time limits, and returns a list of corresponding escalation triggers.
        """
        triggers = []
        
        session_duration = datetime.now() - session.start_time
        max_duration = timedelta(minutes=self.config.max_session_duration_minutes)
        
        if session_duration > max_duration:
            triggers.append(EscalationTrigger.TIME_LIMIT_EXCEEDED)
        
        # Check if individual steps are taking too long
        current_step = session.current_step
        if current_step and current_step.execution_start_time:
            step_duration = datetime.now() - current_step.execution_start_time
            expected_duration = timedelta(minutes=current_step.time_estimate_minutes)
            
            if step_duration > expected_duration * 2:  # Double the expected time
                triggers.append(EscalationTrigger.TIME_LIMIT_EXCEEDED)
        
        return triggers
    
    async def _check_complexity_triggers(self, session: TroubleshootingSession) -> List[EscalationTrigger]:
        """
        Checks for escalation triggers related to workflow complexity and customer technical level.
        
        Returns:
            List of escalation triggers if the workflow is highly complex or if there is a significant mismatch between workflow difficulty and the customer's technical expertise.
        """
        triggers = []
        
        workflow_difficulty = session.workflow.difficulty_level
        customer_technical_level = session.customer_technical_level
        
        # High complexity workflow
        if workflow_difficulty >= 4:
            triggers.append(EscalationTrigger.COMPLEXITY_THRESHOLD)
        
        # Complexity mismatch with customer level
        if workflow_difficulty > customer_technical_level + 2:
            triggers.append(EscalationTrigger.COMPLEXITY_THRESHOLD)
        
        return triggers
    
    async def _check_failure_triggers(self, session: TroubleshootingSession) -> List[EscalationTrigger]:
        """
        Checks for escalation triggers based on the number and severity of failed troubleshooting steps.
        
        Returns:
            List of escalation triggers indicating multiple failures or the presence of a critical issue.
        """
        triggers = []
        
        failed_steps = len(session.failed_steps)
        
        if failed_steps >= 3:
            triggers.append(EscalationTrigger.MULTIPLE_FAILURES)
        
        # Check for critical failures
        for failed_step in session.failed_steps:
            if failed_step.difficulty_level >= 4 and 'critical' in failed_step.title.lower():
                triggers.append(EscalationTrigger.CRITICAL_ISSUE)
                break
        
        return triggers
    
    async def _check_customer_satisfaction_triggers(self, session: TroubleshootingSession) -> List[EscalationTrigger]:
        """
        Checks for escalation triggers based on customer emotional state and feedback.
        
        Returns:
            List of escalation triggers if the customer is frustrated, urgent, or has requested escalation in feedback.
        """
        triggers = []
        
        emotion = session.customer_emotional_state
        
        # Emotional state triggers
        if emotion in [EmotionalState.FRUSTRATED, EmotionalState.URGENT]:
            triggers.append(EscalationTrigger.CUSTOMER_REQUEST)
        
        # Check customer feedback for escalation requests
        for step in session.completed_steps:
            if step.customer_feedback:
                feedback_lower = step.customer_feedback.lower()
                escalation_keywords = ['escalate', 'manager', 'supervisor', 'specialist', 'expert']
                if any(keyword in feedback_lower for keyword in escalation_keywords):
                    triggers.append(EscalationTrigger.CUSTOMER_REQUEST)
                    break
        
        return triggers
    
    async def _check_resource_triggers(self, session: TroubleshootingSession) -> List[EscalationTrigger]:
        """
        Check for escalation triggers related to external dependencies and insufficient permissions in the troubleshooting session.
        
        Returns:
            List of escalation triggers indicating the presence of external dependencies or required elevated permissions.
        """
        triggers = []
        
        # Check for external dependencies
        for step in session.workflow.diagnostic_steps:
            if any(tool in step.required_tools for tool in ['external_api', 'admin_access', 'specialist_tools']):
                triggers.append(EscalationTrigger.EXTERNAL_DEPENDENCY)
                break
        
        # Check for permission requirements
        required_permissions = session.workflow.required_permissions
        if any('admin' in perm.lower() or 'elevated' in perm.lower() for perm in required_permissions):
            triggers.append(EscalationTrigger.INSUFFICIENT_PERMISSIONS)
        
        return triggers
    
    # Pathway scoring and selection
    
    async def _score_escalation_pathway(
        self,
        session: TroubleshootingSession,
        pathway_name: str,
        pathway_info: Dict[str, Any]
    ) -> float:
        """
        Calculates a suitability score for an escalation pathway based on session characteristics and pathway attributes.
        
        The score incorporates the pathway's historical success rate, the degree to which session criteria match the pathway's requirements, urgency adjustments for customer emotional state, and alignment with the customer's technical level.
        
        Returns:
            float: The computed suitability score for the escalation pathway.
        """
        
        score = 0.0
        
        # Base score from pathway success rate
        score += pathway_info['success_rate'] * 0.3
        
        # Score based on criteria match
        criteria_match_score = await self._calculate_criteria_match(session, pathway_info['criteria'])
        score += criteria_match_score * 0.4
        
        # Adjust for urgency
        if session.customer_emotional_state == EmotionalState.URGENT:
            # Prefer faster pathways for urgent customers
            time_factor = max(0.1, 1.0 - (pathway_info['estimated_resolution_time'] / 120))
            score += time_factor * 0.2
        
        # Adjust for customer technical level
        if pathway_name == 'technical_specialist' and session.customer_technical_level >= 4:
            score += 0.1  # Technical customers prefer technical specialists
        elif pathway_name == 'senior_support' and session.customer_technical_level <= 2:
            score += 0.1  # Non-technical customers prefer senior support
        
        return score
    
    async def _calculate_criteria_match(
        self,
        session: TroubleshootingSession,
        pathway_criteria: List[str]
    ) -> float:
        """
        Calculate the fraction of escalation pathway criteria that are met by the troubleshooting session.
        
        Parameters:
            pathway_criteria (List[str]): List of criteria names to evaluate against the session.
        
        Returns:
            float: The proportion of pathway criteria satisfied by the session, as a value between 0.0 and 1.0.
        """
        
        matches = 0
        total_criteria = len(pathway_criteria)
        
        for criteria in pathway_criteria:
            if await self._check_criteria_match(session, criteria):
                matches += 1
        
        return matches / total_criteria if total_criteria > 0 else 0.0
    
    async def _check_criteria_match(self, session: TroubleshootingSession, criteria: str) -> bool:
        """
        Determine whether a troubleshooting session meets a specified escalation criterion.
        
        Parameters:
        	criteria (str): The escalation criterion to check, such as 'complexity', 'failure', 'frustration', 'time', 'account', 'billing', 'technical', 'expert', 'critical', or 'bug'.
        
        Returns:
        	bool: True if the session matches the specified criterion, otherwise False.
        """
        
        criteria_lower = criteria.lower()
        
        if 'complexity' in criteria_lower:
            return session.workflow.difficulty_level >= 4
        
        elif 'failure' in criteria_lower:
            return len(session.failed_steps) >= 2
        
        elif 'frustration' in criteria_lower:
            return session.customer_emotional_state == EmotionalState.FRUSTRATED
        
        elif 'time' in criteria_lower:
            session_duration = datetime.now() - session.start_time
            return session_duration > timedelta(minutes=30)
        
        elif 'account' in criteria_lower:
            return 'account' in session.workflow.name.lower()
        
        elif 'billing' in criteria_lower:
            return 'billing' in session.workflow.name.lower()
        
        elif 'technical' in criteria_lower:
            return session.workflow.difficulty_level >= 3
        
        elif 'expert' in criteria_lower:
            return session.customer_technical_level >= 4 or session.workflow.difficulty_level >= 4
        
        elif 'critical' in criteria_lower:
            return session.customer_emotional_state == EmotionalState.URGENT
        
        elif 'bug' in criteria_lower:
            # Check for bug-related patterns in failed steps
            for step in session.failed_steps:
                if any(word in step.execution_notes.lower() for word in ['unexpected', 'should work', 'bug']):
                    return True
            return False
        
        return False
    
    # Documentation generation
    
    async def _generate_session_summary(self, session: TroubleshootingSession) -> str:
        """
        Generate a concise summary of the troubleshooting session, including duration, workflow, customer technical level and emotional state, number of completed and failed steps, and overall progress.
        
        Returns:
            str: A formatted summary string describing key session attributes.
        """
        
        duration = datetime.now() - session.start_time
        
        summary = f"""
        Session Duration: {duration.total_seconds()/60:.1f} minutes
        Workflow: {session.workflow.name}
        Customer Technical Level: {session.customer_technical_level}/5
        Customer Emotional State: {session.customer_emotional_state.value}
        Steps Completed: {len(session.completed_steps)}
        Steps Failed: {len(session.failed_steps)}
        Overall Progress: {session.overall_progress:.1%}
        """
        
        return summary.strip()
    
    async def _generate_problem_analysis(self, session: TroubleshootingSession) -> str:
        """
        Generate a detailed analysis of the troubleshooting problem, including the original issue, category, complexity, observed symptoms, and failure patterns.
        
        Returns:
            str: A formatted string summarizing the problem analysis for the session.
        """
        
        analysis_parts = []
        
        # Original problem context
        analysis_parts.append(f"Original Issue: {session.workflow.description}")
        
        # Problem category and complexity
        analysis_parts.append(f"Category: {session.workflow.problem_category.value}")
        analysis_parts.append(f"Complexity Level: {session.workflow.difficulty_level}/5")
        
        # Symptoms and patterns
        symptoms = session.workflow.applicable_symptoms
        if symptoms:
            analysis_parts.append(f"Observed Symptoms: {', '.join(symptoms[:3])}")
        
        # Failure patterns
        if session.failed_steps:
            failed_types = [step.step_type.value for step in session.failed_steps]
            analysis_parts.append(f"Failed Step Types: {', '.join(set(failed_types))}")
        
        return " | ".join(analysis_parts)
    
    async def _document_attempted_solutions(self, session: TroubleshootingSession) -> List[Dict[str, Any]]:
        """
        Generates a list of documented attempted solutions from completed and failed troubleshooting steps in the session.
        
        Each solution includes step details, status, duration, summary notes, and customer feedback.
        
        Returns:
            List of dictionaries, each representing an attempted solution with step metadata and outcomes.
        """
        
        solutions = []
        
        for step in session.completed_steps + session.failed_steps:
            solution_doc = {
                'step_title': step.title,
                'step_type': step.step_type.value,
                'status': step.execution_status,
                'duration_minutes': 0,
                'result_summary': step.execution_notes or "No specific notes",
                'customer_feedback': step.customer_feedback or "No feedback provided"
            }
            
            # Calculate duration if available
            if step.execution_start_time and step.execution_end_time:
                duration = step.execution_end_time - step.execution_start_time
                solution_doc['duration_minutes'] = duration.total_seconds() / 60
            
            solutions.append(solution_doc)
        
        return solutions
    
    async def _generate_customer_profile(self, session: TroubleshootingSession) -> Dict[str, Any]:
        """
        Builds a customer profile summarizing technical level, emotional state, communication style, patience level, and preferred troubleshooting approach for escalation documentation.
        
        Returns:
            profile (Dict[str, Any]): Dictionary containing customer attributes relevant to escalation and handoff.
        """
        
        profile = {
            'technical_level': session.customer_technical_level,
            'emotional_state': session.customer_emotional_state.value,
            'communication_style': 'Professional' if session.customer_emotional_state == EmotionalState.PROFESSIONAL else 'Standard',
            'patience_level': 'Low' if session.customer_emotional_state in [EmotionalState.FRUSTRATED, EmotionalState.URGENT] else 'Normal',
            'preferred_approach': await self._determine_preferred_approach(session)
        }
        
        return profile
    
    async def _gather_technical_context(self, session: TroubleshootingSession) -> Dict[str, Any]:
        """
        Collects and returns technical context information from a troubleshooting session for escalation purposes.
        
        Returns:
            A dictionary containing workflow details, required tools and permissions, system context, environmental factors, and verification results relevant to the session.
        """
        
        context = {
            'workflow_used': session.workflow.name,
            'required_tools': session.workflow.required_tools,
            'required_permissions': session.workflow.required_permissions,
            'system_context': getattr(session, 'system_context', {}),
            'environmental_factors': getattr(session, 'environmental_factors', {}),
            'verification_results': [
                {
                    'checkpoint': vr.name,
                    'status': vr.status.value,
                    'confidence': vr.confidence_score
                }
                for vr in session.verification_results
            ]
        }
        
        return context
    
    async def _generate_recommended_actions(
        self,
        session: TroubleshootingSession,
        pathway_name: str
    ) -> List[str]:
        """
        Generate a list of recommended actions tailored to the specified escalation pathway and the current troubleshooting session.
        
        Parameters:
            pathway_name (str): The name of the escalation pathway for which to generate actions.
        
        Returns:
            List[str]: A list of recommended actions based on the escalation pathway and session context, including considerations for multiple failed steps and customer frustration.
        """
        
        actions = []
        
        # Pathway-specific actions
        if pathway_name == 'technical_specialist':
            actions.extend([
                "Review failed diagnostic steps for technical accuracy",
                "Perform advanced system diagnostics",
                "Consider alternative technical approaches",
                "Validate system configuration and compatibility"
            ])
        
        elif pathway_name == 'senior_support':
            actions.extend([
                "Focus on customer satisfaction and communication",
                "Review session for process improvements",
                "Consider simplified alternative approaches",
                "Ensure customer feels heard and supported"
            ])
        
        elif pathway_name == 'development_team':
            actions.extend([
                "Investigate potential software defects",
                "Reproduce issue in controlled environment",
                "Review system logs and error patterns",
                "Consider hotfix or workaround development"
            ])
        
        # Session-specific actions
        if len(session.failed_steps) >= 3:
            actions.append("Investigate why multiple approaches have failed")
        
        if session.customer_emotional_state == EmotionalState.FRUSTRATED:
            actions.append("Prioritize customer satisfaction and quick resolution")
        
        return actions
    
    async def _determine_escalation_priority(self, session: TroubleshootingSession) -> str:
        """
        Assign an escalation priority level (HIGH, MEDIUM, NORMAL) based on session attributes such as customer emotional state, failure count, session duration, and workflow difficulty.
        
        Returns:
            str: The escalation priority level ("HIGH", "MEDIUM", or "NORMAL").
        """
        
        high_priority_conditions = [
            session.customer_emotional_state == EmotionalState.URGENT,
            len(session.failed_steps) >= 4,
            (datetime.now() - session.start_time) > timedelta(hours=1),
            session.workflow.difficulty_level >= 5
        ]
        
        medium_priority_conditions = [
            session.customer_emotional_state == EmotionalState.FRUSTRATED,
            len(session.failed_steps) >= 2,
            session.workflow.difficulty_level >= 4
        ]
        
        if any(high_priority_conditions):
            return "HIGH"
        elif any(medium_priority_conditions):
            return "MEDIUM"
        else:
            return "NORMAL"
    
    async def _identify_specialist_requirements(self, session: TroubleshootingSession) -> List[str]:
        """
        Determine the specialist skills required for escalation based on the session's workflow, failed troubleshooting steps, and customer characteristics.
        
        Returns:
            requirements (List[str]): A list of specialist skills needed to address the session's specific challenges.
        """
        
        requirements = []
        
        # Based on workflow characteristics
        if 'network' in session.workflow.name.lower():
            requirements.append("Network configuration expertise")
        
        if 'email' in session.workflow.name.lower():
            requirements.append("Email protocol knowledge")
        
        if session.workflow.difficulty_level >= 4:
            requirements.append("Advanced troubleshooting skills")
        
        # Based on failed step types
        failed_step_types = [step.step_type.value for step in session.failed_steps]
        if 'connectivity_test' in failed_step_types:
            requirements.append("Network connectivity diagnosis")
        
        if 'account_validation' in failed_step_types:
            requirements.append("Account management expertise")
        
        # Based on customer characteristics
        if session.customer_technical_level <= 2:
            requirements.append("Customer communication skills for non-technical users")
        
        if session.customer_emotional_state == EmotionalState.FRUSTRATED:
            requirements.append("Customer de-escalation skills")
        
        return requirements
    
    async def _generate_handoff_instructions(
        self,
        session: TroubleshootingSession,
        pathway_name: str
    ) -> str:
        """
        Generate tailored handoff instructions summarizing the troubleshooting session, customer state, and pathway-specific guidance for the next support specialist.
        
        Parameters:
            session (TroubleshootingSession): The current troubleshooting session.
            pathway_name (str): The name of the recommended escalation pathway.
        
        Returns:
            str: A formatted string containing handoff instructions, including session progress, customer emotional and technical state, recent actions, and pathway-specific recommendations.
        """
        
        instructions = []
        
        # Basic handoff info
        instructions.append(f"Customer has been through {len(session.completed_steps)} troubleshooting steps")
        instructions.append(f"Current emotional state: {session.customer_emotional_state.value}")
        instructions.append(f"Technical level: {session.customer_technical_level}/5")
        
        # Specific guidance based on pathway
        if pathway_name == 'technical_specialist':
            instructions.append("Customer may be ready for advanced technical solutions")
            instructions.append("Focus on technical accuracy and detailed explanations")
        
        elif pathway_name == 'senior_support':
            instructions.append("Prioritize customer satisfaction and relationship management")
            instructions.append("Customer may need reassurance and simplified communication")
        
        # Recent context
        if session.current_step:
            instructions.append(f"Last attempted step: {session.current_step.title}")
        
        if session.verification_results:
            last_verification = session.verification_results[-1]
            instructions.append(f"Last verification: {last_verification.status.value}")
        
        return " | ".join(instructions)
    
    async def _determine_preferred_approach(self, session: TroubleshootingSession) -> str:
        """
        Infers the customer's preferred troubleshooting approach based on their technical level and emotional state.
        
        Returns:
            str: A description of the recommended troubleshooting style (e.g., "Technical and detailed", "Quick and efficient", "Simple and guided", "Empathetic and reassuring", or "Balanced and thorough").
        """
        
        if session.customer_technical_level >= 4:
            return "Technical and detailed"
        elif session.customer_emotional_state == EmotionalState.URGENT:
            return "Quick and efficient"
        elif session.customer_emotional_state == EmotionalState.CONFUSED:
            return "Simple and guided"
        elif session.customer_emotional_state == EmotionalState.FRUSTRATED:
            return "Empathetic and reassuring"
        else:
            return "Balanced and thorough"