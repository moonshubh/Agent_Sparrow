from types import SimpleNamespace
from typing import Any, Dict

from langchain_core.messages import ToolMessage

from app.agents.harness.middleware.workspace_write_sandbox_middleware import (
    WorkspaceWriteSandboxMiddleware,
)


class _FakeRequest:
    def __init__(self, *, tool_call: Dict[str, Any] | None = None, state: Any = None):
        self.tool_call = tool_call
        self.state = state

    def override(self, **kwargs):
        return _FakeRequest(
            tool_call=kwargs.get("tool_call", self.tool_call),
            state=kwargs.get("state", getattr(self, "state", None)),
        )


def test_workspace_write_sandbox_allows_run_dir_writes() -> None:
    async def _run() -> None:
        middleware = WorkspaceWriteSandboxMiddleware()
        run_dir = "/scratch/subagents/research/call_123"
        state = SimpleNamespace(subagent_context={"run_dir": run_dir})

        request = _FakeRequest(
            tool_call={
                "id": "tool_1",
                "name": "write_workspace_file",
                "args": {"path": f"{run_dir}/notes.md", "content": "ok"},
            },
            state=state,
        )

        called = {"value": False}

        async def handler(_req: _FakeRequest) -> str:
            called["value"] = True
            return "ok"

        result = await middleware.awrap_tool_call(request, handler)  # type: ignore[arg-type]
        assert result == "ok"
        assert called["value"] is True

    import asyncio

    asyncio.run(_run())


def test_workspace_write_sandbox_blocks_outside_run_dir() -> None:
    async def _run() -> None:
        middleware = WorkspaceWriteSandboxMiddleware()
        run_dir = "/scratch/subagents/research/call_123"
        state = SimpleNamespace(subagent_context={"run_dir": run_dir})

        request = _FakeRequest(
            tool_call={
                "id": "tool_2",
                "name": "write_workspace_file",
                "args": {"path": "/scratch/notes.md", "content": "nope"},
            },
            state=state,
        )

        async def handler(_req: _FakeRequest) -> str:
            return "should-not-run"

        result = await middleware.awrap_tool_call(request, handler)  # type: ignore[arg-type]
        assert isinstance(result, ToolMessage)
        assert "blocked" in result.content.lower()

    import asyncio

    asyncio.run(_run())


def test_workspace_write_sandbox_blocks_path_traversal() -> None:
    async def _run() -> None:
        middleware = WorkspaceWriteSandboxMiddleware()
        run_dir = "/scratch/subagents/research/call_123"
        state = SimpleNamespace(subagent_context={"run_dir": run_dir})

        request = _FakeRequest(
            tool_call={
                "id": "tool_3",
                "name": "write_workspace_file",
                "args": {
                    "path": f"{run_dir}/../call_123/../../notes.md",
                    "content": "nope",
                },
            },
            state=state,
        )

        async def handler(_req: _FakeRequest) -> str:
            return "should-not-run"

        result = await middleware.awrap_tool_call(request, handler)  # type: ignore[arg-type]
        assert isinstance(result, ToolMessage)
        assert "blocked" in result.content.lower()

    import asyncio

    asyncio.run(_run())
