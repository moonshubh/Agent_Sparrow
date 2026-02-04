"""Middleware to sanitize message names for strict providers.

Some OpenAI-compatible providers reject `name` fields on non-user messages.
We rely on `name` internally (e.g., to tag injected system messages), so we
strip names only at the last possible moment: right before the model call.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, cast

from langchain_core.messages import BaseMessage, HumanMessage

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


def _should_strip_names(model: Any) -> bool:
    """Return True when the provider/model is known to reject `name` fields."""
    if model is None:
        return False

    model_cls = getattr(model, "__class__", None)
    module = getattr(model_cls, "__module__", "") if model_cls else ""
    cls_name = getattr(model_cls, "__name__", "") if model_cls else ""
    module_lower = module.lower()
    cls_lower = cls_name.lower()

    # xAI via langchain-xai
    if "langchain_xai" in module_lower or cls_lower == "chatxai":
        return True

    # OpenAI-compatible clients targeting xAI/OpenRouter endpoints.
    base_url = (
        getattr(model, "openai_api_base", None)
        or getattr(model, "base_url", None)
        or getattr(model, "api_base", None)
    )
    if isinstance(base_url, str):
        base_lower = base_url.lower()
        if (
            "openrouter" in base_lower
            or "api.x.ai" in base_lower
            or "x.ai" in base_lower
        ):
            return True

    # Heuristic: Grok model names are typically xAI-backed.
    model_name = (
        getattr(model, "model_name", None)
        or getattr(model, "model", None)
        or getattr(model, "model_id", None)
    )
    if isinstance(model_name, str) and "grok" in model_name.lower():
        return True

    return False


def _strip_name_from_messages(messages: list[BaseMessage]) -> list[BaseMessage]:
    sanitized: list[BaseMessage] = []
    for message in messages:
        if getattr(message, "name", None) is None:
            sanitized.append(message)
            continue

        # xAI error: only role=user can have name. Preserve HumanMessage names
        # (rare) and strip everything else.
        if isinstance(message, HumanMessage):
            sanitized.append(message)
            continue

        try:
            sanitized.append(message.model_copy(update={"name": None}))
        except Exception:
            sanitized.append(message)

    return sanitized


class MessageNameSanitizationMiddleware(AgentMiddleware):
    """Strip `name` from non-user messages before strict provider calls."""

    @property
    def name(self) -> str:  # pragma: no cover - trivial
        return "message_name_sanitization"

    def wrap_model_call(  # type: ignore[override]
        self,
        request: "ModelRequest",
        handler: Callable[["ModelRequest"], "ModelResponse"],
    ) -> Any:
        if not _should_strip_names(getattr(request, "model", None)):
            return handler(request)

        messages = list(getattr(request, "messages", []) or [])
        if not messages:
            return handler(request)

        return handler(
            request.override(messages=cast(Any, _strip_name_from_messages(messages)))
        )

    async def awrap_model_call(  # type: ignore[override]
        self,
        request: "ModelRequest",
        handler: Callable[["ModelRequest"], Awaitable["ModelResponse"]],
    ) -> Any:
        if not _should_strip_names(getattr(request, "model", None)):
            return await handler(request)

        messages = list(getattr(request, "messages", []) or [])
        if not messages:
            return await handler(request)

        return await handler(
            request.override(messages=cast(Any, _strip_name_from_messages(messages)))
        )
