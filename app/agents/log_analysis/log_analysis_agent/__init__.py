"""
Agent Sparrow Log Analysis Engine

Comprehensive log analysis system for Mailbird application logs
with advanced pattern recognition and empathetic user communication.

Legacy agent router removed - use unified agent's log_diagnoser_tool instead.
"""

# Import simplified and comprehensive implementations
# Note: Legacy agent.py router removed - use unified agent for routing
# Comprehensive agent temporarily disabled due to reasoning engine dependency
# from .comprehensive_agent import LogAnalysisAgent
from .simplified_schemas import (
    SimplifiedLogAnalysisOutput,
    SimplifiedAgentState,
    LogSection,
    SimplifiedIssue,
    SimplifiedSolution,
    SimplifiedLogAnalysisRequest
)
from .schemas.log_schemas import (
    LogEntry,
    LogMetadata,
    LogAnalysisResult,
    RootCause,
    ErrorPattern,
    Severity,
    UserContext,
    PerformanceMetrics,
)
from .privacy import (
    LogSanitizer,
    RedactionLevel,
    SanitizationConfig,
    LogCleanupManager,
    CleanupConfig,
    AttachmentSanitizer,
)
from .security import (
    SecurityValidator,
    ValidationConfig,
    ValidationResult,
    ValidationStatus,
    ThreatLevel,
    ComplianceManager,
    ComplianceConfig,
    ComplianceReport,
)

__all__ = [
    # Simplified implementation (used by unified agent)
    "SimplifiedLogAnalysisOutput",
    "SimplifiedAgentState",
    "LogSection",
    "SimplifiedIssue",
    "SimplifiedSolution",
    "SimplifiedLogAnalysisRequest",
    # Comprehensive implementation
    # "LogAnalysisAgent",  # Temporarily disabled due to reasoning engine dependency
    "LogEntry",
    "LogMetadata",
    "LogAnalysisResult",
    "RootCause",
    "ErrorPattern",
    "Severity",
    "UserContext",
    "PerformanceMetrics",
    # Security & privacy modules
    "LogSanitizer",
    "RedactionLevel",
    "SanitizationConfig",
    "LogCleanupManager",
    "CleanupConfig",
    "AttachmentSanitizer",
    "SecurityValidator",
    "ValidationConfig",
    "ValidationResult",
    "ValidationStatus",
    "ThreatLevel",
    "ComplianceManager",
    "ComplianceConfig",
    "ComplianceReport",
]

__version__ = "1.0.0"
