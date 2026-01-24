import asyncio
from types import SimpleNamespace
from typing import Any, Dict

from langchain_core.messages import AIMessage, ToolMessage
from langgraph.types import Command
try:  # pragma: no cover - version compatibility
    from langgraph.prebuilt import ToolRuntime
except Exception:  # pragma: no cover
    try:
        from langgraph.prebuilt.tool_node import ToolRuntime
    except Exception:  # pragma: no cover
        class ToolRuntime:  # type: ignore[override]
            def __init__(
                self,
                *,
                state: Any,
                tool_call_id: str | None = None,
                config: dict | None = None,
                context: dict | None = None,
                store: Any = None,
                stream_writer: Any = None,
            ) -> None:
                self.state = state
                self.tool_call_id = tool_call_id
                self.config = config or {}
                self.context = context or {}
                self.store = store
                self.stream_writer = stream_writer

from app.agents.harness.store.workspace_store import SparrowWorkspaceStore, _IMPORT_FAILED
from app.agents.unified.subagent_workspace_bridge_middleware import (
    SubagentWorkspaceBridgeMiddleware,
)


class _FakeRequest:
    def __init__(self, *, tool_call: Dict[str, Any] | None = None, state: Any = None, runtime: Any = None):
        self.tool_call = tool_call
        self.state = state
        self.runtime = runtime

    def override(self, **kwargs):
        return _FakeRequest(
            tool_call=kwargs.get("tool_call", self.tool_call),
            state=kwargs.get("state", getattr(self, "state", None)),
            runtime=kwargs.get("runtime", getattr(self, "runtime", None)),
        )


def test_awrap_tool_call_persists_report_and_replaces_tool_message() -> None:
    async def _run() -> None:
        store = SparrowWorkspaceStore(
            session_id="sess-bridge",
            user_id="user-1",
            supabase_client=_IMPORT_FAILED,  # cache-only
        )
        middleware = SubagentWorkspaceBridgeMiddleware(workspace_store=store, report_read_limit_chars=5000, capsule_max_chars=4000)

        tool_call_id = "call_123"
        subagent_type = "research"
        events: list[dict[str, Any]] = []

        def _stream_writer(event: dict[str, Any]) -> None:
            events.append(event)

        state = SimpleNamespace(
            session_id="sess-bridge",
            trace_id="trace-bridge",
            user_id="user-1",
            provider="google",
            model="gemini",
            agent_type="primary",
            forwarded_props={"customer_id": "cust-1"},
            thread_state={"foo": "bar"},
            scratchpad={"_system": {"existing": True}},
        )

        runtime = ToolRuntime(
            state=state,
            tool_call_id=tool_call_id,
            config={},
            context={},
            store=None,
            stream_writer=_stream_writer,
        )

        request = _FakeRequest(
            tool_call={
                "name": "task",
                "id": tool_call_id,
                "args": {"description": "Do the thing", "subagent_type": subagent_type},
            },
            state=state,
            runtime=runtime,
        )

        full_report = ("A" * 1500) + "TAIL_MARKER"

        async def handler(req: _FakeRequest) -> Command:
            desc = req.tool_call["args"]["description"]
            assert "<context_capsule>" in desc
            assert "<workspace_instructions>" in desc
            assert f"/scratch/subagents/{subagent_type}/{tool_call_id}" in desc
            # Subagent runtime should be allowlisted (no attachments).
            assert isinstance(req.runtime.state, dict)
            assert "attachments" not in req.runtime.state
            assert req.runtime.state.get("subagent_context", {}).get("run_dir")
            return Command(update={"messages": [ToolMessage(content=full_report, tool_call_id=tool_call_id)]})

        result = await middleware.awrap_tool_call(request, handler)  # type: ignore[arg-type]

        assert isinstance(result, Command)
        report_path = f"/scratch/subagents/{subagent_type}/{tool_call_id}/report.md"
        persisted = await store.read_file(report_path)
        assert persisted == full_report

        messages = list((result.update or {}).get("messages") or [])
        assert len(messages) == 1
        assert isinstance(messages[0], ToolMessage)
        assert report_path in messages[0].content
        assert "Excerpt:" in messages[0].content
        assert "TAIL_MARKER" not in messages[0].content

        scratchpad = (result.update or {}).get("scratchpad") or {}
        assert scratchpad["_system"]["subagent_reports"][tool_call_id]["read"] is False
        assert scratchpad["_system"]["subagent_reports"][tool_call_id]["path"] == report_path

        spawn = next((e for e in events if e.get("name") == "subagent_spawn"), None)
        end = next((e for e in events if e.get("name") == "subagent_end"), None)
        assert spawn is not None
        assert end is not None
        assert spawn.get("data", {}).get("toolCallId") == tool_call_id
        assert spawn.get("data", {}).get("subagentType") == subagent_type
        assert end.get("data", {}).get("status") == "success"
        assert end.get("data", {}).get("reportPath") == report_path

    asyncio.run(_run())


def test_awrap_model_call_forces_ingest_of_unread_reports() -> None:
    async def _run() -> None:
        store = SparrowWorkspaceStore(
            session_id="sess-bridge",
            user_id="user-1",
            supabase_client=_IMPORT_FAILED,  # cache-only
        )
        middleware = SubagentWorkspaceBridgeMiddleware(workspace_store=store, report_read_limit_chars=1234, capsule_max_chars=4000)

        state = SimpleNamespace(
            scratchpad={
                "_system": {
                    "subagent_reports": {
                        "call_123": {
                            "path": "/scratch/subagents/research/call_123/report.md",
                            "read": False,
                        }
                    }
                }
            }
        )

        request = _FakeRequest(state=state)

        async def handler(_req: Any) -> Any:
            return "ok"

        response = await middleware.awrap_model_call(request, handler)  # type: ignore[arg-type]
        assert isinstance(response, AIMessage)
        tool_calls = list(response.tool_calls or [])
        assert any(tc.get("name") == "read_workspace_file" for tc in tool_calls)
        assert any(tc.get("name") == "mark_subagent_reports_read" for tc in tool_calls)

    asyncio.run(_run())
