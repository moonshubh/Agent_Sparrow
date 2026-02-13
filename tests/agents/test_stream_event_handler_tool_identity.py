from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.messages import HumanMessage

from app.agents.streaming.handler import StreamEventHandler


class _Emitter:
    def __init__(self) -> None:
        self.root_id = "test-root"
        self.start_calls: list[dict[str, Any]] = []
        self.end_calls: list[dict[str, Any]] = []
        self.error_calls: list[dict[str, Any]] = []

    def add_trace_step(self, **_kwargs: Any) -> None:
        return None

    def emit_custom_event(self, _name: str, _payload: dict[str, Any]) -> None:
        return None

    def emit_objective_hint(self, **_kwargs: Any) -> None:
        return None

    def start_tool(
        self,
        tool_call_id: str,
        tool_name: str,
        _tool_input: Any,
        goal: str | None = None,
    ) -> None:
        self.start_calls.append(
            {"tool_call_id": tool_call_id, "tool_name": tool_name, "goal": goal}
        )

    def end_tool(
        self,
        tool_call_id: str,
        tool_name: str,
        output: Any,
        summary: str | None,
        cards: list[dict[str, Any]] | None = None,
    ) -> None:
        self.end_calls.append(
            {
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
                "output": output,
                "summary": summary,
                "cards": cards or [],
            }
        )

    def error_tool(self, tool_call_id: str, tool_name: str, raw_error: Any) -> None:
        self.error_calls.append(
            {
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
                "error": raw_error,
            }
        )


def _build_handler(emitter: _Emitter) -> StreamEventHandler:
    return StreamEventHandler(
        agent=SimpleNamespace(),
        emitter=emitter,  # type: ignore[arg-type]
        config={"configurable": {}},
        state=SimpleNamespace(attachments=[], scratchpad={}),
        messages=[HumanMessage(content="hello")],
        fallback_agent_factory=None,
        helper=None,
        session_cache={},
        last_user_query="hello",
    )


@pytest.mark.asyncio
async def test_on_tool_end_uses_run_metadata_when_tool_call_id_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    emitter = _Emitter()
    handler = _build_handler(emitter)

    image_calls: list[Any] = []

    async def _fake_handle_image(output: Any) -> None:
        image_calls.append(output)

    monkeypatch.setattr(handler, "_handle_image_generation", _fake_handle_image)
    monkeypatch.setattr(handler, "_compact_image_output", lambda output: output)

    await handler._on_tool_start(
        {
            "run_id": "run-generate-image",
            "name": "generate_image",
            "data": {
                "input": {"prompt": "blue square"},
                # Simulate providers that omit tool_call_id in stream events.
                "tool_call_id": None,
            },
        }
    )

    assert emitter.start_calls
    assert emitter.start_calls[0]["tool_call_id"] == "run-run-generate-image"
    assert emitter.start_calls[0]["tool_name"] == "generate_image"

    await handler._on_tool_end(
        {
            "run_id": "run-generate-image",
            "name": "tool",
            "data": {
                "output": {
                    "success": True,
                    "image_url": "https://example.com/generated.png",
                }
            },
        }
    )

    assert len(image_calls) == 1
    assert emitter.end_calls
    assert emitter.end_calls[0]["tool_call_id"] == "run-run-generate-image"
    assert emitter.end_calls[0]["tool_name"] == "generate_image"


@pytest.mark.asyncio
async def test_on_tool_error_uses_run_metadata_when_tool_call_id_missing() -> None:
    emitter = _Emitter()
    handler = _build_handler(emitter)

    await handler._on_tool_start(
        {
            "run_id": "run-image-error",
            "name": "generate_image",
            "data": {"tool_call_id": None, "input": {"prompt": "blue square"}},
        }
    )

    await handler._on_tool_error(
        {
            "run_id": "run-image-error",
            "name": "tool",
            "data": {
                "tool_call_id": None,
                "error": "provider timeout",
            },
        }
    )

    assert emitter.error_calls
    assert emitter.error_calls[0]["tool_call_id"] == "run-run-image-error"
    assert emitter.error_calls[0]["tool_name"] == "generate_image"

