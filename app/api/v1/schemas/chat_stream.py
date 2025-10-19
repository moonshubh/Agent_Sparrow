"""Pydantic models describing the primary agent streaming SSE contract."""

from __future__ import annotations

from typing import Any, Optional, Literal

from pydantic import BaseModel, ConfigDict


class ChatStreamEvent(BaseModel):
    """Represents a single Server-Sent Event emitted by the primary chat stream."""

    type: Literal[
        "text-start",
        "text-delta",
        "text-end",
        "assistant-structured",
        "data-followups",
        "data-thinking",
        "data-tool-result",
        "message-metadata",
        "reasoning-start",
        "reasoning-delta",
        "reasoning-end",
        "finish",
        "error",
    ]
    id: Optional[str] = None
    delta: Optional[str] = None
    data: Optional[Any] = None
    messageMetadata: Optional[dict[str, Any]] = None
    text: Optional[str] = None
    errorText: Optional[str] = None
    stream_id: Optional[str] = None
    session_id: Optional[str] = None
    step: Optional[str] = None
    transient: Optional[bool] = None
    trace_id: Optional[str] = None

    model_config = ConfigDict(extra="allow", populate_by_name=True)
