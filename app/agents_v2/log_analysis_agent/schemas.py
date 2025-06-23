from typing import TypedDict, List, Optional, Any, Dict
from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field

# Agent-related Schemas
class LogAnalysisAgentState(TypedDict):
    """Represents the state of the Log Analysis Agent as it executes."""
    messages: List[BaseMessage]
    raw_log_content: str
    parsed_log_data: Optional[Dict[str, Any]] = None
    final_report: Optional['StructuredLogAnalysisOutput'] = None

class RawLogInput(BaseModel):
    """Input schema for the endpoint receiving the raw log content."""
    content: str = Field(description="The raw string content of the log file.")

# --- V2 Output Schemas (aligns with the new prompt) ---

class SystemMetadata(BaseModel):
    """Schema for the system metadata block."""
    mailbird_version: str = Field(description="Extracted Mailbird version, or 'Unknown'.")
    database_size_mb: str = Field(description="Extracted database size in MB/GB, or 'Unknown'.")
    account_count: str = Field(description="Number of configured accounts, or 'Unknown'.")
    folder_count: str = Field(description="Total folder count across all accounts, or 'Unknown'.")
    log_timeframe: str = Field(description="The date range covered by the log entries.")
    analysis_timestamp: str = Field(description="The timestamp when the analysis was performed.")

class IdentifiedIssue(BaseModel):
    """Schema for a single, well-defined issue identified in the logs."""
    issue_id: str = Field(description="A short, descriptive slug for the issue (e.g., 'smtp_auth_fail').")
    signature: str = Field(description="A regex-like pattern or error message that uniquely identifies this issue.")
    occurrences: int = Field(description="The number of times this issue was found in the logs.")
    severity: str = Field(description="Assessed severity: 'High', 'Medium', or 'Low'.")
    root_cause: str = Field(description="The inferred primary cause of the issue, based on LLM reasoning.")
    user_impact: str = Field(description="A clear description of how this issue affects the user's experience.")
    first_occurrence: Optional[str] = Field(None, description="Timestamp of the first time this issue appeared.")
    last_occurrence: Optional[str] = Field(None, description="Timestamp of the most recent occurrence.")

class ProposedSolution(BaseModel):
    """Schema for a detailed, actionable solution to a corresponding issue."""
    issue_id: str = Field(description="The issue_id this solution is intended to resolve.")
    solution_summary: str = Field(description="A brief, one-sentence summary of the proposed fix.")
    solution_steps: List[str] = Field(description="A list of concrete, step-by-step instructions for the user.")
    references: List[str] = Field(default=[], description="Canonical URLs from LLM knowledge that support the solution.")
    success_probability: str = Field(description="Estimated probability of success: 'High', 'Medium', or 'Low'.")

class SupplementalResearch(BaseModel):
    """Schema for recommending user-led web research when LLM reasoning is insufficient."""
    rationale: str = Field(description="Explanation of why web research is recommended for this specific case.")
    recommended_queries: List[str] = Field(description="A list of precise search queries for the user to execute.")

class StructuredLogAnalysisOutput(BaseModel):
    """The final, comprehensive JSON output from the Log Analysis Agent v2."""
    overall_summary: str = Field(description="A high-level executive summary of the system's health and key findings.")
    system_metadata: SystemMetadata = Field(description="Detailed metadata extracted and derived from the logs.")
    identified_issues: List[IdentifiedIssue] = Field(description="A list of all significant issues detected.")
    proposed_solutions: List[ProposedSolution] = Field(description="A list of detailed solutions for the identified issues.")
    supplemental_research: Optional[SupplementalResearch] = Field(None, description="Recommendations for user-led web research, if necessary.")

    class Config:
        populate_by_name = True
