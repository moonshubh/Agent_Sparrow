from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agents.streaming.handler import StreamEventHandler


class _AgentStub:
    def __init__(self) -> None:
        self.calls = 0

    async def ainvoke(self, *_args, **_kwargs):
        self.calls += 1
        return {"output": "should not be called"}


@pytest.mark.asyncio
async def test_recover_missing_final_output_skips_when_artifacts_present() -> None:
    agent = _AgentStub()
    handler = StreamEventHandler(
        agent=agent,  # type: ignore[arg-type]
        emitter=SimpleNamespace(),  # type: ignore[arg-type]
        config={"configurable": {}},
        state=SimpleNamespace(attachments=[], scratchpad={}),
        messages=[],
    )

    handler._artifact_events_emitted = 1
    await handler._recover_missing_final_output()

    assert agent.calls == 0
