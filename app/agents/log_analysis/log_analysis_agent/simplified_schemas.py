"""
Simplified schemas for the question-driven log analysis agent.
Designed for AI SDK integration with focused, direct responses.
"""

from typing import List, Optional, Literal
from pydantic import BaseModel, Field, field_validator
from datetime import datetime


class LogSection(BaseModel):
    """Represents a relevant section extracted from the log."""

    line_numbers: str = Field(description="Line numbers range (e.g., '145-167')")
    content: str = Field(description="The actual log content")
    relevance_score: float = Field(
        description="How relevant this section is to the question", ge=0.0, le=1.0
    )

    @field_validator("line_numbers")
    @classmethod
    def validate_line_numbers(cls, v: str) -> str:
        """Validate line number format."""
        if not v or "-" not in v:
            raise ValueError("Line numbers must be in format 'start-end'")
        return v


class SimplifiedIssue(BaseModel):
    """Simplified issue representation focused on the user's question."""

    title: str = Field(description="Brief issue title", min_length=1)
    details: str = Field(description="Issue details relevant to the question")
    severity: Literal["Critical", "High", "Medium", "Low"] = Field(
        default="Medium", description="Issue severity level"
    )


class SimplifiedSolution(BaseModel):
    """Direct solution addressing the user's question."""

    title: str = Field(description="Solution title", min_length=1)
    steps: List[str] = Field(
        description="Action steps to resolve the issue", min_length=1
    )
    expected_outcome: str = Field(
        default="Issue will be resolved",
        description="What will happen after applying this solution",
    )


class SimplifiedLogAnalysisRequest(BaseModel):
    """Request schema with question support."""

    content: str = Field(description="The log file content to analyze")
    question: Optional[str] = Field(
        default=None, description="Specific question about the logs"
    )
    trace_id: Optional[str] = Field(
        default=None, description="Trace ID for request tracking"
    )


class SimplifiedLogAnalysisOutput(BaseModel):
    """
    Simplified output focused on answering specific questions.
    Maintains backward compatibility with AI SDK expectations.
    """

    # Core response to user's question
    overall_summary: str = Field(
        description="Direct answer to the user's question or executive summary"
    )

    # Backward compatibility fields for AI SDK
    health_status: str = Field(default="Analyzed", description="System health status")
    priority_concerns: List[str] = Field(
        default_factory=list, description="Key concerns from the logs"
    )
    identified_issues: List[SimplifiedIssue] = Field(
        default_factory=list, description="Issues found"
    )
    proposed_solutions: List[SimplifiedSolution] = Field(
        default_factory=list, description="Solutions"
    )

    # Question-driven fields
    question: Optional[str] = Field(
        default=None, description="The question that was answered"
    )
    relevant_log_sections: Optional[List[LogSection]] = Field(
        default=None, description="Log sections relevant to the question"
    )
    confidence_level: float = Field(
        default=0.8, description="Confidence in the analysis (0-1)"
    )

    # Metadata
    analysis_timestamp: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat()
    )
    trace_id: Optional[str] = Field(default=None, description="Request trace ID")
    analysis_method: str = Field(
        default="simplified", description="Analysis method used"
    )


class SimplifiedAgentState(BaseModel):
    """Simplified state for the log analysis agent."""

    raw_log_content: str
    question: Optional[str] = None
    trace_id: Optional[str] = None
    final_report: Optional[SimplifiedLogAnalysisOutput] = None
