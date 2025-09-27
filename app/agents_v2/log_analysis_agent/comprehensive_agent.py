"""
Comprehensive Log Analysis Agent for Mailbird

This module implements the main agent that orchestrates all components
for intelligent log analysis with empathetic user communication.
"""

import logging
import re
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple, Union
from pathlib import Path
import hashlib
from uuid import uuid4

from app.providers.registry import load_model
from app.agents_v2.primary_agent.reasoning.schemas import ReasoningConfig

from .schemas.log_schemas import (
    LogEntry,
    LogMetadata,
    LogAnalysisResult,
    ErrorPattern,
    RootCause,
    PerformanceMetrics,
    UserContext,
    Severity,
)
from .extractors.metadata_extractor import MetadataExtractor
from .extractors.pattern_analyzer import PatternAnalyzer
from .reasoning.log_reasoning_engine import LogReasoningEngine
from .reasoning.root_cause_classifier import RootCauseClassifier
from .context.context_ingestor import ContextIngestor
from .formatters.response_formatter import LogResponseFormatter, FormattingConfig
from app.agents_v2.primary_agent.prompts.emotion_templates import EmotionalState

logger = logging.getLogger(__name__)


class LogAnalysisAgent:
    """
    Comprehensive agent for analyzing Mailbird logs.

    This agent orchestrates:
    - Log parsing and entry extraction
    - Metadata extraction
    - Pattern analysis
    - Root cause classification
    - User context integration
    - Emotional intelligence
    - Response generation
    """

    def __init__(
        self,
        provider: str = "google",
        model_name: str = "gemini-2.5-pro",
        api_key: Optional[str] = None,
        config: Optional[ReasoningConfig] = None,
    ):
        """
        Initialize the log analysis agent.

        Args:
            provider: Model provider (default: google)
            model_name: Model to use (default: gemini-2.5-pro)
            api_key: Optional API key
            config: Optional reasoning configuration
        """
        self.provider = provider
        self.model_name = model_name
        self.api_key = api_key
        self.config = config or ReasoningConfig(
            enable_chain_of_thought=True,
            enable_problem_solving_framework=True,
            enable_tool_intelligence=False,  # Not needed for log analysis
            enable_self_critique=True,
            enable_quality_assessment=True,
            enable_reasoning_transparency=True,
            quality_score_threshold=0.7,
            escalation_threshold=0.4,
        )

        # Initialize components
        self.metadata_extractor = MetadataExtractor()
        self.pattern_analyzer = PatternAnalyzer()
        self.root_cause_classifier = RootCauseClassifier()
        self.context_ingestor = ContextIngestor()

        # Initialize response formatter with config
        formatter_config = FormattingConfig(
            enable_quality_check=True,
            min_quality_score=self.config.quality_score_threshold
        )
        self.response_formatter = LogResponseFormatter(formatter_config)

        # Model and reasoning engine will be initialized on first use
        self._model = None
        self._reasoning_engine = None

        # Cache for analysis results
        self._analysis_cache: Dict[str, LogAnalysisResult] = {}

    async def _initialize_model(self):
        """Initialize the model and reasoning engine if not already done."""
        if self._model is None:
            self._model = await load_model(
                provider=self.provider,
                model=self.model_name,
                api_key=self.api_key,
            )

        if self._reasoning_engine is None:
            self._reasoning_engine = LogReasoningEngine(
                model=self._model,
                config=self.config,
                provider=self.provider,
                model_name=self.model_name,
            )

    async def analyze_log_file(
        self,
        log_file_path: Union[str, Path],
        user_query: Optional[str] = None,
        user_context_input: Optional[str] = None,
        use_cache: bool = True,
    ) -> Tuple[LogAnalysisResult, str]:
        """
        Analyze a log file and generate a user-friendly response.

        Args:
            log_file_path: Path to the log file
            user_query: Optional specific query about the logs
            user_context_input: Optional user description of the issue
            use_cache: Whether to use cached results

        Returns:
            Tuple of (analysis_result, user_response)
        """
        log_file_path = Path(log_file_path)

        # Check cache
        cache_key = self._generate_cache_key(log_file_path, user_query, user_context_input)
        if use_cache and cache_key in self._analysis_cache:
            logger.info(f"Using cached analysis for {log_file_path}")
            cached_result = self._analysis_cache[cache_key]
            _, response = await self._generate_response(
                cached_result, user_query, user_context_input
            )
            return cached_result, response

        # Read log file
        log_content = await self._read_log_file(log_file_path)

        # Analyze logs
        analysis_result = await self.analyze_log_content(
            log_content, user_query, user_context_input
        )

        # Cache result
        if use_cache:
            self._analysis_cache[cache_key] = analysis_result

        # Generate response
        _, response = await self._generate_response(
            analysis_result, user_query, user_context_input
        )

        return analysis_result, response

    async def analyze_log_content(
        self,
        log_content: str,
        user_query: Optional[str] = None,
        user_context_input: Optional[str] = None,
    ) -> LogAnalysisResult:
        """
        Analyze raw log content.

        Args:
            log_content: Raw log text
            user_query: Optional specific query
            user_context_input: Optional user context

        Returns:
            Complete analysis result
        """
        # Initialize model if needed
        await self._initialize_model()

        # Parse log entries
        log_entries = self._parse_log_entries(log_content)

        # Extract metadata
        metadata = self.metadata_extractor.extract_from_entries(log_entries)

        # Also extract from raw text for additional context
        metadata_from_text = self.metadata_extractor.extract_from_text(log_content)
        metadata = self._merge_metadata(metadata, metadata_from_text)

        # Analyze patterns
        error_patterns = self.pattern_analyzer.analyze_entries(log_entries)

        # Detect cascading failures
        cascades = self.pattern_analyzer.detect_cascading_failures(log_entries)

        # Process user context
        user_context = None
        if user_context_input:
            user_context = self.context_ingestor.ingest_user_input(user_context_input)

            # Enhance with log correlation
            if log_entries:
                timestamp_range = (
                    min(e.timestamp for e in log_entries),
                    max(e.timestamp for e in log_entries),
                )
                user_context = self.context_ingestor.enhance_with_log_correlation(
                    user_context, timestamp_range
                )

        # Classify root causes
        root_causes = self.root_cause_classifier.classify(
            error_patterns, metadata, user_context
        )

        # Extract performance metrics
        performance_metrics = self._extract_performance_metrics(log_entries)

        # Generate recommendations
        recommendations = self._generate_recommendations(
            root_causes, error_patterns, metadata, performance_metrics
        )

        # Build analysis result
        analysis_result = LogAnalysisResult(
            analysis_id=self._generate_analysis_id(),
            timestamp=datetime.now(),
            metadata=metadata,
            error_patterns=error_patterns,
            root_causes=root_causes,
            performance_metrics=performance_metrics,
            user_context=user_context,
            recommendations=recommendations,
            executive_summary="",  # Will be generated next
            technical_details="",  # Will be generated next
            confidence_score=self._calculate_overall_confidence(
                root_causes, error_patterns
            ),
            requires_escalation=self._check_escalation_needed(
                root_causes, error_patterns, metadata
            ),
            escalation_reason="",
            affected_functionality=self._identify_affected_functionality(
                error_patterns, root_causes
            ),
            data_integrity_risk=self._assess_data_risk(root_causes, error_patterns),
            estimated_resolution_time=self._estimate_total_resolution_time(root_causes),
        )

        # Generate summaries
        analysis_result.executive_summary = self._generate_executive_summary(
            analysis_result
        )
        analysis_result.technical_details = self._generate_technical_details(
            analysis_result, cascades
        )

        # Set escalation reason if needed
        if analysis_result.requires_escalation:
            analysis_result.escalation_reason = self._generate_escalation_reason(
                analysis_result
            )

        return analysis_result

    def _parse_log_entries(self, log_content: str) -> List[LogEntry]:
        """Parse raw log content into structured entries."""
        entries = []
        lines = log_content.split("\n")

        # Common log patterns
        patterns = [
            # ISO timestamp pattern
            re.compile(
                r"^(\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?)\s+"
                r"\[?(\w+)\]?\s+\[([^\]]+)\]\s*(.+)$"
            ),
            # Simple timestamp pattern
            re.compile(
                r"^(\d{2}:\d{2}:\d{2}(?:\.\d+)?)\s+\[?(\w+)\]?\s+([^\s]+)\s+(.+)$"
            ),
            # Bracketed format
            re.compile(r"^\[([^\]]+)\]\s+\[(\w+)\]\s+\[([^\]]+)\]\s*(.+)$"),
        ]

        current_entry: Optional[LogEntry] = None

        for line_num, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped:
                if current_entry:
                    current_entry.raw_text = f"{current_entry.raw_text}\n"
                continue

            entry: Optional[LogEntry] = None
            for pattern in patterns:
                match = pattern.match(line)
                if match:
                    try:
                        timestamp_str = match.group(1)
                        severity_str = match.group(2)
                        component = match.group(3)
                        message = match.group(4)

                        # Parse timestamp
                        timestamp = self._parse_timestamp(timestamp_str)

                        # Parse severity
                        severity = self._parse_severity(severity_str)

                        entry = LogEntry(
                            timestamp=timestamp,
                            severity=severity,
                            component=component,
                            message=message,
                            raw_text=line,
                            line_number=line_num,
                        )
                        current_entry = entry
                        break
                    except Exception as e:
                        logger.debug(f"Failed to parse line {line_num}: {e}")
                        continue

            # If no pattern matched, create a generic entry
            if not entry:
                if current_entry:
                    # Treat as continuation of previous entry (e.g. stack trace)
                    current_entry.message = f"{current_entry.message}\n{line}"
                    current_entry.raw_text = f"{current_entry.raw_text}\n{line}"
                    continue

                entry = LogEntry(
                    timestamp=datetime.now(),
                    severity=Severity.INFO,
                    component="unknown",
                    message=stripped,
                    raw_text=line,
                    line_number=line_num,
                )
                current_entry = entry

            if entry:
                entries.append(entry)

        return entries

    def _parse_timestamp(self, timestamp_str: str) -> datetime:
        """Parse various timestamp formats."""
        cleaned = timestamp_str.strip()
        if not cleaned:
            return datetime.now()

        # Normalize to ISO format when possible
        normalized = cleaned
        if normalized.endswith("Z"):
            normalized = f"{normalized[:-1]}+00:00"

        if "T" not in normalized and " " in normalized:
            date_part, time_part = normalized.split(" ", 1)
            normalized = f"{date_part}T{time_part}"

        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            # Handle offsets without colon (e.g. +0000)
            tz_match = re.match(r"(.*)([+-]\d{2})(\d{2})$", normalized)
            if tz_match:
                base, hours, minutes = tz_match.groups()
                try:
                    return datetime.fromisoformat(f"{base}{hours}:{minutes}")
                except ValueError:
                    pass

        # Try common fallback formats
        formats = [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M:%S.%f",
            "%H:%M:%S",
            "%H:%M:%S.%f",
        ]

        for fmt in formats:
            try:
                if fmt.startswith("%H"):  # Time only, use today's date
                    time_part = datetime.strptime(cleaned, fmt)
                    now = datetime.now()
                    return now.replace(
                        hour=time_part.hour,
                        minute=time_part.minute,
                        second=time_part.second,
                        microsecond=time_part.microsecond if "%f" in fmt else 0,
                    )
                return datetime.strptime(cleaned, fmt)
            except ValueError:
                continue

        # Fallback to current time
        return datetime.now()

    def _parse_severity(self, severity_str: str) -> Severity:
        """Parse severity level from string."""
        try:
            return Severity.from_string(severity_str)
        except ValueError:
            # Default to INFO for unknown severities
            return Severity.INFO

    def _merge_metadata(
        self, primary: LogMetadata, secondary: LogMetadata
    ) -> LogMetadata:
        """Merge two metadata objects, preferring non-default values."""
        # Prefer non-default values from secondary
        if secondary.mailbird_version != "Unknown":
            primary.mailbird_version = secondary.mailbird_version
        if secondary.build_number:
            primary.build_number = secondary.build_number
        if secondary.os_version != "Unknown":
            primary.os_version = secondary.os_version
        if secondary.database_size_mb:
            primary.database_size_mb = secondary.database_size_mb
        if secondary.account_providers:
            primary.account_providers.extend(secondary.account_providers)
            primary.account_providers = list(set(primary.account_providers))

        return primary

    def _extract_performance_metrics(self, entries: List[LogEntry]) -> PerformanceMetrics:
        """Extract performance-related metrics from log entries."""
        metrics = PerformanceMetrics()

        response_times = []
        memory_peaks = []
        cpu_peaks = []

        for entry in entries:
            message_lower = entry.message.lower()

            # Extract response times
            response_match = re.search(r"response time[:\s]+(\d+)ms", message_lower)
            if response_match:
                response_times.append(float(response_match.group(1)))

            # Extract memory usage
            memory_match = re.search(r"memory[:\s]+(\d+)mb", message_lower)
            if memory_match:
                memory_mb = float(memory_match.group(1))
                if memory_mb > 500:  # Consider peaks above 500MB
                    memory_peaks.append((entry.timestamp, memory_mb))

            # Extract CPU usage
            cpu_match = re.search(r"cpu[:\s]+(\d+)%", message_lower)
            if cpu_match:
                cpu_percent = float(cpu_match.group(1))
                if cpu_percent > 70:  # Consider peaks above 70%
                    cpu_peaks.append((entry.timestamp, cpu_percent))

            # Count slow queries
            if "slow query" in message_lower or "query took" in message_lower:
                metrics.slow_queries += 1

            # Count UI freezes
            if "ui freeze" in message_lower or "not responding" in message_lower:
                metrics.ui_freezes += 1

            # Count crashes
            if "crash" in message_lower or "fatal error" in message_lower:
                metrics.crash_events += 1

        # Calculate averages
        if response_times:
            metrics.avg_response_time_ms = sum(response_times) / len(response_times)
            metrics.max_response_time_ms = max(response_times)

        metrics.memory_peaks = memory_peaks[:10]  # Keep top 10
        metrics.cpu_peaks = cpu_peaks[:10]  # Keep top 10

        return metrics

    def _generate_recommendations(
        self,
        root_causes: List[RootCause],
        patterns: List[ErrorPattern],
        metadata: LogMetadata,
        performance: PerformanceMetrics,
    ) -> List[str]:
        """Generate actionable recommendations."""
        recommendations = []

        # Root cause based recommendations
        for cause in root_causes[:2]:  # Top 2 causes
            if cause.resolution_steps:
                recommendations.append(
                    f"For {cause.title}: {cause.resolution_steps[0]}"
                )

        # Pattern based recommendations
        auth_patterns = [p for p in patterns if p.category == "AUTHENTICATION"]
        if auth_patterns:
            recommendations.append(
                "Multiple authentication errors detected - verify email account credentials"
            )

        # Metadata based recommendations
        if metadata.database_size_mb and metadata.database_size_mb > 2000:
            recommendations.append(
                "Large database detected - consider archiving old emails"
            )

        if metadata.error_rate > 20:
            recommendations.append(
                "High error rate - consider updating to the latest Mailbird version"
            )

        # Performance based recommendations
        if performance.has_performance_issues:
            recommendations.append(
                "Performance issues detected - restart Mailbird and clear cache"
            )

        return recommendations[:5]  # Limit to 5 recommendations

    def _calculate_overall_confidence(
        self, root_causes: List[RootCause], patterns: List[ErrorPattern]
    ) -> float:
        """Calculate overall confidence in the analysis."""
        if not root_causes and not patterns:
            return 0.3

        confidences = []

        # Add root cause confidences
        for cause in root_causes[:3]:
            confidences.append(cause.confidence_score)

        # Add pattern confidences
        for pattern in patterns[:3]:
            confidences.append(pattern.confidence)

        if not confidences:
            return 0.5

        # Weighted average with emphasis on top items
        weights = [1.0, 0.8, 0.6, 0.4, 0.2, 0.1]
        weighted_sum = sum(
            c * w for c, w in zip(confidences, weights[: len(confidences)])
        )
        weight_sum = sum(weights[: len(confidences)])

        return min(weighted_sum / weight_sum, 1.0)

    def _check_escalation_needed(
        self,
        root_causes: List[RootCause],
        patterns: List[ErrorPattern],
        metadata: LogMetadata,
    ) -> bool:
        """Check if the issue requires escalation to support."""
        # Check for critical root causes
        if any(c.requires_support for c in root_causes):
            return True

        # Check for data integrity issues
        if any(c.category.name == "DATABASE" and c.impact.value == "critical" for c in root_causes):
            return True

        # Check for excessive errors
        if metadata.error_rate > 30:
            return True

        # Check for pattern frequency
        high_frequency_patterns = [p for p in patterns if p.occurrences > 100]
        if len(high_frequency_patterns) > 3:
            return True

        return False

    def _identify_affected_functionality(
        self, patterns: List[ErrorPattern], root_causes: List[RootCause]
    ) -> List[str]:
        """Identify which Mailbird features are affected."""
        affected = set()

        # From patterns
        for pattern in patterns:
            affected.update(pattern.affected_components)

        # From root causes
        for cause in root_causes:
            affected.update(cause.affected_features)

        return list(affected)

    def _assess_data_risk(
        self, root_causes: List[RootCause], patterns: List[ErrorPattern]
    ) -> bool:
        """Assess if there's risk to user data integrity."""
        # Check for database issues
        database_causes = [c for c in root_causes if c.category.name == "DATABASE"]
        if any(c.impact.value in ["critical", "high"] for c in database_causes):
            return True

        # Check for corruption patterns
        corruption_keywords = ["corrupt", "integrity", "damaged", "invalid"]
        for pattern in patterns:
            if any(keyword in pattern.description.lower() for keyword in corruption_keywords):
                return True

        return False

    def _estimate_total_resolution_time(self, root_causes: List[RootCause]) -> int:
        """Estimate total time to resolve all issues in minutes."""
        if not root_causes:
            return 0

        # Sum up resolution times, with some parallelization factor
        total_time = sum(c.estimated_resolution_time for c in root_causes)

        # Apply parallelization factor (some tasks can be done together)
        if len(root_causes) > 1:
            total_time = int(total_time * 0.7)

        return total_time

    def _generate_executive_summary(self, result: LogAnalysisResult) -> str:
        """Generate executive summary for the analysis."""
        parts = []

        # Opening
        if result.has_critical_issues:
            parts.append(
                "⚠️ Critical issues detected requiring immediate attention."
            )
        elif result.root_causes:
            parts.append(
                f"Analysis identified {len(result.root_causes)} issues affecting Mailbird."
            )
        else:
            parts.append("✅ No significant issues detected in the logs.")

        # Key metrics
        parts.append(
            f"Analyzed {result.metadata.total_entries} log entries with "
            f"{result.metadata.error_count} errors ({result.metadata.error_rate:.1f}% error rate)."
        )

        # Top issue
        if result.top_priority_cause:
            parts.append(
                f"Primary issue: {result.top_priority_cause.title} "
                f"(Impact: {result.top_priority_cause.impact.value})."
            )

        # Resolution time
        if result.estimated_resolution_time > 0:
            parts.append(
                f"Estimated resolution time: {result.estimated_resolution_time} minutes."
            )

        return " ".join(parts)

    def _generate_technical_details(
        self, result: LogAnalysisResult, cascades: List[Tuple[LogEntry, List[LogEntry]]]
    ) -> str:
        """Generate technical details section."""
        parts = []

        # System information
        parts.append("System Information:")
        parts.append(f"- Mailbird Version: {result.metadata.mailbird_version}")
        parts.append(f"- OS: {result.metadata.os_version}")
        parts.append(f"- Accounts: {result.metadata.account_count}")
        if result.metadata.database_size_mb:
            parts.append(f"- Database Size: {result.metadata.database_size_mb:.0f} MB")

        # Error patterns
        if result.error_patterns:
            parts.append(f"\nError Patterns ({len(result.error_patterns)} detected):")
            for pattern in result.error_patterns[:3]:
                parts.append(
                    f"- {pattern.description} ({pattern.occurrences}x, "
                    f"{pattern.frequency:.1f}/min)"
                )

        # Cascading failures
        if cascades:
            parts.append(f"\nCascading Failures ({len(cascades)} detected)")

        # Performance metrics
        if result.performance_metrics.has_performance_issues:
            parts.append("\nPerformance Issues:")
            if result.performance_metrics.avg_response_time_ms:
                parts.append(
                    f"- Avg Response Time: {result.performance_metrics.avg_response_time_ms:.0f}ms"
                )
            if result.performance_metrics.ui_freezes:
                parts.append(f"- UI Freezes: {result.performance_metrics.ui_freezes}")

        return "\n".join(parts)

    def _generate_escalation_reason(self, result: LogAnalysisResult) -> str:
        """Generate reason for escalation."""
        reasons = []

        if result.data_integrity_risk:
            reasons.append("Data integrity risk detected")

        critical_causes = [c for c in result.root_causes if c.requires_support]
        if critical_causes:
            reasons.append(f"{len(critical_causes)} issues require support intervention")

        if result.metadata.error_rate > 30:
            reasons.append(f"Excessive error rate ({result.metadata.error_rate:.1f}%)")

        return ". ".join(reasons) if reasons else "Complex issue requiring expert analysis"

    async def _generate_response(
        self,
        analysis_result: LogAnalysisResult,
        user_query: Optional[str],
        user_context_input: Optional[str],
    ) -> Tuple[Any, str]:
        """Generate user-friendly response using the reasoning engine and formatter."""
        # Reuse enriched user context when available
        user_context = analysis_result.user_context
        if user_context is None and user_context_input:
            user_context = self.context_ingestor.ingest_user_input(user_context_input)

        # Use reasoning engine for analysis and tool gathering
        reasoning_state, initial_response = await self._reasoning_engine.analyze_logs_with_reasoning(
            analysis_result, user_query, user_context
        )

        # Detect emotional state from user context or query
        emotional_state = self._detect_emotional_state(user_context, user_context_input, user_query)

        # Get tool results if available from reasoning engine
        tool_results = None
        if hasattr(self._reasoning_engine, '_tool_results_cache'):
            tool_results = self._reasoning_engine._tool_results_cache.get(analysis_result.analysis_id)

        # Get user name from dedicated field if available
        user_name = getattr(user_context, 'user_name', None) if user_context else None

        # Format the response using the new formatter
        formatted_response, validation_result = await self.response_formatter.format_response(
            analysis=analysis_result,
            emotional_state=emotional_state,
            user_context=user_context,
            tool_results=tool_results,
            attachment_data=None,  # Could be added if attachments are processed
            user_name=user_name
        )

        # Log quality metrics
        if validation_result.score.overall_score < self.config.quality_score_threshold:
            logger.warning(
                f"Response quality below threshold: {validation_result.score.overall_score:.2f} "
                f"for analysis {analysis_result.analysis_id}"
            )

        return reasoning_state, formatted_response

    def _detect_emotional_state(
        self,
        user_context: Optional[UserContext],
        user_input: Optional[str],
        query: Optional[str]
    ) -> EmotionalState:
        """Detect emotional state from user input and context."""
        # Use emotional state from user context if available
        if user_context and hasattr(user_context, 'emotional_state') and user_context.emotional_state:
            # Handle both string and enum types
            if isinstance(user_context.emotional_state, EmotionalState):
                return user_context.emotional_state
            elif isinstance(user_context.emotional_state, str):
                emotion_map = {
                    'frustrated': EmotionalState.FRUSTRATED,
                    'anxious': EmotionalState.ANXIOUS,
                    'confused': EmotionalState.CONFUSED,
                    'professional': EmotionalState.PROFESSIONAL,
                    'urgent': EmotionalState.URGENT,
                    'neutral': EmotionalState.NEUTRAL
                }
                return emotion_map.get(user_context.emotional_state.lower(), EmotionalState.NEUTRAL)

        # Simple keyword detection for emotional state
        combined_text = f"{user_input or ''} {query or ''}".lower()

        if any(word in combined_text for word in ['frustrated', 'annoying', 'broken', 'stupid']):
            return EmotionalState.FRUSTRATED
        elif any(word in combined_text for word in ['urgent', 'asap', 'critical', 'worried']):
            return EmotionalState.ANXIOUS
        elif any(word in combined_text for word in ['confused', "don't understand", 'help me']):
            return EmotionalState.CONFUSED
        elif any(word in combined_text for word in ['kindly', 'please assist', 'regarding']):
            return EmotionalState.PROFESSIONAL
        else:
            return EmotionalState.NEUTRAL

    async def _read_log_file(self, file_path: Path) -> str:
        """Read log file content."""
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        except Exception as e:
            logger.error(f"Failed to read log file {file_path}: {e}")
            raise

    def _generate_cache_key(self, file_path: Path, query: Optional[str], context: Optional[str]) -> str:
        """Generate cache key for analysis results."""
        try:
            resolved_path = str(file_path.resolve())
        except OSError:
            resolved_path = str(file_path)

        key_parts = [resolved_path]

        if file_path.exists():
            try:
                stat_result = file_path.stat()
                key_parts.extend([
                    str(stat_result.st_size),
                    str(stat_result.st_mtime_ns),
                ])
            except OSError:
                pass

        key_parts.extend([query or "", context or ""])
        key_string = "|".join(key_parts)
        return hashlib.md5(key_string.encode()).hexdigest()

    def _generate_analysis_id(self) -> str:
        """Generate unique analysis ID."""
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
        return f"LA-{timestamp}-{uuid4().hex[:6].upper()}"
