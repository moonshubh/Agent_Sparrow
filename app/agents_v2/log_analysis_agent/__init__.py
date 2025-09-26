"""
Agent Sparrow Log Analysis Engine

Comprehensive log analysis system for Mailbird application logs
with advanced pattern recognition and empathetic user communication.
"""

# Import both simplified and comprehensive implementations
from .agent import run_log_analysis_agent
from .comprehensive_agent import LogAnalysisAgent
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

__all__ = [
    # Simplified implementation
    "run_log_analysis_agent",
    "SimplifiedLogAnalysisOutput",
    "SimplifiedAgentState",
    "LogSection",
    "SimplifiedIssue",
    "SimplifiedSolution",
    "SimplifiedLogAnalysisRequest",
    # Comprehensive implementation
    "LogAnalysisAgent",
    "LogEntry",
    "LogMetadata",
    "LogAnalysisResult",
    "RootCause",
    "ErrorPattern",
    "Severity",
    "UserContext",
    "PerformanceMetrics",
]

__version__ = "1.0.0"