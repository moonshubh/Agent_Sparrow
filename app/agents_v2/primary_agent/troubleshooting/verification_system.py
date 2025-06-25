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
        Initializes the VerificationSystem with troubleshooting configuration and sets up verification templates for each troubleshooting phase.
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
        Runs a verification checkpoint for the current troubleshooting session, assessing progress and solution effectiveness based on the session state and checkpoint type.
        
        Parameters:
            session (TroubleshootingSession): The active troubleshooting session.
            checkpoint_type (Optional[str]): The specific type of checkpoint to run. If not provided, the type is determined automatically.
        
        Returns:
            VerificationCheckpoint: The completed verification checkpoint with status, notes, evidence, and confidence score.
        """
        
        # Determine checkpoint type if not specified
        if not checkpoint_type:
            checkpoint_type = self._determine_checkpoint_type(session)
        
        # Create verification checkpoint
        checkpoint = await self._create_verification_checkpoint(session, checkpoint_type)
        
        try:
            # Execute verification process with error handling
            verification_result = await self._execute_verification(session, checkpoint)
            
            # Update checkpoint with results
            checkpoint.status = verification_result['status']
            checkpoint.verification_time = datetime.now()
            checkpoint.verification_notes = verification_result['notes']
            checkpoint.evidence_collected = verification_result['evidence']
            checkpoint.confidence_score = verification_result['confidence']
            
            logger.info(f"Verification checkpoint completed with status: {checkpoint.status.value}")
            
        except Exception as e:
            # Log the error with full context
            logger.error(
                f"Error during verification checkpoint for session {session.session_id}: {str(e)}",
                exc_info=True
            )
            
            # Update checkpoint with error state
            checkpoint.status = VerificationStatus.FAILED
            checkpoint.verification_time = datetime.now()
            checkpoint.verification_notes = (
                f"Verification failed due to an error: {str(e)}. "
                "Please check logs for more details."
            )
            checkpoint.evidence_collected = []
            checkpoint.confidence_score = 0.0
            
            logger.warning(
                f"Verification checkpoint failed for session {session.session_id}. "
                f"Checkpoint marked as {checkpoint.status.value}."
            )
        
        return checkpoint
    
    async def run_final_verification(
        self,
        session: TroubleshootingSession
    ) -> VerificationCheckpoint:
        """
        Performs a comprehensive final verification to confirm issue resolution, customer satisfaction, and solution stability for a completed troubleshooting session.
        
        Returns:
            VerificationCheckpoint: The finalized checkpoint summarizing the outcome, supporting evidence, and confidence score of the final verification.
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
        Validates whether a diagnostic step in a troubleshooting session has been successfully completed.
        
        Assesses the step result against defined success criteria and failure indicators, performs additional validation checks, and computes a confidence score. Returns whether validation passed, the confidence score, and explanatory notes.
        
        Returns:
            Tuple[bool, float, List[str]]: A tuple containing a boolean indicating if validation passed, the confidence score, and a list of validation notes.
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
        """
        Creates a verification checkpoint for the current troubleshooting session and phase.
        
        Selects a phase-specific checkpoint template if available, or generates a generic checkpoint otherwise. The checkpoint is then adapted to the customer's emotional state and technical level before being returned.
         
        Returns:
            VerificationCheckpoint: The adapted verification checkpoint for the session and phase.
        """
        
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
        """
        Executes a verification checkpoint by analyzing recent diagnostic steps for success and failure indicators.
        
        Evaluates evidence from the most recent completed steps, checks for the presence of defined success and failure indicators, determines the checkpoint status (PASSED, FAILED, INCONCLUSIVE), and calculates a confidence score based on the findings.
        
        Returns:
            Dict[str, Any]: A dictionary containing the verification status, confidence score, collected evidence, and explanatory notes.
        """
        
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
        """
        Performs a comprehensive final verification of the troubleshooting session, evaluating problem resolution, customer satisfaction, and solution stability.
        
        Collects evidence from all completed diagnostic steps, assesses whether the original issue is resolved, measures customer satisfaction, and evaluates the stability of the implemented solution. Returns a dictionary containing the final verification status, confidence score, supporting notes, and collected evidence.
         
        Returns:
            Dict[str, Any]: A dictionary with keys 'status', 'confidence', 'notes', and 'evidence' summarizing the final verification outcome.
        """
        
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
        """
        Create a verification checkpoint template for the basic diagnostics phase.
        
        This checkpoint focuses on confirming that fundamental system and application functions are operational, with questions and indicators tailored to early-stage troubleshooting.
        """
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
        """
        Create a verification checkpoint template for the intermediate diagnostics phase.
        
        This checkpoint focuses on validating progress made during intermediate troubleshooting steps, such as configuration changes and connectivity improvements. It defines relevant verification questions, success and failure indicators, and specifies the required evidence for assessing the effectiveness of intermediate diagnostics.
        
        Returns:
            VerificationCheckpoint: A checkpoint configured for intermediate diagnostics verification.
        """
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
        """
        Create a verification checkpoint template for the advanced diagnostics phase.
        
        This checkpoint focuses on verifying the effectiveness of advanced diagnostic procedures, including root cause analysis and complex configuration validation.
        """
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
        """
        Create a verification checkpoint template focused on confirming complete problem resolution at the end of troubleshooting.
        
        Returns:
            VerificationCheckpoint: A checkpoint configured to assess whether the original problem is resolved, the customer can complete intended tasks, and the solution is stable and reliable.
        """
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
        """
        Create a generic verification checkpoint to assess overall troubleshooting progress and effectiveness.
        
        Returns:
            VerificationCheckpoint: A checkpoint with questions and indicators focused on evaluating whether the troubleshooting session is making progress, including required evidence such as step results and customer feedback.
        """
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
        """
        Determines the appropriate verification checkpoint type based on the session's completed steps and current troubleshooting phase.
        
        Returns:
            str: The checkpoint type identifier corresponding to the session's progress and phase.
        """
        
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
        """
        Adapts a verification checkpoint's description and questions to match the customer's emotional state and technical level.
        
        Modifies checkpoint language and content to provide reassurance, brevity, or technical detail based on the customer's emotional profile, and adjusts question complexity and evidence requirements according to technical proficiency.
        
        Returns:
            VerificationCheckpoint: The adapted verification checkpoint tailored to the customer's characteristics.
        """
        
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
        """
        Determines whether a specified criterion is satisfied within a diagnostic step result.
        
        Checks for the presence of the criterion as a keyword in the result, evaluates success indicators, and matches status fields to identify if the criterion is met.
        
        Parameters:
            criteria (str): The success or failure criterion to check for.
            step_result (Dict[str, Any]): The result data from a diagnostic step.
        
        Returns:
            bool: True if the criterion is satisfied in the step result, otherwise False.
        """
        
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
        """
        Determine whether a specified indicator string is present within any of the collected evidence items.
        
        Returns:
            bool: True if the indicator is found in any evidence item (case-insensitive), otherwise False.
        """
        
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
        """
        Extracts evidence strings from a diagnostic step, including result data, execution notes, customer feedback, and execution status.
        
        Returns:
            List[str]: A list of evidence strings relevant to the verification checkpoint.
        """
        
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
        """
        Performs additional validation checks for a diagnostic step based on its type and execution timing.
        
        Adds step-type-specific validation notes and confidence factors, such as confirming network connectivity, configuration status, and whether the step was completed within the expected time frame.
        """
        
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
        """
        Determines whether the original problem described in the troubleshooting session has been resolved based on provided evidence.
        
        Returns:
            bool: True if resolution indicators in the evidence outnumber problem indicators and at least one resolution indicator is present; otherwise, False.
        """
        
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
        """
        Calculates a customer satisfaction score for the troubleshooting session.
        
        The score is determined by analyzing customer feedback from completed steps, overall session progress, and the number of failed steps. The result is a float between 0.0 (very dissatisfied) and 1.0 (very satisfied).
         
        Returns:
            float: The computed customer satisfaction score for the session.
        """
        
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
        """
        Evaluates the stability and reliability of the implemented solution based on evidence and recent troubleshooting step outcomes.
        
        Returns:
            float: A stability score between 0.0 and 1.0, where higher values indicate greater solution stability.
        """
        
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