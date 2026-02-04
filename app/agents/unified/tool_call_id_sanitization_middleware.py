"""Middleware to sanitize tool call IDs for OpenAI-compatible providers.

Some OpenAI-compatible backends (including Minimax Coding Plan) reject tool_call_id
values that don't follow their expected format. This middleware normalizes tool_call_id
values in AIMessage.tool_calls and ToolMessage.tool_call_id fields before model calls.
"""

from __future__ import annotations

import re
from typing import Any, Awaitable, Callable, Dict, cast
from uuid import uuid4

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

try:
    from langchain.agents.middleware import AgentMiddleware
    from langchain.agents.middleware.types import ModelRequest, ModelResponse

    MIDDLEWARE_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency

    class AgentMiddleware:  # type: ignore[no-redef]
        pass

    class ModelRequest:  # type: ignore[no-redef]
        pass

    class ModelResponse:  # type: ignore[no-redef]
        pass

    MIDDLEWARE_AVAILABLE = False


_INVALID_ID_RE = re.compile(r"[^a-zA-Z0-9_-]")


def _should_sanitize_tool_call_ids(model: Any) -> bool:
    """Return True for OpenAI-compatible models that enforce tool_call_id format."""
    if model is None:
        return False

    model_cls = getattr(model, "__class__", None)
    module = getattr(model_cls, "__module__", "") if model_cls else ""
    module_lower = module.lower()

    if "langchain_openai" in module_lower:
        return True

    base_url = (
        getattr(model, "openai_api_base", None)
        or getattr(model, "base_url", None)
        or getattr(model, "api_base", None)
    )
    if isinstance(base_url, str) and "minimax" in base_url.lower():
        return True

    return False


def _sanitize_tool_call_id(raw_id: str | None) -> str:
    if not isinstance(raw_id, str) or not raw_id.strip():
        return f"call_{uuid4().hex}"
    cleaned = _INVALID_ID_RE.sub("", raw_id.strip())
    if not cleaned:
        cleaned = uuid4().hex
    if not cleaned.startswith("call_"):
        cleaned = f"call_{cleaned}"
    return cleaned[:64]


def _sanitize_messages(messages: list[BaseMessage]) -> list[BaseMessage]:
    mapping: Dict[str, str] = {}
    sanitized: list[BaseMessage] = []

    for message in messages:
        if isinstance(message, AIMessage):
            tool_calls = getattr(message, "tool_calls", None) or []
            if not tool_calls:
                sanitized.append(message)
                continue

            updated_calls: list[dict[str, Any]] = []
            changed = False
            for call in tool_calls:
                if not isinstance(call, dict):
                    updated_calls.append(call)
                    continue
                raw_id = (
                    call.get("id") or call.get("tool_call_id") or call.get("toolCallId")
                )
                new_id = mapping.get(raw_id) if isinstance(raw_id, str) else None
                if not new_id:
                    new_id = _sanitize_tool_call_id(raw_id)
                if isinstance(raw_id, str):
                    mapping[raw_id] = new_id
                if raw_id != new_id:
                    updated = dict(call)
                    updated["id"] = new_id
                    updated.pop("tool_call_id", None)
                    updated.pop("toolCallId", None)
                    updated_calls.append(updated)
                    changed = True
                else:
                    updated_calls.append(call)

            if changed:
                sanitized.append(
                    message.model_copy(update={"tool_calls": updated_calls})
                )
            else:
                sanitized.append(message)
            continue

        if isinstance(message, ToolMessage):
            raw_id = getattr(message, "tool_call_id", None)
            new_id = mapping.get(raw_id) if isinstance(raw_id, str) else None
            if not new_id:
                new_id = _sanitize_tool_call_id(raw_id)
            if isinstance(raw_id, str):
                mapping[raw_id] = new_id
            if raw_id != new_id:
                sanitized.append(message.model_copy(update={"tool_call_id": new_id}))
            else:
                sanitized.append(message)
            continue

        sanitized.append(message)

    return sanitized


class ToolCallIdSanitizationMiddleware(AgentMiddleware):
    """Normalize tool_call_id values before model calls."""

    @property
    def name(self) -> str:  # pragma: no cover - trivial
        return "tool_call_id_sanitization"

    def wrap_model_call(  # type: ignore[override]
        self,
        request: "ModelRequest",
        handler: Callable[["ModelRequest"], "ModelResponse"],
    ) -> Any:
        if not _should_sanitize_tool_call_ids(getattr(request, "model", None)):
            return handler(request)

        messages = list(getattr(request, "messages", []) or [])
        if not messages:
            return handler(request)

        return handler(
            request.override(messages=cast(Any, _sanitize_messages(messages)))
        )

    async def awrap_model_call(  # type: ignore[override]
        self,
        request: "ModelRequest",
        handler: Callable[["ModelRequest"], Awaitable["ModelResponse"]],
    ) -> Any:
        if not _should_sanitize_tool_call_ids(getattr(request, "model", None)):
            return await handler(request)

        messages = list(getattr(request, "messages", []) or [])
        if not messages:
            return await handler(request)

        return await handler(
            request.override(messages=cast(Any, _sanitize_messages(messages)))
        )
