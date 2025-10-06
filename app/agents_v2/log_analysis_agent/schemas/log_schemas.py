"""
Log Analysis Schemas and Data Models

This module defines the data structures used throughout the log analysis system,
following Pythonic principles with clear type hints and comprehensive docstrings.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Dict, List, Optional, Any, Set, Tuple
from pathlib import Path


class Severity(Enum):
    """Log severity levels in ascending order of importance."""

    TRACE = "trace"
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"
    FATAL = "fatal"

    @classmethod
    def from_string(cls, value: str) -> "Severity":
        """
        Convert string representation to Severity enum.

        Args:
            value: String representation of severity level

        Returns:
            Corresponding Severity enum value

        Raises:
            ValueError: If the string doesn't match any severity level
        """
        normalized = value.upper()
        mapping = {
            "TRACE": cls.TRACE,
            "DEBUG": cls.DEBUG,
            "INFO": cls.INFO,
            "WARN": cls.WARNING,
            "WARNING": cls.WARNING,
            "ERROR": cls.ERROR,
            "CRITICAL": cls.CRITICAL,
            "FATAL": cls.FATAL,
        }

        if normalized not in mapping:
            raise ValueError(f"Unknown severity level: {value}")

        return mapping[normalized]

    @property
    def numeric_value(self) -> int:
        """Get numeric representation for comparison."""
        order = [
            self.TRACE,
            self.DEBUG,
            self.INFO,
            self.WARNING,
            self.ERROR,
            self.CRITICAL,
            self.FATAL,
        ]
        return order.index(self)


class ErrorCategory(Enum):
    """Categories of errors found in logs."""

    AUTHENTICATION = auto()
    SYNCHRONIZATION = auto()
    NETWORK = auto()
    DATABASE = auto()
    CONFIGURATION = auto()
    PERFORMANCE = auto()
    UI_INTERACTION = auto()
    FILE_SYSTEM = auto()
    MEMORY = auto()
    LICENSING = auto()
    UNKNOWN = auto()


class IssueImpact(Enum):
    """Impact level of identified issues."""

    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def numeric_score(self) -> int:
        """Convert to numeric score for comparison."""
        scores = {
            self.MINIMAL: 1,
            self.LOW: 2,
            self.MEDIUM: 3,
            self.HIGH: 4,
            self.CRITICAL: 5,
        }
        return scores[self]


@dataclass
class LogEntry:
    """
    Represents a single log entry with parsed components.

    Attributes:
        timestamp: When the log event occurred
        severity: Log level/severity
        component: System component that generated the log
        message: The log message content
        thread_id: Thread identifier if available
        correlation_id: Correlation ID for tracking related events
        metadata: Additional structured data from the log
        raw_text: Original unparsed log line
        line_number: Line number in the original log file
    """

    timestamp: datetime
    severity: Severity
    component: str
    message: str
    thread_id: Optional[str] = None
    correlation_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    raw_text: str = ""
    line_number: Optional[int] = None

    @property
    def is_error(self) -> bool:
        """Check if this entry represents an error condition."""
        return self.severity.numeric_value >= Severity.ERROR.numeric_value

    def __str__(self) -> str:
        """Human-readable representation."""
        return (
            f"[{self.timestamp.isoformat()}] "
            f"{self.severity.value.upper()}: "
            f"{self.component} - {self.message}"
        )


@dataclass
class ErrorPattern:
    """
    Represents a detected error pattern in the logs.

    Attributes:
        pattern_id: Unique identifier for this pattern
        category: Error category classification
        description: Human-readable description of the pattern
        occurrences: Number of times this pattern appears
        first_seen: Timestamp of first occurrence
        last_seen: Timestamp of most recent occurrence
        affected_components: Set of components exhibiting this pattern
        sample_entries: Example log entries showing this pattern
        confidence: Confidence score for pattern detection (0-1)
        indicators: Specific indicators that identified this pattern
    """

    pattern_id: str
    category: ErrorCategory
    description: str
    occurrences: int
    first_seen: datetime
    last_seen: datetime
    affected_components: Set[str] = field(default_factory=set)
    sample_entries: List[LogEntry] = field(default_factory=list)
    confidence: float = 0.0
    indicators: List[str] = field(default_factory=list)

    @property
    def duration(self) -> float:
        """Calculate duration between first and last occurrence in seconds."""
        return (self.last_seen - self.first_seen).total_seconds()

    @property
    def frequency(self) -> float:
        """Calculate occurrences per minute."""
        duration_minutes = self.duration / 60
        if duration_minutes == 0:
            return float(self.occurrences)
        return self.occurrences / duration_minutes


@dataclass
class LogMetadata:
    """
    Extracted metadata from log files.

    Attributes:
        mailbird_version: Application version string
        build_number: Build identifier
        os_version: Operating system information
        os_architecture: System architecture (x86, x64, ARM)
        database_size_mb: Database file size in megabytes
        account_count: Number of configured email accounts
        account_providers: Email providers (Gmail, Outlook, etc.)
        session_start: When this session started
        session_end: When this session ended (if available)
        total_entries: Total number of log entries
        error_count: Number of error-level entries
        warning_count: Number of warning-level entries
        memory_usage_mb: Average memory usage during session
        cpu_usage_percent: Average CPU usage during session
        network_state: Network connectivity status
        proxy_configured: Whether proxy is configured
        plugins_enabled: List of enabled plugins
    """

    mailbird_version: str
    build_number: Optional[str] = None
    os_version: str = "Unknown"
    os_architecture: str = "x64"
    database_size_mb: Optional[float] = None
    account_count: int = 0
    account_providers: List[str] = field(default_factory=list)
    session_start: Optional[datetime] = None
    session_end: Optional[datetime] = None
    total_entries: int = 0
    error_count: int = 0
    warning_count: int = 0
    memory_usage_mb: Optional[float] = None
    cpu_usage_percent: Optional[float] = None
    network_state: str = "Unknown"
    proxy_configured: bool = False
    plugins_enabled: List[str] = field(default_factory=list)

    @property
    def session_duration_hours(self) -> Optional[float]:
        """Calculate session duration in hours."""
        if self.session_start and self.session_end:
            return (self.session_end - self.session_start).total_seconds() / 3600
        return None

    @property
    def error_rate(self) -> float:
        """Calculate percentage of entries that are errors."""
        if self.total_entries == 0:
            return 0.0
        return (self.error_count / self.total_entries) * 100


@dataclass
class RootCause:
    """
    Identified root cause for issues in the logs.

    Attributes:
        cause_id: Unique identifier
        category: Error category
        title: Brief title of the root cause
        description: Detailed explanation
        confidence_score: Confidence in this diagnosis (0-1)
        evidence: Supporting evidence from logs
        impact: Assessed impact level
        affected_features: Features affected by this issue
        resolution_steps: Ordered steps to resolve
        preventive_measures: Steps to prevent recurrence
        estimated_resolution_time: Estimated minutes to fix
        requires_user_action: Whether user intervention is needed
        requires_support: Whether support team involvement is needed
        related_patterns: Associated error patterns
    """

    cause_id: str
    category: ErrorCategory
    title: str
    description: str
    confidence_score: float
    evidence: List[str] = field(default_factory=list)
    impact: IssueImpact = IssueImpact.MEDIUM
    affected_features: List[str] = field(default_factory=list)
    resolution_steps: List[str] = field(default_factory=list)
    preventive_measures: List[str] = field(default_factory=list)
    estimated_resolution_time: int = 10  # minutes
    requires_user_action: bool = True
    requires_support: bool = False
    related_patterns: List[str] = field(default_factory=list)

    def __str__(self) -> str:
        """Human-readable representation."""
        return (
            f"{self.title} ({self.category.name}) - "
            f"Confidence: {self.confidence_score:.0%}, "
            f"Impact: {self.impact.value}"
        )


@dataclass
class PerformanceMetrics:
    """
    Performance-related metrics extracted from logs.

    Attributes:
        avg_response_time_ms: Average response time in milliseconds
        max_response_time_ms: Maximum response time observed
        slow_queries: Number of database queries exceeding threshold
        memory_peaks: List of memory usage peaks (timestamp, MB)
        cpu_peaks: List of CPU usage peaks (timestamp, percent)
        network_latency_ms: Average network latency
        sync_duration_seconds: Average sync operation duration
        ui_freezes: Number of UI freeze events detected
        crash_events: Number of application crashes
    """

    avg_response_time_ms: Optional[float] = None
    max_response_time_ms: Optional[float] = None
    slow_queries: int = 0
    memory_peaks: List[Tuple[datetime, float]] = field(default_factory=list)
    cpu_peaks: List[Tuple[datetime, float]] = field(default_factory=list)
    network_latency_ms: Optional[float] = None
    sync_duration_seconds: Optional[float] = None
    ui_freezes: int = 0
    crash_events: int = 0

    @property
    def has_performance_issues(self) -> bool:
        """Check if performance issues are present."""
        return (
            self.slow_queries > 10
            or self.ui_freezes > 0
            or self.crash_events > 0
            or (self.avg_response_time_ms and self.avg_response_time_ms > 1000)
        )


@dataclass
class UserContext:
    """
    User-provided context for log analysis.

    Attributes:
        reported_issue: User's description of the problem
        occurrence_time: When user noticed the issue
        affected_accounts: Specific email accounts affected
        recent_changes: Recent system or app changes
        attempted_solutions: Solutions already tried
        business_impact: Impact on user's workflow
        urgency_level: How urgent the resolution is
        technical_proficiency: User's technical skill level
        emotional_state: Detected emotional state from communication
    """

    reported_issue: str
    occurrence_time: Optional[datetime] = None
    affected_accounts: List[str] = field(default_factory=list)
    recent_changes: List[str] = field(default_factory=list)
    attempted_solutions: List[str] = field(default_factory=list)
    business_impact: str = ""
    urgency_level: str = "normal"
    technical_proficiency: str = "intermediate"
    emotional_state: str = "neutral"


@dataclass
class LogAnalysisResult:
    """
    Complete result of log analysis.

    Attributes:
        analysis_id: Unique analysis identifier
        timestamp: When analysis was performed
        metadata: Extracted log metadata
        error_patterns: Detected error patterns
        root_causes: Identified root causes
        performance_metrics: Performance analysis results
        user_context: Integrated user context
        recommendations: Prioritized recommendations
        executive_summary: Brief summary for user
        technical_details: Detailed technical findings
        confidence_score: Overall confidence in analysis
        requires_escalation: Whether to escalate to support
        escalation_reason: Why escalation is needed
        affected_functionality: List of affected features
        data_integrity_risk: Whether data is at risk
        estimated_resolution_time: Total time to resolve all issues
    """

    analysis_id: str
    timestamp: datetime
    metadata: LogMetadata
    error_patterns: List[ErrorPattern] = field(default_factory=list)
    root_causes: List[RootCause] = field(default_factory=list)
    performance_metrics: PerformanceMetrics = field(
        default_factory=PerformanceMetrics
    )
    user_context: Optional[UserContext] = None
    recommendations: List[str] = field(default_factory=list)
    executive_summary: str = ""
    technical_details: str = ""
    confidence_score: float = 0.0
    requires_escalation: bool = False
    escalation_reason: str = ""
    affected_functionality: List[str] = field(default_factory=list)
    data_integrity_risk: bool = False
    estimated_resolution_time: int = 0  # minutes

    @property
    def has_critical_issues(self) -> bool:
        """Check if critical issues are present."""
        return any(
            cause.impact == IssueImpact.CRITICAL for cause in self.root_causes
        ) or self.data_integrity_risk

    @property
    def top_priority_cause(self) -> Optional[RootCause]:
        """Get the highest priority root cause."""
        if not self.root_causes:
            return None

        return max(
            self.root_causes,
            key=lambda c: (c.impact.numeric_score, c.confidence_score),
        )

    def get_patterns_by_category(self, category: ErrorCategory) -> List[ErrorPattern]:
        """Get all error patterns of a specific category."""
        return [p for p in self.error_patterns if p.category == category]

    def generate_user_summary(self) -> str:
        """
        Generate a user-friendly summary of the analysis.

        Returns:
            Formatted summary string suitable for end users
        """
        summary_parts = []

        # Opening based on severity
        if self.has_critical_issues:
            summary_parts.append(
                "I've identified critical issues in your Mailbird logs that need immediate attention."
            )
        elif self.root_causes:
            summary_parts.append(
                "I've analyzed your logs and found the following issues:"
            )
        else:
            summary_parts.append(
                "I've completed the log analysis. Your Mailbird appears to be running normally."
            )

        # Main findings
        if self.root_causes:
            summary_parts.append("\n\nMain Findings:")
            for i, cause in enumerate(self.root_causes[:3], 1):
                summary_parts.append(
                    f"{i}. {cause.title} (Impact: {cause.impact.value})"
                )

        # Recommendations
        if self.recommendations:
            summary_parts.append("\n\nRecommended Actions:")
            for i, rec in enumerate(self.recommendations[:3], 1):
                summary_parts.append(f"{i}. {rec}")

        # Resolution time
        if self.estimated_resolution_time > 0:
            summary_parts.append(
                f"\n\nEstimated time to resolve: {self.estimated_resolution_time} minutes"
            )

        return "\n".join(summary_parts)