from typing import List, Optional, Dict, Any
from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field

class PrimaryAgentState(BaseModel):
    """
    Represents the state of the primary agent.
    """
    messages: List[BaseMessage] = Field(
        ...,
        description="The conversation history.",
    )
    model: Optional[str] = Field(
        None,
        description="Optional model selection for the primary agent (e.g., 'google/gemini-2.5-flash', 'google/gemini-2.5-pro', 'moonshotai/kimi-k2')"
    )
    routing_metadata: Optional[Dict[str, Any]] = Field(
        None,
        description="Metadata from router including confidence, complexity, and embeddings"
    )

    class Config:
        arbitrary_types_allowed = True