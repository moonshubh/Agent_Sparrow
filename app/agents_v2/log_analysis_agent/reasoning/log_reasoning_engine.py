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
from ..tools import LogToolOrchestrator, ToolResults
from ..formatters.response_formatter import LogResponseFormatter, FormattingConfig

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
        self.tool_orchestrator = LogToolOrchestrator()

        # Initialize response formatter
        formatter_config = FormattingConfig(
            enable_quality_check=True,
            min_quality_score=config.quality_score_threshold if config else 0.7
        )
        self.response_formatter = LogResponseFormatter(formatter_config)

        self._analysis_cache: Dict[str, LogAnalysisResult] = {}
        self._tool_results_cache: Dict[str, ToolResults] = {}
        self._max_cache_size = 100  # Prevent unbounded cache growth

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

        # Phase 6: Tool Context Gathering - Search for additional context
        if log_analysis.error_patterns:
            tool_results = await self._gather_tool_context(
                log_analysis.error_patterns,
                log_analysis.metadata
            )

            if tool_results and tool_results.has_results:
                step = ReasoningStep(
                    phase=ReasoningPhase.CONTEXT_RECOGNITION,
                    description="Gathered additional context from knowledge sources",
                    reasoning=self._summarize_tool_results(tool_results),
                    confidence=0.8,
                    evidence=self._extract_tool_evidence(tool_results),
                )
                reasoning_state.add_reasoning_step(step)

                # Store tool results for response generation
                self._manage_cache_size()
                self._tool_results_cache[log_analysis.analysis_id] = tool_results
            else:
                # Clear stale cache entry when no results are found
                # This prevents stale data from persisting
                self._tool_results_cache.pop(log_analysis.analysis_id, None)

        # Update overall confidence
        if log_analysis.confidence_score > reasoning_state.overall_confidence:
            reasoning_state.overall_confidence = log_analysis.confidence_score

    def _manage_cache_size(self) -> None:
        """
        Manage cache size to prevent unbounded growth.

        Uses FIFO (First In, First Out) strategy when cache exceeds max size.
        """
        if len(self._tool_results_cache) >= self._max_cache_size:
            # Remove the oldest entry (first item in dict)
            # In Python 3.7+, dict maintains insertion order
            oldest_key = next(iter(self._tool_results_cache))
            del self._tool_results_cache[oldest_key]
            logger.debug(f"Evicted oldest cache entry: {oldest_key}")

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

        # Try to use the new response formatter if available
        if hasattr(self, 'response_formatter'):
            try:
                # Get tool results from cache
                tool_results = self._tool_results_cache.get(log_analysis.analysis_id)

                # Extract user name if possible
                user_name = getattr(user_context, "user_name", None) if user_context else None
                if not user_name and user_context and user_context.reported_issue:
                    tokens = user_context.reported_issue.split()
                    stoplist = {"My", "The", "Email", "I", "A"}
                    if tokens:
                        candidate = tokens[0]
                        if (
                            candidate
                            and candidate not in stoplist
                            and candidate[0].isupper()
                            and candidate[1:].islower()
                            and candidate.isalpha()
                            and len(candidate) > 1
                        ):
                            user_name = candidate

                # Use the new formatter for high-quality responses
                formatted_response, validation_result = await self.response_formatter.format_response(
                    analysis=log_analysis,
                    emotional_state=emotional_state,
                    user_context=user_context,
                    tool_results=tool_results,
                    attachment_data=None,
                    user_name=user_name
                )

                # Log quality metrics
                logger.info(
                    f"Response quality score: {validation_result.score.overall_score:.2f} "
                    f"for analysis {log_analysis.analysis_id}"
                )

                return formatted_response

            except (ValueError, TypeError) as exc:
                logger.warning("Response formatter rejected input: %s", exc, exc_info=True)
                # Fall through to basic formatting
            except Exception as exc:
                logger.exception("Unexpected formatter failure", exc_info=True)
                raise

        # Fallback to basic formatting if formatter not available or failed
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

        # Add resources from tools if available
        tool_results = self._tool_results_cache.get(log_analysis.analysis_id)
        if tool_results and tool_results.has_results:
            response_parts.append(self._format_tool_resources(tool_results))

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

    async def _gather_tool_context(
        self,
        error_patterns: List[ErrorPattern],
        metadata: LogMetadata
    ) -> Optional[ToolResults]:
        """
        Gather additional context from tools (KB, FeedMe, Tavily).

        Args:
            error_patterns: List of detected error patterns
            metadata: Log metadata

        Returns:
            ToolResults with gathered context or None
        """
        try:
            logger.info("Gathering tool context for log analysis")

            # Execute parallel tool searches
            tool_results = await self.tool_orchestrator.search_all(
                patterns=error_patterns,
                metadata=metadata,
                use_cache=True
            )

            if tool_results.has_results:
                logger.info(
                    f"Tool context gathered - KB: {len(tool_results.kb_articles)}, "
                    f"FeedMe: {len(tool_results.feedme_conversations)}, "
                    f"Web: {len(tool_results.web_resources)}"
                )
            else:
                logger.warning("No tool results found")

            return tool_results

        except Exception as e:
            logger.error(f"Error gathering tool context: {e}", exc_info=True)
            return None

    def _summarize_tool_results(self, tool_results: ToolResults) -> str:
        """Summarize tool search results."""
        parts = []

        if tool_results.kb_articles:
            parts.append(
                f"Found {len(tool_results.kb_articles)} relevant KB articles"
            )

        if tool_results.feedme_conversations:
            resolved = sum(
                1 for c in tool_results.feedme_conversations
                if c.resolution_status == "resolved"
            )
            parts.append(
                f"Found {resolved} resolved similar issues in past conversations"
            )

        if tool_results.web_resources:
            official = sum(
                1
                for r in tool_results.web_resources
                if (getattr(r, "source_domain", None) or "").lower().find("mailbird") != -1
            )
            parts.append(
                f"Found {len(tool_results.web_resources)} web resources "
                f"({official} from official sources)"
            )

        summary = ". ".join(parts) if parts else "No additional context found"

        # Add cache status
        if tool_results.cache_hit:
            summary += " (cached)"
        else:
            summary += f" (search took {tool_results.execution_time_ms}ms)"

        return summary

    def _extract_tool_evidence(self, tool_results: ToolResults) -> List[str]:
        """Extract key evidence from tool results."""
        evidence = []

        # Add top KB article
        if tool_results.kb_articles:
            top_article = tool_results.kb_articles[0]
            evidence.append(
                f"KB: {top_article.title} (relevance: {top_article.relevance_score:.0%})"
            )

        # Add top FeedMe conversation
        if tool_results.feedme_conversations:
            top_conv = tool_results.feedme_conversations[0]
            evidence.append(
                f"Similar issue: {top_conv.title} - {top_conv.resolution_status}"
            )

        # Add top web resource
        if tool_results.web_resources:
            top_resource = tool_results.web_resources[0]
            evidence.append(
                f"Web: {top_resource.title} from {getattr(top_resource, 'source_domain', 'unknown source')}"
            )

        return evidence[:5]  # Limit to 5 pieces of evidence

    def _format_tool_resources(self, tool_results: ToolResults) -> str:
        """Format tool resources section for user response."""
        resource_parts = ["**📚 Helpful Resources:**"]

        # Add KB articles
        if tool_results.kb_articles:
            resource_parts.append("\n*Knowledge Base Articles:*")
            for article in tool_results.kb_articles[:2]:
                resource_parts.append(
                    f"• [{article.title}]({article.url}) - "
                    f"Relevance: {article.relevance_score:.0%}"
                )

        # Add resolved conversations
        if tool_results.feedme_conversations:
            resolved = [
                c for c in tool_results.feedme_conversations
                if c.resolution_status == "resolved"
            ][:2]

            if resolved:
                resource_parts.append("\n*Previously Resolved Similar Issues:*")
                for conv in resolved:
                    # Ensure resolution is not None
                    resolution_text = conv.resolution or "Resolution details not available"
                    if len(resolution_text) > 100:
                        resource_parts.append(
                            f"• {conv.title} - "
                            f"Resolution: {resolution_text[:100]}..."
                        )
                    else:
                        resource_parts.append(
                            f"• {conv.title} - Resolution: {resolution_text}"
                        )

        # Add web resources
        if tool_results.web_resources:
            resource_parts.append("\n*Additional Resources:*")
            for resource in tool_results.web_resources[:2]:
                domain = getattr(resource, "source_domain", None)
                domain_lower = domain.lower() if domain else ""
                if domain_lower and "mailbird" in domain_lower:
                    resource_parts.append(
                        f"• [Official: {resource.title}]({resource.url})"
                    )
                else:
                    resource_parts.append(
                        f"• [{resource.title}]({resource.url}) "
                        f"from {domain or 'unknown source'}"
                    )

        return "\n".join(resource_parts) if len(resource_parts) > 1 else ""
