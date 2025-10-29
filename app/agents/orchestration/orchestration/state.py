from typing import List, Literal, Optional, Any, Dict, ClassVar, Set
from langchain_core.documents import Document
from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field, model_serializer, ConfigDict, field_validator

from app.agents.log_analysis.log_analysis_agent.simplified_schemas import SimplifiedLogAnalysisOutput as StructuredLogAnalysisOutput
from app.agents.reflection.reflection.schema import ReflectionFeedback  # noqa: E402, isort:skip

class Attachment(BaseModel):
    """Represents an attachment provided via CopilotKit or SSE frontends."""

    ALLOWED_MIME_TYPES: ClassVar[Set[str]] = {
        "text/plain",
        "text/markdown",
        "application/pdf",
        "image/png",
        "image/jpeg",
        "image/gif",
    }
    MAX_ATTACHMENT_SIZE_BYTES: ClassVar[int] = 10 * 1024 * 1024  # 10 MiB

    name: Optional[str] = Field(default=None, description="Original filename provided by the client if available.")
    mime_type: Optional[str] = Field(default=None, description="Attachment MIME type constrained to a safe allowlist.")
    data_url: str = Field(..., description="Inline data URL representation of the attachment contents.")
    size: Optional[int] = Field(
        default=None,
        ge=0,
        le=MAX_ATTACHMENT_SIZE_BYTES,
        description="Attachment size in bytes used for guard rails before processing.",
    )

    model_config = ConfigDict(extra="ignore")

    @field_validator("data_url")
    @classmethod
    def _validate_data_url(cls, value: str) -> str:
        if not value.startswith("data:"):
            raise ValueError("Attachment data_url must be a valid data: URL.")
        if "," not in value:
            raise ValueError("Attachment data_url must contain encoded content after metadata.")
        return value

    @field_validator("mime_type")
    @classmethod
    def _validate_mime_type(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        if value not in cls.ALLOWED_MIME_TYPES:
            allowed = ", ".join(sorted(cls.ALLOWED_MIME_TYPES))
            raise ValueError(f"Attachment mime_type must be one of: {allowed}.")
        return value

    @field_validator("size")
    @classmethod
    def _validate_size(cls, value: Optional[int]) -> Optional[int]:
        if value is None:
            return value
        if value > cls.MAX_ATTACHMENT_SIZE_BYTES:
            raise ValueError("Attachment size exceeds the maximum allowed limit of 10 MiB.")
        return value


class GraphState(BaseModel):
    """
    Represents the overall state of the agentic system.
    """
    session_id: str = "default"
    trace_id: Optional[str] = None
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
    # Global knowledge adapter context
    global_knowledge_context: Optional[Dict[str, Any]] = None
    # Supervisor decisions captured during human escalations
    escalation_review: Optional[Dict[str, Any]] = None
    # Attachments forwarded from CopilotKit or SSE frontends (data URLs, etc.)
    attachments: Optional[List[Attachment]] = Field(
        default=None,
        description="Validated attachments forwarded from the client, if any.",
    )

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
