import asyncio
from types import SimpleNamespace
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.streaming.handler import StreamEventHandler


class _FakeEmitter:
    def __init__(self) -> None:
        self.custom_events: list[dict[str, Any]] = []
        self.trace_steps: list[dict[str, Any]] = []

    def add_trace_step(self, **kwargs: Any) -> None:
        self.trace_steps.append(dict(kwargs))

    def emit_custom_event(self, _name: str, payload: dict[str, Any]) -> None:
        self.custom_events.append(payload)

    def complete_root(self) -> None:  # pragma: no cover - not exercised
        return None


def test_streaming_failure_returns_user_visible_overload_error() -> None:
    async def _run() -> None:
        class _FakeAgent:
            async def astream_events(self, *_args: Any, **_kwargs: Any):
                if False:  # pragma: no cover - makes this an async generator
                    yield {}
                raise Exception(
                    "503 Service Unavailable: The model is overloaded. Please try again later."
                )

            async def ainvoke(self, *_args: Any, **_kwargs: Any) -> Any:
                raise Exception("fallback boom")

        state = SimpleNamespace(attachments=[], scratchpad={})
        handler = StreamEventHandler(
            agent=_FakeAgent(),
            emitter=_FakeEmitter(),
            config={"configurable": {}},
            state=state,
            messages=[HumanMessage(content="hello")],
            fallback_agent_factory=None,
            helper=None,
            session_cache={},
            last_user_query="hello",
        )

        output = await handler.stream_and_process()
        assert isinstance(output, dict)
        assert "temporarily overloaded" in str(output.get("output", "")).lower()

        system_bucket = (state.scratchpad or {}).get("_system") or {}
        failure = system_bucket.get("streaming_failure") or {}
        assert failure.get("google_overloaded") is True
        assert failure.get("fallback_attempted") is True
        assert failure.get("fallback_succeeded") is False

    asyncio.run(_run())


def test_fallback_coerces_system_messages_on_invalid_role_error() -> None:
    async def _run() -> None:
        class _FakeAgent:
            def __init__(self) -> None:
                self.calls = 0
                self.last_messages: list[Any] = []

            async def astream_events(self, *_args: Any, **_kwargs: Any):
                if False:  # pragma: no cover - makes this an async generator
                    yield {}
                raise Exception("The model is overloaded. Please try again later.")

            async def ainvoke(self, inputs: dict[str, Any], **_kwargs: Any) -> Any:
                self.calls += 1
                messages = list(inputs.get("messages") or [])
                self.last_messages = messages
                if any(isinstance(m, SystemMessage) for m in messages):
                    raise Exception("Error code: 400 … invalid message role: system (2013)")
                return {"output": "ok"}

        agent = _FakeAgent()
        state = SimpleNamespace(attachments=[], scratchpad={})
        handler = StreamEventHandler(
            agent=agent,
            emitter=_FakeEmitter(),
            config={"configurable": {}},
            state=state,
            messages=[SystemMessage(content="sys"), HumanMessage(content="hi")],
            fallback_agent_factory=None,
            helper=None,
            session_cache={},
            last_user_query="hi",
        )

        output = await handler.stream_and_process()
        assert output == {"output": "ok"}
        assert agent.calls == 2
        assert agent.last_messages
        assert not any(isinstance(m, SystemMessage) for m in agent.last_messages)
        assert "SYSTEM INSTRUCTIONS:" in str(getattr(agent.last_messages[0], "content", ""))

    asyncio.run(_run())

