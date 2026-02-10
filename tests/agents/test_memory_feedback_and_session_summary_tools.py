from __future__ import annotations

from types import SimpleNamespace
import uuid

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.agents.unified.tools import (
    MemoryFeedbackInput,
    SessionSummaryInput,
    memory_feedback_tool,
    session_summary_tool,
)
from app.core.settings import settings


@pytest.mark.asyncio
async def test_memory_feedback_tool_rejects_subagent_context() -> None:
    state = SimpleNamespace(
        subagent_context={"type": "research-agent", "tool_call_id": "call_1"},
        scratchpad={},
    )

    result = await memory_feedback_tool.coroutine(
        input=MemoryFeedbackInput(
            memory_id=str(uuid.uuid4()),
            feedback_type="positive",
        ),
        state=state,
        runtime=None,
    )

    assert result["success"] is False
    assert result["reason"] == "coordinator_only"


@pytest.mark.asyncio
async def test_memory_feedback_tool_uses_uuid_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    memory_id = uuid.uuid4()
    fallback_user_id = "11111111-1111-4111-8111-111111111111"
    monkeypatch.setattr(settings, "development_user_id", fallback_user_id)

    calls: dict[str, object] = {}

    class _FakeMemoryUIService:
        async def submit_feedback(
            self,
            memory_id,
            user_id,
            feedback_type,
            session_id=None,
            ticket_id=None,
            notes=None,
        ):
            calls["memory_id"] = memory_id
            calls["user_id"] = user_id
            calls["feedback_type"] = feedback_type
            calls["session_id"] = session_id
            calls["ticket_id"] = ticket_id
            calls["notes"] = notes
            return {"new_confidence": 0.91}

    from app.memory import memory_ui_service

    monkeypatch.setattr(
        memory_ui_service,
        "get_memory_ui_service",
        lambda: _FakeMemoryUIService(),
    )

    state = SimpleNamespace(
        user_id="not-a-uuid",
        session_id="sess-123",
        scratchpad={
            "_system": {
                "memory_stats": {
                    "retrieved_memory_ids": [str(memory_id)],
                }
            }
        },
    )

    result = await memory_feedback_tool.coroutine(
        input=MemoryFeedbackInput(
            feedback_type="positive",
            notes="Confirmed helpful",
        ),
        state=state,
        runtime=None,
    )

    assert result["success"] is True
    assert result["memory_id"] == str(memory_id)
    assert result["user_id"] == fallback_user_id
    assert calls["memory_id"] == memory_id
    assert str(calls["user_id"]) == fallback_user_id
    assert calls["feedback_type"] == "positive"


def test_session_summary_tool_returns_structured_read_only_summary() -> None:
    state = SimpleNamespace(
        session_id="sess-summary",
        trace_id="trace-summary",
        user_id="00000000-0000-0000-0000-000000000001",
        thread_state={"one_line_status": "Working", "active_todos": ["search KB"]},
        messages=[
            HumanMessage(content="Please investigate sync issues"),
            AIMessage(content="I will analyze logs and KB entries."),
        ],
        scratchpad={
            "todos": [{"id": "t1", "content": "Search KB", "status": "in_progress"}],
            "_system": {
                "memory_stats": {
                    "retrieved_memory_ids": ["aaaaaaa1-0000-4000-8000-000000000001"],
                    "memory_ui_retrieved": 2,
                    "mem0_retrieved": 1,
                },
                "subagent_reports": {
                    "call_1": {"read": False},
                    "call_2": {"read": True},
                },
            },
        },
    )

    before = dict(state.scratchpad)
    result = session_summary_tool.func(  # type: ignore[attr-defined]
        input=SessionSummaryInput(include_recent_messages=True, recent_message_limit=2),
        state=state,
        runtime=None,
    )

    assert result["session_id"] == "sess-summary"
    assert result["message_count"] == 2
    assert result["last_user_message"] == "Please investigate sync issues"
    assert result["unread_subagent_reports"] == ["call_1"]
    assert result["memory"]["memory_ui_retrieved"] == 2
    assert result["memory"]["mem0_retrieved"] == 1
    assert len(result["recent_messages"]) == 2
    assert state.scratchpad == before
