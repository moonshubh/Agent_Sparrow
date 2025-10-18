from typing import Any, Dict, List, Optional
from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field, ConfigDict

class PrimaryAgentState(BaseModel):
    """
    Represents the state of the primary agent.
    """
    messages: List[BaseMessage] = Field(
        ...,
        description="The conversation history.",
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Optional session identifier to maintain context."
    )
    provider: Optional[str] = Field(
        default=None,
        description="LLM provider override (e.g., 'google' or 'openai')."
    )
    model: Optional[str] = Field(
        default=None,
        description="LLM model id override (e.g., 'gemini-2.5-flash' or 'gpt-5-mini-2025-08-07')."
    )
    # Manual web search flags (frontend pill)
    force_websearch: Optional[bool] = Field(default=None, description="Force enable web search regardless of KB gating")
    websearch_max_results: Optional[int] = Field(default=None, description="Override Tavily max results")
    websearch_profile: Optional[str] = Field(default=None, description="Tavily profile hint (e.g., medium/advanced)")

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        # Allow future forward-compat fields if added by callers
        extra="ignore",
    )


class GroundingMetadata(BaseModel):
    """Observability-friendly grounding summary for the final response."""

    kb_results: int = Field(default=0, description="Total KB results considered.")
    avg_relevance: float = Field(default=0.0, description="Average relevance score of KB results.")
    used_tavily: bool = Field(default=False, description="Indicates whether Tavily web search was used.")
    fallback_used: bool = Field(default=False, description="True if a fallback summarizer was used.")
    mailbird_settings_loaded: bool = Field(default=False, description="True if Mailbird settings were loaded.")

    model_config = ConfigDict(extra="ignore")


class ToolResultMetadata(BaseModel):
    """Structured description of any tool or routing decision."""

    id: Optional[str] = Field(default=None, description="Identifier for the tool invocation.")
    name: Optional[str] = Field(default=None, description="Human-friendly tool name.")
    summary: Optional[str] = Field(default=None, description="Short summary of the tool result.")
    reasoning: Optional[str] = Field(default=None, description="Reasoning snippet associated with the tool decision.")
    decision: Optional[str] = Field(default=None, description="Decision category emitted by tool reasoning.")
    confidence: Optional[float] = Field(default=None, description="Confidence score for the tool decision.")
    required_information: Optional[List[str]] = Field(default=None, description="Additional information required.")
    knowledge_gaps: Optional[List[str]] = Field(default=None, description="Knowledge gaps identified.")
    expected_sources: Optional[List[str]] = Field(default=None, description="Expected sources to reference.")

    model_config = ConfigDict(extra="ignore")


class PrimaryAgentFinalResponse(BaseModel):
    """Structured payload emitted alongside the final assistant text."""

    text: str = Field(..., description="Final assistant message text.")
    follow_up_questions: List[str] = Field(
        default_factory=list, description="Suggested follow-up questions."
    )
    grounding: Optional[GroundingMetadata] = Field(
        default=None, description="Grounding metadata summarizing retrieval activity."
    )
    tool_results: Optional[ToolResultMetadata] = Field(
        default=None, description="Details about tool usage or reasoning decisions."
    )
    thinking_trace: Optional[Dict[str, Any]] = Field(
        default=None, description="Optional thinking trace emitted when enabled."
    )

    model_config = ConfigDict(extra="ignore")
