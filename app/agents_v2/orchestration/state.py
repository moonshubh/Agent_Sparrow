from typing import List, Literal, Optional, Any, Dict
from langchain_core.documents import Document
from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field, model_serializer


class ThoughtStep(BaseModel):
    """Represents a structured thought step from the reasoning engine with enhanced frontend support."""
    step: str = Field(description="The name/title of the reasoning step")
    content: str = Field(description="The detailed content/reasoning for this step")
    confidence: float = Field(description="Confidence score for this step (0.0 to 1.0)")
    phase: str = Field(description="The reasoning phase this step belongs to")
    evidence: List[str] = Field(default_factory=list, description="Supporting evidence for this reasoning step")
    category: str = Field(default="analysis", description="Category: analysis, solution, validation, or critique")
    user_friendly: bool = Field(default=True, description="Whether this step should be shown to users")
    processing_time_ms: Optional[float] = Field(default=None, description="Time taken for this step in milliseconds")
    
    class Config:
        frozen = True

from app.agents_v2.log_analysis_agent.enhanced_schemas import ComprehensiveLogAnalysisOutput, StructuredLogAnalysisOutput
from app.agents_v2.reflection.schema import ReflectionFeedback  # noqa: E402, isort:skip

from pydantic import model_serializer

class GraphState(BaseModel):
    """
    Represents the overall state of the agentic system.
    """
    session_id: Optional[str] = "default"
    messages: List[BaseMessage] = Field(default_factory=list)
    destination: Optional[Literal["primary_agent", "log_analyst", "researcher", "__end__"]] = None
    raw_log_content: Optional[str] = None
    final_report: Optional[StructuredLogAnalysisOutput] = None
    selected_model: Optional[str] = None  # User-selected model (e.g., 'google/gemini-2.5-flash')
    # Pre-processing cache hit response stored here.
    cached_response: Optional[Any] = None
    # Retrieved context snippets from Qdrant
    context: Optional[List[Document]] = None
    # Arbitrary tool output (LangGraph ToolNode)
    tool_invocation_output: Optional[Any] = Field(default=None, description="Output from the last tool invocation if any.")
    # --- QA / Reflection Loop Fields ---
    # Stores the structured feedback from the reflection node
    reflection_feedback: Optional[ReflectionFeedback] = None
    # Count of refinement attempts already performed in current session
    qa_retry_count: int = 0
    # Enhanced thought steps from reasoning engine for frontend display
    thought_steps: Optional[List[ThoughtStep]] = None
    # Summary of reasoning process for quick overview
    reasoning_summary: Optional[str] = None
    # Overall confidence score for the response
    overall_confidence: Optional[float] = None
    # Routing metadata from enhanced router
    routing_confidence: Optional[float] = None
    query_complexity: Optional[float] = None
    routing_metadata: Optional[Dict[str, Any]] = None

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

    class Config:
        arbitrary_types_allowed = True

GraphState.model_rebuild()
