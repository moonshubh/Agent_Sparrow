from typing import List, Optional
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