from typing import List
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

    class Config:
        arbitrary_types_allowed = True