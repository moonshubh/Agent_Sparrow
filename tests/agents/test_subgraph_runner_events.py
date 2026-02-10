from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from app.agents.orchestration.orchestration.state import GraphState
from app.agents.orchestration.orchestration.subagent_state import PendingTaskCall
from app.agents.orchestration.subgraphs.research import build_research_subgraph


@pytest.mark.asyncio
async def test_subgraph_runner_emits_spawn_and_end_events(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.agents.orchestration.subgraphs import _base

    class _FakeSubagent:
        async def ainvoke(self, _state: dict[str, Any], config=None):  # noqa: ARG002
            return {"messages": [AIMessage(content="research complete")]}

    monkeypatch.setattr(
        _base,
        "get_subagent_by_name",
        lambda _name: {
            "model": "fake-model",
            "tools": [],
            "system_prompt": "",
            "middleware": [],
        },
    )
    monkeypatch.setattr(_base, "create_agent", lambda **_kwargs: _FakeSubagent())

    runner = build_research_subgraph()
    events: list[dict[str, Any]] = []

    state = GraphState(session_id="sess-subgraph")
    call = PendingTaskCall(
        tool_call_id="call_sub_1",
        subagent_type="research-agent",
        description="Investigate mail sync behaviors",
        args={"description": "Investigate mail sync behaviors"},
    )

    result = await runner(state, call, events.append, config={})

    assert isinstance(result, ToolMessage)
    assert result.tool_call_id == "call_sub_1"
    assert "research complete" in result.content

    names = [event.get("name") for event in events]
    assert "subagent_spawn" in names
    assert "subagent_end" in names
    assert "subagent_thinking_delta" in names
