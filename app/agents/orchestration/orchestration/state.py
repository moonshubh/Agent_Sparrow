from typing import List, Literal, Optional, Any
from langchain_core.documents import Document
from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field, model_serializer, ConfigDict

from app.agents.log_analysis.log_analysis_agent.simplified_schemas import SimplifiedLogAnalysisOutput as StructuredLogAnalysisOutput
from app.agents.reflection.reflection.schema import ReflectionFeedback  # noqa: E402, isort:skip

from pydantic import model_serializer

class GraphState(BaseModel):
    """
    Represents the overall state of the agentic system.
    """
    session_id: str = "default"
    messages: List[BaseMessage] = Field(default_factory=list)
    destination: Optional[Literal["primary_agent", "log_analyst", "researcher", "__end__"]] = None
    raw_log_content: Optional[str] = None
    final_report: Optional[StructuredLogAnalysisOutput] = None
    # Pre-processing cache hit response stored here.
    cached_response: Optional[Any] = None
    # Context retrieval now handled directly by agents using Supabase
    # context field removed - was originally for Qdrant integration
    # Arbitrary tool output (LangGraph ToolNode)
    tool_invocation_output: Optional[Any] = Field(default=None, description="Output from the last tool invocation if any.")
    # --- QA / Reflection Loop Fields ---
    # Stores the structured feedback from the reflection node
    reflection_feedback: Optional[ReflectionFeedback] = None
    # Count of refinement attempts already performed in current session
    qa_retry_count: int = 0

    # ------------------------------------------------------------------
    # Dict-like access helpers (compatibility with legacy nodes)
    # ------------------------------------------------------------------

    def __getitem__(self, item):
        """Enable dict-style access (state["messages"])."""
        return getattr(self, item)

    def __setitem__(self, key, value):
        """Enable assignment via dict-style access if needed."""
        setattr(self, key, value)

    def get(self, key, default=None):
        """Compatibility helper for dict-like get()."""
        return getattr(self, key, default)

    @model_serializer(when_used='always')
    def serialize_model(self):
        # This custom serializer is used to address a RecursionError caused by
        # `model_dump()` calling the serializer itself. By manually building the
        # dictionary from the model's fields, we avoid the recursive loop.
        # We also ensure the `messages` field preserves its BaseMessage objects,
        # as required by the LangGraph framework.
        serialized_data = {
            key: getattr(self, key)
            for key in self.model_fields
            if hasattr(self, key)
        }
        serialized_data['messages'] = self.messages
        return serialized_data

    model_config = ConfigDict(arbitrary_types_allowed=True)

GraphState.model_rebuild()
