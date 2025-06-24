"""
Agent Sparrow - Verification Checkpoint System

This module implements comprehensive verification checkpoints to validate progress,
ensure solution effectiveness, and maintain quality throughout troubleshooting workflows.
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
import asyncio

from .troubleshooting_schemas import (
    TroubleshootingSession,
    VerificationCheckpoint,
    VerificationStatus,
    TroubleshootingConfig,
    DiagnosticStep,
    TroubleshootingPhase
)
from app.agents_v2.primary_agent.prompts.emotion_templates import EmotionalState

logger = logging.getLogger(__name__)


class VerificationSystem:
    """
    Comprehensive verification checkpoint system
    
    Provides systematic progress validation through:
    - Phase-based verification checkpoints
    - Solution effectiveness validation
    - Customer satisfaction confirmation
    - Technical accuracy verification
    - Adaptive verification based on customer needs
    """
    
    def __init__(self, config: TroubleshootingConfig):
        """
        Initialize verification system
        
        Args:
            config: Troubleshooting configuration
        """
        self.config = config
        
        # Verification templates by phase
        self.verification_templates = {
            TroubleshootingPhase.BASIC_DIAGNOSTICS: self._create_basic_verification_template,
            TroubleshootingPhase.INTERMEDIATE_DIAGNOSTICS: self._create_intermediate_verification_template,
            TroubleshootingPhase.ADVANCED_DIAGNOSTICS: self._create_advanced_verification_template,
            TroubleshootingPhase.RESOLUTION_VERIFICATION: self._create_resolution_verification_template
        }
        
        logger.info("VerificationSystem initialized with comprehensive checkpoint capabilities")
    
    async def run_verification_checkpoint(
        self,
        session: TroubleshootingSession,
        checkpoint_type: Optional[str] = None
    ) -> VerificationCheckpoint:
        """
        Run verification checkpoint for current session state
        
        Args:
            session: Active troubleshooting session
            checkpoint_type: Optional specific checkpoint type
            
        Returns:
            Completed verification checkpoint
        """
        
        # Determine checkpoint type if not specified
        if not checkpoint_type:
            checkpoint_type = self._determine_checkpoint_type(session)
        
        # Create verification checkpoint
        checkpoint = await self._create_verification_checkpoint(session, checkpoint_type)
        
        # Execute verification process
        verification_result = await self._execute_verification(session, checkpoint)
        
        # Update checkpoint with results
        checkpoint.status = verification_result['status']
        checkpoint.verification_time = datetime.now()
        checkpoint.verification_notes = verification_result['notes']
        checkpoint.evidence_collected = verification_result['evidence']
        checkpoint.confidence_score = verification_result['confidence']
        
        logger.info(f"Verification checkpoint completed with status: {checkpoint.status.value}")
        
        return checkpoint
    
    async def run_final_verification(
        self,
        session: TroubleshootingSession
    ) -> VerificationCheckpoint:
        """
        Run comprehensive final verification for resolved issues
        
        Args:
            session: Completed troubleshooting session
            
        Returns:
            Final verification checkpoint
        """
        
        # Create comprehensive final verification
        final_checkpoint = VerificationCheckpoint(
            name="Final Resolution Verification",
            description="Comprehensive validation of issue resolution and customer satisfaction",
            verification_questions=[
                "Is the original problem completely resolved?",
                "Can the customer successfully perform the intended action?",
                "Are there any remaining issues or concerns?",
                "Is the customer satisfied with the resolution?",
                "Will the solution persist over time?"
            ],
            success_indicators=[
                "Original problem symptoms eliminated",
                "Customer can complete intended tasks",
                "No error messages or warnings",
                "Customer expresses satisfaction",
                "Solution shows stability"
            ],
            failure_indicators=[
                "Original problem persists",
                "New issues introduced",
                "Customer reports dissatisfaction",
                "Intermittent failures observed",
                "Temporary workaround only"
            ],
            verification_method="comprehensive_testing_and_customer_confirmation",
            required_evidence=[
                "Successful task completion",
                "Customer satisfaction confirmation",
                "System stability evidence",
                "No error conditions present"
            ]
        )
        
        # Execute final verification
        verification_result = await self._execute_final_verification(session, final_checkpoint)
        
        # Update checkpoint
        final_checkpoint.status = verification_result['status']
        final_checkpoint.verification_time = datetime.now()
        final_checkpoint.verification_notes = verification_result['notes']
        final_checkpoint.evidence_collected = verification_result['evidence']
        final_checkpoint.confidence_score = verification_result['confidence']
        
        logger.info(f"Final verification completed with status: {final_checkpoint.status.value}, confidence: {final_checkpoint.confidence_score:.2f}")
        
        return final_checkpoint
    
    async def validate_step_completion(
        self,
        session: TroubleshootingSession,
        completed_step: DiagnosticStep,
        step_result: Dict[str, Any]
    ) -> Tuple[bool, float, List[str]]:
        """
        Validate completion of individual diagnostic step
        
        Args:
            session: Current troubleshooting session
            completed_step: The completed diagnostic step
            step_result: Results from step execution
            
        Returns:
            Tuple of (validation_passed, confidence_score, validation_notes)
        """
        
        validation_notes = []
        confidence_factors = []
        
        # Check success criteria
        success_criteria_met = 0
        for criteria in completed_step.success_criteria:
            if self._check_criteria_in_result(criteria, step_result):
                success_criteria_met += 1
                validation_notes.append(f"✅ Success criteria met: {criteria}")
                confidence_factors.append(0.9)
            else:
                validation_notes.append(f"❌ Success criteria not met: {criteria}")
                confidence_factors.append(0.3)
        
        # Check for failure indicators
        failure_indicators_found = 0
        for indicator in completed_step.failure_indicators:
            if self._check_criteria_in_result(indicator, step_result):
                failure_indicators_found += 1
                validation_notes.append(f"⚠️ Failure indicator found: {indicator}")
                confidence_factors.append(0.1)
        
        # Calculate base validation
        if success_criteria_met > 0 and failure_indicators_found == 0:
            base_validation = True
            confidence_factors.append(0.8)
        elif success_criteria_met == 0 and failure_indicators_found > 0:
            base_validation = False
            confidence_factors.append(0.2)
        else:
            # Mixed results - use ratio
            ratio = success_criteria_met / max(1, success_criteria_met + failure_indicators_found)
            base_validation = ratio >= 0.6
            confidence_factors.append(ratio)
        
        # Additional validation checks
        await self._perform_additional_validation_checks(
            session, completed_step, step_result, validation_notes, confidence_factors
        )
        
        # Calculate overall confidence
        overall_confidence = sum(confidence_factors) / len(confidence_factors) if confidence_factors else 0.5
        
        validation_passed = base_validation and overall_confidence >= self.config.minimum_verification_confidence
        
        logger.debug(f"Step validation: passed={validation_passed}, confidence={overall_confidence:.2f}")
        
        return validation_passed, overall_confidence, validation_notes
    
    async def _create_verification_checkpoint(
        self,
        session: TroubleshootingSession,
        checkpoint_type: str
    ) -> VerificationCheckpoint:
        """Create verification checkpoint based on session state"""
        
        current_phase = session.current_phase
        
        # Use template if available
        if current_phase in self.verification_templates:
            template_func = self.verification_templates[current_phase]
            checkpoint = await template_func(session)
        else:
            # Create generic checkpoint
            checkpoint = await self._create_generic_verification_checkpoint(session)
        
        # Adapt checkpoint for customer characteristics
        adapted_checkpoint = await self._adapt_checkpoint_for_customer(checkpoint, session)
        
        return adapted_checkpoint
    
    async def _execute_verification(
        self,
        session: TroubleshootingSession,
        checkpoint: VerificationCheckpoint
    ) -> Dict[str, Any]:
        """Execute verification checkpoint process"""
        
        verification_result = {
            'status': VerificationStatus.PENDING,
            'notes': '',
            'evidence': [],
            'confidence': 0.0
        }
        
        evidence_collected = []
        confidence_factors = []
        notes = []
        
        # Check recent step results for evidence
        recent_steps = session.completed_steps[-3:] if len(session.completed_steps) >= 3 else session.completed_steps
        
        for step in recent_steps:
            step_evidence = self._extract_evidence_from_step(step, checkpoint)
            evidence_collected.extend(step_evidence)
        
        # Evaluate success indicators
        success_indicators_met = 0
        for indicator in checkpoint.success_indicators:
            if self._check_indicator_in_evidence(indicator, evidence_collected):
                success_indicators_met += 1
                notes.append(f"✅ Success indicator confirmed: {indicator}")
                confidence_factors.append(0.8)
        
        # Check for failure indicators
        failure_indicators_found = 0
        for indicator in checkpoint.failure_indicators:
            if self._check_indicator_in_evidence(indicator, evidence_collected):
                failure_indicators_found += 1
                notes.append(f"❌ Failure indicator detected: {indicator}")
                confidence_factors.append(0.2)
        
        # Determine verification status
        if success_indicators_met > 0 and failure_indicators_found == 0:
            verification_result['status'] = VerificationStatus.PASSED
        elif failure_indicators_found > 0:
            verification_result['status'] = VerificationStatus.FAILED
        elif success_indicators_met == 0:
            verification_result['status'] = VerificationStatus.INCONCLUSIVE
        else:
            # Mixed results
            success_ratio = success_indicators_met / (success_indicators_met + failure_indicators_found)
            if success_ratio >= 0.7:
                verification_result['status'] = VerificationStatus.PASSED
            elif success_ratio <= 0.3:
                verification_result['status'] = VerificationStatus.FAILED
            else:
                verification_result['status'] = VerificationStatus.INCONCLUSIVE
        
        # Calculate confidence
        overall_confidence = sum(confidence_factors) / len(confidence_factors) if confidence_factors else 0.5
        
        verification_result['confidence'] = overall_confidence
        verification_result['notes'] = ' | '.join(notes)
        verification_result['evidence'] = evidence_collected
        
        return verification_result
    
    async def _execute_final_verification(
        self,
        session: TroubleshootingSession,
        checkpoint: VerificationCheckpoint
    ) -> Dict[str, Any]:
        """Execute comprehensive final verification"""
        
        verification_result = {
            'status': VerificationStatus.PENDING,
            'notes': '',
            'evidence': [],
            'confidence': 0.0
        }
        
        evidence_collected = []
        confidence_factors = []
        notes = []
        
        # Comprehensive evidence collection
        all_completed_steps = session.completed_steps
        for step in all_completed_steps:
            step_evidence = self._extract_evidence_from_step(step, checkpoint)
            evidence_collected.extend(step_evidence)
        
        # Check original problem resolution
        original_problem_resolved = await self._verify_original_problem_resolved(session, evidence_collected)
        if original_problem_resolved:
            notes.append("✅ Original problem confirmed resolved")
            confidence_factors.append(0.9)
        else:
            notes.append("❌ Original problem may not be fully resolved")
            confidence_factors.append(0.3)
        
        # Check for customer satisfaction indicators
        satisfaction_level = await self._assess_customer_satisfaction(session)
        if satisfaction_level >= 0.7:
            notes.append(f"✅ Customer satisfaction high ({satisfaction_level:.1%})")
            confidence_factors.append(satisfaction_level)
        else:
            notes.append(f"⚠️ Customer satisfaction concerns ({satisfaction_level:.1%})")
            confidence_factors.append(satisfaction_level)
        
        # Check solution stability
        stability_score = await self._assess_solution_stability(session, evidence_collected)
        if stability_score >= 0.8:
            notes.append(f"✅ Solution appears stable ({stability_score:.1%})")
            confidence_factors.append(stability_score)
        else:
            notes.append(f"⚠️ Solution stability concerns ({stability_score:.1%})")
            confidence_factors.append(stability_score)
        
        # Determine final status
        overall_confidence = sum(confidence_factors) / len(confidence_factors) if confidence_factors else 0.5
        
        if overall_confidence >= 0.8 and original_problem_resolved:
            verification_result['status'] = VerificationStatus.PASSED
        elif overall_confidence <= 0.4 or not original_problem_resolved:
            verification_result['status'] = VerificationStatus.FAILED
        else:
            verification_result['status'] = VerificationStatus.INCONCLUSIVE
        
        verification_result['confidence'] = overall_confidence
        verification_result['notes'] = ' | '.join(notes)
        verification_result['evidence'] = evidence_collected
        
        return verification_result
    
    # Verification template creators
    
    async def _create_basic_verification_template(self, session: TroubleshootingSession) -> VerificationCheckpoint:
        """Create basic diagnostics verification checkpoint"""
        return VerificationCheckpoint(
            name="Basic Diagnostics Verification",
            description="Verify basic diagnostic steps are working correctly",
            verification_questions=[
                "Are basic system functions working?",
                "Is the application responding normally?",
                "Are there any obvious error messages?"
            ],
            success_indicators=[
                "Application launches successfully",
                "Basic functions accessible",
                "No critical error messages"
            ],
            failure_indicators=[
                "Application fails to start",
                "Critical functions unavailable",
                "Error messages persist"
            ],
            verification_method="basic_functionality_test",
            required_evidence=[
                "Application status confirmation",
                "Basic function test results"
            ]
        )
    
    async def _create_intermediate_verification_template(self, session: TroubleshootingSession) -> VerificationCheckpoint:
        """Create intermediate diagnostics verification checkpoint"""
        return VerificationCheckpoint(
            name="Intermediate Diagnostics Verification",
            description="Verify intermediate diagnostic steps show progress",
            verification_questions=[
                "Are configuration changes taking effect?",
                "Is connectivity improving?",
                "Are error patterns changing?"
            ],
            success_indicators=[
                "Configuration settings applied",
                "Connection tests successful",
                "Error frequency reduced"
            ],
            failure_indicators=[
                "Configuration changes ignored",
                "Connection tests still failing",
                "Error patterns unchanged"
            ],
            verification_method="configuration_and_connectivity_test",
            required_evidence=[
                "Configuration verification",
                "Connection test results",
                "Error log analysis"
            ]
        )
    
    async def _create_advanced_verification_template(self, session: TroubleshootingSession) -> VerificationCheckpoint:
        """Create advanced diagnostics verification checkpoint"""
        return VerificationCheckpoint(
            name="Advanced Diagnostics Verification",
            description="Verify advanced diagnostic procedures are effective",
            verification_questions=[
                "Are deep system issues being addressed?",
                "Is root cause analysis complete?",
                "Are complex configurations working?"
            ],
            success_indicators=[
                "System-level issues resolved",
                "Root cause identified",
                "Complex features functional"
            ],
            failure_indicators=[
                "Deep issues persist",
                "Root cause unclear",
                "Complex configurations failing"
            ],
            verification_method="deep_system_analysis",
            required_evidence=[
                "System diagnostic results",
                "Root cause analysis",
                "Complex feature testing"
            ]
        )
    
    async def _create_resolution_verification_template(self, session: TroubleshootingSession) -> VerificationCheckpoint:
        """Create resolution verification checkpoint"""
        return VerificationCheckpoint(
            name="Resolution Verification",
            description="Verify complete problem resolution",
            verification_questions=[
                "Is the original problem completely resolved?",
                "Can the customer complete their intended task?",
                "Is the solution stable and reliable?"
            ],
            success_indicators=[
                "Original problem eliminated",
                "Intended tasks completable",
                "Solution shows stability"
            ],
            failure_indicators=[
                "Original problem remains",
                "Tasks still cannot be completed",
                "Solution is unstable"
            ],
            verification_method="complete_resolution_test",
            required_evidence=[
                "Problem resolution confirmation",
                "Task completion verification",
                "Solution stability testing"
            ]
        )
    
    async def _create_generic_verification_checkpoint(self, session: TroubleshootingSession) -> VerificationCheckpoint:
        """Create generic verification checkpoint"""
        return VerificationCheckpoint(
            name="Progress Verification",
            description="Verify troubleshooting progress and effectiveness",
            verification_questions=[
                "Is progress being made toward resolution?",
                "Are the steps having the expected effect?",
                "Should we continue with current approach?"
            ],
            success_indicators=[
                "Positive changes observed",
                "Steps producing expected results",
                "Customer reports improvement"
            ],
            failure_indicators=[
                "No improvement observed",
                "Steps not working as expected",
                "Customer reports worsening"
            ],
            verification_method="progress_assessment",
            required_evidence=[
                "Step execution results",
                "Customer feedback",
                "System status changes"
            ]
        )
    
    # Helper methods
    
    def _determine_checkpoint_type(self, session: TroubleshootingSession) -> str:
        """Determine appropriate checkpoint type for session state"""
        
        completed_steps = len(session.completed_steps)
        current_phase = session.current_phase
        
        if completed_steps <= 2:
            return "initial_progress"
        elif current_phase == TroubleshootingPhase.BASIC_DIAGNOSTICS:
            return "basic_diagnostics"
        elif current_phase == TroubleshootingPhase.INTERMEDIATE_DIAGNOSTICS:
            return "intermediate_diagnostics"
        elif current_phase == TroubleshootingPhase.ADVANCED_DIAGNOSTICS:
            return "advanced_diagnostics"
        else:
            return "general_progress"
    
    async def _adapt_checkpoint_for_customer(
        self,
        checkpoint: VerificationCheckpoint,
        session: TroubleshootingSession
    ) -> VerificationCheckpoint:
        """Adapt verification checkpoint for customer characteristics"""
        
        # Adapt based on customer emotional state
        emotion = session.customer_emotional_state
        
        if emotion == EmotionalState.ANXIOUS:
            # Add reassuring language
            checkpoint.description = f"🔍 Careful verification: {checkpoint.description}"
            checkpoint.verification_questions.insert(0, "Is everything working safely?")
            
        elif emotion == EmotionalState.FRUSTRATED:
            # Focus on quick verification
            checkpoint.description = f"⚡ Quick check: {checkpoint.description}"
            checkpoint.verification_questions = checkpoint.verification_questions[:2]  # Limit questions
            
        elif emotion == EmotionalState.PROFESSIONAL:
            # Add technical details
            checkpoint.description = f"📊 Technical verification: {checkpoint.description}"
            checkpoint.verification_questions.append("Are all technical parameters within normal ranges?")
        
        # Adapt based on technical level
        tech_level = session.customer_technical_level
        
        if tech_level <= 2:
            # Simplify verification questions
            simplified_questions = []
            for question in checkpoint.verification_questions:
                simplified_questions.append(question.replace("configuration", "settings"))
            checkpoint.verification_questions = simplified_questions
            
        elif tech_level >= 4:
            # Add technical verification questions
            checkpoint.verification_questions.append("Are system logs showing normal operation?")
            checkpoint.required_evidence.append("Technical diagnostic data")
        
        return checkpoint
    
    def _check_criteria_in_result(self, criteria: str, step_result: Dict[str, Any]) -> bool:
        """Check if criteria is met in step result"""
        
        criteria_lower = criteria.lower()
        result_str = str(step_result).lower()
        
        # Direct keyword matching
        if criteria_lower in result_str:
            return True
        
        # Check for success indicators
        if 'success' in step_result and criteria_lower in ['successful', 'working', 'completed']:
            return bool(step_result['success'])
        
        # Check for specific status
        if 'status' in step_result:
            status = str(step_result['status']).lower()
            if 'success' in criteria_lower and 'success' in status:
                return True
            if 'fail' in criteria_lower and 'fail' in status:
                return True
        
        return False
    
    def _check_indicator_in_evidence(self, indicator: str, evidence: List[str]) -> bool:
        """Check if indicator is present in collected evidence"""
        
        indicator_lower = indicator.lower()
        
        for evidence_item in evidence:
            if indicator_lower in evidence_item.lower():
                return True
        
        return False
    
    def _extract_evidence_from_step(
        self,
        step: DiagnosticStep,
        checkpoint: VerificationCheckpoint
    ) -> List[str]:
        """Extract relevant evidence from diagnostic step"""
        
        evidence = []
        
        # Extract from step result data
        if step.result_data:
            for key, value in step.result_data.items():
                evidence.append(f"{key}: {value}")
        
        # Extract from execution notes
        if step.execution_notes:
            evidence.append(f"Step notes: {step.execution_notes}")
        
        # Extract from customer feedback
        if step.customer_feedback:
            evidence.append(f"Customer feedback: {step.customer_feedback}")
        
        # Extract from execution status
        evidence.append(f"Step status: {step.execution_status}")
        
        return evidence
    
    async def _perform_additional_validation_checks(
        self,
        session: TroubleshootingSession,
        completed_step: DiagnosticStep,
        step_result: Dict[str, Any],
        validation_notes: List[str],
        confidence_factors: List[float]
    ) -> None:
        """Perform additional validation checks specific to step type"""
        
        step_type = completed_step.step_type
        
        # Add step-type specific validation
        if step_type.value in ['connectivity_test', 'network_test']:
            if 'connection' in step_result and step_result['connection']:
                validation_notes.append("✅ Network connectivity confirmed")
                confidence_factors.append(0.9)
            else:
                validation_notes.append("❌ Network connectivity issues remain")
                confidence_factors.append(0.3)
        
        elif step_type.value in ['configuration_check', 'account_validation']:
            if 'configured' in step_result and step_result['configured']:
                validation_notes.append("✅ Configuration validated")
                confidence_factors.append(0.8)
            else:
                validation_notes.append("⚠️ Configuration may need adjustment")
                confidence_factors.append(0.5)
        
        # Check execution time vs estimate
        if completed_step.execution_start_time and completed_step.execution_end_time:
            actual_time = (completed_step.execution_end_time - completed_step.execution_start_time).total_seconds() / 60
            estimated_time = completed_step.time_estimate_minutes
            
            if actual_time <= estimated_time * 1.5:  # Within 150% of estimate
                validation_notes.append(f"✅ Completed within expected time ({actual_time:.1f}min)")
                confidence_factors.append(0.7)
            else:
                validation_notes.append(f"⚠️ Took longer than expected ({actual_time:.1f}min vs {estimated_time}min)")
                confidence_factors.append(0.4)
    
    async def _verify_original_problem_resolved(
        self,
        session: TroubleshootingSession,
        evidence: List[str]
    ) -> bool:
        """Verify that the original problem has been resolved"""
        
        # This would typically involve checking against the original problem description
        # and looking for resolution indicators in the evidence
        
        resolution_indicators = [
            'success', 'working', 'resolved', 'fixed', 'completed',
            'no error', 'functioning', 'operational'
        ]
        
        problem_indicators = [
            'error', 'failed', 'not working', 'broken', 'issue',
            'problem', 'cannot', 'unable'
        ]
        
        resolution_count = 0
        problem_count = 0
        
        for evidence_item in evidence:
            evidence_lower = evidence_item.lower()
            
            for indicator in resolution_indicators:
                if indicator in evidence_lower:
                    resolution_count += 1
            
            for indicator in problem_indicators:
                if indicator in evidence_lower:
                    problem_count += 1
        
        # Resolution confirmed if more resolution indicators than problem indicators
        return resolution_count > problem_count and resolution_count > 0
    
    async def _assess_customer_satisfaction(self, session: TroubleshootingSession) -> float:
        """Assess customer satisfaction based on session data"""
        
        satisfaction_score = 0.5  # Neutral baseline
        
        # Check customer feedback from completed steps
        positive_feedback_count = 0
        negative_feedback_count = 0
        
        for step in session.completed_steps:
            if step.customer_feedback:
                feedback_lower = step.customer_feedback.lower()
                
                if any(word in feedback_lower for word in ['good', 'great', 'thanks', 'working', 'fixed']):
                    positive_feedback_count += 1
                elif any(word in feedback_lower for word in ['not', 'still', 'problem', 'issue', 'wrong']):
                    negative_feedback_count += 1
        
        # Adjust based on feedback
        if positive_feedback_count > negative_feedback_count:
            satisfaction_score += 0.3
        elif negative_feedback_count > positive_feedback_count:
            satisfaction_score -= 0.3
        
        # Adjust based on session progress
        if session.overall_progress >= 0.8:
            satisfaction_score += 0.2
        elif session.overall_progress <= 0.3:
            satisfaction_score -= 0.2
        
        # Adjust based on failed steps
        if len(session.failed_steps) == 0:
            satisfaction_score += 0.1
        elif len(session.failed_steps) >= 3:
            satisfaction_score -= 0.2
        
        return max(0.0, min(1.0, satisfaction_score))
    
    async def _assess_solution_stability(
        self,
        session: TroubleshootingSession,
        evidence: List[str]
    ) -> float:
        """Assess stability and reliability of the solution"""
        
        stability_score = 0.7  # Optimistic baseline
        
        # Check for stability indicators in evidence
        stability_indicators = [
            'stable', 'consistent', 'reliable', 'persistent',
            'permanent', 'lasting', 'maintained'
        ]
        
        instability_indicators = [
            'intermittent', 'sometimes', 'occasionally', 'temporary',
            'unstable', 'inconsistent', 'random'
        ]
        
        stability_count = 0
        instability_count = 0
        
        for evidence_item in evidence:
            evidence_lower = evidence_item.lower()
            
            for indicator in stability_indicators:
                if indicator in evidence_lower:
                    stability_count += 1
            
            for indicator in instability_indicators:
                if indicator in evidence_lower:
                    instability_count += 1
        
        # Adjust based on indicators
        if stability_count > instability_count:
            stability_score += 0.2
        elif instability_count > stability_count:
            stability_score -= 0.3
        
        # Penalize if recent steps had mixed results
        recent_steps = session.completed_steps[-3:] if len(session.completed_steps) >= 3 else session.completed_steps
        mixed_results = len(session.failed_steps) > 0 and len(recent_steps) > 0
        
        if mixed_results:
            stability_score -= 0.1
        
        return max(0.0, min(1.0, stability_score))