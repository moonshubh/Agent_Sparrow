"""
Agent Sparrow - Reasoning Framework Schemas

This module defines the data structures used throughout the advanced reasoning
framework for chain-of-thought processing and problem-solving workflows.
"""

from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import uuid

from langchain_core.messages import BaseMessage

from app.agents_v2.primary_agent.prompts.emotion_templates import EmotionalState


class ReasoningPhase(Enum):
    """Phases of the reasoning process"""
    QUERY_ANALYSIS = "query_analysis"
    CONTEXT_RECOGNITION = "context_recognition"
    SOLUTION_MAPPING = "solution_mapping" 
    TOOL_ASSESSMENT = "tool_assessment"
    RESPONSE_STRATEGY = "response_strategy"
    EXECUTION = "execution"
    VALIDATION = "validation"
    SELF_CRITIQUE = "self_critique"
    QUALITY_ASSESSMENT = "quality_assessment"


class ProblemCategory(Enum):
    """Categories of problems Agent Sparrow can handle"""
    TECHNICAL_ISSUE = "technical_issue"
    ACCOUNT_SETUP = "account_setup"
    FEATURE_EDUCATION = "feature_education"
    BILLING_INQUIRY = "billing_inquiry"
    PERFORMANCE_OPTIMIZATION = "performance_optimization"
    TROUBLESHOOTING = "troubleshooting"
    GENERAL_SUPPORT = "general_support"


class BusinessImpact(Enum):
    """Business impact levels"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TimeSensitivity(Enum):
    """Time sensitivity levels"""
    IMMEDIATE = "immediate"
    HOURS = "hours"
    DAYS = "days"


class ToolDecisionType(Enum):
    """Types of tool usage decisions"""
    NO_TOOLS_NEEDED = "no_tools_needed"
    INTERNAL_KB_ONLY = "internal_kb_only"
    WEB_SEARCH_REQUIRED = "web_search_required"
    BOTH_SOURCES_NEEDED = "both_sources_needed"
    ESCALATION_REQUIRED = "escalation_required"


class ConfidenceLevel(Enum):
    """Confidence levels for reasoning outputs"""
    VERY_LOW = "very_low"      # < 0.3
    LOW = "low"                # 0.3 - 0.5
    MEDIUM = "medium"          # 0.5 - 0.7
    HIGH = "high"              # 0.7 - 0.9
    VERY_HIGH = "very_high"    # > 0.9


@dataclass
class ReasoningStep:
    """Individual step in the reasoning process"""
    phase: ReasoningPhase
    description: str
    reasoning: str
    confidence: float
    step_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    evidence: List[str] = field(default_factory=list)
    alternatives_considered: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)
    
    def get_confidence_level(self) -> ConfidenceLevel:
        """
        Returns the confidence level as a ConfidenceLevel enum based on the numeric confidence score.
        
        Returns:
            ConfidenceLevel: The corresponding confidence level enum value.
        """
        if self.confidence < 0.3:
            return ConfidenceLevel.VERY_LOW
        elif self.confidence < 0.5:
            return ConfidenceLevel.LOW
        elif self.confidence < 0.7:
            return ConfidenceLevel.MEDIUM
        elif self.confidence < 0.9:
            return ConfidenceLevel.HIGH
        else:
            return ConfidenceLevel.VERY_HIGH


@dataclass
class SituationalAnalysis:
    """V9 Situational Analysis from the deep reasoning matrix"""
    technical_complexity: int  # Scale 1-10
    emotional_intensity: int  # Scale 1-10
    business_impact: BusinessImpact
    time_sensitivity: TimeSensitivity


@dataclass
class QueryAnalysis:
    """Analysis of the customer query, enhanced for V9"""
    query_text: str
    # V9 Query Deconstruction
    surface_meaning: str
    latent_intent: str
    emotional_subtext: str
    historical_context: str

    # Core attributes
    emotional_state: EmotionalState
    emotion_confidence: float
    problem_category: ProblemCategory
    category_confidence: float
    key_entities: List[str] = field(default_factory=list)

    # V9 Situational Analysis
    situational_analysis: Optional[SituationalAnalysis] = None
    
    # Additional attributes for compatibility
    complexity_score: float = 0.5
    urgency_level: int = 3


@dataclass
class SolutionCandidate:
    """A potential solution pathway."""
    solution_summary: str
    detailed_steps: List[str]
    preventive_measures: List[str]
    confidence_score: float
    estimated_time_minutes: int
    solution_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    required_tools: List[str] = field(default_factory=list)
    fallback_options: List[str] = field(default_factory=list)
    risk_factors: List[str] = field(default_factory=list)
    success_indicators: List[str] = field(default_factory=list)
    _detailed_approach_override: Optional[str] = field(default=None, repr=False, init=False)

    @property
    def detailed_approach(self) -> str:
        """Return a rich text description of the solution steps."""
        if self._detailed_approach_override:
            return self._detailed_approach_override
        if isinstance(self.detailed_steps, str):
            return self.detailed_steps
        return "\n".join(self.detailed_steps)

    @detailed_approach.setter
    def detailed_approach(self, value: str) -> None:
        self._detailed_approach_override = value


@dataclass
class SolutionArchitecture:
    """V9 Solution Architecture"""
    primary_pathway: SolutionCandidate
    alternative_routes: List[SolutionCandidate] = field(default_factory=list)
    enhancement_opportunities: List[str] = field(default_factory=list)


@dataclass
class PredictiveInsight:
    """An insight from the predictive intelligence engine."""
    pattern_detected: str
    proactive_suggestion: str
    confidence: float


@dataclass
class ResponseOrchestration:
    """V9 Response Orchestration strategy"""
    emotional_acknowledgment_strategy: str
    technical_solution_delivery_method: str
    relationship_strengthening_elements: List[str]
    delight_injection_points: List[str]
    final_response_preview: Optional[str] = None


@dataclass
class SelfCritiqueResult:
    """Result of the self-critique process."""
    passed_critique: bool
    critique_score: float  # Score from 0.0 to 1.0
    suggested_improvements: List[str] = field(default_factory=list)
    refined_response: Optional[str] = None


@dataclass
class ToolDecisionReasoning:
    """Reasoning behind tool usage decisions"""
    decision_type: ToolDecisionType
    reasoning: str
    confidence: float
    required_information: List[str] = field(default_factory=list)
    temporal_factors: List[str] = field(default_factory=list)  # Recent updates, current status
    knowledge_gaps: List[str] = field(default_factory=list)
    search_strategy: Optional[str] = None
    expected_sources: List[str] = field(default_factory=list)


@dataclass
class ProblemSolvingPhase:
    """Individual phase in the 5-step problem solving framework"""
    phase_number: int
    phase_name: str
    description: str
    key_questions: List[str]
    deliverables: List[str]
    status: str = "pending"  # pending, in_progress, completed, skipped
    findings: List[str] = field(default_factory=list)
    confidence: float = 0.0
    time_spent_seconds: float = 0.0


@dataclass
class QualityAssessment:
    """Quality assessment of reasoning and response"""
    overall_quality_score: float  # 0-1
    reasoning_clarity: float
    solution_completeness: float
    emotional_appropriateness: float
    technical_accuracy: float
    response_structure: float
    improvement_suggestions: List[str] = field(default_factory=list)
    quality_issues: List[str] = field(default_factory=list)
    confidence_in_assessment: float = 0.0


@dataclass
class ReasoningState:
    """Complete state of the reasoning process"""
    reasoning_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = "default"
    start_time: datetime = field(default_factory=datetime.now)
    
    # Query text
    query_text: Optional[str] = None
    
    # Input analysis
    query_analysis: Optional[QueryAnalysis] = None
    
    # Reasoning steps
    reasoning_steps: List[ReasoningStep] = field(default_factory=list)
    
    # Problem solving
    problem_solving_phases: List[ProblemSolvingPhase] = field(default_factory=list)
    
    # Reasoning outputs
    predictive_insights: List[PredictiveInsight] = field(default_factory=list)
    solution_architecture: Optional[SolutionArchitecture] = None
    selected_solution: Optional[SolutionCandidate] = None  # For compatibility
    tool_reasoning: Optional[ToolDecisionReasoning] = None
    response_orchestration: Optional[ResponseOrchestration] = None
    self_critique_result: Optional[SelfCritiqueResult] = None
    quality_assessment: Optional[QualityAssessment] = None
    
    # Final outputs
    response_strategy: str = ""
    reasoning_summary: str = ""
    
    # Metadata
    total_processing_time: float = 0.0
    overall_confidence: float = 0.0
    requires_human_review: bool = False
    escalation_reasons: List[str] = field(default_factory=list)
    
    def add_reasoning_step(self, step: ReasoningStep) -> None:
        """
        Appends a new reasoning step to the list of reasoning steps in the process.
        """
        self.reasoning_steps.append(step)
        
    def get_current_phase(self) -> Optional[ReasoningPhase]:
        """
        Returns the phase of the most recent reasoning step, or None if no steps have been recorded.
        
        Returns:
            ReasoningPhase or None: The current reasoning phase, or None if there are no reasoning steps.
        """
        if not self.reasoning_steps:
            return None
        return self.reasoning_steps[-1].phase
    
    def get_phase_confidence(self, phase: ReasoningPhase) -> float:
        """
        Calculate the average confidence score for all reasoning steps within a specified reasoning phase.
        
        Parameters:
        	phase (ReasoningPhase): The reasoning phase for which to compute the average confidence.
        
        Returns:
        	float: The average confidence score for the specified phase, or 0.0 if no steps exist for that phase.
        """
        phase_steps = [step for step in self.reasoning_steps if step.phase == phase]
        if not phase_steps:
            return 0.0
        return sum(step.confidence for step in phase_steps) / len(phase_steps)
    
    def is_high_confidence(self, threshold: float = 0.8) -> bool:
        """
        Determine whether the overall reasoning confidence meets or exceeds a specified threshold.
        
        Parameters:
            threshold (float): The minimum confidence value required to be considered high confidence. Defaults to 0.8.
        
        Returns:
            bool: True if overall confidence is greater than or equal to the threshold, otherwise False.
        """
        return self.overall_confidence >= threshold
    
    def get_reasoning_trace(self) -> str:
        """
        Generate a human-readable summary of the reasoning process, including session metadata, query analysis, reasoning steps, selected solution, and tool usage decisions.
        
        Returns:
            str: A formatted string detailing the reasoning workflow and key decision points for the session.
        """
        trace_lines = []
        trace_lines.append(f"# Reasoning Trace for Query Analysis")
        trace_lines.append(f"**Session ID**: {self.session_id}")
        trace_lines.append(f"**Processing Time**: {self.total_processing_time:.2f}s")
        trace_lines.append(f"**Overall Confidence**: {self.overall_confidence:.2f}")
        trace_lines.append("")
        
        if self.query_analysis:
            trace_lines.append("## Query Analysis")
            trace_lines.append(f"- **Emotional State**: {self.query_analysis.emotional_state.value}")
            trace_lines.append(f"- **Problem Category**: {self.query_analysis.problem_category.value}")
            trace_lines.append(f"- **Urgency Level**: {self.query_analysis.urgency_level}/5")
            trace_lines.append(f"- **Complexity**: {self.query_analysis.complexity_score:.2f}")
            trace_lines.append("")
        
        if self.reasoning_steps:
            trace_lines.append("## Reasoning Steps")
            for i, step in enumerate(self.reasoning_steps, 1):
                trace_lines.append(f"**{i}. {step.phase.value.title()}** (Confidence: {step.confidence:.2f})")
                trace_lines.append(f"   {step.reasoning}")
                if step.alternatives_considered:
                    trace_lines.append(f"   *Alternatives*: {', '.join(step.alternatives_considered)}")
                trace_lines.append("")
        
        if self.solution_architecture and self.solution_architecture.primary_pathway:
            primary = self.solution_architecture.primary_pathway
            trace_lines.append("## Selected Solution (Primary Pathway)")
            trace_lines.append(f"**Summary**: {primary.solution_summary}")
            trace_lines.append(f"**Confidence**: {primary.confidence_score:.2f}")
            trace_lines.append(f"**Estimated Time**: {primary.estimated_time_minutes} minutes")
            trace_lines.append("")
        
        if self.tool_reasoning:
            trace_lines.append("## Tool Usage Decision")
            trace_lines.append(f"**Decision**: {self.tool_reasoning.decision_type.value}")
            trace_lines.append(f"**Reasoning**: {self.tool_reasoning.reasoning}")
            trace_lines.append("")
        
        return "\n".join(trace_lines)


@dataclass
class ReasoningConfig:
    """Configuration for the reasoning engine"""
    enable_chain_of_thought: bool = True
    enable_problem_solving_framework: bool = True
    enable_tool_intelligence: bool = True
    enable_quality_assessment: bool = True
    enable_reasoning_transparency: bool = True
    enable_self_critique: bool = True
    
    # Confidence thresholds
    minimum_confidence_threshold: float = 0.6
    high_confidence_threshold: float = 0.8
    escalation_threshold: float = 0.3
    
    # Processing limits
    max_reasoning_steps: int = 10
    max_solution_candidates: int = 5
    max_processing_time_seconds: float = 30.0
    
    # Quality standards
    quality_score_threshold: float = 0.7
    require_fallback_solutions: bool = True
    require_confidence_explanation: bool = True
    
    # Debug and transparency
    debug_mode: bool = False
    include_reasoning_trace: bool = False
    log_reasoning_steps: bool = True
    
    # Integration settings
    emotion_weight: float = 0.3
    urgency_weight: float = 0.2
    complexity_weight: float = 0.3
    confidence_weight: float = 0.2
    
    # Thinking budget controls
    thinking_budget_override: Optional[int] = None
    quality_level: str = "balanced"
