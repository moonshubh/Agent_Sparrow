from typing import Any, ClassVar, Dict, List, Optional, Set

from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_serializer

class Attachment(BaseModel):
    """Represents an attachment provided via the AG-UI or SSE frontends."""

    ALLOWED_MIME_TYPES: ClassVar[Set[str]] = {
        "text/plain",
        "text/markdown",
        "application/pdf",
        "image/png",
        "image/jpeg",
        "image/gif",
        "application/octet-stream",
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
    """Typed state shared across the unified LangGraph execution."""

    session_id: str = Field(default="default", description="Logical conversation / thread identifier.")
    trace_id: Optional[str] = Field(default=None, description="Trace or run identifier propagated to LangSmith.")
    user_id: Optional[str] = Field(default=None, description="Authenticated user id for memory scoping and auditing.")
    messages: List[BaseMessage] = Field(default_factory=list, description="Ordered conversation history.")
    attachments: List[Attachment] = Field(
        default_factory=list,
        description="Validated attachments forwarded from the client, if any.",
    )
    provider: Optional[str] = Field(
        default=None,
        description="Model provider override (currently 'google' for Gemini models).",
    )
    model: Optional[str] = Field(
        default=None,
        description="Model identifier override (e.g., 'gemini-2.5-flash').",
    )
    agent_type: Optional[str] = Field(
        default=None,
        description="Calling agent type or persona hint forwarded by the client.",
    )
    use_server_memory: bool = Field(
        default=False,
        description="Whether to persist conversation summaries in server-side memory.",
    )
    forwarded_props: Dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary forwarded properties from the client for tool or agent use.",
    )
    scratchpad: Dict[str, Any] = Field(
        default_factory=dict,
        description="Ephemeral state used by tools/subagents during execution.",
    )
    todos: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Optional todo list shared across the run (e.g., from planning middleware).",
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
        serialized_data["messages"] = self.messages
        return serialized_data

    model_config = ConfigDict(arbitrary_types_allowed=True)

GraphState.model_rebuild()
