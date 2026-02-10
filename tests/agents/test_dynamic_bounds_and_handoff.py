from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.agents.harness.middleware.handoff_capture_middleware import (
    HandoffCaptureMiddleware,
)
from app.agents.orchestration.orchestration.state import bounded_add_messages
from app.core.settings import settings


class _FakeWorkspaceStore:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.handoff_context = None
        self.progress_notes = None

    async def set_handoff_context(self, context):
        self.handoff_context = context

    async def set_progress_notes(self, notes: str):
        self.progress_notes = notes


def test_bounded_add_messages_uses_global_bound(monkeypatch) -> None:
    monkeypatch.setattr(settings, "graph_message_bound", 2)

    reducer = bounded_add_messages(30)
    result = reducer(
        [
            SystemMessage(content="memory", name="server_memory_context"),
            HumanMessage(content="m1"),
            AIMessage(content="m2"),
            HumanMessage(content="m3"),
        ],
        [AIMessage(content="m4")],
    )

    assert isinstance(result[0], SystemMessage)
    assert result[0].name == "server_memory_context"
    visible = [msg.content for msg in result[1:]]
    assert visible == ["m3", "m4"]


@pytest.mark.asyncio
async def test_handoff_enriched_payload_adds_expected_fields() -> None:
    store = _FakeWorkspaceStore(session_id="sess-handoff")
    middleware = HandoffCaptureMiddleware(workspace_store=store)

    messages = [
        HumanMessage(content="Please investigate sync issue"),
        AIMessage(
            content="I'll delegate this task.",
            tool_calls=[
                {
                    "id": "task_1",
                    "name": "task",
                    "args": {
                        "description": "Research auth errors",
                        "subagent_type": "research-agent",
                    },
                }
            ],
        ),
        ToolMessage(content="Found references", tool_call_id="task_1", name="task"),
    ]

    scratchpad = {
        "_system": {
            "memory_stats": {
                "retrieved_memory_ids": [
                    "aaaaaaa1-0000-4000-8000-000000000001",
                    "aaaaaaa2-0000-4000-8000-000000000002",
                ]
            }
        }
    }

    await middleware._capture_handoff(messages, scratchpad)

    assert store.handoff_context is not None
    assert "tool_usage_summary" in store.handoff_context
    assert "subagent_deployments" in store.handoff_context
    assert "memory_ids" in store.handoff_context
    assert "evidence_trail" in store.handoff_context

    summary = store.handoff_context["tool_usage_summary"]
    assert "task" in summary["requested"]
    assert summary["requested_count"] >= 1
    assert store.handoff_context["subagent_deployments"] == ["research-agent"]
