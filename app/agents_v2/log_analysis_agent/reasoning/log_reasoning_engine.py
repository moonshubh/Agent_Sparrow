"""
Log Reasoning Engine

Extends the base ReasoningEngine with specialized capabilities for log analysis,
incorporating emotional intelligence and technical pattern recognition.
"""

import logging
import asyncio
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from pathlib import Path

from app.agents_v2.primary_agent.reasoning.reasoning_engine import ReasoningEngine
from app.agents_v2.primary_agent.reasoning.schemas import (
    ReasoningState,
    ReasoningStep,
    ReasoningPhase,
    QueryAnalysis,
    ReasoningConfig,
    SolutionCandidate,
)
from app.agents_v2.primary_agent.prompts.emotion_templates import (
    EmotionalState,
    EmotionTemplates,
)
from app.providers.base import BaseChatModel

from ..schemas.log_schemas import (
    LogAnalysisResult,
    LogMetadata,
    ErrorPattern,
    RootCause,
    UserContext,
)
from .root_cause_classifier import RootCauseClassifier

logger = logging.getLogger(__name__)


class LogReasoningEngine(ReasoningEngine):
    """
    Specialized reasoning engine for log analysis with enhanced capabilities.

    Extends the base ReasoningEngine to provide:
    - Log-specific pattern recognition
    - Root cause analysis integration
    - Technical-to-empathetic translation
    - Confidence scoring for diagnoses
    """

    def __init__(
        self,
        model: BaseChatModel,
        config: Optional[ReasoningConfig] = None,
        provider: Optional[str] = None,
        model_name: Optional[str] = None,
    ):
        """
        Initialize the log reasoning engine.

        Args:
            model: The language model to use
            config: Reasoning configuration
            provider: Model provider name
            model_name: Specific model name
        """
        super().__init__(model, config, provider, model_name)
        self.root_cause_classifier = RootCauseClassifier()
        self._analysis_cache: Dict[str, LogAnalysisResult] = {}

    async def analyze_logs_with_reasoning(
        self,
        log_analysis: LogAnalysisResult,
        user_query: Optional[str] = None,
        user_context: Optional[UserContext] = None,
    ) -> Tuple[ReasoningState, str]:
        """
        Perform reasoning on log analysis results.

        Args:
            log_analysis: Results from log analysis
            user_query: Optional user query about the logs
            user_context: Optional user context

        Returns:
            Tuple of (reasoning_state, user_response)
        """
        # Create a contextualized query
        if user_query:
            contextualized_query = user_query
        else:
            contextualized_query = self._generate_analysis_query(log_analysis)

        # Prepare context with log analysis data
        context = self._prepare_log_context(log_analysis, user_context)

        # Run reasoning process
        reasoning_state = await self.reason_about_query(
            query=contextualized_query,
            context=context,
            session_id=log_analysis.analysis_id,
        )

        # Enhance reasoning with log-specific analysis
        await self._enhance_with_log_reasoning(
            reasoning_state, log_analysis, user_context
        )

        # Generate user-friendly response
        user_response = await self._generate_log_analysis_response(
            reasoning_state, log_analysis, user_context
        )

        return reasoning_state, user_response

    def _generate_analysis_query(self, log_analysis: LogAnalysisResult) -> str:
        """Generate a query based on log analysis results."""
        if log_analysis.has_critical_issues:
            return (
                f"Critical issues detected in Mailbird logs: "
                f"{log_analysis.top_priority_cause.title if log_analysis.top_priority_cause else 'Multiple errors found'}. "
                f"Need immediate assistance with resolution."
            )
        elif log_analysis.root_causes:
            return (
                f"Log analysis reveals {len(log_analysis.root_causes)} issues "
                f"affecting Mailbird performance. Help needed with troubleshooting."
            )
        else:
            return "Mailbird log analysis completed. Please review findings and recommendations."

    def _prepare_log_context(
        self,
        log_analysis: LogAnalysisResult,
        user_context: Optional[UserContext],
    ) -> Dict[str, Any]:
        """Prepare context dictionary with log analysis data."""
        context = {
            "log_analysis": {
                "total_errors": log_analysis.metadata.error_count,
                "error_rate": log_analysis.metadata.error_rate,
                "session_duration": log_analysis.metadata.session_duration_hours,
                "has_critical_issues": log_analysis.has_critical_issues,
                "pattern_count": len(log_analysis.error_patterns),
                "root_cause_count": len(log_analysis.root_causes),
            },
            "system_info": {
                "mailbird_version": log_analysis.metadata.mailbird_version,
                "os_version": log_analysis.metadata.os_version,
                "account_count": log_analysis.metadata.account_count,
                "database_size_mb": log_analysis.metadata.database_size_mb,
            },
        }

        # Add top issues
        if log_analysis.root_causes:
            top_causes = log_analysis.root_causes[:3]
            context["top_issues"] = [
                {
                    "title": cause.title,
                    "category": cause.category.name,
                    "confidence": cause.confidence_score,
                    "impact": cause.impact.value,
                }
                for cause in top_causes
            ]

        # Add user context if available
        if user_context:
            context["user_context"] = {
                "reported_issue": user_context.reported_issue,
                "urgency": user_context.urgency_level,
                "business_impact": user_context.business_impact,
                "emotional_state": user_context.emotional_state,
            }

        return context

    async def _enhance_with_log_reasoning(
        self,
        reasoning_state: ReasoningState,
        log_analysis: LogAnalysisResult,
        user_context: Optional[UserContext],
    ):
        """Enhance reasoning state with log-specific analysis."""
        # Add log analysis phase
        step = ReasoningStep(
            phase=ReasoningPhase.CONTEXT_RECOGNITION,
            description="Analyzed Mailbird log patterns and metadata",
            reasoning=self._summarize_log_findings(log_analysis),
            confidence=log_analysis.confidence_score,
            evidence=self._extract_key_evidence(log_analysis),
        )
        reasoning_state.add_reasoning_step(step)

        # Add root cause analysis phase
        if log_analysis.root_causes:
            top_cause = log_analysis.top_priority_cause
            step = ReasoningStep(
                phase=ReasoningPhase.SOLUTION_MAPPING,
                description="Identified root causes and solutions",
                reasoning=f"Primary root cause: {top_cause.title} with {top_cause.confidence_score:.0%} confidence",
                confidence=top_cause.confidence_score,
                evidence=top_cause.evidence[:3],
            )
            reasoning_state.add_reasoning_step(step)

        # Update overall confidence
        if log_analysis.confidence_score > reasoning_state.overall_confidence:
            reasoning_state.overall_confidence = log_analysis.confidence_score

    def _summarize_log_findings(self, log_analysis: LogAnalysisResult) -> str:
        """Create a summary of log analysis findings."""
        parts = []

        # Error summary
        if log_analysis.metadata.error_count > 0:
            parts.append(
                f"Found {log_analysis.metadata.error_count} errors "
                f"({log_analysis.metadata.error_rate:.1f}% error rate)"
            )

        # Pattern summary
        if log_analysis.error_patterns:
            pattern_categories = set(p.category for p in log_analysis.error_patterns)
            parts.append(
                f"Detected {len(log_analysis.error_patterns)} error patterns "
                f"across {len(pattern_categories)} categories"
            )

        # Root cause summary
        if log_analysis.root_causes:
            high_confidence = [
                c for c in log_analysis.root_causes if c.confidence_score >= 0.7
            ]
            parts.append(
                f"Identified {len(log_analysis.root_causes)} root causes "
                f"({len(high_confidence)} with high confidence)"
            )

        return ". ".join(parts) if parts else "Log analysis completed successfully"

    def _extract_key_evidence(self, log_analysis: LogAnalysisResult) -> List[str]:
        """Extract key evidence from log analysis."""
        evidence = []

        # Add metadata evidence
        if log_analysis.metadata.database_size_mb and log_analysis.metadata.database_size_mb > 1000:
            evidence.append(
                f"Large database size: {log_analysis.metadata.database_size_mb:.0f} MB"
            )

        # Add pattern evidence
        for pattern in log_analysis.error_patterns[:2]:
            evidence.append(
                f"{pattern.description}: {pattern.occurrences} occurrences"
            )

        # Add root cause evidence
        if log_analysis.root_causes:
            top_cause = log_analysis.root_causes[0]
            evidence.extend(top_cause.evidence[:2])

        return evidence

    async def _generate_log_analysis_response(
        self,
        reasoning_state: ReasoningState,
        log_analysis: LogAnalysisResult,
        user_context: Optional[UserContext],
    ) -> str:
        """
        Generate a user-friendly response based on log analysis.

        Args:
            reasoning_state: The reasoning state
            log_analysis: Log analysis results
            user_context: User context if available

        Returns:
            Formatted response for the user
        """
        # Determine emotional tone
        emotional_state = self._determine_emotional_tone(log_analysis, user_context)

        # Get empathy template
        issue_summary = (
            log_analysis.top_priority_cause.title
            if log_analysis.top_priority_cause
            else "the issues found in your logs"
        )
        empathy_opening = EmotionTemplates.get_empathy_template(
            emotional_state, issue_summary
        )

        # Build response sections
        response_parts = [empathy_opening]

        # Add key findings
        if log_analysis.root_causes:
            response_parts.append(self._format_key_findings(log_analysis))

        # Add primary solution
        if log_analysis.top_priority_cause:
            response_parts.append(
                self._format_primary_solution(log_analysis.top_priority_cause)
            )

        # Add additional recommendations
        if log_analysis.recommendations:
            response_parts.append(self._format_recommendations(log_analysis))

        # Add reassurance and next steps
        response_parts.append(self._generate_closing(log_analysis, emotional_state))

        return "\n\n".join(response_parts)

    def _determine_emotional_tone(
        self,
        log_analysis: LogAnalysisResult,
        user_context: Optional[UserContext],
    ) -> EmotionalState:
        """Determine appropriate emotional tone for response."""
        # Use user context if available
        if user_context and user_context.emotional_state:
            emotion_map = {
                "frustrated": EmotionalState.FRUSTRATED,
                "confused": EmotionalState.CONFUSED,
                "anxious": EmotionalState.ANXIOUS,
                "professional": EmotionalState.PROFESSIONAL,
                "urgent": EmotionalState.URGENT,
                "disappointed": EmotionalState.DISAPPOINTED,
            }
            return emotion_map.get(
                user_context.emotional_state.lower(), EmotionalState.NEUTRAL
            )

        # Determine based on issue severity
        if log_analysis.has_critical_issues:
            return EmotionalState.ANXIOUS
        elif log_analysis.metadata.error_rate > 20:
            return EmotionalState.FRUSTRATED
        elif len(log_analysis.root_causes) > 3:
            return EmotionalState.CONFUSED
        else:
            return EmotionalState.PROFESSIONAL

    def _format_key_findings(self, log_analysis: LogAnalysisResult) -> str:
        """Format key findings section."""
        findings = ["**Key Findings from Your Logs:**"]

        for i, cause in enumerate(log_analysis.root_causes[:3], 1):
            confidence_text = self._confidence_to_text(cause.confidence_score)
            impact_emoji = self._impact_to_emoji(cause.impact)
            findings.append(
                f"{i}. {impact_emoji} **{cause.title}** "
                f"({confidence_text} confidence)"
            )
            if cause.affected_features:
                findings.append(
                    f"   Affecting: {', '.join(cause.affected_features[:3])}"
                )

        return "\n".join(findings)

    def _format_primary_solution(self, root_cause: RootCause) -> str:
        """Format primary solution section."""
        solution_parts = [
            f"**Let's fix the main issue: {root_cause.title}**",
            "",
            "Here's what we need to do:",
        ]

        for i, step in enumerate(root_cause.resolution_steps[:5], 1):
            solution_parts.append(f"{i}. {step}")

        if root_cause.estimated_resolution_time:
            solution_parts.append(
                f"\n⏱️ Estimated time: {root_cause.estimated_resolution_time} minutes"
            )

        return "\n".join(solution_parts)

    def _format_recommendations(self, log_analysis: LogAnalysisResult) -> str:
        """Format additional recommendations."""
        rec_parts = ["**Additional Recommendations:**"]

        for i, rec in enumerate(log_analysis.recommendations[:3], 1):
            rec_parts.append(f"• {rec}")

        return "\n".join(rec_parts)

    def _generate_closing(
        self,
        log_analysis: LogAnalysisResult,
        emotional_state: EmotionalState,
    ) -> str:
        """Generate closing section with reassurance."""
        if log_analysis.data_integrity_risk:
            closing = (
                "⚠️ **Important**: Your email data needs immediate attention. "
                "Please follow the steps above carefully, and don't hesitate to "
                "reach out if you need any clarification."
            )
        elif log_analysis.has_critical_issues:
            closing = (
                "I understand this might seem overwhelming, but we'll get through "
                "this step by step. Your emails are safe, and these issues are "
                "fixable. Start with step 1 and let me know how it goes!"
            )
        else:
            closing = (
                "These improvements will enhance your Mailbird experience. "
                "The issues found are common and easily resolved. Feel free to "
                "ask if you need any clarification on the steps!"
            )

        # Add escalation note if needed
        if log_analysis.requires_escalation:
            closing += (
                f"\n\n🔄 **Note**: {log_analysis.escalation_reason}. "
                "If the steps don't resolve the issue, our support team is ready to help."
            )

        return closing

    def _confidence_to_text(self, confidence: float) -> str:
        """Convert confidence score to human-readable text."""
        if confidence >= 0.9:
            return "very high"
        elif confidence >= 0.75:
            return "high"
        elif confidence >= 0.6:
            return "moderate"
        elif confidence >= 0.4:
            return "low"
        else:
            return "uncertain"

    def _impact_to_emoji(self, impact) -> str:
        """Convert impact level to emoji."""
        emoji_map = {
            "minimal": "🟢",
            "low": "🟡",
            "medium": "🟠",
            "high": "🔴",
            "critical": "🚨",
        }
        return emoji_map.get(impact.value if hasattr(impact, "value") else impact, "⚪")

    async def generate_reflection_prompt(
        self,
        log_analysis: LogAnalysisResult,
        initial_response: str,
    ) -> str:
        """
        Generate a reflection prompt for secondary reasoning.

        Args:
            log_analysis: The log analysis results
            initial_response: The initial response generated

        Returns:
            Reflection prompt for quality improvement
        """
        reflection = f"""
Reflect on this log analysis response for quality improvement:

**Log Analysis Summary:**
- Errors found: {log_analysis.metadata.error_count}
- Root causes identified: {len(log_analysis.root_causes)}
- Confidence score: {log_analysis.confidence_score:.0%}
- Critical issues: {log_analysis.has_critical_issues}

**Initial Response:**
{initial_response[:500]}...

**Reflection Questions:**
1. Is the technical diagnosis accurately conveyed in user-friendly language?
2. Are the resolution steps clear and actionable for the user's technical level?
3. Does the emotional tone match the severity of the issues?
4. Are there any missing critical details that would help resolution?
5. Is the response structure logical and easy to follow?

**Enhancement Focus:**
- Ensure empathy is appropriate to issue severity
- Verify technical accuracy of solutions
- Check for completeness of troubleshooting steps
- Confirm clarity for non-technical users
"""
        return reflection