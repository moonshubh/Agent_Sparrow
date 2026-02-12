from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.messages import HumanMessage

import app.agents.streaming.handler as handler_module
from app.agents.streaming.handler import ThinkingBlockTracker, StreamEventHandler


class _FakeEmitter:
    def __init__(self) -> None:
        self.root_id = "test-root"
        self.operations: dict[str, dict[str, Any]] = {}
        self.text_events: list[dict[str, Any]] = []
        self.objective_hints: list[dict[str, Any]] = []
        self._message_started = False

    def add_trace_step(self, **_kwargs: Any) -> None:
        return None

    def emit_custom_event(self, _name: str, _payload: dict[str, Any]) -> None:
        return None

    def emit_objective_hint(self, **kwargs: Any) -> None:
        self.objective_hints.append(dict(kwargs))

    def start_text_message(self, message_id: str | None = None) -> str:
        self._message_started = True
        resolved = message_id or "msg-test"
        self.text_events.append({"type": "TEXT_MESSAGE_START", "messageId": resolved})
        return resolved

    def emit_text_content(self, delta: str) -> None:
        if not self._message_started:
            self.start_text_message()
        self.text_events.append({"type": "TEXT_MESSAGE_CONTENT", "delta": delta})

    def end_text_message(self) -> None:
        self._message_started = False
        self.text_events.append({"type": "TEXT_MESSAGE_END"})

    def start_thought(self, run_id: str, **_kwargs: Any) -> None:
        self.operations[str(run_id)] = {"status": "running"}

    def end_thought(self, run_id: str, _content: Any) -> None:
        self.operations.pop(str(run_id), None)

    def update_trace_step(self, **_kwargs: Any) -> None:
        return None

    def stream_thought_chunk(self, _run_id: str, _delta: str) -> None:
        return None

    def stream_subagent_thinking_delta(
        self, *, tool_call_id: str, delta: str, subagent_type: str | None = None
    ) -> None:
        _ = (tool_call_id, delta, subagent_type)

    def mark_all_todos_done(self) -> None:
        return None

    def get_todos_as_dicts(self) -> list[dict[str, Any]]:
        return []

    def complete_root(self) -> None:
        return None


class _FakeAgent:
    def __init__(self, events: list[dict[str, Any]] | None = None) -> None:
        self.events = events or []

    async def astream_events(self, *_args: Any, **_kwargs: Any):
        for event in self.events:
            yield event


def _text_payload(events: list[dict[str, Any]]) -> str:
    return "".join(
        str(event.get("delta") or "")
        for event in events
        if event.get("type") == "TEXT_MESSAGE_CONTENT"
    )


@pytest.mark.asyncio
async def test_model_end_flushes_tracker_tail_in_gemini_buffer_mode() -> None:
    emitter = _FakeEmitter()
    handler = StreamEventHandler(
        agent=_FakeAgent(),
        emitter=emitter,
        config={"configurable": {}},
        state=SimpleNamespace(attachments=[], scratchpad={}),
        messages=[HumanMessage(content="hello")],
        fallback_agent_factory=None,
        helper=None,
        session_cache={},
        last_user_query="hello",
    )

    run_id = "run-gemini-tail"
    await handler._on_model_start(
        {
            "run_id": run_id,
            "data": {"model": "gemini-3-flash-preview", "messages": []},
        }
    )
    await handler._on_model_stream(
        {
            "run_id": run_id,
            "data": {"chunk": SimpleNamespace(content="tail-only-content")},
        }
    )
    assert _text_payload(emitter.text_events) == ""

    await handler._on_model_end(
        {
            "run_id": run_id,
            "data": {"output": {"content": "tail-only-content"}},
        }
    )

    assert "tail-only-content" in _text_payload(emitter.text_events)
    assert run_id not in handler._gemini_buffer_runs
    assert run_id not in getattr(handler, "_thinking_trackers", {})


@pytest.mark.asyncio
async def test_stream_completion_flushes_orphan_tracker_tail() -> None:
    emitter = _FakeEmitter()
    handler = StreamEventHandler(
        agent=_FakeAgent(events=[]),
        emitter=emitter,
        config={"configurable": {}},
        state=SimpleNamespace(attachments=[], scratchpad={}),
        messages=[HumanMessage(content="hello")],
        fallback_agent_factory=None,
        helper=None,
        session_cache={},
        last_user_query="hello",
    )

    tracker = ThinkingBlockTracker()
    tracker.process_chunk("orphan-tail")
    handler._thinking_trackers = {"run-orphan": tracker}

    output = await handler.stream_and_process()

    assert output == {"output": "orphan-tail"}
    assert "orphan-tail" in _text_payload(emitter.text_events)
    assert any(event.get("type") == "TEXT_MESSAGE_END" for event in emitter.text_events)


@pytest.mark.asyncio
async def test_model_end_flushes_without_operation_when_trace_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(handler_module.settings, "trace_mode", "off")

    emitter = _FakeEmitter()
    handler = StreamEventHandler(
        agent=_FakeAgent(),
        emitter=emitter,
        config={"configurable": {}},
        state=SimpleNamespace(attachments=[], scratchpad={}),
        messages=[HumanMessage(content="hello")],
        fallback_agent_factory=None,
        helper=None,
        session_cache={},
        last_user_query="hello",
    )

    run_id = "run-no-op"
    await handler._on_model_start(
        {
            "run_id": run_id,
            "data": {"model": "gemini-3-flash-preview", "messages": []},
        }
    )
    await handler._on_model_stream(
        {
            "run_id": run_id,
            "data": {"chunk": SimpleNamespace(content="buffered final answer")},
        }
    )

    # No thought operation is created when trace mode is off.
    assert not emitter.operations

    await handler._on_model_end(
        {
            "run_id": run_id,
            "data": {"output": {"content": "buffered final answer"}},
        }
    )

    assert "buffered final answer" in _text_payload(emitter.text_events)


def test_reconcile_visible_output_backfills_when_short_streamed_text() -> None:
    emitter = _FakeEmitter()
    handler = StreamEventHandler(
        agent=_FakeAgent(),
        emitter=emitter,
        config={"configurable": {}},
        state=SimpleNamespace(attachments=[], scratchpad={}),
        messages=[HumanMessage(content="hello")],
        fallback_agent_factory=None,
        helper=None,
        session_cache={},
        last_user_query="hello",
    )

    handler._visible_text_buffer = "short prefix"
    handler.final_output = {
        "output": {
            "messages": [
                {
                    "role": "assistant",
                    "content": (
                        "Customer impact is high. Immediate mitigation is to rollback to the "
                        "previous stable release, publish an incident update every 30 minutes, "
                        "and assign owners for API, sync, and UI validation."
                    ),
                }
            ]
        }
    }

    handler._reconcile_visible_output_with_final()

    payload = _text_payload(emitter.text_events)
    assert "Customer impact is high." in payload
    assert "rollback" in payload.lower()
