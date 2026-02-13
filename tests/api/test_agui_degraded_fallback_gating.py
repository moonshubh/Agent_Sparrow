from __future__ import annotations

from typing import Any

import pytest
from fastapi.responses import StreamingResponse
from starlette.requests import Request

from ag_ui.core import CustomEvent, RunFinishedEvent, RunStartedEvent
from ag_ui.core.types import RunAgentInput

from app.api.v1.endpoints import agui_endpoints


class _FakeAgent:
    def __init__(self, events: list[Any]) -> None:
        self._events = events

    async def run(self, _input: RunAgentInput):
        for event in self._events:
            yield event


def _build_request() -> Request:
    async def _receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/agui/stream",
        "headers": [(b"accept", b"text/event-stream")],
    }
    return Request(scope, _receive)


def _build_input(thread_id: str, run_id: str) -> RunAgentInput:
    return RunAgentInput.model_validate(
        {
            "threadId": thread_id,
            "runId": run_id,
            "state": {},
            "messages": [{"id": "u-1", "role": "user", "content": "test"}],
            "tools": [],
            "context": [],
            "forwardedProps": {
                "session_id": thread_id,
                "trace_id": run_id,
                "provider": "google",
                "model": "gemini-3-flash-preview",
                "agent_mode": "general",
                "force_websearch": False,
            },
        }
    )


async def _collect_stream(response: StreamingResponse) -> str:
    parts: list[str] = []
    async for chunk in response.body_iterator:  # type: ignore[attr-defined]
        if isinstance(chunk, bytes):
            parts.append(chunk.decode("utf-8", errors="replace"))
        else:
            parts.append(str(chunk))
    return "".join(parts)


@pytest.mark.asyncio
async def test_degraded_fallback_suppressed_when_artifact_custom_event_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread_id = "thread-artifact"
    run_id = "run-artifact"
    events = [
        RunStartedEvent(thread_id=thread_id, run_id=run_id),
        CustomEvent(name="image_artifact", value={"id": "img-1"}),
        RunFinishedEvent(thread_id=thread_id, run_id=run_id),
    ]

    monkeypatch.setattr(agui_endpoints, "get_langgraph_agent", lambda: _FakeAgent(events))

    fallback_calls = {"count": 0}

    async def _fake_fallback(**_kwargs: Any) -> str:
        fallback_calls["count"] += 1
        return "fallback should not run"

    monkeypatch.setattr(agui_endpoints, "_degraded_direct_response_fallback", _fake_fallback)

    response = await agui_endpoints.agui_stream(
        _build_input(thread_id, run_id),
        _build_request(),
        user_id="user-1",
    )

    assert isinstance(response, StreamingResponse)
    body = await _collect_stream(response)

    assert fallback_calls["count"] == 0
    assert '"name":"image_artifact"' in body


@pytest.mark.asyncio
async def test_degraded_fallback_runs_when_no_text_and_no_artifact_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread_id = "thread-no-artifact"
    run_id = "run-no-artifact"
    events = [
        RunStartedEvent(thread_id=thread_id, run_id=run_id),
        RunFinishedEvent(thread_id=thread_id, run_id=run_id),
    ]

    monkeypatch.setattr(agui_endpoints, "get_langgraph_agent", lambda: _FakeAgent(events))

    fallback_calls = {"count": 0}

    async def _fake_fallback(**_kwargs: Any) -> str:
        fallback_calls["count"] += 1
        return "fallback text"

    monkeypatch.setattr(agui_endpoints, "_degraded_direct_response_fallback", _fake_fallback)

    response = await agui_endpoints.agui_stream(
        _build_input(thread_id, run_id),
        _build_request(),
        user_id="user-1",
    )

    assert isinstance(response, StreamingResponse)
    body = await _collect_stream(response)

    assert fallback_calls["count"] == 1
    assert '"type":"TEXT_MESSAGE_CONTENT"' in body
    assert "fallback text" in body
