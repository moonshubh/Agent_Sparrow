"""
Enhanced schemas for comprehensive log analysis with detailed system profiling and solution generation.
"""

from typing import TypedDict, List, Optional, Any, Dict
from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field
from datetime import datetime


# Enhanced Agent State
class EnhancedLogAnalysisAgentState(TypedDict):
    """Enhanced state for the Log Analysis Agent with comprehensive analysis."""
    messages: List[BaseMessage]
    raw_log_content: str
    parsed_log_data: Optional[Dict[str, Any]]
    system_profile: Optional[Dict[str, Any]]
    detected_issues: Optional[List[Dict[str, Any]]]
    generated_solutions: Optional[List[Dict[str, Any]]]
    final_report: Optional['ComprehensiveLogAnalysisOutput']
    analysis_metadata: Optional[Dict[str, Any]]


# System Information Schemas
class DetailedSystemMetadata(BaseModel):
    """Comprehensive system metadata with performance metrics."""
    mailbird_version: str = Field(description="Extracted Mailbird version with build info")
    database_size_mb: float = Field(description="Database size in MB with precision")
    account_count: int = Field(description="Number of configured email accounts")
    folder_count: int = Field(description="Total folder count across all accounts")
    memory_usage_mb: Optional[float] = Field(None, description="Memory usage in MB")
    startup_time_ms: Optional[float] = Field(None, description="Application startup time in milliseconds")
    email_providers: List[str] = Field(default_factory=list, description="List of detected email providers")
    sync_status: Optional[str] = Field(None, description="Current synchronization status")
    os_version: Optional[str] = Field(None, description="Operating system version")
    system_architecture: Optional[str] = Field(None, description="System architecture (x64/x86)")
    log_timeframe: str = Field(description="Date range covered by log entries")
    analysis_timestamp: str = Field(description="Timestamp when analysis was performed")
    total_entries_parsed: int = Field(description="Number of log entries processed")
    error_rate_percentage: float = Field(description="Percentage of error/warning entries")
    log_level_distribution: Dict[str, int] = Field(default_factory=dict, description="Distribution of log levels")


class DetailedIssue(BaseModel):
    """Comprehensive issue description with analysis metadata."""
    issue_id: str = Field(description="Unique identifier for the issue")
    category: str = Field(description="Issue category (e.g., database_corruption, authentication_failure)")
    signature: str = Field(description="Error pattern or signature that identifies this issue")
    occurrences: int = Field(description="Number of times this issue occurred")
    severity: str = Field(description="Severity level: High, Medium, or Low")
    root_cause: str = Field(description="Detailed analysis of the underlying cause")
    user_impact: str = Field(description="Description of how this affects user experience")
    first_occurrence: Optional[str] = Field(None, description="Timestamp of first occurrence")
    last_occurrence: Optional[str] = Field(None, description="Timestamp of last occurrence")
    frequency_pattern: str = Field(description="Analysis of temporal occurrence pattern")
    related_log_levels: List[str] = Field(default_factory=list, description="Log levels associated with this issue")
    confidence_score: Optional[float] = Field(None, description="Confidence in issue detection (0-1)")


class SolutionStep(BaseModel):
    """Individual step in a solution with detailed guidance."""
    step_number: int = Field(description="Sequential step number")
    description: str = Field(description="Detailed description of the action to take")
    expected_outcome: str = Field(description="What the user should see after completing this step")
    troubleshooting_note: Optional[str] = Field(None, description="Additional help if step fails")
    estimated_time_minutes: Optional[int] = Field(None, description="Estimated time for this step")
    risk_level: Optional[str] = Field(None, description="Risk level: Low, Medium, High")


class ComprehensiveSolution(BaseModel):
    """Detailed solution with validation and alternatives."""
    issue_id: str = Field(description="ID of the issue this solution addresses")
    solution_summary: str = Field(description="Brief summary of the solution approach")
    confidence_level: str = Field(description="Confidence in solution: High, Medium, Low")
    solution_steps: List[SolutionStep] = Field(description="Detailed step-by-step instructions")
    prerequisites: List[str] = Field(default_factory=list, description="Required conditions or preparations")
    estimated_total_time_minutes: int = Field(description="Total estimated time for complete solution")
    success_probability: str = Field(description="Estimated probability of success: High, Medium, Low")
    alternative_approaches: List[str] = Field(default_factory=list, description="Alternative solutions if primary fails")
    references: List[str] = Field(default_factory=list, description="Documentation or support URLs")
    technical_notes: Optional[str] = Field(None, description="Additional technical considerations")
    requires_restart: bool = Field(default=False, description="Whether solution requires application restart")
    data_backup_required: bool = Field(default=False, description="Whether data backup is recommended")


class ResearchRecommendation(BaseModel):
    """Enhanced research recommendations with context."""
    rationale: str = Field(description="Detailed explanation of why research is needed")
    recommended_queries: List[str] = Field(description="Specific search queries for additional research")
    research_priority: str = Field(description="Priority level: High, Medium, Low")
    expected_information: str = Field(description="What type of information the research should provide")
    alternative_resources: List[str] = Field(default_factory=list, description="Alternative sources of information")


class AnalysisMetrics(BaseModel):
    """Metrics about the analysis process itself."""
    analysis_duration_seconds: Optional[float] = Field(None, description="Time taken for analysis")
    parser_version: str = Field(description="Version of the parser used")
    llm_model_used: str = Field(description="Language model used for analysis")
    web_search_performed: bool = Field(default=False, description="Whether web search was used")
    confidence_threshold_met: bool = Field(description="Whether analysis meets confidence threshold")
    completeness_score: Optional[float] = Field(None, description="Completeness of analysis (0-1)")


class ComprehensiveLogAnalysisOutput(BaseModel):
    """The final comprehensive output with all analysis results."""
    
    # Executive Summary
    overall_summary: str = Field(description="Executive summary of system health and findings")
    health_status: str = Field(description="Overall system health: Healthy, Degraded, Critical")
    priority_concerns: List[str] = Field(description="Top priority issues requiring attention")
    
    # Detailed System Information
    system_metadata: DetailedSystemMetadata = Field(description="Comprehensive system information")
    
    # Issue Analysis
    identified_issues: List[DetailedIssue] = Field(description="All detected issues with detailed analysis")
    issue_summary_by_severity: Dict[str, int] = Field(description="Count of issues by severity level")
    
    # Solution Guidance
    proposed_solutions: List[ComprehensiveSolution] = Field(description="Detailed solutions for all issues")
    
    # Research Recommendations
    supplemental_research: Optional[ResearchRecommendation] = Field(None, description="Additional research recommendations")
    
    # Analysis Metadata
    analysis_metrics: AnalysisMetrics = Field(description="Metadata about the analysis process")
    
    # Recommendations
    immediate_actions: List[str] = Field(description="Actions that should be taken immediately")
    preventive_measures: List[str] = Field(description="Steps to prevent future issues")
    monitoring_recommendations: List[str] = Field(description="What to monitor going forward")
    
    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


# Legacy compatibility
StructuredLogAnalysisOutput = ComprehensiveLogAnalysisOutput
LogAnalysisAgentState = EnhancedLogAnalysisAgentState