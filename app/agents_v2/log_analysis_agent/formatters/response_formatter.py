"""
Log Response Formatter

Main formatter that orchestrates all formatting components to create
comprehensive, empathetic, and user-friendly log analysis responses.
"""

from typing import Dict, Optional, Any, List, Tuple
from dataclasses import dataclass
import logging

from app.agents_v2.primary_agent.prompts.emotion_templates import (
    EmotionalState,
    EmotionTemplates,
)

# Import with fallbacks to support both package and top-level test imports
try:
    from ..schemas.log_schemas import (
        LogAnalysisResult,
        UserContext,
        ErrorPattern,
        RootCause,
        LogEntry,
    )
except ImportError:  # When imported as top-level `formatters.*` in tests
    try:
        from schemas.log_schemas import (
            LogAnalysisResult,
            UserContext,
            ErrorPattern,
            RootCause,
            LogEntry,
        )
    except ImportError:
        from app.agents_v2.log_analysis_agent.schemas.log_schemas import (
            LogAnalysisResult,
            UserContext,
            ErrorPattern,
            RootCause,
            LogEntry,
        )

try:
    from ..tools import ToolResults, ToolStatus
except ImportError:
    try:
        from tools import ToolResults, ToolStatus
    except ImportError:
        from app.agents_v2.log_analysis_agent.tools import ToolResults, ToolStatus

from .markdown_builder import MarkdownBuilder, AlertLevel, TableRow
from .error_formatter import ErrorBlockFormatter, ErrorContext
from .metadata_formatter import MetadataFormatter
from .solution_formatter import SolutionFormatter, Solution, SolutionType, Difficulty
from .natural_language import NaturalLanguageGenerator, ToneProfile

try:
    from ..templates.response_templates import ResponseTemplates, TemplateContext
except ImportError:
    try:
        from templates.response_templates import ResponseTemplates, TemplateContext
    except ImportError:
        from app.agents_v2.log_analysis_agent.templates.response_templates import ResponseTemplates, TemplateContext

try:
    from ..quality.quality_validator import QualityValidator, ValidationResult
except ImportError:
    try:
        from quality.quality_validator import QualityValidator, ValidationResult
    except ImportError:
        from app.agents_v2.log_analysis_agent.quality.quality_validator import QualityValidator, ValidationResult

logger = logging.getLogger(__name__)


@dataclass
class FormattingConfig:
    """Configuration for response formatting"""
    show_metadata: bool = True
    show_error_blocks: bool = True
    show_attachments: bool = True
    show_resources: bool = True
    show_escalation: bool = True
    max_error_samples: int = 3
    max_solutions: int = 5
    enable_quality_check: bool = True
    min_quality_score: float = 0.7


class LogResponseFormatter:
    """
    Main formatter for log analysis responses.

    Orchestrates all formatting components to create comprehensive responses
    following the 10-section structure:
    1. Metadata Overview
    2. Personalized Introduction
    3. Root Cause Summary
    4. Attachment Highlights
    5. Detailed Issue Analysis
    6. Error Highlighting
    7. Solutions & Workarounds
    8. Escalation Note
    9. Resources
    10. Closing
    """

    def __init__(self, config: Optional[FormattingConfig] = None):
        """
        Initialize the response formatter.

        Args:
            config: Formatting configuration
        """
        self.config = config or FormattingConfig()

        # Initialize components
        self.markdown_builder = MarkdownBuilder()
        self.error_formatter = ErrorBlockFormatter()
        self.metadata_formatter = MetadataFormatter()
        self.solution_formatter = SolutionFormatter()
        self.nlg = NaturalLanguageGenerator()
        self.templates = ResponseTemplates()
        self.emotion_templates = EmotionTemplates()
        self.quality_validator = QualityValidator()

    async def format_response(
        self,
        analysis: LogAnalysisResult,
        emotional_state: EmotionalState,
        user_context: Optional[UserContext] = None,
        tool_results: Optional[ToolResults] = None,
        attachment_data: Optional[Dict[str, Any]] = None,
        user_name: Optional[str] = None,
    ) -> Tuple[str, ValidationResult]:
        """
        Format complete log analysis response.

        Args:
            analysis: Log analysis results
            emotional_state: Detected emotional state
            user_context: User context information
            tool_results: Results from tool searches
            attachment_data: Attachment/screenshot data
            user_name: User's name if available

        Returns:
            Tuple of (formatted response, validation result)
        """
        try:
            # Build response sections
            response = self._build_response(
                analysis,
                emotional_state,
                user_context,
                tool_results,
                attachment_data,
                user_name
            )

            # Quality check if enabled
            if self.config.enable_quality_check:
                validation = self.quality_validator.validate_response(
                    response,
                    analysis,
                    emotional_state,
                    user_context.__dict__ if user_context else None
                )

                # Revise if quality is below threshold
                if validation.score.overall_score < self.config.min_quality_score:
                    logger.warning(
                        f"Response quality below threshold: {validation.score.overall_score:.2f}"
                    )
                    # Could trigger revision here if needed
            else:
                # Create dummy passing validation
                try:
                    from ..quality.quality_validator import QualityScore
                except ImportError:
                    try:
                        from quality.quality_validator import QualityScore
                    except ImportError:
                        from app.agents_v2.log_analysis_agent.quality.quality_validator import QualityScore
                validation = ValidationResult(
                    score=QualityScore(overall_score=1.0, passed=True),
                    is_acceptable=True,
                    needs_revision=False
                )

            return response, validation

        except Exception as e:
            logger.error(f"Error formatting response: {e}")
            # Return fallback response
            fallback = self._create_fallback_response(analysis, str(e))
            try:
                from ..quality.quality_validator import QualityScore
            except ImportError:
                try:
                    from quality.quality_validator import QualityScore
                except ImportError:
                    from app.agents_v2.log_analysis_agent.quality.quality_validator import QualityScore
            validation = ValidationResult(
                score=QualityScore(overall_score=0.5, passed=False),
                is_acceptable=False,  # Fallback response is not acceptable
                needs_revision=True,
                warnings=[f"Fallback response due to error: {e}"]
            )
            return fallback, validation

    def _build_response(
        self,
        analysis: LogAnalysisResult,
        emotional_state: EmotionalState,
        user_context: Optional[UserContext],
        tool_results: Optional[ToolResults],
        attachment_data: Optional[Dict[str, Any]],
        user_name: Optional[str],
    ) -> str:
        """Build the complete response following 10-section structure"""
        builder = MarkdownBuilder()

        # Section 1: Metadata Overview (always first)
        if self.config.show_metadata:
            metadata_section = self.metadata_formatter.format_compact_metadata(
                analysis.metadata
            )
            builder.add_raw(metadata_section)
            builder.add_horizontal_rule()

        # Section 2: Personalized Introduction
        greeting = self.nlg.generate_personalized_greeting(
            emotional_state,
            user_name,
            user_context
        )
        builder.add_paragraph(greeting)

        # Executive summary
        summary = self.nlg.generate_summary_statement(
            analysis,
            ToneProfile(0.5, 0.3, 0.7, 0.5)
        )
        builder.add_paragraph(summary)

        # Section 3: Root Cause Summary
        if analysis.root_causes:
            self._add_root_cause_summary(builder, analysis, emotional_state)

        # Section 4: Attachment Highlights (if present)
        if self.config.show_attachments and attachment_data:
            attachment_summary = self.nlg.generate_attachment_summary(
                attachment_data,
                emotional_state
            )
            if attachment_summary:
                builder.add_paragraph(attachment_summary)
                if attachment_data.get("ocr_details"):
                    attachment_section = self.metadata_formatter.format_attachment_info(
                        attachment_data
                    )
                    builder.add_raw(attachment_section)

        # Section 5: Detailed Issue Analysis
        if analysis.error_patterns:
            self._add_detailed_analysis(builder, analysis)

        # Section 6: Error Highlighting
        if self.config.show_error_blocks and analysis.error_patterns:
            self._add_error_highlights(builder, analysis)

        # Section 7: Solutions & Workarounds
        if analysis.root_causes:
            self._add_solutions(builder, analysis, emotional_state)

        # Section 8: Escalation Note (if needed)
        if self.config.show_escalation and analysis.requires_escalation:
            escalation_msg = self.nlg.generate_escalation_message(
                analysis.escalation_reason,
                workaround_available=bool(analysis.recommendations)
            )
            builder.add_raw(escalation_msg)

        # Section 9: Resources
        if self.config.show_resources and tool_results and tool_results.has_results:
            self._add_resources(builder, tool_results, emotional_state)

        # Section 10: Closing
        resolution_status = self._determine_resolution_status(analysis)
        closing = self.nlg.generate_closing_message(
            resolution_status,
            emotional_state,
            user_name
        )
        builder.add_horizontal_rule()
        builder.add_paragraph(closing)

        return builder.build()

    def _add_root_cause_summary(
        self,
        builder: MarkdownBuilder,
        analysis: LogAnalysisResult,
        emotional_state: EmotionalState
    ) -> None:
        """Add root cause summary section"""
        builder.add_header("🎯 Root Cause Identified", 2)

        # Get template introduction
        intro = self.templates.get_root_cause_intro(emotional_state)
        builder.add_paragraph(intro)

        # Add primary root cause
        if analysis.top_priority_cause:
            cause = analysis.top_priority_cause
            explanation = self.nlg.generate_root_cause_explanation(
                cause,
                "intermediate"  # Could be from user_context
            )

            # Add alert box with confidence
            alert_level = self._get_alert_level_for_impact(cause.impact)
            builder.add_alert_box(explanation, alert_level)

            # Add confidence statement
            confidence_statement = self.templates.format_confidence_statement(
                cause.confidence_score,
                emotional_state
            )
            builder.add_paragraph(f"*{confidence_statement}*")

    def _add_detailed_analysis(
        self,
        builder: MarkdownBuilder,
        analysis: LogAnalysisResult
    ) -> None:
        """Add detailed issue analysis section"""
        builder.add_header("📊 Detailed Analysis", 2)

        # Create summary table
        headers = ["Issue Type", "Occurrences", "Impact", "First Seen"]
        rows = []

        for pattern in analysis.error_patterns[:5]:  # Top 5 patterns
            rows.append(TableRow([
                pattern.category.name.replace("_", " ").title(),
                str(pattern.occurrences),
                self._get_impact_label(pattern),
                pattern.first_seen.strftime("%H:%M:%S")
            ]))

        if rows:
            builder.add_table(headers, rows)

        # Add performance metrics if available
        if analysis.performance_metrics.has_performance_issues:
            perf_section = self.metadata_formatter.format_performance_metrics(
                analysis.performance_metrics
            )
            builder.add_raw(perf_section)

    def _add_error_highlights(
        self,
        builder: MarkdownBuilder,
        analysis: LogAnalysisResult
    ) -> None:
        """Add error highlighting section"""
        builder.add_header("🔍 Error Details", 2)

        # Show top error patterns with samples
        shown_patterns = 0
        for pattern in analysis.error_patterns:
            if shown_patterns >= self.config.max_error_samples:
                break

            if pattern.sample_entries:
                # Format the error pattern
                formatted_pattern = self.error_formatter.format_error_pattern(pattern)
                builder.add_raw(formatted_pattern)
                shown_patterns += 1

    def _add_solutions(
        self,
        builder: MarkdownBuilder,
        analysis: LogAnalysisResult,
        emotional_state: EmotionalState
    ) -> None:
        """Add solutions and workarounds section"""
        # Get solution introduction
        intro = self.templates.get_solution_intro(emotional_state)
        builder.add_header("🔧 Solutions", 2)
        builder.add_paragraph(intro)

        # Format solutions for each root cause
        for i, cause in enumerate(analysis.root_causes[:self.config.max_solutions], 1):
            if i > 1:
                builder.add_horizontal_rule()

            solution_text = self.solution_formatter.format_root_cause_solutions(cause)
            builder.add_raw(solution_text)

            # Add time estimate
            if cause.estimated_resolution_time:
                time_text = self.templates.format_time_estimate(
                    cause.estimated_resolution_time,
                    emotional_state
                )
                builder.add_paragraph(f"*{time_text}*")

    def _add_resources(
        self,
        builder: MarkdownBuilder,
        tool_results: ToolResults,
        emotional_state: EmotionalState
    ) -> None:
        """Add resources section from tool results"""
        builder.add_header("📚 Helpful Resources", 2)

        # Detail tool execution status so support agents understand coverage
        if tool_results.tool_statuses:
            status_parts = []
            for tool, status in tool_results.tool_statuses.items():
                label = tool.replace("_", " ").title()
                icon = {
                    ToolStatus.SUCCESS: "✅",
                    ToolStatus.CACHED: "♻️",
                    ToolStatus.TIMEOUT: "⏳",
                    ToolStatus.FAILED: "⚠️",
                }.get(status, "ℹ️")
                status_parts.append(f"{icon} {label}: {status.value}")

            builder.add_paragraph(" | ".join(status_parts))

        # Get resource introduction
        intro = self.templates.get_resource_intro(emotional_state)
        builder.add_paragraph(intro)

        # Add KB articles
        if tool_results.kb_articles:
            builder.add_paragraph("**Knowledge Base Articles:**")
            for article in tool_results.kb_articles[:3]:
                link = self._format_link(article.title, article.url)
                meta_parts: List[str] = []
                if article.relevance_score:
                    meta_parts.append(f"{article.relevance_score:.0%} match")
                if article.categories:
                    meta_parts.append(", ".join(article.categories[:2]))
                meta_suffix = f" — {' • '.join(meta_parts)}" if meta_parts else ""
                builder.add_raw(f"- {link}{meta_suffix}")
            builder.add_raw("")

        # Add FeedMe results
        if tool_results.feedme_conversations:
            builder.add_paragraph("**Community Solutions:**")
            for conv in tool_results.feedme_conversations[:3]:
                title = conv.title or f"Conversation {conv.conversation_id}"
                summary = conv.summary or conv.resolution or "Resolution details provided"
                confidence = f"{conv.confidence_score:.0%} match" if conv.confidence_score else ""
                status = conv.resolution_status.title() if conv.resolution_status else ""
                details = " • ".join(filter(None, [status, confidence]))
                summary_text = self._escape_inline(self._truncate_text(summary, 200))
                builder.add_raw(
                    f"- {self._escape_inline(title)} — {summary_text}" \
                    f"{(' (' + self._escape_inline(details) + ')') if details else ''}"
                )
            builder.add_raw("")

        # Add web search results
        if tool_results.web_resources:
            builder.add_paragraph("**Additional Resources:**")
            for resource in tool_results.web_resources[:3]:
                link = self._format_link(resource.title, resource.url)
                domain = self._escape_inline(resource.source_domain or "External")
                relevance = (
                    f"{resource.relevance_score:.0%} match" if resource.relevance_score else None
                )
                meta_suffix = " • ".join(
                    filter(None, [domain, self._escape_inline(relevance) if relevance else None])
                )
                builder.add_raw(f"- {link}{(' — ' + meta_suffix) if meta_suffix else ''}")
            builder.add_raw("")

    def _escape_inline(self, text: str) -> str:
        """Escape text for inline usage without relying on private builder APIs."""
        replacements = {
            "[": r"\\[",
            "]": r"\\]",
            "(": r"\\(",
            ")": r"\\)",
            "*": r"\\*",
            "_": r"\\_",
            "`": r"\\`",
        }
        escaped = text or ""
        for char, replacement in replacements.items():
            escaped = escaped.replace(char, replacement)
        return escaped

    def _format_link(self, text: str, url: str) -> str:
        """Create a markdown link while reusing the markdown builder's escaping"""
        safe_text = text or "Resource"
        if not url:
            return self._escape_inline(safe_text)

        temp_builder = MarkdownBuilder()
        temp_builder.add_link(safe_text, url)
        return temp_builder.build().strip()

    def _truncate_text(self, text: str, max_length: int) -> str:
        """Truncate long text for compact resource listings"""
        if not text or len(text) <= max_length:
            return text
        return text[: max_length - 3] + "..."

    def _determine_resolution_status(self, analysis: LogAnalysisResult) -> str:
        """Determine resolution status for closing message"""
        if not analysis.root_causes:
            return "partial"  # No root causes found means partial resolution
        elif analysis.requires_escalation:
            return "escalated"
        elif all(c.confidence_score > 0.7 for c in analysis.root_causes):
            return "success"
        else:
            return "partial"

    def _get_alert_level_for_impact(self, impact) -> AlertLevel:
        """Convert impact level to alert level"""
        try:
            from ..schemas.log_schemas import IssueImpact
        except ImportError:
            try:
                from schemas.log_schemas import IssueImpact
            except ImportError:
                from app.agents_v2.log_analysis_agent.schemas.log_schemas import IssueImpact
        mapping = {
            IssueImpact.CRITICAL: AlertLevel.CRITICAL,
            IssueImpact.HIGH: AlertLevel.ERROR,
            IssueImpact.MEDIUM: AlertLevel.WARNING,
            IssueImpact.LOW: AlertLevel.INFO,
            IssueImpact.MINIMAL: AlertLevel.INFO,
        }
        return mapping.get(impact, AlertLevel.INFO)

    def _get_impact_label(self, pattern: ErrorPattern) -> str:
        """Get impact label for error pattern"""
        if pattern.frequency > 10:
            return "High"
        elif pattern.frequency > 5:
            return "Medium"
        else:
            return "Low"

    def _create_fallback_response(self, analysis: LogAnalysisResult, error: str) -> str:
        """Create fallback response when formatting fails"""
        builder = MarkdownBuilder()

        builder.add_header("Log Analysis Results", 1)
        builder.add_alert_box(
            "Note: Simplified response due to formatting issue",
            AlertLevel.WARNING
        )

        # Basic summary
        builder.add_paragraph(analysis.generate_user_summary())

        # Basic metadata
        if analysis.metadata:
            builder.add_paragraph(
                f"**System**: Mailbird {analysis.metadata.mailbird_version} "
                f"on {analysis.metadata.os_version}"
            )
            builder.add_paragraph(
                f"**Errors Found**: {analysis.metadata.error_count} "
                f"({analysis.metadata.error_rate:.1f}% of logs)"
            )

        # Basic root causes
        if analysis.root_causes:
            builder.add_header("Issues Found", 2)
            for cause in analysis.root_causes:
                builder.add_list([
                    f"{cause.title} - {cause.impact.value} impact "
                    f"({cause.confidence_score:.0%} confidence)"
                ])

        # Basic recommendations
        if analysis.recommendations:
            builder.add_header("Recommendations", 2)
            builder.add_list(analysis.recommendations[:5])

        builder.add_horizontal_rule()
        builder.add_paragraph(
            "Please contact support if you need additional assistance. "
            f"Reference: {analysis.analysis_id}"
        )

        return builder.build()

    def format_quick_summary(
        self,
        analysis: LogAnalysisResult,
        max_length: int = 500
    ) -> str:
        """
        Format a quick summary for notifications or previews.

        Args:
            analysis: Log analysis results
            max_length: Maximum character length

        Returns:
            Brief formatted summary
        """
        parts = []

        # Status emoji
        if analysis.has_critical_issues:
            parts.append("🚨 Critical Issues Found")
        elif analysis.root_causes:
            parts.append("⚠️ Issues Detected")
        else:
            parts.append("✅ No Major Issues")

        # Top issue
        if analysis.top_priority_cause:
            parts.append(f"Main issue: {analysis.top_priority_cause.title}")

        # Stats
        parts.append(
            f"Errors: {analysis.metadata.error_count} | "
            f"Version: {analysis.metadata.mailbird_version}"
        )

        # Resolution time
        if analysis.estimated_resolution_time:
            parts.append(f"Fix time: ~{analysis.estimated_resolution_time} min")

        result = " | ".join(parts)
        if len(result) > max_length:
            result = result[:max_length-3] + "..."

        return result
