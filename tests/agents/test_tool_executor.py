from __future__ import annotations

import pytest
from langchain_core.tools import tool

from app.agents.tools.tool_executor import ToolExecutor
from app.core.settings import settings


@tool
def _echo_tool(message: str = "ok") -> dict[str, str]:
    """Return the provided message."""
    return {"message": message}


@pytest.mark.asyncio
async def test_tool_executor_succeeds_with_timeouts_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "agent_disable_timeouts", True)
    executor = ToolExecutor()

    result = await executor.execute(
        tool=_echo_tool,
        tool_call_id="call_tool_executor_1",
        args={"message": "hello"},
        config=None,
    )

    assert result.success is True
    assert result.error is None
    assert result.result == {"message": "hello"}
