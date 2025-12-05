"""Middleware that redacts tool outputs and agent replies before emission."""

from __future__ import annotations

from typing import Any, Callable

from langchain.agents.middleware import AgentMiddleware, AgentState
from langchain.agents.middleware.types import ModelRequest, ModelResponse, ToolCallRequest
from langchain_core.messages import BaseMessage, ToolMessage
from langgraph.runtime import Runtime
from langgraph.types import Command, Overwrite
from loguru import logger


try:  # pragma: no cover - dependency wired in Phase 2
    from app.security.pii_redactor import redact_pii, redact_pii_from_dict
except ImportError as e:  # pragma: no cover - fallback until module exists
    import logging
    logging.error(
        "Failed to import PII redactor from app.security.pii_redactor: %s. "
        "Using no-op fallback which WILL NOT redact sensitive data. "
        "This is unsafe for production.",
        e
    )

    def redact_pii(text: str) -> str:
        return text

    def redact_pii_from_dict(payload: Any) -> Any:
        return payload


class SecurityRedactionMiddleware(AgentMiddleware[AgentState[Any], Any]):
    """Redacts PII in tool responses and coordinator outputs."""

    @property
    def name(self) -> str:  # pragma: no cover - simple override
        return "security-redaction"

    def before_agent(self, state: AgentState, runtime: Runtime[Any]) -> dict[str, Any] | None:  # noqa: ARG002
        return None

    async def abefore_agent(self, state: AgentState, runtime: Runtime[Any]) -> dict[str, Any] | None:  # noqa: ARG002
        return None

    def after_agent(self, state: AgentState, runtime: Runtime[Any]) -> dict[str, Any] | None:  # noqa: ARG002
        return self._redact_state_messages(state)

    async def aafter_agent(self, state: AgentState, runtime: Runtime[Any]) -> dict[str, Any] | None:  # noqa: ARG002
        return self._redact_state_messages(state)

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        response = handler(request)
        return self._redact_model_response(response)

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Any],
    ) -> ModelResponse:
        response = await handler(request)
        return self._redact_model_response(response)

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command],
    ) -> ToolMessage | Command:
        result = handler(request)
        return self._redact_tool_result(result)

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Any],
    ) -> ToolMessage | Command:
        result = await handler(request)
        return self._redact_tool_result(result)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _redact_state_messages(self, state: AgentState) -> dict[str, Any] | None:
        messages = state.get("messages")
        if not messages:
            return None

        mutated = False
        sanitized = []
        for message in messages:
            cleaned = self._redact_message(message)
            mutated = mutated or cleaned is not message
            sanitized.append(cleaned)

        if not mutated:
            return None

        logger.info("security_redaction_applied", count=len(sanitized))
        return {"messages": Overwrite(sanitized)}

    def _redact_model_response(self, response: ModelResponse) -> ModelResponse:
        result_messages = getattr(response, "result", []) or []
        cleaned_messages = []
        mutated = False
        for msg in result_messages:
            cleaned = self._redact_message(msg)
            mutated = mutated or cleaned is not msg
            cleaned_messages.append(cleaned)
        if mutated:
            logger.info("security_redaction_applied_model_response", count=len(cleaned_messages))
            return ModelResponse(  # type: ignore[call-arg]
                result=cleaned_messages,
                structured_response=response.structured_response,
            )
        return response

    def _redact_tool_result(self, result: ToolMessage | Command) -> ToolMessage | Command:
        if isinstance(result, ToolMessage):
            return self._redact_message(result)
        return result

    def _redact_message(self, message: BaseMessage) -> BaseMessage:
        content = getattr(message, "content", None)
        cleaned_content = self._redact_payload(content)
        if cleaned_content is content:
            return message

        try:
            return message.model_copy(update={"content": cleaned_content})
        except Exception:  # pragma: no cover - guard older LC versions
            # Create a new message instance instead of mutating
            new_message = message.__class__(**message.dict())
            new_message.content = cleaned_content
            return new_message

    def _redact_payload(self, payload: Any) -> Any:
        if payload is None:
            return None
        if isinstance(payload, str):
            return redact_pii(payload)
        if isinstance(payload, list):
            updated_items = []
            changed = False
            for item in payload:
                redacted_item = self._redact_payload(item)
                updated_items.append(redacted_item)
                if redacted_item is not item:
                    changed = True
            return updated_items if changed else payload
        if isinstance(payload, dict):
            redacted = redact_pii_from_dict(payload)
            return redacted
        # Fallback: leave other payloads unchanged
        return payload
