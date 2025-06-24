"""
Agent Sparrow - Structured Troubleshooting Schemas

This module defines the data structures for systematic troubleshooting workflows,
diagnostic step sequencing, and verification checkpoints.
"""

from typing import Dict, List, Optional, Any, Union, Callable
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import uuid

from app.agents_v2.primary_agent.reasoning.schemas import ProblemCategory, SolutionCandidate
from app.agents_v2.primary_agent.prompts.emotion_templates import EmotionalState


class ExecutionStatus(Enum):
    """Status of diagnostic step execution"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class TroubleshootingPhase(Enum):
    """Phases of structured troubleshooting workflow"""
    INITIAL_ASSESSMENT = "initial_assessment"
    BASIC_DIAGNOSTICS = "basic_diagnostics" 
    INTERMEDIATE_DIAGNOSTICS = "intermediate_diagnostics"
    ADVANCED_DIAGNOSTICS = "advanced_diagnostics"
    SPECIALIZED_TESTING = "specialized_testing"
    ESCALATION_PREPARATION = "escalation_preparation"
    RESOLUTION_VERIFICATION = "resolution_verification"


class DiagnosticStepType(Enum):
    """Types of diagnostic steps"""
    INFORMATION_GATHERING = "information_gathering"
    QUICK_TEST = "quick_test"
    CONFIGURATION_CHECK = "configuration_check"
    SYSTEM_VERIFICATION = "system_verification"
    NETWORK_TEST = "network_test"
    ACCOUNT_VALIDATION = "account_validation"
    PERMISSION_CHECK = "permission_check"
    CONNECTIVITY_TEST = "connectivity_test"
    DATA_INTEGRITY_CHECK = "data_integrity_check"
    PERFORMANCE_ANALYSIS = "performance_analysis"


class VerificationStatus(Enum):
    """Status of verification checkpoints"""
    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"
    SKIPPED = "skipped"


class EscalationTrigger(Enum):
    """Triggers for escalation"""
    COMPLEXITY_THRESHOLD = "complexity_threshold"
    TIME_LIMIT_EXCEEDED = "time_limit_exceeded"
    MULTIPLE_FAILURES = "multiple_failures" 
    CUSTOMER_REQUEST = "customer_request"
    CRITICAL_ISSUE = "critical_issue"
    INSUFFICIENT_PERMISSIONS = "insufficient_permissions"
    EXTERNAL_DEPENDENCY = "external_dependency"


class TroubleshootingOutcome(Enum):
    """Possible outcomes of troubleshooting"""
    RESOLVED = "resolved"
    PARTIALLY_RESOLVED = "partially_resolved"
    ESCALATED = "escalated"
    DEFERRED = "deferred"
    REQUIRES_FOLLOW_UP = "requires_follow_up"


@dataclass
class DiagnosticStep:
    """Individual diagnostic step in troubleshooting workflow"""
    step_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    step_number: int = 0
    step_type: DiagnosticStepType = DiagnosticStepType.INFORMATION_GATHERING
    title: str = ""
    description: str = ""
    instructions: str = ""
    expected_outcome: str = ""
    time_estimate_minutes: int = 5
    difficulty_level: int = 1  # 1-5 scale
    prerequisites: List[str] = field(default_factory=list)
    success_criteria: List[str] = field(default_factory=list)
    failure_indicators: List[str] = field(default_factory=list)
    next_steps_on_success: List[str] = field(default_factory=list)
    next_steps_on_failure: List[str] = field(default_factory=list)
    verification_method: str = ""
    troubleshooting_tips: List[str] = field(default_factory=list)
    common_issues: List[str] = field(default_factory=list)
    
    # Execution tracking
    execution_status: ExecutionStatus = field(default=ExecutionStatus.PENDING)
    execution_start_time: Optional[datetime] = None
    execution_end_time: Optional[datetime] = None
    execution_notes: str = ""
    customer_feedback: str = ""
    result_data: Dict[str, Any] = field(default_factory=dict)


@dataclass 
class VerificationCheckpoint:
    """Verification checkpoint to validate progress"""
    checkpoint_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    verification_questions: List[str] = field(default_factory=list)
    success_indicators: List[str] = field(default_factory=list)
    failure_indicators: List[str] = field(default_factory=list)
    verification_method: str = ""
    required_evidence: List[str] = field(default_factory=list)
    
    # Status tracking
    status: VerificationStatus = VerificationStatus.PENDING
    verification_time: Optional[datetime] = None
    verification_notes: str = ""
    evidence_collected: List[str] = field(default_factory=list)
    confidence_score: float = 0.0


@dataclass
class EscalationCriteria:
    """Criteria for determining when to escalate"""
    max_diagnostic_steps: int = 10
    max_time_minutes: int = 30
    max_failed_attempts: int = 3
    complexity_threshold: float = 0.8
    customer_frustration_threshold: float = 0.7
    required_expertise_level: int = 3  # 1-5 scale
    
    # Specific triggers
    triggers: List[EscalationTrigger] = field(default_factory=list)
    custom_conditions: List[str] = field(default_factory=list)
    escalation_pathways: Dict[str, str] = field(default_factory=dict)


@dataclass
class TroubleshootingWorkflow:
    """Complete troubleshooting workflow template"""
    workflow_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    problem_category: ProblemCategory = ProblemCategory.TECHNICAL_ISSUE
    applicable_symptoms: List[str] = field(default_factory=list)
    phases: List[TroubleshootingPhase] = field(default_factory=list)
    diagnostic_steps: List[DiagnosticStep] = field(default_factory=list)
    verification_checkpoints: List[VerificationCheckpoint] = field(default_factory=list)
    escalation_criteria: EscalationCriteria = field(default_factory=EscalationCriteria)
    
    # Workflow metadata
    estimated_time_minutes: int = 20
    success_rate: float = 0.85
    difficulty_level: int = 2  # 1-5 scale
    required_tools: List[str] = field(default_factory=list)
    required_permissions: List[str] = field(default_factory=list)
    
    # Conditional logic
    branching_conditions: Dict[str, Any] = field(default_factory=dict)
    adaptive_paths: Dict[str, List[str]] = field(default_factory=dict)


@dataclass
class TroubleshootingSession:
    """Active troubleshooting session state"""
    workflow: TroubleshootingWorkflow
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    current_phase: TroubleshootingPhase = TroubleshootingPhase.INITIAL_ASSESSMENT
    current_step: Optional[DiagnosticStep] = None
    completed_steps: List[DiagnosticStep] = field(default_factory=list)
    failed_steps: List[DiagnosticStep] = field(default_factory=list)
    skipped_steps: List[DiagnosticStep] = field(default_factory=list)
    
    # Session metadata
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    customer_emotional_state: EmotionalState = EmotionalState.NEUTRAL
    customer_technical_level: int = 2  # 1-5 scale
    
    # Progress tracking
    overall_progress: float = 0.0
    phase_progress: Dict[TroubleshootingPhase, float] = field(default_factory=dict)
    verification_results: List[VerificationCheckpoint] = field(default_factory=list)
    
    # Outcome tracking
    outcome: Optional[TroubleshootingOutcome] = None
    resolution_summary: str = ""
    escalation_reason: str = ""
    follow_up_actions: List[str] = field(default_factory=list)
    
    # Adaptive adjustments
    difficulty_adjustments: List[str] = field(default_factory=list)
    customer_preferences: Dict[str, Any] = field(default_factory=dict)
    session_notes: List[str] = field(default_factory=list)


@dataclass
class TroubleshootingState:
    """Complete state of structured troubleshooting system"""
    state_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    query_text: str = ""
    problem_category: ProblemCategory = ProblemCategory.TECHNICAL_ISSUE
    customer_emotion: EmotionalState = EmotionalState.NEUTRAL
    
    # Active session
    active_session: Optional[TroubleshootingSession] = None
    
    # Available workflows
    available_workflows: List[TroubleshootingWorkflow] = field(default_factory=list)
    recommended_workflow: Optional[TroubleshootingWorkflow] = None
    
    # Integration with reasoning
    reasoning_insights: Dict[str, Any] = field(default_factory=dict)
    solution_candidates: List[SolutionCandidate] = field(default_factory=list)
    
    # System state
    system_context: Dict[str, Any] = field(default_factory=dict)
    environmental_factors: Dict[str, Any] = field(default_factory=dict)
    
    # Progress and outcomes
    troubleshooting_history: List[TroubleshootingSession] = field(default_factory=list)
    success_patterns: Dict[str, Any] = field(default_factory=dict)
    learning_insights: List[str] = field(default_factory=list)


@dataclass
class TroubleshootingConfig:
    """Configuration for structured troubleshooting system"""
    enable_adaptive_workflows: bool = True
    enable_progressive_complexity: bool = True
    enable_verification_checkpoints: bool = True
    enable_automatic_escalation: bool = True
    enable_session_persistence: bool = True
    
    # Timing and limits
    default_step_timeout_minutes: int = 10
    max_session_duration_minutes: int = 60
    verification_interval_steps: int = 3
    
    # Adaptation settings
    emotional_adaptation_enabled: bool = True
    technical_level_adaptation: bool = True
    progressive_hint_system: bool = True
    
    # Quality settings
    minimum_verification_confidence: float = 0.7
    escalation_confidence_threshold: float = 0.3
    success_rate_threshold: float = 0.8
    
    # Integration settings
    integrate_with_reasoning_engine: bool = True
    use_solution_candidates: bool = True
    enable_workflow_learning: bool = True
    
    # Debug and monitoring
    debug_mode: bool = False
    log_detailed_steps: bool = True
    track_performance_metrics: bool = True