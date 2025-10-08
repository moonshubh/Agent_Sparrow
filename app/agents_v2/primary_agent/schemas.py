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

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        # Allow future forward-compat fields if added by callers
        extra="ignore",
    )